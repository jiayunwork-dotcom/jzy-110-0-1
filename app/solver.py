"""收敛求解一环——给定填料能力反求实际出口水温。

填料能力以水流量基准的传质单元数 NTU 给出（或由填料高度 H [m]
乘体积传质系数 ka/L_d [1/m] 得到）。正算给出的是
"把水从 t_c 冷却到 t_h 所需要的 NTU"，反求即解一维方程：

    required_NTU(t_c) = fill_NTU,   t_c ∈ (t_wb, t_h)

``required_NTU`` 随 t_c 单调：出水越逼近湿球，所需 NTU 越大并趋于
无穷（pinch），因此解唯一。用 Brent 法（scipy.optimize.brentq）收敛，
逼近度 = t_c - t_wb，出塔空气焓由整塔能量衡算给出。
"""

from __future__ import annotations

from dataclasses import dataclass

from scipy.optimize import brentq

from . import psychrometrics as psy
from . import validation
from .air_balance import air_outlet_enthalpy, inlet_air_enthalpy
from .errors import InfeasibleError
from .merkel import merkel_number

# 出水贴着湿球时的数值下限 [℃]：物理上出水不可能低于进塔湿球
_CLIP_EPS = 1.0e-6


@dataclass(frozen=True)
class SolveResult:
    """反求结果。"""

    t_cold: float
    """实际出口（冷）水温 [℃]。"""
    approach: float
    """逼近度 t_c - t_wb [℃]。"""
    range: float
    """冷却幅度 t_h - t_c [℃]。"""
    t_hot: float
    t_wet_bulb: float
    fill_ntu: float
    required_ntu: float
    """该出口水温正算所需 NTU（应与填料能力一致）。"""
    h_air_in: float
    h_air_out: float
    l_to_g: float
    iterations: int


def _required_ntu_or_inf(t_c: float, twb: float, t_h: float,
                         l_to_g: float, pressure: float, n_steps: int) -> float:
    """正算所需 NTU；越过可行区（pinch）或越界时返回 +inf 而不是发散。"""
    if not twb < t_c < t_h:
        return float("inf")
    try:
        r = merkel_number(
            t_wet_bulb=twb,
            t_hot=t_h,
            t_cold=float(t_c),
            l_to_g=l_to_g,
            pressure=pressure,
            n_steps=n_steps,
            update_air=True,
        )
    except InfeasibleError:
        return float("inf")
    return r.ntu


def solve_outlet(
    *,
    t_wet_bulb: float,
    t_hot: float,
    l_to_g: float,
    fill_ntu: float,
    pressure: float = psy.P0,
    n_steps: int = 200,
    xtol: float = 1.0e-8,
) -> SolveResult:
    """给定填料传质能力，求实际出口水温、逼近度、空气侧出口焓。

    调用方负责先用 :mod:`app.validation` 校验输入；内核入口重复一次，
    保证被直接调用时非法输入也在求解前挡下。
    """
    validation.validate_common(
        twb=t_wet_bulb, t_hot=t_hot, l_to_g=l_to_g, pressure=pressure,
    )
    validation.validate_fill_capability(fill_ntu=fill_ntu)

    # 若离散段数为奇数，merkel 内部会抬到偶数，这里保持一致以免函数值跳变
    if n_steps < 4:
        raise validation.ValidationError("离散段数必须不小于 4")
    if n_steps % 2 != 0:
        n_steps += 1

    eval_count = 0

    def residual(t_c: float) -> float:
        # required_NTU 随 t_c 单调下降；残差在湿球侧为正、进水侧为负。
        nonlocal eval_count
        eval_count += 1
        req = _required_ntu_or_inf(t_c, t_wet_bulb, t_hot,
                                   l_to_g, pressure, n_steps)
        return 1.0e6 if req == float("inf") else req - fill_ntu

    # 右端略低于进水温度（严格 t_c < t_h），此处所需 NTU≈0，残差为负
    high = t_hot - 1.0e-9
    if residual(high) >= 0.0:
        raise InfeasibleError(
            "填料传质能力不足以达到任何可行出口水温：即使出水几乎等于进水，"
            "所需 NTU 仍不低于给定能力",
            detail={
                "fill_ntu": fill_ntu,
                "t_wet_bulb": t_wet_bulb,
                "t_hot": t_hot,
                "l_to_g": l_to_g,
            },
        )

    # 左端从湿球上方极小值起步：贴着湿球必为 pinch（残差按 +inf 处理，为正）。
    # 若填料能力强到该点仍可行（残差为负），则按 10 倍放大步长找正侧。
    delta = 1.0e-9
    low = t_wet_bulb + delta
    f_low = residual(low)
    probes = 0
    while f_low <= 0.0 and low < high and probes < 12:
        delta *= 10.0
        low = t_wet_bulb + delta
        f_low = residual(low)
        probes += 1

    h_in = inlet_air_enthalpy(t_wet_bulb, pressure)
    if f_low <= 0.0:
        # 填料能力远超过把出水压到湿球所需：数值下限即物理下限湿球温度
        t_c = t_wet_bulb + _CLIP_EPS
        req = _required_ntu_or_inf(t_c, t_wet_bulb, t_hot,
                                   l_to_g, pressure, n_steps)
        return SolveResult(
            t_cold=t_c,
            approach=_CLIP_EPS,
            range=t_hot - t_c,
            t_hot=t_hot,
            t_wet_bulb=t_wet_bulb,
            fill_ntu=fill_ntu,
            required_ntu=(fill_ntu if req == float("inf") else req),
            h_air_in=h_in,
            h_air_out=air_outlet_enthalpy(h_in, t_hot, t_c, l_to_g),
            l_to_g=l_to_g,
            iterations=eval_count,
        )

    t_c_root = brentq(residual, low, high, xtol=xtol, rtol=1.0e-12, maxiter=200)

    # 一致性核对：根处正算所需 NTU 必须等于填料能力
    req = _required_ntu_or_inf(t_c_root, t_wet_bulb, t_hot,
                               l_to_g, pressure, n_steps)
    if req == float("inf"):  # 数值上不应发生
        raise InfeasibleError("收敛点落在可行区外")

    return SolveResult(
        t_cold=float(t_c_root),
        approach=float(t_c_root - t_wet_bulb),
        range=float(t_hot - t_c_root),
        t_hot=float(t_hot),
        t_wet_bulb=float(t_wet_bulb),
        fill_ntu=float(fill_ntu),
        required_ntu=float(req),
        h_air_in=float(h_in),
        h_air_out=air_outlet_enthalpy(h_in, t_hot, t_c_root, l_to_g),
        l_to_g=float(l_to_g),
        iterations=eval_count,
    )
