"""随仓库交付的三条钉板物理关系 + 逆流基准回归。

钉住：
1. 同样填料能力下增大水气比 L/G，出口水温升高（冷却幅度下降）；
2. 增强填料传质能力，出口水温下降、逼近度变小；
3. 出口水温始终不低于进塔湿球（物理下限），且低于进水温度。

另有手算核对基准：twb=28℃、进水=40℃、L/G=1、填料 NTU=1.2。
"""

import pytest

from app.psychrometrics import saturated_enthalpy, saturation_pressure
from app.merkel import merkel_number
from app.solver import solve_outlet

# 基准逆流工况
T_WB = 28.0
T_HOT = 40.0
L_TO_G = 1.0
FILL_NTU = 1.2


def test_water_to_air_ratio_increase_raises_outlet_temperature():
    """水气比增大：更多水分摊同一份空气吸热能力 -> 出水升高。"""
    results = [
        solve_outlet(t_wet_bulb=T_WB, t_hot=T_HOT, l_to_g=lg, fill_ntu=FILL_NTU)
        for lg in (0.6, 0.8, 1.0, 1.2, 1.5, 2.0)
    ]
    t_cold = [r.t_cold for r in results]
    assert t_cold == sorted(t_cold)
    assert t_cold[0] < t_cold[-1]
    # 冷却幅度随之下降
    ranges = [r.range for r in results]
    assert ranges == sorted(ranges, reverse=True)
    assert ranges[0] > ranges[-1]


def test_stronger_fill_lowers_outlet_temperature_and_approach():
    """填料传质能力增强 -> 出水下降、逼近度变小。"""
    results = [
        solve_outlet(t_wet_bulb=T_WB, t_hot=T_HOT, l_to_g=L_TO_G, fill_ntu=ntu)
        for ntu in (0.6, 0.9, 1.2, 1.8, 2.5, 4.0)
    ]
    t_cold = [r.t_cold for r in results]
    approaches = [r.approach for r in results]
    assert t_cold == sorted(t_cold, reverse=True)
    assert t_cold[0] > t_cold[-1]
    assert approaches == sorted(approaches, reverse=True)
    assert approaches[0] > approaches[-1]


@pytest.mark.parametrize("twb,th,lg,ntu", [
    (24.0, 40.0, 1.0, 1.2),
    (28.0, 40.0, 1.0, 1.2),
    (30.0, 42.0, 1.3, 0.8),
    (20.0, 35.0, 0.9, 2.5),
    (33.0, 45.0, 1.5, 3.0),
    (28.0, 40.0, 1.0, 100.0),   # 极强填料，出水贴着湿球
    (28.0, 40.0, 0.3, 0.2),     # 极弱填料
])
def test_outlet_never_below_wet_bulb_physical_floor(twb, th, lg, ntu):
    """出口水温恒满足 湿球 <= t_cold < 进水；抬高湿球，下限跟着抬高。"""
    r = solve_outlet(t_wet_bulb=twb, t_hot=th, l_to_g=lg, fill_ntu=ntu)
    assert r.t_cold >= twb
    assert r.approach >= 0.0
    assert r.t_cold < th


def test_wet_bulb_raise_lifts_the_floor():
    """抬高进塔湿球，同一填料能力下出口水温整体抬高。"""
    t_cold = [
        solve_outlet(t_wet_bulb=w, t_hot=T_HOT, l_to_g=L_TO_G, fill_ntu=FILL_NTU).t_cold
        for w in (22.0, 25.0, 28.0, 31.0)
    ]
    assert t_cold == sorted(t_cold)
    assert t_cold[0] < t_cold[-1]
    # 每一种湿球下，出水都在 (湿球, 进水) 之间
    for w, tc in zip((22.0, 25.0, 28.0, 31.0), t_cold):
        assert w < tc < T_HOT


def test_baseline_counterflow_case_regression():
    """预置逆流工况手算核对基准（twb=28, 进水=40, L/G=1, 填料 NTU=1.2）。"""
    r = solve_outlet(t_wet_bulb=T_WB, t_hot=T_HOT, l_to_g=L_TO_G, fill_ntu=FILL_NTU)
    # 出水落在进塔湿球与进水之间
    assert T_WB < r.t_cold < T_HOT
    # 钉住回归值（容差 0.02 ℃；内核数值本身 1e-6 内一致）
    assert r.t_cold == pytest.approx(31.893623, abs=0.02)
    assert r.approach == pytest.approx(3.893623, abs=0.02)
    # 正算所需 NTU 必须与填料能力闭合
    assert r.required_ntu == pytest.approx(FILL_NTU, rel=1e-6)
    # 能量衡算：h_out = h_in + c_pw*L/G*(t_h - t_c)
    assert r.h_air_out == pytest.approx(
        r.h_air_in + 4.186 * L_TO_G * (T_HOT - r.t_cold), rel=1e-12
    )


def test_baseline_forward_merkel_number_handcheck():
    """正算基准：出水 32℃ 时所需 NTU≈1.159（Simpson 50 段起即收敛）。"""
    m = merkel_number(t_wet_bulb=T_WB, t_hot=T_HOT, t_cold=32.0, l_to_g=L_TO_G)
    assert m.ntu == pytest.approx(1.159224, abs=1e-3)
    m_fine = merkel_number(t_wet_bulb=T_WB, t_hot=T_HOT, t_cold=32.0,
                           l_to_g=L_TO_G, n_steps=800)
    assert m.ntu == pytest.approx(m_fine.ntu, rel=1e-6)


def test_saturated_enthalpy_matches_steam_table():
    """饱和蒸汽压/焓抽查（与水蒸气表对照）。"""
    assert saturation_pressure(0.0) == pytest.approx(611.2, rel=2e-3)
    assert saturation_pressure(40.0) == pytest.approx(7384.0, rel=2e-3)
    assert saturated_enthalpy(0.0) == pytest.approx(9.4, abs=0.2)
    assert saturated_enthalpy(40.0) == pytest.approx(166.1, abs=0.5)
