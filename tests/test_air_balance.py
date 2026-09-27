"""空气侧能量衡算的区分性测试。

要求：空气焓随高度更新与固定不更新必须给出能区分的结果，
以此验证空气侧衡算确实起作用；逐段中间量沿水温单调上升。
"""

import numpy as np
import pytest

from app.air_balance import (
    CP_WATER,
    air_enthalpy_profile,
    air_outlet_enthalpy,
    inlet_air_enthalpy,
)
from app.merkel import merkel_number

T_WB, T_HOT, T_COLD, L_TO_G = 28.0, 40.0, 32.0, 1.0


def test_air_enthalpy_rises_along_water_temperature():
    """逐段更新：空气焓沿水温（自下而上）严格单调上升，斜率 = c_pw*L/G。"""
    temps = np.linspace(T_COLD, T_HOT, 11)
    h_in = inlet_air_enthalpy(T_WB)
    profile = air_enthalpy_profile(temps, T_COLD, h_in, L_TO_G)

    assert profile[0] == pytest.approx(h_in)
    assert np.all(np.diff(profile) > 0)
    # 每段增量 = c_pw * L/G * dt
    dts = np.diff(temps)
    np.testing.assert_allclose(np.diff(profile), CP_WATER * L_TO_G * dts)
    # 顶端即整塔衡算值
    assert profile[-1] == pytest.approx(
        air_outlet_enthalpy(h_in, T_HOT, T_COLD, L_TO_G)
    )


def test_updated_vs_fixed_air_enthalpy_give_distinguishable_ntu():
    """更新 vs 固定空气焓：Merkel 数必须显著不同（固定做法低估 NTU）。"""
    updated = merkel_number(
        t_wet_bulb=T_WB, t_hot=T_HOT, t_cold=T_COLD,
        l_to_g=L_TO_G, update_air=True, keep_nodes=True,
    )
    fixed = merkel_number(
        t_wet_bulb=T_WB, t_hot=T_HOT, t_cold=T_COLD,
        l_to_g=L_TO_G, update_air=False, keep_nodes=True,
    )
    assert updated.update_air is True
    assert fixed.update_air is False
    # 差距足够大，可被测试区分（约 30%）
    assert updated.ntu != pytest.approx(fixed.ntu, rel=0.05)
    assert updated.ntu > fixed.ntu

    # 逐段节点上：更新做法空气焓持续上升；固定做法全程一条直线
    assert np.all(np.diff(updated.nodes.h_air) > 0)
    assert np.allclose(fixed.nodes.h_air, fixed.nodes.h_air[0])
    # 两种做法的饱和焓曲线完全相同（差异只来自空气侧衡算）
    assert updated.nodes.h_sat == fixed.nodes.h_sat
    # 出口端：更新做法驱动力被热湿空气显著削弱
    assert updated.nodes.driving_force[-1] < fixed.nodes.driving_force[-1]
    # L/G=1 工况最小驱动力出现在冷端（塔底空气焓最低、饱和焓也最低）
    assert updated.pinch_temperature == pytest.approx(T_COLD, abs=0.05)
    # 而 L/G 大到空气侧热湿负荷主导时，pinch 移到塔顶
    high_lg = merkel_number(t_wet_bulb=T_WB, t_hot=T_HOT, t_cold=T_COLD,
                            l_to_g=2.0, keep_nodes=True)
    assert high_lg.pinch_temperature == pytest.approx(T_HOT, abs=0.05)


def test_fixed_mode_still_reports_energy_balance_outlet_enthalpy():
    """固定模式仅供对照：出塔空气焓仍按整塔衡算如实给出，不冒充恒定。"""
    fixed = merkel_number(
        t_wet_bulb=T_WB, t_hot=T_HOT, t_cold=T_COLD,
        l_to_g=L_TO_G, update_air=False,
    )
    assert fixed.h_air_out == pytest.approx(
        fixed.h_air_in + CP_WATER * L_TO_G * (T_HOT - T_COLD)
    )
    assert fixed.h_air_out > fixed.h_air_in


def test_nodes_are_independent_between_calls():
    """两次求解的中间焓值/水温是各自局部量，互不污染。"""
    a = merkel_number(t_wet_bulb=28, t_hot=40, t_cold=32, l_to_g=1.0, keep_nodes=True)
    a_vals = (list(a.nodes.temps), list(a.nodes.h_air))
    b = merkel_number(t_wet_bulb=24, t_hot=42, t_cold=31, l_to_g=1.4, keep_nodes=True)
    # a 的节点在 b 之后仍然是 a 自己的值
    assert a.nodes.temps == a_vals[0]
    assert a.nodes.h_air == a_vals[1]
    assert b.nodes.temps[0] == 31.0
    assert b.nodes.h_air[0] != a.nodes.h_air[0]
