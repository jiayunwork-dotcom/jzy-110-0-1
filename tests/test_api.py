"""HTTP 接口层测试：请求收发、错误响应结构、工况档存取与隔离。"""

import concurrent.futures

import pytest


BASE = {"t_wet_bulb": 28.0, "t_hot": 40.0, "l_to_g": 1.0}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_solve_endpoint_baseline(client):
    r = client.post("/merkel/solve", json={**BASE, "fill_ntu": 1.2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert 28.0 < body["t_cold"] < 40.0
    assert body["t_cold"] == pytest.approx(31.893623, abs=0.02)
    assert body["approach"] > 0
    assert body["h_air_out"] > body["h_air_in"]


def test_solve_endpoint_accepts_height_times_coefficient(client):
    r = client.post("/merkel/solve",
                    json={**BASE, "fill_height": 1.5, "ka_ld": 0.8})  # NTU = 1.2
    assert r.status_code == 200, r.text
    assert r.json()["fill_ntu"] == pytest.approx(1.2)
    assert r.json()["t_cold"] == pytest.approx(31.893623, abs=0.02)


def test_required_ntu_endpoint(client):
    r = client.post("/merkel/required-ntu",
                    json={**BASE, "t_cold": 32.0})
    assert r.status_code == 200
    body = r.json()
    assert body["ntu"] == pytest.approx(1.159224, abs=1e-3)
    assert body["update_air"] is True


def test_updated_vs_fixed_distinguishable_over_http(client):
    payload = {**BASE, "t_cold": 32.0}
    a = client.post("/merkel/required-ntu",
                    json={**payload, "update_air": True}).json()
    b = client.post("/merkel/required-ntu",
                    json={**payload, "update_air": False}).json()
    assert abs(a["ntu"] - b["ntu"]) > 0.1
    assert a["ntu"] > b["ntu"]


def test_invalid_input_returns_structured_error(client):
    # 湿球 >= 进水
    r = client.post("/merkel/solve",
                    json={"t_wet_bulb": 40.0, "t_hot": 40.0,
                          "l_to_g": 1.0, "fill_ntu": 1.0})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_input"
    assert "湿球" in err["reason"]

    # L/G 不为正（pydantic 形状约束 422，结构稳定）
    r2 = client.post("/merkel/solve",
                     json={"t_wet_bulb": 28.0, "t_hot": 40.0,
                           "l_to_g": 0.0, "fill_ntu": 1.0})
    assert r2.status_code == 422

    # 填料能力缺失
    r3 = client.post("/merkel/solve", json=BASE)
    assert r3.status_code == 422


def test_infeasible_condition_returns_structured_error(client):
    r = client.post("/merkel/required-ntu",
                    json={**BASE, "t_cold": 32.0, "l_to_g": 3.0})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "infeasible_operating_condition"
    assert err["detail"]["h_sat"] <= err["detail"]["h_air"]


def test_profile_crud_and_solve(client):
    p = {"name": "design-A", **BASE, "fill_ntu": 1.2}
    r = client.post("/profiles", json=p)
    assert r.status_code == 201
    assert r.json()["fill_ntu_effective"] == pytest.approx(1.2)

    assert client.get("/profiles/design-A").status_code == 200
    listed = client.get("/profiles").json()
    assert [x["name"] for x in listed] == ["design-A"]

    sol = client.post("/profiles/design-A/solve").json()
    assert sol["t_cold"] == pytest.approx(31.893623, abs=0.02)

    # 临时覆盖 L/G：增大水气比 -> 出水升高
    sol2 = client.post("/profiles/design-A/solve",
                       json={"l_to_g": 1.5}).json()
    assert sol2["t_cold"] > sol["t_cold"]
    # 覆盖不落回档：档内 L/G 仍是 1.0
    assert client.get("/profiles/design-A").json()["l_to_g"] == 1.0

    assert client.delete("/profiles/design-A").status_code == 204
    assert client.get("/profiles/design-A").status_code == 422


def test_unknown_profile_is_validation_error(client):
    assert client.post("/profiles/nope/solve").status_code == 422


def test_two_profiles_solve_concurrently_are_isolated(client):
    """两套工况档同时求解，中间水温/焓值互不污染。"""
    client.post("/profiles", json={"name": "P-low", "t_wet_bulb": 24.0,
                                   "t_hot": 40.0, "l_to_g": 0.8, "fill_ntu": 2.0})
    client.post("/profiles", json={"name": "P-high", "t_wet_bulb": 31.0,
                                   "t_hot": 45.0, "l_to_g": 1.6, "fill_ntu": 0.7})

    def solve(name):
        r = client.post(f"/profiles/{name}/solve")
        return name, r.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(solve, n) for n in (["P-low", "P-high"] * 12)]
        rows = [f.result() for f in concurrent.futures.as_completed(futs)]

    low = {b["t_cold"] for n, b in rows if n == "P-low"}
    high = {b["t_cold"] for n, b in rows if n == "P-high"}
    assert len(low) == 1 and len(high) == 1
    tc_low = low.pop()
    tc_high = high.pop()
    # 各自稳定在自己的区间，互不串档
    assert 24.0 < tc_low < 40.0
    assert 31.0 < tc_high < 45.0
    assert abs(tc_low - tc_high) > 1.0
