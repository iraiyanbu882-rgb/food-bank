from datetime import date

from .helpers import make_dataset
from app.models import (
    BudgetScenario,
    OptimizeOptions,
    StorageExpansionOption,
    VehicleOption,
)
from app.optimizer import solve_scenario


def test_scip_balances_donations_and_meets_demand():
    dataset = make_dataset()

    result = solve_scenario(
        dataset,
        BudgetScenario(name="Base"),
        OptimizeOptions(scenarios=[BudgetScenario(name="Base")]),
    )

    assert result["solver_status"] == "OPTIMAL"
    assert result["kpis"]["total_food_distributed_kg"] == 5
    assert result["kpis"]["total_food_collected_kg"] == 5
    assert result["kpis"]["total_uncollected_donations_kg"] == 5
    assert result["kpis"]["total_unmet_demand_packets"] == 0
    assert result["beneficiary_allocations"][0]["packets_allocated"] == 5
    assert result["food_item_balances"][0]["balance_residual_kg"] == 0
    assert result["constraint_results"]["max_food_item_balance_residual_kg"] == 0


def test_budget_cap_reports_mathematical_infeasibility():
    dataset = make_dataset(required_packets=0)
    options = OptimizeOptions(
        scenarios=[BudgetScenario(name="No funds", budget_cap=0)]
    )

    result = solve_scenario(dataset, options.scenarios[0], options)

    assert result["solver_status"] == "INFEASIBLE"
    assert result["objective_value"] is None
    assert "infeasible" in result["message"].lower()


def test_expired_donations_are_not_collected():
    dataset = make_dataset(expiry_date=date(2020, 1, 1))
    options = OptimizeOptions(scenarios=[BudgetScenario(name="Base")])

    result = solve_scenario(dataset, options.scenarios[0], options)

    assert result["solver_status"] == "OPTIMAL"
    assert result["kpis"]["total_food_collected_kg"] == 0
    assert result["kpis"]["food_expired_before_plan_kg"] == 10


def test_storage_vehicle_and_workforce_expansion_are_optimized():
    dataset = make_dataset()
    facility = dataset.facilities[0]
    facility.initial_storage_capacity_kg = 2
    facility.initial_transport_capacity_kg = 2
    facility.existing_paid_employees = 1
    facility.donation_handling_capacity_kg_per_employee = 1
    facility.packet_preparation_capacity_per_employee = 1
    facility.storage_expansion_options = [
        StorageExpansionOption(name="Additional storage", additional_capacity_kg=5)
    ]
    facility.vehicle_options = [
        VehicleOption(name="Extra truck", capacity_kg=5, available_count=1)
    ]
    facility.max_additional_staff = 5
    dataset.costs.storage_expansion_cost_per_kg = 1
    dataset.costs.vehicle_hiring_cost = 1
    dataset.costs.staff_hiring_cost = 1
    options = OptimizeOptions(scenarios=[BudgetScenario(name="Capacity expansion")])

    result = solve_scenario(dataset, options.scenarios[0], options)
    facility_result = result["facility_allocations"][0]

    assert result["solver_status"] == "OPTIMAL"
    assert result["kpis"]["total_food_distributed_kg"] == 5
    assert facility_result["storage_capacity_kg"] == 7
    assert facility_result["vehicles_hired"] == 1
    assert facility_result["staff_hired"] == 4
    assert facility_result["storage_utilization_pct"] <= 100
    assert facility_result["transportation_utilization_pct"] <= 100


def test_equity_scenario_reduces_unmet_rate_gap():
    dataset = make_dataset(
        required_packets=2,
        donor_quantity=2,
        beneficiaries=[
            {
                "id": "children",
                "location": "North",
                "latitude": 13.1,
                "longitude": 80.2,
                "number_of_beneficiaries": 2,
                "category": "CHILDREN",
                "required_food_packets": 2,
                "packet_type": "standard",
                "priority_multiplier": 2,
            },
            {
                "id": "adults",
                "location": "South",
                "latitude": 13.0,
                "longitude": 80.3,
                "number_of_beneficiaries": 2,
                "category": "ADULTS",
                "required_food_packets": 2,
                "packet_type": "standard",
                "priority_multiplier": 1,
            },
        ],
    )
    dataset.costs.food_procurement_cost_per_kg = 1000
    options = OptimizeOptions(
        scenarios=[
            BudgetScenario(name="Cost only"),
            BudgetScenario(name="Equity", equity_oriented=True),
        ],
        equity_weight=1000,
    )

    cost_result = solve_scenario(dataset, options.scenarios[0], options)
    equity_result = solve_scenario(dataset, options.scenarios[1], options)

    assert cost_result["solver_status"] == "OPTIMAL"
    assert equity_result["solver_status"] == "OPTIMAL"
    assert (
        equity_result["objective_value"]
        == equity_result["cost_breakdown"]["total_operational_cost"]
        + equity_result["cost_breakdown"]["equity_objective_penalty"]
    )
    assert (
        equity_result["equity_analysis"]["unmet_rate_disparity_pct"]
        < cost_result["equity_analysis"]["unmet_rate_disparity_pct"]
    )
