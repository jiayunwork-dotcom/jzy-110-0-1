"""湿空气热物性——与水温对应的饱和湿空气焓取值一环。

路易斯因子取 1，焓基准统一取 0 ℃ 干空气与 0 ℃ 液态水：

    h = c_pa * t + W * (h_fg0 + c_pv * t)        单位 kJ/kg(干空气)

饱和蒸汽压采用 ASHRAE Handbook—Fundamentals (2017) 第 1 章
0 ℃ 以上水侧的多项式公式（P_ws 单位 Pa，温度单位 K）。
该公式在冷却塔常用水温区间（0~50 ℃）与标准水蒸气表偏差极小。
"""

from __future__ import annotations

import numpy as np

# 标准大气压，Pa
P0 = 101325.0

# 干空气定压比热，kJ/(kg·K)
CP_AIR = 1.006
# 水蒸气定压比热，kJ/(kg·K)
CP_VAPOR = 1.86
# 0 ℃ 水汽化潜热，kJ/kg
H_FG_0 = 2501.0

# ASHRAE 2017 水侧饱和蒸汽压多项式系数（0~200 ℃，指数 -1~8）
_A = (-5.8002206e3, 1.3914993, -4.8640239e-2, 4.1764768e-5,
      -1.4452093e-8, 6.5459673)


def saturation_pressure(tw: float | np.ndarray) -> float | np.ndarray:
    """水面饱和水蒸气压力 P_ws [Pa]。

    Parameters
    ----------
    tw:
        水温，℃，须 >= 0。
    """
    t = np.asarray(tw, dtype=float) + 273.15
    if np.any(t < 273.15):
        raise ValueError("饱和蒸汽压公式仅支持 0 ℃ 及以上的水温")
    ln_pws = (
        _A[0] / t
        + _A[1]
        + _A[2] * t
        + _A[3] * t**2
        + _A[4] * t**3
        + _A[5] * np.log(t)
    )
    return np.exp(ln_pws)


def humidity_ratio(pv: float | np.ndarray, p: float = P0) -> float | np.ndarray:
    """由水蒸气分压力 pv [Pa] 计算含湿量 W [kg/kg 干空气]。"""
    return 0.621945 * pv / (p - pv)


def saturation_humidity_ratio(tw: float | np.ndarray, p: float = P0) -> float | np.ndarray:
    """水温 tw [℃] 对应的饱和空气含湿量 W_s [kg/kg 干空气]。"""
    pws = saturation_pressure(tw)
    return humidity_ratio(pws, p)


def moist_air_enthalpy(t: float | np.ndarray, w: float | np.ndarray) -> float | np.ndarray:
    """湿空气焓 h [kJ/kg 干空气]，温度 t [℃]，含湿量 w [kg/kg]。"""
    return CP_AIR * np.asarray(t, dtype=float) + np.asarray(w, dtype=float) * (
        H_FG_0 + CP_VAPOR * np.asarray(t, dtype=float)
    )


def saturated_enthalpy(tw: float | np.ndarray, p: float = P0) -> float | np.ndarray:
    """与水温 tw [℃] 对应的饱和湿空气焓 h_s [kJ/kg 干空气]。

    标量与数组均可（积分时整段水温一次取值）。
    """
    tw_arr = np.asarray(tw, dtype=float)
    ws = saturation_humidity_ratio(tw_arr, p)
    return moist_air_enthalpy(tw_arr, ws)
