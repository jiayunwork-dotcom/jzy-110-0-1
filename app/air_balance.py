"""空气侧能量衡算——空气焓随填料高度逐段更新一环。

逆流塔中，水自上而下、空气自下而上。沿水温 t 自出口冷水 t_c
向入口热水 t_h 做离散推进时（即沿填料由下向上走），微元段的
绝热能量衡算为：

    dh = c_pw * L/G * dt          （水失去的显热 = 空气得到的全热）

因此任意水温 t 处的空气焓由进塔空气焓起算：

    h_a(t) = h_a1 + c_pw * l_to_g * (t - t_c)

整塔衡算的出口空气焓：

    h_a2 = h_a1 + c_pw * l_to_g * (t_h - t_c)

注意：本模块只负责"逐段更新空气焓"，不含焓差积分（那在 ``merkel`` 里）。
所有中间状态都是函数局部量，两次求解之间天然隔离。
"""

from __future__ import annotations

import numpy as np

from .psychrometrics import saturation_humidity_ratio, moist_air_enthalpy

# 水的比热，kJ/(kg·K)
CP_WATER = 4.186


def air_enthalpy_profile(
    temps: np.ndarray,
    t_c: float,
    h_a_in: float,
    l_to_g: float,
) -> np.ndarray:
    """沿水温离散网格逐段更新空气焓。

    Parameters
    ----------
    temps:
        沿水温的温度数组 [℃]，自出口冷水 t_c 向入口热水 t_h 单调递增。
        每段增量 ``temps[i] - t_c`` 对应水自该段以上释放的显热，
        空气焓随之逐段抬升。
    t_c:
        出口（冷）水温 [℃]，对应进风口位置。
    h_a_in:
        进塔空气焓（由进塔湿球温度确定）[kJ/kg 干空气]。
    l_to_g:
        水与空气的质量流量之比 L/G。

    Returns
    -------
    numpy.ndarray
        与 ``temps`` 同形的空气焓数组，``temps == t_c`` 处即 h_a_in。
    """
    temps = np.asarray(temps, dtype=float)
    return h_a_in + CP_WATER * l_to_g * (temps - t_c)


def air_outlet_enthalpy(
    h_a_in: float,
    t_h: float,
    t_c: float,
    l_to_g: float,
) -> float:
    """整塔能量衡算：出塔空气焓 [kJ/kg 干空气]。"""
    return float(h_a_in + CP_WATER * l_to_g * (t_h - t_c))


def inlet_air_enthalpy(t_wb: float, p: float = 101325.0) -> float:
    """进塔空气焓 [kJ/kg 干空气]。

    路易斯因子取 1 时，湿球温度 t_wb [℃] 下空气焓等于同温饱和空气焓
    （湿球绝热饱和线即等焓线）。
    """
    w_wb = saturation_humidity_ratio(t_wb, p)
    return float(moist_air_enthalpy(t_wb, w_wb))


def cp_water() -> float:
    """水侧比热，供其他模块统一取值。"""
    return CP_WATER
