"""出口水温与逼近度的收敛求解。

给定进塔湿球、进水温度、水气比与填料传质能力（KaV/L），反算
出口水温：寻找 T_out 使 Merkel 积分恰好等于填料能力。求解器
不持有任何跨调用状态，多次/并发求解互不影响。
"""
from __future__ import annotations

from dataclasses import dataclass

from scipy.optimize import brentq

from .air_balance import build_air_path
from .merkel import (
    DEFAULT_SEGMENTS,
    InfeasibleOperatingPoint,
    integrate_merkel_ntu,
)
from .psychrometrics import saturation_air_enthalpy_kj_per_kg


@dataclass(frozen=True)
class CoolingTowerSolution:
    """逆流工况求解结果。"""

    t_outlet_c: float
    approach_c: float
    cooling_range_c: float
    ntu: float
    h_air_inlet_kj_per_kg: float
    h_air_exit_kj_per_kg: float
    min_driving_force_kj_per_kg: float
    segments: int


def solve_counterflow(
    twb_c: float,
    t_inlet_c: float,
    water_air_ratio: float,
    fill_ntu: float,
    segments: int = DEFAULT_SEGMENTS,
    air_enthalpy_mode: str = "energy_balance",
) -> CoolingTowerSolution:
    """求解出口水温、逼近度与出塔空气焓。

    出口水温被夹在 (进塔湿球, 进水温度) 内：逼近度趋于 0 时所需
    NTU 发散，冷却幅趋于 0 时 NTU 趋于 0，故目标 NTU 有唯一根。
    """
    h_inlet = float(saturation_air_enthalpy_kj_per_kg(twb_c))

    # 出口水温被夹在 (进塔湿球, 进水温度) 内。逼近可行区边界时冷端
    # 驱动力趋于 0、所需 NTU 发散；越过可行区（操作线穿越饱和曲线）
    # 物理上等价于 NTU 不可达，以大的正哨兵值参与夹逼。冷却幅趋于 0
    # 时 NTU 趋于 0。可行区内 NTU 随 T_out 严格单调下降，根唯一。
    _INFEASIBLE_SENTINEL = 1.0e15

    def residual(t_outlet_c: float) -> float:
        path = build_air_path(
            air_enthalpy_mode, h_inlet, water_air_ratio, t_outlet_c
        )
        try:
            result = integrate_merkel_ntu(
                t_outlet_c, t_inlet_c, path, segments=segments
            )
        except InfeasibleOperatingPoint:
            return _INFEASIBLE_SENTINEL
        return result.ntu - fill_ntu

    lo = twb_c + 1e-9
    hi = t_inlet_c - 1e-9
    t_outlet = brentq(residual, lo, hi, xtol=1e-12, rtol=1e-14, maxiter=200)

    path = build_air_path(air_enthalpy_mode, h_inlet, water_air_ratio, t_outlet)
    final = integrate_merkel_ntu(t_outlet, t_inlet_c, path, segments=segments)
    return CoolingTowerSolution(
        t_outlet_c=t_outlet,
        approach_c=t_outlet - twb_c,
        cooling_range_c=t_inlet_c - t_outlet,
        ntu=final.ntu,
        h_air_inlet_kj_per_kg=h_inlet,
        h_air_exit_kj_per_kg=path.exit_enthalpy_kj_per_kg(t_inlet_c),
        min_driving_force_kj_per_kg=final.min_driving_force_kj_per_kg,
        segments=segments,
    )
