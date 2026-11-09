from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import storage
from .models import (
    Beneficiary,
    Donor,
    Facility,
    FoodPacketType,
    OperationalCosts,
    OptimizationDataset,
    OptimizeRequest,
)
from .optimizer import SolverUnavailableError, solve_scenarios

router = APIRouter()


class DatasetUpdateResponse(BaseModel):
    status: str
    counts: dict[str, int]


def _save_dataset_parts(dataset: OptimizationDataset) -> None:
    payload = dataset.model_dump(mode="json")
    storage.save_datasets(
        {
            **{
                kind: payload[kind]
                for kind in ("donors", "facilities", "beneficiaries", "packet_types", "costs")
            },
            "planning": {
                "planning_start_date": payload["planning_start_date"],
                "planning_days": payload["planning_days"],
            },
        },
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "resqnet-optimizer"}


@router.get("/dataset")
def get_dataset() -> dict[str, Any]:
    saved = storage.load_all_datasets()
    return {
        "donors": saved.get("donors", []),
        "facilities": saved.get("facilities", []),
        "beneficiaries": saved.get("beneficiaries", []),
        "packet_types": saved.get("packet_types", []),
        "costs": saved.get("costs"),
        "planning": saved.get("planning", {}),
    }


@router.put("/dataset", response_model=DatasetUpdateResponse)
def replace_dataset(dataset: OptimizationDataset) -> DatasetUpdateResponse:
    _save_dataset_parts(dataset)
    return DatasetUpdateResponse(
        status="saved",
        counts={
            "donors": len(dataset.donors),
            "facilities": len(dataset.facilities),
            "beneficiaries": len(dataset.beneficiaries),
            "packet_types": len(dataset.packet_types),
        },
    )


@router.post("/donors")
def save_donors(donors: list[Donor]) -> dict[str, Any]:
    storage.save_dataset("donors", [item.model_dump(mode="json") for item in donors])
    return {"status": "saved", "count": len(donors)}


@router.post("/facilities")
def save_facilities(facilities: list[Facility]) -> dict[str, Any]:
    storage.save_dataset(
        "facilities", [item.model_dump(mode="json") for item in facilities]
    )
    return {"status": "saved", "count": len(facilities)}


@router.post("/beneficiaries")
def save_beneficiaries(beneficiaries: list[Beneficiary]) -> dict[str, Any]:
    storage.save_dataset(
        "beneficiaries", [item.model_dump(mode="json") for item in beneficiaries]
    )
    return {"status": "saved", "count": len(beneficiaries)}


@router.post("/packet-types")
def save_packet_types(packet_types: list[FoodPacketType]) -> dict[str, Any]:
    storage.save_dataset(
        "packet_types", [item.model_dump(mode="json") for item in packet_types]
    )
    return {"status": "saved", "count": len(packet_types)}


@router.post("/costs")
def save_costs(costs: OperationalCosts) -> dict[str, str]:
    storage.save_dataset("costs", costs.model_dump(mode="json"))
    return {"status": "saved"}


@router.post("/optimize")
def optimize(request: OptimizeRequest) -> dict[str, Any]:
    _save_dataset_parts(request.dataset)
    try:
        results = solve_scenarios(request.dataset, request.options)
    except SolverUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    created_at = datetime.now(timezone.utc).isoformat()
    for result in results:
        result.update(
            {
                "result_id": storage.new_result_id(),
                "created_at": created_at,
                "dataset_snapshot": request.dataset.model_dump(mode="json"),
            }
        )
        storage.save_result(result)
    return {"results": results, "created_at": created_at}


@router.get("/optimization-results")
def optimization_results(
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    return storage.list_results(limit)


@router.get("/allocation-details/{result_id}")
def allocation_details(result_id: str) -> dict[str, Any]:
    result = storage.get_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Optimization result not found.")
    return {
        "result_id": result_id,
        "donor_allocations": result["donor_allocations"],
        "facility_allocations": result["facility_allocations"],
        "food_item_balances": result["food_item_balances"],
        "beneficiary_allocations": result["beneficiary_allocations"],
        "allocation_details": result["allocation_details"],
    }


@router.get("/equity-analysis/{result_id}")
def equity_analysis(result_id: str) -> dict[str, Any]:
    result = storage.get_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Optimization result not found.")
    return {"result_id": result_id, "equity_analysis": result["equity_analysis"]}
