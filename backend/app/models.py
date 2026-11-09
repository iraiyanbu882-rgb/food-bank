from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(gt=0)]
NonNegative = Annotated[float, Field(ge=0)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Name = Annotated[str, Field(min_length=1, max_length=120)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FacilityTier(StrEnum):
    TIER_I = "TIER_I"
    TIER_II = "TIER_II"


class BeneficiaryCategory(StrEnum):
    CHILDREN = "CHILDREN"
    ADULTS = "ADULTS"
    VULNERABLE = "VULNERABLE"


class DonationFrequency(StrEnum):
    ONCE = "ONCE"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class DonatedFood(StrictModel):
    food_item: Name
    quantity_kg: Positive
    expiry_date: date | None = None
    donation_frequency: DonationFrequency = DonationFrequency.ONCE


class Donor(StrictModel):
    id: Name
    name: Name
    location: Name
    latitude: Latitude
    longitude: Longitude
    available_food_items: Annotated[list[DonatedFood], Field(min_length=1)]


class StorageExpansionOption(StrictModel):
    name: Name
    additional_capacity_kg: Positive


class VehicleOption(StrictModel):
    name: Name
    capacity_kg: Positive
    available_count: Annotated[int, Field(ge=1, le=1000)] = 1


class Facility(StrictModel):
    id: Name
    name: Name
    facility_type: FacilityTier
    location: Name
    latitude: Latitude
    longitude: Longitude
    initial_storage_capacity_kg: NonNegative
    initial_transport_capacity_kg: NonNegative
    existing_paid_employees: Annotated[int, Field(ge=0)] = 0
    existing_volunteers: Annotated[int, Field(ge=0)] = 0
    existing_vehicles: Annotated[int, Field(ge=0)] = 0
    donation_handling_capacity_kg_per_employee: Positive
    packet_preparation_capacity_per_employee: Positive
    storage_expansion_options: list[StorageExpansionOption] = Field(default_factory=list)
    vehicle_options: list[VehicleOption] = Field(default_factory=list)
    max_additional_staff: Annotated[int, Field(ge=0, le=10000)] = 1000


class Beneficiary(StrictModel):
    id: Name
    location: Name
    latitude: Latitude
    longitude: Longitude
    number_of_beneficiaries: Annotated[int, Field(ge=1)]
    category: BeneficiaryCategory
    required_food_packets: Annotated[int, Field(ge=0)]
    packet_type: Name
    priority_multiplier: Annotated[float, Field(gt=0, le=100)] = 1.0


class FoodPacketType(StrictModel):
    id: Name
    name: Name
    # Ingredient quantities are kg per packet; these are administrator-configured,
    # illustrative recipe values rather than nutritional recommendations.
    composition_kg: Annotated[dict[Name, Positive], Field(min_length=1)]


class OperationalCosts(StrictModel):
    food_procurement_cost_per_kg: NonNegative
    transportation_cost_per_km_kg: NonNegative
    facility_opening_cost: NonNegative
    storage_expansion_cost_per_kg: NonNegative
    vehicle_hiring_cost: NonNegative
    staff_hiring_cost: NonNegative
    uncollected_donation_penalty_per_kg: NonNegative
    unused_food_penalty_per_kg: NonNegative
    unmet_demand_penalty_per_packet: NonNegative


class OptimizationDataset(StrictModel):
    donors: Annotated[list[Donor], Field(min_length=1)]
    facilities: Annotated[list[Facility], Field(min_length=1)]
    beneficiaries: Annotated[list[Beneficiary], Field(min_length=1)]
    packet_types: Annotated[list[FoodPacketType], Field(min_length=1)]
    costs: OperationalCosts
    planning_start_date: date = Field(default_factory=date.today)
    planning_days: Annotated[int, Field(ge=1, le=365)] = 7

    @model_validator(mode="after")
    def validate_references_and_unique_ids(self) -> OptimizationDataset:
        for label, records in (
            ("donor", self.donors),
            ("facility", self.facilities),
            ("beneficiary", self.beneficiaries),
            ("packet type", self.packet_types),
        ):
            ids = [record.id for record in records]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label.title()} IDs must be unique.")

        packet_ids = {packet.id for packet in self.packet_types}
        missing_packets = sorted(
            {beneficiary.packet_type for beneficiary in self.beneficiaries} - packet_ids
        )
        if missing_packets:
            raise ValueError(
                "Every beneficiary must reference a configured packet type; missing: "
                + ", ".join(missing_packets)
            )

        for facility in self.facilities:
            option_names = [option.name for option in facility.storage_expansion_options]
            if len(option_names) != len(set(option_names)):
                raise ValueError(f"Storage expansion option names must be unique at {facility.name}.")
            vehicle_names = [option.name for option in facility.vehicle_options]
            if len(vehicle_names) != len(set(vehicle_names)):
                raise ValueError(f"Vehicle option names must be unique at {facility.name}.")
        return self


class BudgetScenario(StrictModel):
    name: Name
    budget_cap: NonNegative | None = None
    equity_oriented: bool = False


class OptimizeOptions(StrictModel):
    scenarios: Annotated[list[BudgetScenario], Field(min_length=1, max_length=10)]
    equity_weight: NonNegative = 0
    solver_time_limit_seconds: Annotated[int, Field(ge=1, le=300)] = 30


class OptimizeRequest(StrictModel):
    dataset: OptimizationDataset
    options: OptimizeOptions


class OptimizationResultSummary(StrictModel):
    result_id: str
    scenario_name: str
    solver_status: str
    created_at: str
    objective_value: float | None = None
