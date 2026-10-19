"""API persistence uses the same engine as the reference tests."""

from decimal import Decimal

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "valuationlab.db").as_posix())
    monkeypatch.setenv("VALUATIONLAB_SECRET", "test-secret")
    from backend.app.main import create_app
    return TestClient(create_app())


def test_saved_model_recalculates_from_assumptions_and_keeps_history(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/api/v1/health").json()["status"] == "ok"
        assert client.get("/api/v1/companies").status_code == 401
        login = client.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-valuationlab"})
        assert login.status_code == 200
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        listed = client.get("/api/v1/companies", headers=headers).json()
        company = listed["items"][0]
        assert company["synthetic"] is True
        detail = client.get(f"/api/v1/models/{company['model_id']}", headers=headers).json()
        original_ev = detail["result"]["dcf"]["enterprise_value"]
        historical_revenue = next(
            year["income"]["revenue"] for year in detail["result"]["years"] if year["year"] == 2024
        )
        assumptions = detail["snapshot"]["assumptions"]
        assumptions["growth_rates"]["2025"] = "0.20"
        updated = client.put(
            f"/api/v1/assumptions/{company['model_id']}",
            headers=headers,
            json={"assumptions": assumptions, "note": "Raise 2025 growth"},
        )
        assert updated.status_code == 200
        new_id = updated.json()["model_id"]
        assert new_id != company["model_id"]
        calculated = client.post(f"/api/v1/models/{new_id}/calculate", headers=headers)
        assert calculated.status_code == 200
        body = calculated.json()
        assert body["result"]["dcf"]["enterprise_value"] != original_ev
        revenue_2024 = next(year["income"]["revenue"] for year in body["result"]["years"] if year["year"] == 2024)
        revenue_2025 = next(year["income"]["revenue"] for year in body["result"]["years"] if year["year"] == 2025)
        assert Decimal(revenue_2024) == Decimal(historical_revenue)
        assert Decimal(revenue_2025) == Decimal("120000")
        checks = client.get(f"/api/v1/models/{new_id}/checks", headers=headers).json()
        assert any(check["status"] == "pass" for check in checks["checks"])
        assert client.get(f"/api/v1/models/{new_id}/wacc", headers=headers).json()["wacc"]["wacc"]
        assert client.get(f"/api/v1/models/{new_id}/sensitivities", headers=headers).json()["sensitivities"]
        workbook = client.post(f"/api/v1/models/{new_id}/export/excel", headers=headers)
        assert workbook.status_code == 200
        assert workbook.content[:2] == b"PK"
        explained = client.post(
            f"/api/v1/models/{new_id}/analyse",
            headers=headers,
            json={"topic": "enterprise_value", "question": "set growth to 5%", "consent_to_send": False},
        ).json()
        assert body["result"]["dcf"]["enterprise_value"] in " ".join(explained["facts"])
        assert explained["assumption_changes_applied"] is False
        created = client.post(
            "/api/v1/companies",
            headers=headers,
            json={"name": "Empty Co", "currency": "USD", "synthetic": True, "synthetic_notice": "Synthetic test company."},
        )
        assert created.status_code == 201
        csv_file = (
            "period,line_item,value,currency,unit_scale\n"
            "2024,Revenue,,USD,units\n"
            "2024,Not a mapped line,9,USD,units\n"
        ).encode()
        imported = client.post(
            "/api/v1/financials/import",
            headers=headers,
            data={"company_id": created.json()["id"]},
            files={"file": ("history.csv", csv_file, "text/csv")},
        )
        assert imported.status_code == 200
        periods = client.get(f"/api/v1/financials/{created.json()['id']}", headers=headers).json()["periods"]
        revenue = next(line for line in periods[0]["lines"] if line["canonical_key"] == "revenue")
        assert revenue["amount"] is None
        assert all(line["canonical_key"] != "not_a_mapped_line" for line in periods[0]["lines"])
