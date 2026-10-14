import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "connected"


def test_dashboard_endpoint():
    response = client.get("/dashboard")
    assert response.status_code == 200


def test_required_assignment_routes_exist():
    paths = {route.path for route in app.routes}

    required_paths = {
        "/employees",
        "/attendance/punch-in",
        "/attendance/punch-out",
        "/attendance",
        "/attendance/{emp_code}/{date}",
        "/analytics/employees/{emp_code}/monthly",
        "/analytics/departments/summary",
        "/analytics/leaderboard/late",
        "/analytics/departments/{department}/trend",
        "/admin/explain/{endpoint}",
    }

    assert required_paths.issubset(paths)


def test_openapi_documentation_loads():
    response = client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    assert "paths" in schema

    for path in [
        "/employees",
        "/attendance/punch-in",
        "/attendance/punch-out",
        "/analytics/departments/summary",
    ]:
        assert path in schema["paths"]


def test_invalid_employee_code_is_rejected():
    response = client.post(
        "/employees",
        json={
            "emp_code": "INVALID",
            "name": "Test Employee",
            "email": "test.employee@example.com",
            "department": "Engineering",
            "shift_start": "09:30",
            "shift_end": "18:30",
            "joined_on": "2026-10-01",
        },
    )

    assert response.status_code == 422


def test_invalid_joined_on_date_is_rejected():
    response = client.post(
        "/employees",
        json={
            "emp_code": "EMP1234",
            "name": "Test Employee",
            "email": "test.employee@example.com",
            "department": "Engineering",
            "shift_start": "09:30",
            "shift_end": "18:30",
            "joined_on": "not-a-date",
        },
    )

    assert response.status_code == 422


def test_invalid_punch_in_status_is_rejected():
    response = client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "EMP1234",
            "punched_at": 1792000000000,
            "status": "INVALID_STATUS",
        },
    )

    assert response.status_code == 422
