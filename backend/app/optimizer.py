from __future__ import annotations

from datetime import date
from math import ceil, cos, radians, sin, sqrt
from typing import Any

from ortools.linear_solver import pywraplp

from .models import (
    Beneficiary,
    BudgetScenario,
    Donor,
    Facility,
    FacilityTier,
    OptimizationDataset,
    OperationalCosts,
    OptimizeOptions,
)


class SolverUnavailableError(RuntimeError):
    pass


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0088
    lat_delta = radians(lat2 - lat1)
    lon_delta = radians(lon2 - lon1)
    haversine = (
        sin(lat_delta / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_delta / 2) ** 2
    )
    return 2 * earth_radius_km * atan_sqrt(haversine)


def atan_sqrt(value: float) -> float:
    # atan2 provides stable behaviour for coincident and antipodal points.
    from math import atan2

    return atan2(sqrt(max(0.0, value)), sqrt(max(0.0, 1.0 - value)))


def _value(variable: pywraplp.Variable) -> float:
    return max(0.0, variable.solution_value())


def _frequency_occurrences(frequency: str, days: int) -> int:
    if frequency == "DAILY":
        return days
    if frequency == "WEEKLY":
        return max(1, ceil(days / 7))
    if frequency == "MONTHLY":
        return max(1, ceil(days / 30))
    return 1


def _cost_terms(
    costs: OperationalCosts,
    open_facilities: dict[str, pywraplp.Variable],
    expansions: dict[tuple[str, int], pywraplp.Variable],
    vehicle_hires: dict[tuple[str, int], pywraplp.Variable],
    staff_hires: dict[str, pywraplp.Variable],
    purchases: dict[tuple[str, str], pywraplp.Variable],
    collections: dict[tuple[str, int, str], pywraplp.Variable],
    transfers: dict[tuple[str, str, str], pywraplp.Variable],
    allocations: dict[tuple[str, str], pywraplp.Variable],
    uncollected: dict[tuple[str, int], pywraplp.Variable],
    unused: dict[tuple[str, str], pywraplp.Variable],
    unmet: dict[str, pywraplp.Variable],
    equity_gap: pywraplp.Variable,
    donor_map: dict[str, Donor],
    packet_map: dict[str, Any],
    facility_map: dict[str, Facility],
    beneficiary_map: dict[str, Beneficiary],
    scenario: BudgetScenario,
    equity_weight: float,
) -> dict[str, list[tuple[pywraplp.Variable, float]]]:
    terms: dict[str, list[tuple[pywraplp.Variable, float]]] = {
        "facility_opening": [(var, costs.facility_opening_cost) for var in open_facilities.values()],
        "storage_expansion": [],
        "vehicle_hiring": [],
        "staff_hiring": [(var, costs.staff_hiring_cost) for var in staff_hires.values()],
        "food_procurement": [(var, costs.food_procurement_cost_per_kg) for var in purchases.values()],
        "transportation": [],
        "uncollected_donation": [
            (var, costs.uncollected_donation_penalty_per_kg) for var in uncollected.values()
        ],
        "unused_food": [],
        "unmet_demand": [
            (var, costs.unmet_demand_penalty_per_packet * beneficiary_map[key].priority_multiplier)
            for key, var in unmet.items()
        ],
        "equity": [(equity_gap, equity_weight if scenario.equity_oriented else 0.0)],
    }

    for (facility_id, option_index), variable in expansions.items():
        option = facility_map[facility_id].storage_expansion_options[option_index]
        terms["storage_expansion"].append(
            (variable, option.additional_capacity_kg * costs.storage_expansion_cost_per_kg)
        )

    for (facility_id, option_index), variable in vehicle_hires.items():
        del facility_id, option_index
        terms["vehicle_hiring"].append((variable, costs.vehicle_hiring_cost))

    for (donor_id, _line_index, facility_id), variable in collections.items():
        donor = donor_map[donor_id]
        facility = facility_map[facility_id]
        terms["transportation"].append(
            (
                variable,
                _distance_km(
                    donor.latitude,
                    donor.longitude,
                    facility.latitude,
                    facility.longitude,
                )
                * costs.transportation_cost_per_km_kg,
            )
        )

    for (source_id, destination_id, _item), variable in transfers.items():
        source = facility_map[source_id]
        destination = facility_map[destination_id]
        terms["transportation"].append(
            (
                variable,
                _distance_km(
                    source.latitude,
                    source.longitude,
                    destination.latitude,
                    destination.longitude,
                )
                * costs.transportation_cost_per_km_kg,
            )
        )

    for (facility_id, beneficiary_id), variable in allocations.items():
        facility = facility_map[facility_id]
        beneficiary = beneficiary_map[beneficiary_id]
        packet = packet_map[beneficiary.packet_type]
        kg_per_packet = sum(packet.composition_kg.values())
        terms["transportation"].append(
            (
                variable,
                _distance_km(
                    facility.latitude,
                    facility.longitude,
                    beneficiary.latitude,
                    beneficiary.longitude,
                )
                * kg_per_packet
                * costs.transportation_cost_per_km_kg,
            )
        )

    for (facility_id, item), variable in unused.items():
        del facility_id, item
        terms["unused_food"].append((variable, costs.unused_food_penalty_per_kg))

    return terms


def solve_scenario(
    data: OptimizationDataset,
    scenario: BudgetScenario,
    options: OptimizeOptions,
) -> dict[str, Any]:
    solver = pywraplp.Solver.CreateSolver("SCIP")
    if solver is None:
        raise SolverUnavailableError(
            "Google OR-Tools could not create the SCIP solver. Install an OR-Tools "
            "wheel that includes SCIP support and verify Solver.CreateSolver('SCIP')."
        )
    solver.SetTimeLimit(options.solver_time_limit_seconds * 1000)

    donor_map = {donor.id: donor for donor in data.donors}
    facility_map = {facility.id: facility for facility in data.facilities}
    beneficiary_map = {beneficiary.id: beneficiary for beneficiary in data.beneficiaries}
    packet_map = {packet.id: packet for packet in data.packet_types}
    tier_two = [f for f in data.facilities if f.facility_type == FacilityTier.TIER_II]

    item_labels: dict[str, str] = {}
    for donor in data.donors:
        for line in donor.available_food_items:
            item_labels.setdefault(line.food_item.casefold(), line.food_item)
    for packet in data.packet_types:
        for ingredient in packet.composition_kg:
            item_labels.setdefault(ingredient.casefold(), ingredient)
    item_keys = sorted(item_labels)

    donation_lines: list[dict[str, Any]] = []
    for donor in data.donors:
        for line in donor.available_food_items:
            occurrences = _frequency_occurrences(
                line.donation_frequency.value, data.planning_days
            )
            donation_lines.append(
                {
                    "donor": donor,
                    "food_item": line.food_item,
                    "item_key": line.food_item.casefold(),
                    "quantity_kg": line.quantity_kg * occurrences,
                    "expiry_date": line.expiry_date,
                    "frequency": line.donation_frequency.value,
                }
            )

    total_packet_demand = sum(b.required_food_packets for b in data.beneficiaries)
    recipe_need = {
        item: sum(
            beneficiary.required_food_packets
            * sum(
                amount
                for ingredient, amount in packet_map[beneficiary.packet_type].composition_kg.items()
                if ingredient.casefold() == item
            )
            for beneficiary in data.beneficiaries
        )
        for item in item_keys
    }
    donor_supply = {
        item: sum(line["quantity_kg"] for line in donation_lines if line["item_key"] == item)
        for item in item_keys
    }
    purchase_limit = {
        item: max(0.0, recipe_need[item] - donor_supply[item])
        for item in item_keys
    }

    open_facilities = {
        facility.id: solver.BoolVar(f"open_{index}")
        for index, facility in enumerate(data.facilities)
    }
    expansions: dict[tuple[str, int], pywraplp.Variable] = {}
    vehicle_hires: dict[tuple[str, int], pywraplp.Variable] = {}
    staff_hires: dict[str, pywraplp.Variable] = {}
    for facility_index, facility in enumerate(data.facilities):
        for option_index, _option in enumerate(facility.storage_expansion_options):
            expansions[(facility.id, option_index)] = solver.BoolVar(
                f"expand_{facility_index}_{option_index}"
            )
        for option_index, option in enumerate(facility.vehicle_options):
            vehicle_hires[(facility.id, option_index)] = solver.IntVar(
                0, option.available_count, f"vehicles_{facility_index}_{option_index}"
            )
        staff_hires[facility.id] = solver.IntVar(
            0, facility.max_additional_staff, f"staff_{facility_index}"
        )

    collections: dict[tuple[str, int, str], pywraplp.Variable] = {}
    uncollected: dict[tuple[str, int], pywraplp.Variable] = {}
    for line_index, line in enumerate(donation_lines):
        donor = line["donor"]
        expired_before_start = (
            line["expiry_date"] is not None
            and line["expiry_date"] < data.planning_start_date
        )
        line_collections = []
        for facility_index, facility in enumerate(data.facilities):
            variable = solver.NumVar(
                0,
                0 if expired_before_start else line["quantity_kg"],
                f"collect_{line_index}_{facility_index}",
            )
            collections[(donor.id, line_index, facility.id)] = variable
            line_collections.append(variable)
        uncollected[(donor.id, line_index)] = solver.NumVar(
            0, line["quantity_kg"], f"uncollected_{line_index}"
        )
        solver.Add(sum(line_collections) + uncollected[(donor.id, line_index)] == line["quantity_kg"])

    purchases: dict[tuple[str, str], pywraplp.Variable] = {}
    transfers: dict[tuple[str, str, str], pywraplp.Variable] = {}
    unused: dict[tuple[str, str], pywraplp.Variable] = {}
    for facility_index, facility in enumerate(data.facilities):
        for item_index, item in enumerate(item_keys):
            purchases[(facility.id, item)] = solver.NumVar(
                0, purchase_limit[item], f"purchase_{facility_index}_{item_index}"
            )
            unused[(facility.id, item)] = solver.NumVar(
                0, solver.infinity(), f"unused_{facility_index}_{item_index}"
            )
            if facility.facility_type == FacilityTier.TIER_I:
                for destination_index, destination in enumerate(tier_two):
                    transfers[(facility.id, destination.id, item)] = solver.NumVar(
                        0,
                        max(0.0, donor_supply[item] + purchase_limit[item]),
                        f"transfer_{facility_index}_{destination_index}_{item_index}",
                    )

    for item in item_keys:
        solver.Add(
            sum(purchases[(facility.id, item)] for facility in data.facilities)
            <= purchase_limit[item]
        )

    productions: dict[tuple[str, str], pywraplp.Variable] = {}
    for facility_index, facility in enumerate(data.facilities):
        for packet_index, packet in enumerate(data.packet_types):
            productions[(facility.id, packet.id)] = solver.IntVar(
                0,
                total_packet_demand,
                f"produce_{facility_index}_{packet_index}",
            )

    allocations: dict[tuple[str, str], pywraplp.Variable] = {}
    for facility_index, facility in enumerate(data.facilities):
        for beneficiary_index, beneficiary in enumerate(data.beneficiaries):
            allocations[(facility.id, beneficiary.id)] = solver.IntVar(
                0,
                beneficiary.required_food_packets,
                f"allocate_{facility_index}_{beneficiary_index}",
            )

    unmet = {
        beneficiary.id: solver.IntVar(
            0, beneficiary.required_food_packets, f"unmet_{index}"
        )
        for index, beneficiary in enumerate(data.beneficiaries)
    }
    for beneficiary in data.beneficiaries:
        solver.Add(
            sum(allocations[(facility.id, beneficiary.id)] for facility in data.facilities)
            + unmet[beneficiary.id]
            == beneficiary.required_food_packets
        )

    equity_gap = solver.NumVar(0, 1, "equity_unmet_rate_gap")
    for facility in data.facilities:
        for packet in data.packet_types:
            matching_allocations = [
                allocations[(facility.id, beneficiary.id)]
                for beneficiary in data.beneficiaries
                if beneficiary.packet_type == packet.id
            ]
            solver.Add(
                productions[(facility.id, packet.id)] == sum(matching_allocations)
            )

    for facility in data.facilities:
        for item in item_keys:
            ingredients_consumed = []
            for packet in data.packet_types:
                amount = sum(
                    value
                    for ingredient, value in packet.composition_kg.items()
                    if ingredient.casefold() == item
                )
                if amount:
                    ingredients_consumed.append(
                        productions[(facility.id, packet.id)] * amount
                    )

            donor_in = [
                variable
                for (donor_id, line_index, facility_id), variable in collections.items()
                if facility_id == facility.id
                and donation_lines[line_index]["item_key"] == item
            ]
            transfer_in = [
                variable
                for (source_id, destination_id, transfer_item), variable in transfers.items()
                if destination_id == facility.id and transfer_item == item
            ]
            transfer_out = [
                variable
                for (source_id, destination_id, transfer_item), variable in transfers.items()
                if source_id == facility.id and transfer_item == item
            ]
            purchased = purchases[(facility.id, item)]
            balance_in = sum(donor_in) + sum(transfer_in) + purchased
            balance_out = sum(ingredients_consumed) + sum(transfer_out) + unused[(facility.id, item)]
            solver.Add(balance_in == balance_out)
        expansion_vars = [
            variable
            for (facility_id, _), variable in expansions.items()
            if facility_id == facility.id
        ]
        solver.Add(sum(expansion_vars) <= open_facilities[facility.id])
        for option_index, _option in enumerate(facility.vehicle_options):
            solver.Add(vehicle_hires[(facility.id, option_index)] <=
                       facility.vehicle_options[option_index].available_count * open_facilities[facility.id])
        solver.Add(staff_hires[facility.id] <= facility.max_additional_staff * open_facilities[facility.id])

        incoming_storage = (
            sum(
                variable
                for (donor_id, line_index, facility_id), variable in collections.items()
                if facility_id == facility.id
            )
            + sum(
                variable
                for (source_id, destination_id, _), variable in transfers.items()
                if destination_id == facility.id
            )
            + sum(purchases[(facility.id, item)] for item in item_keys)
        )
        effective_storage = (
            facility.initial_storage_capacity_kg * open_facilities[facility.id]
            + sum(
                facility.storage_expansion_options[index].additional_capacity_kg * variable
                for (facility_id, index), variable in expansions.items()
                if facility_id == facility.id
            )
        )
        solver.Add(incoming_storage <= effective_storage)

        vehicle_capacity = sum(
            facility.vehicle_options[index].capacity_kg * variable
            for (facility_id, index), variable in vehicle_hires.items()
            if facility_id == facility.id
        )
        effective_transport = (
            facility.initial_transport_capacity_kg * open_facilities[facility.id]
            + vehicle_capacity
        )
        solver.Add(incoming_storage <= effective_transport)

        outgoing_transfers = sum(
            variable
            for (source_id, destination_id, _), variable in transfers.items()
            if source_id == facility.id
        )
        delivered_food = sum(
            allocations[(facility.id, beneficiary.id)]
            * sum(packet_map[beneficiary.packet_type].composition_kg.values())
            for beneficiary in data.beneficiaries
        )
        solver.Add(outgoing_transfers + delivered_food <= effective_transport)

        handling_load = (
            sum(
                variable
                for (donor_id, line_index, facility_id), variable in collections.items()
                if facility_id == facility.id
            )
            + sum(
                variable
                for (source_id, destination_id, _), variable in transfers.items()
                if destination_id == facility.id or source_id == facility.id
            )
        )
        available_workforce = (
            facility.existing_paid_employees
            + facility.existing_volunteers
            + staff_hires[facility.id]
        )
        solver.Add(
            handling_load
            <= available_workforce * facility.donation_handling_capacity_kg_per_employee
        )
        solver.Add(
            sum(
                productions[(facility.id, packet.id)]
                for packet in data.packet_types
            )
            <= available_workforce * facility.packet_preparation_capacity_per_employee
        )

    demand_by_category: dict[str, list[Beneficiary]] = {}
    for beneficiary in data.beneficiaries:
        demand_by_category.setdefault(beneficiary.category.value, []).append(beneficiary)
    for category_beneficiaries in demand_by_category.values():
        category_demand = sum(b.required_food_packets for b in category_beneficiaries)
        if category_demand <= 0:
            continue
        category_unmet = sum(unmet[b.id] for b in category_beneficiaries)
        for other_beneficiaries in demand_by_category.values():
            other_demand = sum(b.required_food_packets for b in other_beneficiaries)
            if other_demand <= 0:
                continue
            other_unmet = sum(unmet[b.id] for b in other_beneficiaries)
            solver.Add(
                equity_gap
                >= category_unmet / category_demand - other_unmet / other_demand
            )

    terms = _cost_terms(
        data.costs,
        open_facilities,
        expansions,
        vehicle_hires,
        staff_hires,
        purchases,
        collections,
        transfers,
        allocations,
        uncollected,
        unused,
        unmet,
        equity_gap,
        donor_map,
        packet_map,
        facility_map,
        beneficiary_map,
        scenario,
        options.equity_weight,
    )
    objective = solver.Objective()
    for entries in terms.values():
        for variable, coefficient in entries:
            if coefficient:
                objective.SetCoefficient(variable, coefficient)
    objective.SetMinimization()

    if scenario.budget_cap is not None:
        budget_terms = [
            entries
            for name, entries in terms.items()
            if name != "equity"
        ]
        solver.Add(
            sum(variable * coefficient for entries in budget_terms for variable, coefficient in entries)
            <= scenario.budget_cap
        )

    raw_status = solver.Solve()
    status_names = {
        pywraplp.Solver.OPTIMAL: "OPTIMAL",
        pywraplp.Solver.FEASIBLE: "FEASIBLE",
        pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
        pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
        pywraplp.Solver.ABNORMAL: "ABNORMAL",
        pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
    }
    solver_status = status_names.get(raw_status, "NOT_SOLVED")
    result: dict[str, Any] = {
        "scenario_name": scenario.name,
        "budget_cap": scenario.budget_cap,
        "equity_oriented": scenario.equity_oriented,
        "solver_name": "Google OR-Tools SCIP",
        "solver_status": solver_status,
        "message": "",
        "objective_value": None,
        "model_statistics": {
            "decision_variables": solver.NumVariables(),
            "constraints": solver.NumConstraints(),
            "integer_variables": sum(variable.integer() for variable in solver.variables()),
        },
        "constraint_results": {},
        "cost_breakdown": {},
        "kpis": {},
        "donor_allocations": [],
        "facility_allocations": [],
        "food_item_balances": [],
        "beneficiary_allocations": [],
        "allocation_details": [],
        "equity_analysis": [],
    }
    if solver_status not in {"OPTIMAL", "FEASIBLE"}:
        result["message"] = (
            "The optimization model is infeasible under the configured input and budget constraints."
            if solver_status == "INFEASIBLE"
            else f"The SCIP solver stopped without a feasible solution (status: {solver_status})."
        )
        return result

    component_costs = {
        name: sum(_value(variable) * coefficient for variable, coefficient in entries)
        for name, entries in terms.items()
        if name != "equity"
    }
    equity_objective_penalty = sum(
        _value(variable) * coefficient for variable, coefficient in terms["equity"]
    )
    operational_cost = sum(component_costs.values())
    objective_value = objective.Value()
    result["objective_value"] = objective_value
    result["cost_breakdown"] = {
        **component_costs,
        "equity_objective_penalty": equity_objective_penalty,
        "total_operational_cost": operational_cost,
        "mathematical_objective_value": objective_value,
    }

    donor_collected = 0.0
    donor_uncollected = 0.0
    expired_before_start_kg = 0.0
    max_donor_supply_residual_kg = 0.0
    for line_index, line in enumerate(donation_lines):
        donor = line["donor"]
        collected = sum(
            _value(variable)
            for (donor_id, index, _facility_id), variable in collections.items()
            if donor_id == donor.id and index == line_index
        )
        not_collected = _value(uncollected[(donor.id, line_index)])
        max_donor_supply_residual_kg = max(
            max_donor_supply_residual_kg,
            abs(collected + not_collected - line["quantity_kg"]),
        )
        donor_collected += collected
        donor_uncollected += not_collected
        expired = (
            line["expiry_date"] is not None
            and line["expiry_date"] < data.planning_start_date
        )
        if expired:
            expired_before_start_kg += not_collected
        assigned_facilities = [
            facility_map[facility_id].name
            for (donor_id, index, facility_id), variable in collections.items()
            if donor_id == donor.id and index == line_index and _value(variable) > 1e-7
        ]
        result["donor_allocations"].append(
            {
                "donor": donor.name,
                "food_item": line["food_item"],
                "quantity_donated_kg": line["quantity_kg"],
                "assigned_foodbank": ", ".join(assigned_facilities) or None,
                "quantity_collected_kg": collected,
                "quantity_uncollected_kg": not_collected,
                "expiry_date": line["expiry_date"].isoformat() if line["expiry_date"] else None,
                "donation_frequency": line["frequency"],
            }
        )

    food_item_balances = []
    max_food_item_balance_residual_kg = 0.0
    for facility in data.facilities:
        for item in item_keys:
            direct_donations = sum(
                _value(variable)
                for (donor_id, line_index, facility_id), variable in collections.items()
                if facility_id == facility.id
                and donation_lines[line_index]["item_key"] == item
            )
            transfers_received = sum(
                _value(variable)
                for (source_id, destination_id, transfer_item), variable in transfers.items()
                if destination_id == facility.id and transfer_item == item
            )
            transfers_sent = sum(
                _value(variable)
                for (source_id, destination_id, transfer_item), variable in transfers.items()
                if source_id == facility.id and transfer_item == item
            )
            purchased = _value(purchases[(facility.id, item)])
            food_used = sum(
                _value(productions[(facility.id, packet.id)])
                * sum(
                    amount
                    for ingredient, amount in packet.composition_kg.items()
                    if ingredient.casefold() == item
                )
                for packet in data.packet_types
            )
            unused_food = _value(unused[(facility.id, item)])
            available_food = direct_donations + transfers_received + purchased
            residual = available_food - food_used - transfers_sent - unused_food
            max_food_item_balance_residual_kg = max(
                max_food_item_balance_residual_kg, abs(residual)
            )
            food_item_balances.append(
                {
                    "facility": facility.name,
                    "food_item": item_labels[item],
                    "direct_donations_kg": direct_donations,
                    "transferred_in_kg": transfers_received,
                    "purchased_kg": purchased,
                    "available_kg": available_food,
                    "used_in_packets_kg": food_used,
                    "transferred_out_kg": transfers_sent,
                    "unused_kg": unused_food,
                    "balance_residual_kg": residual,
                }
            )
    result["food_item_balances"] = food_item_balances

    total_purchased = sum(_value(variable) for variable in purchases.values())
    total_unused = sum(_value(variable) for variable in unused.values())
    total_allocated_packets = sum(_value(variable) for variable in allocations.values())
    total_demand_packets = sum(b.required_food_packets for b in data.beneficiaries)
    total_unmet_packets = sum(_value(variable) for variable in unmet.values())
    distributed_kg = 0.0
    for beneficiary in data.beneficiaries:
        packet = packet_map[beneficiary.packet_type]
        packet_kg = sum(packet.composition_kg.values())
        for facility in data.facilities:
            packets = _value(allocations[(facility.id, beneficiary.id)])
            if packets <= 1e-7:
                continue
            food_kg = packets * packet_kg
            distributed_kg += food_kg
            delivery_distance = _distance_km(
                facility.latitude,
                facility.longitude,
                beneficiary.latitude,
                beneficiary.longitude,
            )
            delivery_transport_cost = (
                delivery_distance
                * food_kg
                * data.costs.transportation_cost_per_km_kg
            )
            result["allocation_details"].append(
                {
                    "facility": facility.name,
                    "beneficiary_location": beneficiary.location,
                    "beneficiary_category": beneficiary.category.value,
                    "packet_type": packet.name,
                    "packets": packets,
                    "food_kg": food_kg,
                    "distance_km": delivery_distance,
                    "transportation_cost": delivery_transport_cost,
                    "decision_rationale": (
                        f"The current SCIP solution assigns {packets:g} packets on a "
                        f"{delivery_distance:.2f} km route; modeled delivery transport cost "
                        f"is {delivery_transport_cost:.2f}. The assignment is subject to the "
                        "facility's food, transport, storage, and workforce constraints."
                    ),
                }
            )

    facility_rows = []
    total_staff_required = 0
    total_staff_hired = 0
    total_vehicles_required = 0
    used_facility_count = 0
    expiring_soon_kg = 0.0
    horizon_end = date.fromordinal(
        data.planning_start_date.toordinal() + data.planning_days - 1
    )
    for facility in data.facilities:
        received_donation = sum(
            _value(variable)
            for (donor_id, line_index, facility_id), variable in collections.items()
            if facility_id == facility.id
        )
        received_purchase = sum(
            _value(purchases[(facility.id, item)]) for item in item_keys
        )
        received_transfer = sum(
            _value(variable)
            for (source_id, destination_id, _item), variable in transfers.items()
            if destination_id == facility.id
        )
        transferred_out = sum(
            _value(variable)
            for (source_id, destination_id, _item), variable in transfers.items()
            if source_id == facility.id
        )
        distributed = sum(
            _value(allocations[(facility.id, beneficiary.id)])
            * sum(packet_map[beneficiary.packet_type].composition_kg.values())
            for beneficiary in data.beneficiaries
        )
        total_received = received_donation + received_purchase + received_transfer
        effective_storage = (
            facility.initial_storage_capacity_kg
            + sum(
                facility.storage_expansion_options[index].additional_capacity_kg
                * _value(variable)
                for (facility_id, index), variable in expansions.items()
                if facility_id == facility.id
            )
            if _value(open_facilities[facility.id]) > 0.5
            else 0.0
        )
        vehicle_capacity_added = sum(
            facility.vehicle_options[index].capacity_kg * _value(variable)
            for (facility_id, index), variable in vehicle_hires.items()
            if facility_id == facility.id
        )
        effective_transport = (
            facility.initial_transport_capacity_kg + vehicle_capacity_added
            if _value(open_facilities[facility.id]) > 0.5
            else 0.0
        )
        incoming_transport = received_donation + received_transfer + received_purchase
        outgoing_transport = transferred_out + distributed
        transport_utilization = (
            max(incoming_transport, outgoing_transport) / effective_transport * 100
            if effective_transport > 0
            else 0.0
        )
        handling_required = ceil(
            (received_donation + received_transfer + transferred_out)
            / facility.donation_handling_capacity_kg_per_employee
            - 1e-9
        )
        packets_prepared = sum(
            _value(productions[(facility.id, packet.id)])
            for packet in data.packet_types
        )
        preparation_required = ceil(
            packets_prepared / facility.packet_preparation_capacity_per_employee - 1e-9
        )
        required_staff = max(handling_required, preparation_required)
        available_staff = facility.existing_paid_employees + facility.existing_volunteers
        hired_staff_solution = round(_value(staff_hires[facility.id]))
        total_workforce = available_staff + hired_staff_solution
        minimum_hire_required = max(0, required_staff - available_staff)
        hired_staff = min(
            facility.max_additional_staff,
            max(minimum_hire_required, round(_value(staff_hires[facility.id]))),
        )
        hired_vehicles = sum(
            round(_value(variable))
            for (facility_id, _index), variable in vehicle_hires.items()
            if facility_id == facility.id
        )
        total_staff_required += required_staff
        total_staff_hired += hired_staff
        facility_is_used = (
            total_received > 1e-7 or distributed > 1e-7 or transferred_out > 1e-7
        )
        if facility_is_used:
            total_vehicles_required += facility.existing_vehicles + hired_vehicles
        if facility_is_used:
            used_facility_count += 1

        for (donor_id, line_index, facility_id), variable in collections.items():
            line = donation_lines[line_index]
            expiry = line["expiry_date"]
            if (
                facility_id == facility.id
                and expiry
                and data.planning_start_date <= expiry <= horizon_end
            ):
                expiring_soon_kg += _value(variable)

        facility_transport_cost = sum(
            _value(variable)
            * _distance_km(
                donor_map[donor_id].latitude,
                donor_map[donor_id].longitude,
                facility.latitude,
                facility.longitude,
            )
            * data.costs.transportation_cost_per_km_kg
            for (donor_id, _line_index, facility_id), variable in collections.items()
            if facility_id == facility.id
        )
        facility_transport_cost += sum(
            _value(variable)
            * _distance_km(
                facility.latitude,
                facility.longitude,
                facility_map[destination_id].latitude,
                facility_map[destination_id].longitude,
            )
            * data.costs.transportation_cost_per_km_kg
            for (source_id, destination_id, _item), variable in transfers.items()
            if source_id == facility.id
        )
        facility_transport_cost += sum(
            _value(allocations[(facility.id, beneficiary.id)])
            * sum(packet_map[beneficiary.packet_type].composition_kg.values())
            * _distance_km(
                facility.latitude,
                facility.longitude,
                beneficiary.latitude,
                beneficiary.longitude,
            )
            * data.costs.transportation_cost_per_km_kg
            for beneficiary in data.beneficiaries
        )
        facility_cost_contribution = (
            _value(open_facilities[facility.id]) * data.costs.facility_opening_cost
            + received_purchase * data.costs.food_procurement_cost_per_kg
            + facility_transport_cost
            + _value(staff_hires[facility.id]) * data.costs.staff_hiring_cost
            + hired_vehicles * data.costs.vehicle_hiring_cost
            + sum(
                _value(variable)
                * facility.storage_expansion_options[index].additional_capacity_kg
                * data.costs.storage_expansion_cost_per_kg
                for (facility_id, index), variable in expansions.items()
                if facility_id == facility.id
            )
            + sum(
                _value(unused[(facility.id, item)])
                * data.costs.unused_food_penalty_per_kg
                for item in item_keys
            )
        )
        facility_rows.append(
            {
                "facility": facility.name,
                "facility_type": facility.facility_type.value,
                "food_received_kg": total_received,
                "food_distributed_kg": distributed,
                "food_transferred_kg": transferred_out,
                "food_transfer_received_kg": received_transfer,
                "storage_capacity_kg": effective_storage,
                "storage_utilization_pct": (
                    total_received / effective_storage * 100 if effective_storage else 0.0
                ),
                "transportation_capacity_kg": effective_transport,
                "transportation_utilization_pct": transport_utilization,
                "staff_required": required_staff,
                "staff_hired": hired_staff,
                "donation_handling_load_kg": (
                    received_donation + received_transfer + transferred_out
                ),
                "donation_handling_capacity_kg": (
                    total_workforce
                    * facility.donation_handling_capacity_kg_per_employee
                ),
                "packets_prepared": packets_prepared,
                "packet_preparation_capacity": (
                    total_workforce
                    * facility.packet_preparation_capacity_per_employee
                ),
                "vehicles_required": (
                    facility.existing_vehicles + hired_vehicles
                    if facility_is_used
                    else 0
                ),
                "vehicles_hired": hired_vehicles,
                "facility_open": facility_is_used,
                "cost_contribution": facility_cost_contribution,
                "decision_rationale": (
                    f"Current SCIP solution uses this facility for {distributed:.2f} kg "
                    f"of deliveries and {transferred_out:.2f} kg of transfers; it receives "
                    f"{total_received:.2f} kg, uses {total_received / effective_storage * 100:.1f}% "
                    f"of storage and {transport_utilization:.1f}% of transport capacity, "
                    f"and contributes {facility_cost_contribution:.2f} to modeled cost."
                    if facility_is_used
                    else "No food flow is assigned to this facility in the current SCIP solution."
                ),
            }
        )
    result["facility_allocations"] = facility_rows

    beneficiary_rows = []
    equity_totals: dict[str, dict[str, float]] = {}
    max_demand_balance_residual_packets = 0.0
    for beneficiary in data.beneficiaries:
        allocated = sum(
            _value(allocations[(facility.id, beneficiary.id)])
            for facility in data.facilities
        )
        missed = _value(unmet[beneficiary.id])
        demand = beneficiary.required_food_packets
        max_demand_balance_residual_packets = max(
            max_demand_balance_residual_packets,
            abs(allocated + missed - demand),
        )
        equity = equity_totals.setdefault(
            beneficiary.category.value, {"demand_packets": 0.0, "unmet_packets": 0.0}
        )
        equity["demand_packets"] += demand
        equity["unmet_packets"] += missed
        beneficiary_rows.append(
            {
                "beneficiary_location": beneficiary.location,
                "beneficiary_category": beneficiary.category.value,
                "number_of_beneficiaries": beneficiary.number_of_beneficiaries,
                "total_demand_packets": demand,
                "packets_allocated": allocated,
                "unmet_demand_packets": missed,
                "demand_satisfaction_pct": (allocated / demand * 100) if demand else 100.0,
                "priority_multiplier": beneficiary.priority_multiplier,
            }
        )
    result["beneficiary_allocations"] = beneficiary_rows
    equity_rows = [
        {
            "beneficiary_category": category,
            "demand_packets": values["demand_packets"],
            "unmet_packets": values["unmet_packets"],
            "unmet_demand_rate_pct": (
                values["unmet_packets"] / values["demand_packets"] * 100
                if values["demand_packets"]
                else 0.0
            ),
        }
        for category, values in sorted(equity_totals.items())
    ]
    rates = [row["unmet_demand_rate_pct"] for row in equity_rows]
    result["equity_analysis"] = {
        "groups": equity_rows,
        "unmet_rate_disparity_pct": max(rates) - min(rates) if rates else 0.0,
        "equity_oriented_objective": scenario.equity_oriented,
    }

    total_available_donations = sum(line["quantity_kg"] for line in donation_lines)
    food_available_for_use = donor_collected + total_purchased
    satisfied_pct = (
        total_allocated_packets / total_demand_packets * 100
        if total_demand_packets
        else 100.0
    )
    result["kpis"] = {
        "total_operational_cost": operational_cost,
        "total_donations_available_kg": total_available_donations,
        "total_food_collected_kg": donor_collected,
        "total_food_distributed_kg": distributed_kg,
        "total_food_purchased_kg": total_purchased,
        "total_unused_food_kg": total_unused,
        "total_uncollected_donations_kg": donor_uncollected,
        "total_unmet_demand_packets": total_unmet_packets,
        "food_utilization_pct": (
            distributed_kg / food_available_for_use * 100
            if food_available_for_use
            else 0.0
        ),
        "demand_satisfaction_pct": satisfied_pct,
        "facilities_required": used_facility_count,
        "vehicles_required": total_vehicles_required,
        "staff_required": total_staff_required,
        "staff_hired": total_staff_hired,
        "food_approaching_expiry_kg": expiring_soon_kg,
        "food_expired_before_plan_kg": expired_before_start_kg,
    }
    result["constraint_results"] = {
        "max_donor_supply_balance_residual_kg": max_donor_supply_residual_kg,
        "max_food_item_balance_residual_kg": max_food_item_balance_residual_kg,
        "max_beneficiary_demand_balance_residual_packets": max_demand_balance_residual_packets,
        "max_storage_capacity_violation_kg": max(
            (
                max(0.0, row["food_received_kg"] - row["storage_capacity_kg"])
                for row in facility_rows
            ),
            default=0.0,
        ),
        "max_transport_capacity_violation_kg": max(
            (
                max(
                    0.0,
                    row["food_received_kg"] - row["transportation_capacity_kg"],
                    row["food_transferred_kg"]
                    + row["food_distributed_kg"]
                    - row["transportation_capacity_kg"],
                )
                for row in facility_rows
            ),
            default=0.0,
        ),
        "max_donation_handling_capacity_violation_kg": max(
            (
                max(
                    0.0,
                    row["donation_handling_load_kg"]
                    - row["donation_handling_capacity_kg"],
                )
                for row in facility_rows
            ),
            default=0.0,
        ),
        "max_packet_preparation_capacity_violation": max(
            (
                max(0.0, row["packets_prepared"] - row["packet_preparation_capacity"])
                for row in facility_rows
            ),
            default=0.0,
        ),
        "budget_cap": "satisfied" if scenario.budget_cap is not None else "not configured",
    }
    result["message"] = (
        "SCIP proved an optimal solution."
        if solver_status == "OPTIMAL"
        else "SCIP found a feasible solution before its time limit."
    )
    return result


def solve_scenarios(
    data: OptimizationDataset, options: OptimizeOptions
) -> list[dict[str, Any]]:
    return [
        solve_scenario(data, scenario, options)
        for scenario in options.scenarios
    ]
