"""HTTP 接口层：只做请求收发与结果编排，不含热工计算。

计算环节分属：psychrometrics（饱和焓取值）、merkel（焓差积分）、
air_balance（空气侧能量衡算）、solver（出口水温收敛求解）、
profiles（工况档存取）、validation（参数校验）。
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .air_balance import build_air_path
from .merkel import DEFAULT_SEGMENTS, InfeasibleOperatingPoint, integrate_merkel_ntu
from .profiles import OperatingProfile, ProfileNotFound, ProfileStore
from .psychrometrics import saturation_air_enthalpy_kj_per_kg
from .schemas import (
    MerkelNtuRequest,
    MerkelNtuResponse,
    ProfileIn,
    ProfileOut,
    ProfileSolveResponse,
    SolveRequest,
    SolveResponse,
)
from .solver import CoolingTowerSolution, solve_counterflow
from .validation import (
    InvalidOperatingInput,
    validate_fill_capability,
    validate_inlet_conditions,
    validate_outlet_temperature,
    validate_water_air_ratio,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="机械通风冷却塔 Merkel 核算服务",
        description="Merkel 焓差法评估逆流填料散热能力：传质单元数正算与出口水温反算。",
        version="1.0.0",
    )
    store = ProfileStore()
    app.state.profile_store = store

    @app.exception_handler(InvalidOperatingInput)
    async def _invalid_input(_: Request, exc: InvalidOperatingInput):
        return JSONResponse(
            status_code=422, content={"error": "invalid_input", "reason": str(exc)}
        )

    @app.exception_handler(InfeasibleOperatingPoint)
    async def _infeasible(_: Request, exc: InfeasibleOperatingPoint):
        return JSONResponse(
            status_code=422,
            content={"error": "infeasible_operating_point", "reason": str(exc)},
        )

    @app.exception_handler(ProfileNotFound)
    async def _profile_missing(_: Request, exc: ProfileNotFound):
        return JSONResponse(
            status_code=404, content={"error": "profile_not_found", "reason": str(exc)}
        )

    def _solve_response(sol: CoolingTowerSolution, mode: str) -> SolveResponse:
        return SolveResponse(
            t_outlet_c=sol.t_outlet_c,
            approach_c=sol.approach_c,
            cooling_range_c=sol.cooling_range_c,
            ntu=sol.ntu,
            h_air_inlet_kj_per_kg=sol.h_air_inlet_kj_per_kg,
            h_air_exit_kj_per_kg=sol.h_air_exit_kj_per_kg,
            min_driving_force_kj_per_kg=sol.min_driving_force_kj_per_kg,
            segments=sol.segments,
            air_enthalpy_mode=mode,
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/merkel/ntu", response_model=MerkelNtuResponse)
    def merkel_ntu(req: MerkelNtuRequest):
        """正算：给定出口水温，沿水温积分求填料需要的传质单元数。"""
        validate_inlet_conditions(req.twb_c, req.t_inlet_c)
        validate_water_air_ratio(req.water_air_ratio)
        validate_outlet_temperature(req.twb_c, req.t_inlet_c, req.t_outlet_c)

        h_inlet = float(saturation_air_enthalpy_kj_per_kg(req.twb_c))
        path = build_air_path(
            req.air_enthalpy_mode, h_inlet, req.water_air_ratio, req.t_outlet_c
        )
        result = integrate_merkel_ntu(
            req.t_outlet_c, req.t_inlet_c, path, segments=req.segments
        )
        return MerkelNtuResponse(
            ntu=result.ntu,
            min_driving_force_kj_per_kg=result.min_driving_force_kj_per_kg,
            h_air_inlet_kj_per_kg=h_inlet,
            h_air_exit_kj_per_kg=path.exit_enthalpy_kj_per_kg(req.t_inlet_c),
            segments=result.segments,
            air_enthalpy_mode=req.air_enthalpy_mode,
        )

    @app.post("/merkel/solve", response_model=SolveResponse)
    def merkel_solve(req: SolveRequest):
        """反算：给定填料传质能力，求出口水温、逼近度与出塔空气焓。"""
        validate_inlet_conditions(req.twb_c, req.t_inlet_c)
        validate_water_air_ratio(req.water_air_ratio)
        validate_fill_capability(req.fill_ntu)

        sol = solve_counterflow(
            twb_c=req.twb_c,
            t_inlet_c=req.t_inlet_c,
            water_air_ratio=req.water_air_ratio,
            fill_ntu=req.fill_ntu,
            segments=req.segments,
            air_enthalpy_mode=req.air_enthalpy_mode,
        )
        return _solve_response(sol, req.air_enthalpy_mode)

    @app.post("/profiles", status_code=201, response_model=ProfileOut)
    def create_profile(req: ProfileIn):
        """登记一套命名的进气与填料参数工况档。"""
        validate_inlet_conditions(req.twb_c, req.t_inlet_c)
        validate_water_air_ratio(req.water_air_ratio)
        validate_fill_capability(req.fill_ntu)
        profile = OperatingProfile(
            name=req.name,
            twb_c=req.twb_c,
            t_inlet_c=req.t_inlet_c,
            water_air_ratio=req.water_air_ratio,
            fill_ntu=req.fill_ntu,
        )
        return store.put(profile)

    @app.get("/profiles", response_model=list[ProfileOut])
    def list_profiles():
        return store.list()

    @app.get("/profiles/{name}", response_model=ProfileOut)
    def get_profile(name: str):
        return store.get(name)

    @app.delete("/profiles/{name}", status_code=204)
    def delete_profile(name: str):
        store.remove(name)

    @app.post("/profiles/{name}/solve", response_model=ProfileSolveResponse)
    def solve_profile(name: str, segments: int = DEFAULT_SEGMENTS):
        """按工况档求解出口水温；各档独立求解，中间量互不影响。"""
        profile = store.get(name)
        sol = solve_counterflow(
            twb_c=profile.twb_c,
            t_inlet_c=profile.t_inlet_c,
            water_air_ratio=profile.water_air_ratio,
            fill_ntu=profile.fill_ntu,
            segments=segments,
        )
        return ProfileSolveResponse(
            **_solve_response(sol, "energy_balance").model_dump(),
            profile=profile.name,
        )

    return app


app = create_app()
