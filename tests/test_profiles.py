"""工况档存取与多档并行求解隔离性测试。"""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.solver import solve_counterflow

PROFILE_A = {
    "name": "summer-design",
    "twb_c": 20.0,
    "t_inlet_c": 35.0,
    "water_air_ratio": 1.0,
    "fill_ntu": 1.5,
}
PROFILE_B = {
    "name": "monsoon-high-load",
    "twb_c": 26.0,
    "t_inlet_c": 40.0,
    "water_air_ratio": 1.4,
    "fill_ntu": 2.2,
}


@pytest.fixture()
def client():
    return TestClient(create_app())


def _put(client, profile):
    resp = client.post("/profiles", json=profile)
    assert resp.status_code == 201
    return resp


def test_profile_crud(client):
    _put(client, PROFILE_A)
    assert client.get("/profiles/summer-design").json()["fill_ntu"] == 1.5
    assert [p["name"] for p in client.get("/profiles").json()] == ["summer-design"]
    assert client.delete("/profiles/summer-design").status_code == 204
    assert client.get("/profiles/summer-design").status_code == 404


def test_profile_solve_matches_direct_solve(client):
    _put(client, PROFILE_A)
    via_profile = client.post("/profiles/summer-design/solve").json()
    direct = solve_counterflow(
        twb_c=PROFILE_A["twb_c"],
        t_inlet_c=PROFILE_A["t_inlet_c"],
        water_air_ratio=PROFILE_A["water_air_ratio"],
        fill_ntu=PROFILE_A["fill_ntu"],
    )
    assert via_profile["profile"] == "summer-design"
    assert via_profile["t_outlet_c"] == pytest.approx(direct.t_outlet_c, abs=1e-9)


def test_profile_validation_on_create(client):
    resp = client.post("/profiles", json={**PROFILE_A, "fill_ntu": 0.0})
    assert resp.status_code == 422
    assert "传质能力" in resp.json()["reason"]


def test_concurrent_profile_solves_are_isolated(client):
    """两套工况档同时求解，中间焓值与水温互不污染、结果可复现。"""
    _put(client, PROFILE_A)
    _put(client, PROFILE_B)
    ref_a = client.post("/profiles/summer-design/solve").json()
    ref_b = client.post("/profiles/monsoon-high-load/solve").json()
    assert ref_a["t_outlet_c"] != pytest.approx(ref_b["t_outlet_c"], abs=1e-3)

    def solve(name):
        return client.post(f"/profiles/{name}/solve").json()

    with ThreadPoolExecutor(max_workers=8) as pool:
        for _ in range(20):
            results = list(
                pool.map(solve, ["summer-design", "monsoon-high-load"] * 10)
            )
            for got in results:
                ref = ref_a if got["profile"] == "summer-design" else ref_b
                assert got["t_outlet_c"] == pytest.approx(ref["t_outlet_c"], abs=1e-12)
                assert got["h_air_exit_kj_per_kg"] == pytest.approx(
                    ref["h_air_exit_kj_per_kg"], abs=1e-9
                )

    # 并行求解后工况档本身未被改动
    assert client.get("/profiles/summer-design").json() == PROFILE_A
    assert client.get("/profiles/monsoon-high-load").json() == PROFILE_B
