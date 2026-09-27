"""Merkel 焓差沿水温的数值积分。

传质单元数（冷却数）：

    NTU = ∫_{T_out}^{T_in} c_pw·dT / (h_sat(T) − h_air(T))

沿水温自出口向进口离散推进，逐段取中点求驱动力；空气焓 h_air(T)
由注入的 AirEnthalpyPath 给出（能量衡算逐段更新，或诊断用固定值），
本模块不关心其来源。积分途中若某水温处饱和焓不高于空气焓，说明
工况越过可行区，抛出 InfeasibleOperatingPoint，绝不让积分发散出乱值。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .air_balance import CP_WATER_KJ_PER_KG_K, AirEnthalpyPath
from .psychrometrics import saturation_air_enthalpy_kj_per_kg

DEFAULT_SEGMENTS = 240


class InfeasibleOperatingPoint(RuntimeError):
    """积分途中饱和焓不高于空气焓，工况越过可行区。"""


@dataclass(frozen=True)
class MerkelIntegral:
    """一次 Merkel 积分的结果。"""

    ntu: float
    min_driving_force_kj_per_kg: float
    segments: int
    t_outlet_c: float
    t_inlet_c: float


def integrate_merkel_ntu(
    t_outlet_c: float,
    t_inlet_c: float,
    air_path: AirEnthalpyPath,
    cp_water_kj_per_kg_k: float = CP_WATER_KJ_PER_KG_K,
    segments: int = DEFAULT_SEGMENTS,
) -> MerkelIntegral:
    """沿水温自 T_out 向 T_in 积分 Merkel 传质单元数。

    逆流边界对应关系：T_out 端（填料底部）空气焓为进塔值，
    T_in 端（填料顶部）空气焓为出塔值，由 air_path 保证。
    """
    if segments < 4:
        raise ValueError(f"积分分段数过少: {segments}，至少为 4")
    if not t_inlet_c > t_outlet_c:
        raise ValueError(
            f"进水温度 {t_inlet_c} °C 必须高于出口水温 {t_outlet_c} °C"
        )

    d_t = (t_inlet_c - t_outlet_c) / segments
    # 各段中点水温，自出口向进口推进
    t_mid = t_outlet_c + (np.arange(segments) + 0.5) * d_t
    h_sat = saturation_air_enthalpy_kj_per_kg(t_mid)
    h_air = np.asarray(air_path.enthalpy_at(t_mid), dtype=float)

    driving = h_sat - h_air
    if np.any(driving <= 0.0):
        i = int(np.argmin(driving))
        raise InfeasibleOperatingPoint(
            f"水温 {float(t_mid[i]):.2f} °C 处饱和湿空气焓 {float(h_sat[i]):.3f} kJ/kg "
            f"不高于空气焓 {float(h_air[i]):.3f} kJ/kg，工况越过可行区，积分终止"
        )

    ntu = float(cp_water_kj_per_kg_k * d_t * np.sum(1.0 / driving))
    return MerkelIntegral(
        ntu=ntu,
        min_driving_force_kj_per_kg=float(np.min(driving)),
        segments=segments,
        t_outlet_c=t_outlet_c,
        t_inlet_c=t_inlet_c,
    )
