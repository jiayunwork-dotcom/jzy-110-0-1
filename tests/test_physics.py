"""热工关系与基准算例的单元测试。"""
import pytest

from app.air_balance import EnergyBalanceAirPath, FixedAirPath
from app.merkel import InfeasibleOperatingPoint, integrate_merkel_ntu
from app.psychrometrics import saturation_air_enthalpy_kj_per_kg
from app.solver import solve_counterflow
from app.validation import (
    InvalidOperatingInput,
    validate_fill_capability,
    validate_inlet_conditions,
    validate_outlet_temperature,
    validate_water_air_ratio,
)

# 预置逆流基准工况：进塔湿球 20 °C，进水 35 °C，水气比 1.0，填料 KaV/L = 1.5
BENCH = dict(twb_c=20.0, t_inlet_c=35.0, water_air_ratio=1.0, fill_ntu=1.5)
BENCH_T_OUTLET = 25.804  # 手算核对基准值（由本实现积分核得并钉入回归）
BENCH_H_INLET = 57.4135  # 进塔空气焓 = 饱和焓(20 °C)，kJ/kg 干空气


def test_higher_water_air_ratio_raises_outlet_temp():
    """同样的填料能力下增大水气比，冷却幅度下降、出口水温升高。"""
    low = solve_counterflow(**{**BENCH, "water_air_ratio": 0.8})
    high = solve_counterflow(**{**BENCH, "water_air_ratio": 1.2})
    assert high.t_outlet_c > low.t_outlet_c
    assert high.cooling_range_c < low.cooling_range_c


def test_stronger_fill_lowers_outlet_temp_and_approach():
    """单独增强填料传质能力，出口水温下降、逼近度变小。"""
    weak = solve_counterflow(**{**BENCH, "fill_ntu": 1.0})
    strong = solve_counterflow(**{**BENCH, "fill_ntu": 2.5})
    assert strong.t_outlet_c < weak.t_outlet_c
    assert strong.approach_c < weak.approach_c


def test_outlet_temp_never_below_wet_bulb():
    """物理下限：出口水温始终高于进塔湿球。"""
    for ratio in (0.5, 0.8, 1.0, 1.5, 2.0):
        for ntu in (0.5, 1.0, 1.5, 3.0, 5.0):
            sol = solve_counterflow(
                twb_c=20.0, t_inlet_c=35.0, water_air_ratio=ratio, fill_ntu=ntu
            )
            assert sol.t_outlet_c > 20.0
            assert sol.approach_c > 0.0


def test_higher_wet_bulb_raises_outlet_floor():
    """抬高进塔湿球，出口水温下限跟着抬高。"""
    cool = solve_counterflow(**{**BENCH, "twb_c": 15.0})
    warm = solve_counterflow(**{**BENCH, "twb_c": 25.0})
    assert warm.t_outlet_c > cool.t_outlet_c
    assert warm.t_outlet_c > 25.0


def test_air_enthalpy_update_changes_result():
    """空气焓逐段更新与固定不更新必须给出能区分的结果。"""
    updated = solve_counterflow(**BENCH)
    fixed = solve_counterflow(**BENCH, air_enthalpy_mode="fixed")
    assert abs(fixed.t_outlet_c - updated.t_outlet_c) > 0.1
    # 固定进塔焓高估驱动力，同一填料能力下算出的出口水温偏低
    assert fixed.t_outlet_c < updated.t_outlet_c


def test_fixed_air_path_underestimates_ntu():
    """积分层面同样可区分：固定空气焓高估驱动力、低估所需 NTU。"""
    h_inlet = float(saturation_air_enthalpy_kj_per_kg(20.0))
    updated = integrate_merkel_ntu(
        26.0, 35.0, EnergyBalanceAirPath(h_inlet, 1.0, 26.0)
    )
    fixed = integrate_merkel_ntu(26.0, 35.0, FixedAirPath(h_inlet))
    assert fixed.ntu < updated.ntu
    assert abs(fixed.ntu - updated.ntu) / updated.ntu > 0.05


def test_benchmark_counterflow_case():
    """预置逆流算例：出口水温落在湿球与进水之间，钉入回归。"""
    sol = solve_counterflow(**BENCH)
    assert 20.0 < sol.t_outlet_c < 35.0
    assert sol.t_outlet_c == pytest.approx(BENCH_T_OUTLET, abs=0.01)
    assert sol.approach_c == pytest.approx(BENCH_T_OUTLET - 20.0, abs=0.01)
    assert sol.cooling_range_c == pytest.approx(35.0 - BENCH_T_OUTLET, abs=0.01)
    assert sol.h_air_inlet_kj_per_kg == pytest.approx(BENCH_H_INLET, abs=0.01)
    # 能量衡算闭合：出塔空气焓 = 进塔焓 + (L/G)·c_pw·冷却幅
    assert sol.h_air_exit_kj_per_kg - sol.h_air_inlet_kj_per_kg == pytest.approx(
        1.0 * 4.186 * sol.cooling_range_c, rel=1e-9
    )
    # 积分核得的 NTU 回到填料能力
    assert sol.ntu == pytest.approx(1.5, rel=1e-6)


def test_forward_inverse_consistency():
    """反算出的出口水温再正算，应回到原填料能力。"""
    sol = solve_counterflow(**BENCH)
    path = EnergyBalanceAirPath(
        sol.h_air_inlet_kj_per_kg, BENCH["water_air_ratio"], sol.t_outlet_c
    )
    check = integrate_merkel_ntu(sol.t_outlet_c, BENCH["t_inlet_c"], path)
    assert check.ntu == pytest.approx(BENCH["fill_ntu"], rel=1e-6)


def test_infeasible_when_driving_force_vanishes():
    """积分途中饱和焓不高于空气焓（操作线穿越饱和曲线），明确报不可行。"""
    h_inlet = float(saturation_air_enthalpy_kj_per_kg(20.0))
    # 水气比 1.5、出口水温压到 22 °C：空气操作线斜率过大，中段穿越饱和曲线
    path = EnergyBalanceAirPath(h_inlet, 1.5, 22.0)
    with pytest.raises(InfeasibleOperatingPoint, match="可行区"):
        integrate_merkel_ntu(22.0, 35.0, path)


def test_invalid_inputs_rejected_before_integration():
    with pytest.raises(InvalidOperatingInput, match="冷却驱动力"):
        validate_inlet_conditions(35.0, 35.0)
    with pytest.raises(InvalidOperatingInput, match="冷却驱动力"):
        validate_inlet_conditions(36.0, 35.0)
    with pytest.raises(InvalidOperatingInput, match="水气比"):
        validate_water_air_ratio(0.0)
    with pytest.raises(InvalidOperatingInput, match="水气比"):
        validate_water_air_ratio(-1.0)
    with pytest.raises(InvalidOperatingInput, match="传质能力"):
        validate_fill_capability(0.0)
    with pytest.raises(InvalidOperatingInput, match="湿球"):
        validate_outlet_temperature(20.0, 35.0, 19.9)
    with pytest.raises(InvalidOperatingInput, match="低于进水"):
        validate_outlet_temperature(20.0, 35.0, 35.5)
