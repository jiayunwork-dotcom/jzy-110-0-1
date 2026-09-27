"""与水温对应的饱和湿空气焓取值。

Merkel 法中驱动力的饱和侧：与水温 T 接触的边界层空气视为
温度 T 下的饱和湿空气。这里给出该饱和状态焓的取值，单位
kJ/kg 干空气，参考状态取 0 °C 干空气与 0 °C 液态水。
"""
from __future__ import annotations

import numpy as np

ATMOSPHERIC_PRESSURE_KPA = 101.325


def saturation_vapor_pressure_kpa(t_c):
    """水面饱和水汽压（Buck, 1981），t_c 为摄氏温度，返回 kPa。"""
    t = np.asarray(t_c, dtype=float)
    return 0.61121 * np.exp((18.678 - t / 234.5) * (t / (257.14 + t)))


def saturation_humidity_ratio(t_c, pressure_kpa: float = ATMOSPHERIC_PRESSURE_KPA):
    """温度 t_c 下饱和湿空气含湿量，kg 水汽/kg 干空气。"""
    p_ws = saturation_vapor_pressure_kpa(t_c)
    return 0.62198 * p_ws / (pressure_kpa - p_ws)


def saturation_air_enthalpy_kj_per_kg(
    t_c, pressure_kpa: float = ATMOSPHERIC_PRESSURE_KPA
):
    """温度 t_c 下饱和湿空气焓，kJ/kg 干空气。

    h = 1.006·t + W·(2501 + 1.86·t)，W 为饱和含湿量。
    标量与数组输入均可。
    """
    t = np.asarray(t_c, dtype=float)
    w = saturation_humidity_ratio(t, pressure_kpa)
    return 1.006 * t + w * (2501.0 + 1.86 * t)
