"""FastAPI 接口层——只做请求收发与结果编排，不含热工公式。

路由：

* ``POST /merkel/required-ntu``  正算所需传质单元数（支持固定/更新空气焓对照）
* ``POST /merkel/solve``         给定填料能力反求出口水温、逼近度、空气出口焓
* ``GET/POST/DELETE /profiles``  工况档存取
* ``POST /profiles/{name}/solve``  按命名工况档反求（可临时覆盖参数）
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from . import validation
from .errors import CoolingTowerError, ValidationError, InfeasibleError
from .merkel import merkel_number
from .profiles import Profile, store
from .schemas import (
    HealthResponse,
    ProfileRequest,
    ProfileResponse,
    ProfileSolveOverride,
    RequiredNtuRequest,
    RequiredNtuResponse,
    NodesPayload,
    SolveOutletRequest,
    SolveOutletResponse,
)
from .solver import solve_outlet

app = FastAPI(
    title="逆流填料冷却塔 Merkel 焓差法核算服务",
    version="1.0.0",
    description="常驻 HTTP 服务：Merkel 焓差积分正算传质单元数，给定填料能力反求出口水温。",
)


# ---------------- 错误响应编排 ----------------

def _error_response(exc: CoolingTowerError, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": exc.code,
                "reason": exc.reason,
                "detail": exc.detail,
            }
        },
    )


@app.exception_handler(ValidationError)
async def _on_validation_error(_: Request, exc: ValidationError) -> JSONResponse:
    # 非法输入：积分前挡下
    return _error_response(exc, 422)


@app.exception_handler(InfeasibleError)
async def _on_infeasible_error(_: Request, exc: InfeasibleError) -> JSONResponse:
    # 工况越过可行区（驱动力消失/反转）
    return _error_response(exc, 422)


@app.exception_handler(Exception)
async def _on_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    # 未预期错误不外泄堆栈，给出稳定结构
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error",
                           "reason": "服务内部错误", "detail": {}}},
    )


# ---------------- 正算 ----------------

@app.post("/merkel/required-ntu", response_model=RequiredNtuResponse)
def required_ntu(req: RequiredNtuRequest) -> Any:
    validation.validate_common(
        twb=req.t_wet_bulb, t_hot=req.t_hot,
        l_to_g=req.l_to_g, pressure=req.pressure,
    )
    validation.validate_required_ntu(
        t_cold=req.t_cold, twb=req.t_wet_bulb,
        t_hot=req.t_hot, n_steps=req.n_steps,
    )
    r = merkel_number(
        t_wet_bulb=req.t_wet_bulb,
        t_hot=req.t_hot,
        t_cold=req.t_cold,
        l_to_g=req.l_to_g,
        pressure=req.pressure,
        n_steps=req.n_steps,
        update_air=req.update_air,
        keep_nodes=req.keep_nodes,
    )
    return RequiredNtuResponse(
        ntu=r.ntu,
        t_cold=r.t_cold,
        t_hot=r.t_hot,
        l_to_g=r.l_to_g,
        h_air_in=r.h_air_in,
        h_air_out=r.h_air_out,
        update_air=r.update_air,
        min_driving_force=r.min_driving_force,
        pinch_temperature=r.pinch_temperature,
        nodes=(NodesPayload(
            temps=r.nodes.temps,
            h_sat=r.nodes.h_sat,
            h_air=r.nodes.h_air,
            driving_force=r.nodes.driving_force,
        ) if r.nodes is not None else None),
    )


# ---------------- 反求 ----------------

def _resolve_fill_ntu(*, fill_ntu, fill_height, ka_ld) -> float:
    validation.validate_fill_capability(
        fill_ntu=fill_ntu, fill_height=fill_height, ka_ld=ka_ld,
    )
    if fill_ntu is not None:
        return float(fill_ntu)
    return float(fill_height * ka_ld)


@app.post("/merkel/solve", response_model=SolveOutletResponse)
def solve(req: SolveOutletRequest) -> Any:
    validation.validate_common(
        twb=req.t_wet_bulb, t_hot=req.t_hot,
        l_to_g=req.l_to_g, pressure=req.pressure,
    )
    ntu = _resolve_fill_ntu(
        fill_ntu=req.fill_ntu,
        fill_height=req.fill_height,
        ka_ld=req.ka_ld,
    )
    r = solve_outlet(
        t_wet_bulb=req.t_wet_bulb,
        t_hot=req.t_hot,
        l_to_g=req.l_to_g,
        fill_ntu=ntu,
        pressure=req.pressure,
        n_steps=req.n_steps,
    )
    return SolveOutletResponse(**r.__dict__)


# ---------------- 工况档 ----------------

@app.get("/health", response_model=HealthResponse)
def health() -> Any:
    return HealthResponse(status="ok", service="cooling-tower-merkel")


@app.post("/profiles", response_model=ProfileResponse, status_code=201)
def create_profile(req: ProfileRequest) -> Any:
    validation.validate_common(
        twb=req.t_wet_bulb, t_hot=req.t_hot,
        l_to_g=req.l_to_g, pressure=req.pressure,
    )
    if req.n_steps < 4:
        raise ValidationError("离散段数必须不小于 4")
    validation.validate_fill_capability(
        fill_ntu=req.fill_ntu,
        fill_height=req.fill_height,
        ka_ld=req.ka_ld,
    )
    profile = Profile(
        name=req.name,
        t_wet_bulb=req.t_wet_bulb,
        t_hot=req.t_hot,
        l_to_g=req.l_to_g,
        fill_ntu=req.fill_ntu,
        fill_height=req.fill_height,
        ka_ld=req.ka_ld,
        pressure=req.pressure,
        n_steps=req.n_steps,
    )
    store.put(profile)
    return ProfileResponse(**profile.to_dict())


@app.get("/profiles", response_model=list[ProfileResponse])
def list_profiles() -> Any:
    return [ProfileResponse(**p.to_dict()) for p in store.list()]


@app.get("/profiles/{name}", response_model=ProfileResponse)
def get_profile(name: str) -> Any:
    return ProfileResponse(**store.get(name).to_dict())


@app.delete("/profiles/{name}", status_code=204)
def delete_profile(name: str) -> Response:
    store.delete(name)
    return Response(status_code=204)


@app.post("/profiles/{name}/solve", response_model=SolveOutletResponse)
def solve_profile(name: str, override: ProfileSolveOverride | None = None) -> Any:
    profile = store.get(name)

    twb = override.t_wet_bulb if override and override.t_wet_bulb is not None else profile.t_wet_bulb
    t_hot = override.t_hot if override and override.t_hot is not None else profile.t_hot
    l_to_g = override.l_to_g if override and override.l_to_g is not None else profile.l_to_g
    pressure = override.pressure if override and override.pressure is not None else profile.pressure
    n_steps = override.n_steps if override and override.n_steps is not None else profile.n_steps
    fill_ntu = override.fill_ntu if override and override.fill_ntu is not None else profile.fill_ntu
    fill_height = override.fill_height if override and override.fill_height is not None else profile.fill_height
    ka_ld = override.ka_ld if override and override.ka_ld is not None else profile.ka_ld

    validation.validate_common(twb=twb, t_hot=t_hot, l_to_g=l_to_g, pressure=pressure)
    ntu = _resolve_fill_ntu(fill_ntu=fill_ntu, fill_height=fill_height, ka_ld=ka_ld)

    r = solve_outlet(
        t_wet_bulb=twb,
        t_hot=t_hot,
        l_to_g=l_to_g,
        fill_ntu=ntu,
        pressure=pressure,
        n_steps=n_steps,
    )
    return SolveOutletResponse(**r.__dict__)
