"""参数校验：非法输入在积分前挡住，并说明原因。"""


class InvalidOperatingInput(ValueError):
    """携带原因的非法工况输入。"""


def validate_inlet_conditions(twb_c: float, t_inlet_c: float) -> None:
    """进塔湿球必须低于进水温度，否则没有有效的冷却驱动力。"""
    if not twb_c < t_inlet_c:
        raise InvalidOperatingInput(
            f"进塔湿球温度 {twb_c} °C 高于或等于进水温度 {t_inlet_c} °C，"
            "没有有效的冷却驱动力"
        )


def validate_water_air_ratio(water_air_ratio: float) -> None:
    """水气比必须为正。"""
    if not water_air_ratio > 0.0:
        raise InvalidOperatingInput(
            f"水气比必须为正，当前为 {water_air_ratio}"
        )


def validate_fill_capability(fill_ntu: float) -> None:
    """填料高度/传质能力必须为正。"""
    if not fill_ntu > 0.0:
        raise InvalidOperatingInput(
            f"填料传质能力（KaV/L）必须为正，当前为 {fill_ntu}"
        )


def validate_outlet_temperature(
    twb_c: float, t_inlet_c: float, t_outlet_c: float
) -> None:
    """逆流工况下出口水温应低于进水、高于进塔湿球。"""
    if not t_outlet_c > twb_c:
        raise InvalidOperatingInput(
            f"出口水温 {t_outlet_c} °C 必须高于进塔湿球 {twb_c} °C，"
            "出水最低只能逼近湿球，不可能低于它"
        )
    if not t_outlet_c < t_inlet_c:
        raise InvalidOperatingInput(
            f"出口水温 {t_outlet_c} °C 必须低于进水温度 {t_inlet_c} °C"
        )
