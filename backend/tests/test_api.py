from fastapi.testclient import TestClient

from app.main import app
from .helpers import make_dataset


def test_dataset_and_result_endpoints_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("RESQNET_DB_PATH", str(tmp_path / "test.sqlite3"))
    dataset = make_dataset().model_dump(mode="json")
    request = {
        "dataset": dataset,
        "options": {
            "scenarios": [{"name": "Uncapped"}],
            "equity_weight": 0,
            "solver_time_limit_seconds": 10,
        },
    }

    with TestClient(app) as client:
        saved = client.put("/api/v1/dataset", json=dataset)
        assert saved.status_code == 200
        assert saved.json()["counts"]["donors"] == 1
        preflight = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"

        response = client.post("/api/v1/optimize", json=request)
        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["solver_status"] == "OPTIMAL"

        details = client.get(
            f"/api/v1/allocation-details/{result['result_id']}"
        )
        assert details.status_code == 200
        assert details.json()["beneficiary_allocations"][0]["packets_allocated"] == 5

        history = client.get("/api/v1/optimization-results")
        assert history.status_code == 200
        assert history.json()[0]["result_id"] == result["result_id"]


def test_dataset_schema_rejects_negative_quantity():
    dataset = make_dataset().model_dump(mode="json")
    dataset["donors"][0]["available_food_items"][0]["quantity_kg"] = -2

    with TestClient(app) as client:
        response = client.put("/api/v1/dataset", json=dataset)

    assert response.status_code == 422
