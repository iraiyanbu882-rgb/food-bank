from datetime import date

from app.models import OptimizationDataset


def make_dataset(
    required_packets=5,
    donor_quantity=10,
    expiry_date=None,
    beneficiaries=None,
):
    beneficiary_rows = beneficiaries or [
        {
            "id": "site",
            "location": "Chennai",
            "latitude": 13.08,
            "longitude": 80.27,
            "number_of_beneficiaries": 5,
            "category": "CHILDREN",
            "required_food_packets": required_packets,
            "packet_type": "standard",
            "priority_multiplier": 1,
        }
    ]
    return OptimizationDataset.model_validate(
        {
            "donors": [
                {
                    "id": "donor",
                    "name": "Market",
                    "location": "Chennai",
                    "latitude": 13.08,
                    "longitude": 80.27,
                    "available_food_items": [
                        {
                            "food_item": "Rice",
                            "quantity_kg": donor_quantity,
                            "expiry_date": expiry_date or date(2030, 1, 1),
                            "donation_frequency": "ONCE",
                        }
                    ],
                }
            ],
            "facilities": [
                {
                    "id": "bank",
                    "name": "Central Foodbank",
                    "facility_type": "TIER_II",
                    "location": "Chennai",
                    "latitude": 13.08,
                    "longitude": 80.27,
                    "initial_storage_capacity_kg": 100,
                    "initial_transport_capacity_kg": 100,
                    "existing_paid_employees": 1,
                    "donation_handling_capacity_kg_per_employee": 100,
                    "packet_preparation_capacity_per_employee": 100,
                    "storage_expansion_options": [],
                    "vehicle_options": [],
                    "max_additional_staff": 0,
                }
            ],
            "beneficiaries": beneficiary_rows,
            "packet_types": [
                {
                    "id": "standard",
                    "name": "Standard",
                    "composition_kg": {"Rice": 1},
                }
            ],
            "costs": {
                "food_procurement_cost_per_kg": 10,
                "transportation_cost_per_km_kg": 0,
                "facility_opening_cost": 0,
                "storage_expansion_cost_per_kg": 0,
                "vehicle_hiring_cost": 0,
                "staff_hiring_cost": 0,
                "uncollected_donation_penalty_per_kg": 1,
                "unused_food_penalty_per_kg": 2,
                "unmet_demand_penalty_per_packet": 100,
            },
            "planning_start_date": date(2026, 1, 1),
            "planning_days": 7,
        }
    )
