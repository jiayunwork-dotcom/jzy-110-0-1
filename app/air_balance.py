"""空气焓随填料高度逐段更新的能量衡算。

逆流塔中，空气自填料底部（冷水出口端）进入、自顶部（热水进口端）
离开。水侧放热全部进入空气（路易斯因子取 1，塔体绝热），沿水温的
能量衡算为：

    G·(h_air(T) − h_air,in) = L·c_pw·(T − T_out)

即空气焓随水温线性推进：在 T = T_out 处等于进塔空气焓，在
T = T_in 处等于出塔空气焓。本模块只负责这条空气侧衡算，不参与
Merkel 积分的离散（见 merkel.py）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Union

import numpy as np

CP_WATER_KJ_PER_KG_K = 4.186

ScalarOrArray = Union[float, np.ndarray]


class AirEnthalpyPath(Protocol):
    """沿水温给出空气焓的接口，供 Merkel 积分逐段查询。"""

    def enthalpy_at(self, water_temp_c: ScalarOrArray) -> ScalarOrArray:
        """返回与水温 water_temp_c 对应高度处的空气焓，kJ/kg 干空气。"""
        ...


@dataclass(frozen=True)
class EnergyBalanceAirPath:
    """按能量衡算逐段更新空气焓（正式工况）。

    h_air(T) = h_inlet + (L/G)·c_pw·(T − T_outlet)
    """

    h_inlet_kj_per_kg: float
    water_air_ratio: float
    t_outlet_c: float
    cp_water_kj_per_kg_k: float = CP_WATER_KJ_PER_KG_K

    def enthalpy_at(self, water_temp_c: ScalarOrArray) -> ScalarOrArray:
        t = np.asarray(water_temp_c, dtype=float)
        return self.h_inlet_kj_per_kg + self.water_air_ratio * self.cp_water_kj_per_kg_k * (
            t - self.t_outlet_c
        )

    def exit_enthalpy_kj_per_kg(self, t_inlet_c: float) -> float:
        """出塔空气焓（水温推进到进口端时的空气焓）。"""
        return float(self.enthalpy_at(t_inlet_c))


@dataclass(frozen=True)
class FixedAirPath:
    """诊断对照用：空气焓固定为进塔值、不随高度更新。

    仅用于验证空气侧衡算的作用——固定空气焓会让驱动力恒定偏大，
    使传质单元数与出口水温脱钩，正式求解不应使用。
    """

    h_inlet_kj_per_kg: float

    def enthalpy_at(self, water_temp_c: ScalarOrArray) -> ScalarOrArray:
        t = np.asarray(water_temp_c, dtype=float)
        return np.broadcast_to(self.h_inlet_kj_per_kg, t.shape)

    def exit_enthalpy_kj_per_kg(self, t_inlet_c: float) -> float:
        return self.h_inlet_kj_per_kg


def build_air_path(
    mode: str,
    h_inlet_kj_per_kg: float,
    water_air_ratio: float,
    t_outlet_c: float,
) -> AirEnthalpyPath:
    """按模式构造空气焓路径；mode 为 energy_balance 或 fixed。"""
    if mode == "energy_balance":
        return EnergyBalanceAirPath(h_inlet_kj_per_kg, water_air_ratio, t_outlet_c)
    if mode == "fixed":
        return FixedAirPath(h_inlet_kj_per_kg)
    raise ValueError(f"未知空气焓模式: {mode!r}，应为 'energy_balance' 或 'fixed'")
