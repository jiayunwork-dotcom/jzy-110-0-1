"""HTTP 接口测试：正算、反算与非法输入的带原因错误响应。"""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


SOLVE_BODY = {
    "twb_c": 20.0,
    "t_inlet_c": 35.0,
    "water_air_ratio": 1.0,
    "fill_ntu": 1.5,
}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_solve_endpoint(client):
    resp = client.post("/merkel/solve", json=SOLVE_BODY)
    assert resp.status_code == 200
    body = resp.json()
    assert 20.0 < body["t_outlet_c"] < 35.0
    assert body["approach_c"] == pytest.approx(
        body["t_outlet_c"] - SOLVE_BODY["twb_c"], abs=1e-9
    )
    assert body["ntu"] == pytest.approx(SOLVE_BODY["fill_ntu"], rel=1e-6)
    assert body["h_air_exit_kj_per_kg"] > body["h_air_inlet_kj_per_kg"]


def test_ntu_endpoint_roundtrip(client):
    solved = client.post("/merkel/solve", json=SOLVE_BODY).json()
    resp = client.post(
        "/merkel/ntu",
        json={
            "twb_c": SOLVE_BODY["twb_c"],
            "t_inlet_c": SOLVE_BODY["t_inlet_c"],
            "t_outlet_c": solved["t_outlet_c"],
            "water_air_ratio": SOLVE_BODY["water_air_ratio"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ntu"] == pytest.approx(SOLVE_BODY["fill_ntu"], rel=1e-6)


def test_air_enthalpy_mode_distinguishable(client):
    updated = client.post("/merkel/solve", json=SOLVE_BODY).json()
    fixed = client.post(
        "/merkel/solve", json={**SOLVE_BODY, "air_enthalpy_mode": "fixed"}
    ).json()
    assert abs(fixed["t_outlet_c"] - updated["t_outlet_c"]) > 0.1


def test_wet_bulb_above_inlet_rejected(client):
    resp = client.post("/merkel/solve", json={**SOLVE_BODY, "twb_c": 35.0})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "invalid_input"
    assert "冷却驱动力" in body["reason"]


def test_nonpositive_water_air_ratio_rejected(client):
    resp = client.post("/merkel/solve", json={**SOLVE_BODY, "water_air_ratio": 0.0})
    assert resp.status_code == 422
    assert "水气比" in resp.json()["reason"]


def test_nonpositive_fill_capability_rejected(client):
    resp = client.post("/merkel/solve", json={**SOLVE_BODY, "fill_ntu": -0.5})
    assert resp.status_code == 422
    assert "传质能力" in resp.json()["reason"]


def test_infeasible_point_reported(client):
    """积分途中饱和焓不高于空气焓，作为不可行明确报出，不放出乱值。"""
    resp = client.post(
        "/merkel/ntu",
        json={
            "twb_c": 20.0,
            "t_inlet_c": 35.0,
            "t_outlet_c": 22.0,
            "water_air_ratio": 1.5,
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "infeasible_operating_point"
    assert "可行区" in body["reason"]


def test_ntu_endpoint_rejects_outlet_below_wet_bulb(client):
    resp = client.post(
        "/merkel/ntu",
        json={
            "twb_c": 20.0,
            "t_inlet_c": 35.0,
            "t_outlet_c": 19.0,
            "water_air_ratio": 1.0,
        },
    )
    assert resp.status_code == 422
    assert "湿球" in resp.json()["reason"]
