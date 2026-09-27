"""Merkel 焓差积分一环——沿水温求所需传质单元数。

Merkel 方程（Lewis 因子取 1，水侧比热近似常数）：

    NTU = kaV/L = ∫[t_c → t_h] c_pw * (L/G) / (h_s(t) - h_a(t)) dt

* 驱动力 ``h_s(t) - h_a(t)`` 是**焓差**（kJ/kg 干空气），
  不是温度差——这不是间壁式换热器，不存在对数平均温差；
* ``h_s(t)`` 取当前**水温**对应的饱和湿空气焓；
* ``h_a(t)`` 由空气侧能量衡算沿水温逐段更新（``air_balance`` 模块），
  空气焓随填料高度真实变化；若固定不更新，驱动力形状失真，
  积分结果也会不同（``update_air=False`` 仅供对照试验）。

离散方式：水温自出口 t_c 向进口 t_h 等距推进（逆流，自下而上），
每段先用能量衡算更新该段空气焓，再取饱和焓算驱动力，
被积函数用 Simpson 复合公式积分（scipy）。

若某水温处饱和焓不高于空气焓（驱动力 <= 0），说明工况越过可行区，
立即以 :class:`InfeasibleError` 报出，绝不带符号硬积出乱值。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.integrate import simpson

from . import psychrometrics as psy
from . import validation
from .air_balance import (
    CP_WATER,
    air_enthalpy_profile,
    air_outlet_enthalpy,
    inlet_air_enthalpy,
)
from .errors import InfeasibleError

# 驱动力下限：小于它视为到达可行区边界（逼近湿球时的 pinch）
MIN_DRIVING_FORCE = 1.0e-6


@dataclass(frozen=True)
class MerkelNodes:
    """沿水温的逐段中间量（诊断/回归用）。"""

    temps: list[float]
    h_sat: list[float]
    h_air: list[float]
    driving_force: list[float]


@dataclass(frozen=True)
class MerkelResult:
    """Merkel 积分结果。"""

    ntu: float
    """所需传质单元数（水流量基准）。"""
    t_cold: float
    t_hot: float
    l_to_g: float
    h_air_in: float
    """进塔空气焓，kJ/kg 干空气。"""
    h_air_out: float
    """出塔空气焓（能量衡算），kJ/kg 干空气。"""
    update_air: bool
    """空气焓是否沿填料高度逐段更新。"""
    min_driving_force: float
    pinch_temperature: float
    """驱动力最小处的水温 [℃]。"""
    nodes: MerkelNodes | None = None


def merkel_number(
    *,
    t_wet_bulb: float,
    t_hot: float,
    t_cold: float,
    l_to_g: float,
    pressure: float = psy.P0,
    n_steps: int = 200,
    update_air: bool = True,
    keep_nodes: bool = False,
) -> MerkelResult:
    """沿水温积分求填料需要的传质单元数 NTU。

    调用方（接口层）也会先校验；此处重复一次，保证内核被直接调用时
    非法输入同样在积分前挡下。
    """
    validation.validate_common(
        twb=t_wet_bulb, t_hot=t_hot, l_to_g=l_to_g, pressure=pressure,
    )
    validation.validate_required_ntu(
        t_cold=t_cold, twb=t_wet_bulb, t_hot=t_hot, n_steps=n_steps,
    )

    if n_steps % 2 != 0:
        # Simpson 复合公式要求偶数段
        n_steps = n_steps + (n_steps % 2)
        if n_steps < 4:
            n_steps = 4

    # 沿水温自出口冷水向入口热水离散（逆流推进方向）
    temps = np.linspace(t_cold, t_hot, n_steps + 1)

    # 当前水温对应的饱和湿空气焓
    h_sat = np.asarray(psy.saturated_enthalpy(temps, pressure), dtype=float)

    # 进塔空气焓（湿球等焓）
    h_in = inlet_air_enthalpy(t_wet_bulb, pressure)

    if update_air:
        # 能量衡算逐段更新空气焓：h_a(t) = h_in + c_pw*L/G*(t - t_c)
        h_air = air_enthalpy_profile(temps, t_cold, h_in, l_to_g)
    else:
        # 对照做法：空气焓固定在进塔值不更新（驱动力恒定化的错误做法）
        h_air = np.full_like(temps, h_in)

    force = h_sat - h_air

    # 可行区检查：任意水温处饱和焓必须严格高于空气焓
    i_min = int(np.argmin(force))
    f_min = float(force[i_min])
    if f_min <= MIN_DRIVING_FORCE:
        raise InfeasibleError(
            "积分过程中水温 "
            f"{temps[i_min]:.3f} ℃ 处饱和空气焓（{h_sat[i_min]:.2f} kJ/kg）"
            f"不高于空气焓（{h_air[i_min]:.2f} kJ/kg），"
            "工况越过可行区（出现 pinch/驱动力反转），无法完成 Merkel 积分",
            detail={
                "pinch_temperature": float(temps[i_min]),
                "h_sat": float(h_sat[i_min]),
                "h_air": float(h_air[i_min]),
                "t_wet_bulb": t_wet_bulb,
                "t_hot": t_hot,
                "t_cold": t_cold,
                "l_to_g": l_to_g,
            },
        )

    integrand = CP_WATER * l_to_g / force
    ntu = float(simpson(integrand, x=temps))

    # 出塔空气焓始终按整塔能量衡算给出（固定模式下标记其为对照情形）
    h_out = air_outlet_enthalpy(h_in, t_hot, t_cold, l_to_g)

    nodes = None
    if keep_nodes:
        nodes = MerkelNodes(
            temps=temps.tolist(),
            h_sat=h_sat.tolist(),
            h_air=h_air.tolist(),
            driving_force=force.tolist(),
        )

    return MerkelResult(
        ntu=ntu,
        t_cold=float(t_cold),
        t_hot=float(t_hot),
        l_to_g=float(l_to_g),
        h_air_in=float(h_in),
        h_air_out=float(h_out),
        update_air=update_air,
        min_driving_force=f_min,
        pinch_temperature=float(temps[i_min]),
        nodes=nodes,
    )
