"""非法输入在积分前拦截 + 可行区越界报不可行。"""

import pytest

from app.errors import InfeasibleError, ValidationError
from app.merkel import merkel_number
from app.solver import solve_outlet


@pytest.mark.parametrize("kwargs", [
    dict(t_wet_bulb=30.0, t_hot=28.0, t_cold=29.0, l_to_g=1.0),   # 湿球>进水
    dict(t_wet_bulb=28.0, t_hot=28.0, t_cold=28.0, l_to_g=1.0),   # 湿球=进水
    dict(t_wet_bulb=28.0, t_hot=40.0, t_cold=32.0, l_to_g=0.0),   # L/G=0
    dict(t_wet_bulb=28.0, t_hot=40.0, t_cold=32.0, l_to_g=-1.0),  # L/G 负
])
def test_merkel_rejects_invalid_inputs(kwargs):
    with pytest.raises(ValidationError) as exc:
        merkel_number(**kwargs)
    assert exc.value.code == "invalid_input"
    assert exc.value.reason


@pytest.mark.parametrize("kwargs", [
    dict(t_wet_bulb=28.0, t_hot=40.0, l_to_g=1.0, fill_ntu=0.0),
    dict(t_wet_bulb=28.0, t_hot=40.0, l_to_g=1.0, fill_ntu=-2.0),
])
def test_solver_rejects_nonpositive_capability(kwargs):
    with pytest.raises(ValidationError):
        solve_outlet(**kwargs)


def test_cold_outlet_outside_range_rejected():
    # 出水等于湿球 / 高于进水 / 低于湿球
    for tc in (28.0, 40.0, 27.0):
        with pytest.raises(ValidationError):
            merkel_number(t_wet_bulb=28.0, t_hot=40.0, t_cold=tc, l_to_g=1.0)


def test_pinch_inside_integration_reported_infeasible():
    """L/G 过大时塔顶空气焓超过饱和焓：必须明确报不可行，不发散。"""
    with pytest.raises(InfeasibleError) as exc:
        merkel_number(t_wet_bulb=28.0, t_hot=40.0, t_cold=32.0, l_to_g=3.0)
    d = exc.value.detail
    assert d["h_sat"] <= d["h_air"]
    assert d["pinch_temperature"] > 0


def test_outlet_too_close_to_wetbulb_is_infeasible():
    """出水几乎贴着湿球：底部驱动力消失，按不可行报出。"""
    with pytest.raises((InfeasibleError, ValidationError)):
        merkel_number(t_wet_bulb=28.0, t_hot=40.0,
                      t_cold=28.0 + 1e-7, l_to_g=2.0)
