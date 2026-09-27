"""参数校验一环——非法输入一律在焓差积分开始之前挡住并说明原因。

校验内容（与需求逐条对应）：

* 进塔湿球温度高于或等于进水温度 -> 没有有效的冷却驱动力；
* 水气比 L/G 必须为正；
* 填料高度 / 传质能力（NTU，或高度乘体积传质系数）必须为正；
* 出口水温必须落在进塔湿球与进水温度之间；
* 大气压、离散段数等数值合理性。
"""

from __future__ import annotations

from .errors import ValidationError

# 水温物理下限（本套焓公式取 0 ℃ 以上水侧状态）
MIN_TEMP_C = 0.0


def _require_positive(name: str, value: float, *, unit: str) -> None:
    if value is None:
        raise ValidationError(f"{name}不能为空")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValidationError(f"{name}必须是数值")
    if not value > 0:
        raise ValidationError(f"{name}必须为正（收到 {value:g} {unit}）",
                              detail={"field": name, "value": value})


def validate_common(
    *,
    twb: float,
    t_hot: float,
    l_to_g: float,
    pressure: float = 101325.0,
) -> None:
    """校验各接口共用的进塔空气 / 水侧 / 水气比参数。"""
    for name, value, unit in (
        ("进塔湿球温度", twb, "℃"),
        ("进水温度", t_hot, "℃"),
    ):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValidationError(f"{name}必须是数值")
        if not value >= MIN_TEMP_C:
            raise ValidationError(f"{name}不得低于 {MIN_TEMP_C:g} ℃（收到 {value:g} {unit}）",
                                  detail={"field": name, "value": value})

    if twb >= t_hot:
        raise ValidationError(
            "进塔湿球温度高于或等于进水温度，没有有效的冷却驱动力"
            f"（twb={twb:g} ℃，进水={t_hot:g} ℃）",
            detail={"field": "t_wet_bulb", "t_wet_bulb": twb, "t_hot": t_hot},
        )

    _require_positive("水气比 L/G", l_to_g, unit="kg/kg")
    _require_positive("大气压", pressure, unit="Pa")


def validate_required_ntu(*, t_cold: float, twb: float, t_hot: float,
                          n_steps: int = 200) -> None:
    """校验"正算所需传质单元数"的出口水温与离散段数。"""
    if not isinstance(t_cold, (int, float)) or isinstance(t_cold, bool):
        raise ValidationError("出口水温必须是数值")
    if not t_cold > twb:
        raise ValidationError(
            "出口水温应高于进塔湿球温度，否则逆流段无有效驱动力"
            f"（出水={t_cold:g} ℃，湿球={twb:g} ℃）",
            detail={"field": "t_cold", "t_cold": t_cold, "t_wet_bulb": twb},
        )
    if not t_cold < t_hot:
        raise ValidationError(
            "出口水温应低于进水温度"
            f"（出水={t_cold:g} ℃，进水={t_hot:g} ℃）",
            detail={"field": "t_cold", "t_cold": t_cold, "t_hot": t_hot},
        )
    if not isinstance(n_steps, int) or isinstance(n_steps, bool) or n_steps < 4:
        raise ValidationError("离散段数必须是不小于 4 的整数",
                              detail={"field": "n_steps", "value": n_steps})


def validate_fill_capability(
    *,
    fill_ntu: float | None = None,
    fill_height: float | None = None,
    ka_ld: float | None = None,
) -> None:
    """校验填料传质能力。

    支持两种等价给法（至少给一种）：

    * 直接给填料传质单元数 ``fill_ntu``；
    * 给填料高度 ``fill_height`` [m] 与体积传质系数 ``ka_ld`` [1/m]，
      能力为二者乘积 NTU = H * ka/L_d。
    """
    if fill_ntu is None and (fill_height is None or ka_ld is None):
        raise ValidationError(
            "填料传质能力必须提供：直接给 fill_ntu，或同时给 fill_height 与 ka_ld"
        )
    if fill_ntu is not None:
        _require_positive("填料传质单元数 NTU", fill_ntu, unit="-")
    if fill_height is not None:
        _require_positive("填料高度", fill_height, unit="m")
    if ka_ld is not None:
        _require_positive("体积传质系数 ka/L_d", ka_ld, unit="1/m")
