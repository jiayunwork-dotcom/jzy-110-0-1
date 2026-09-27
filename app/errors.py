"""领域错误类型——区分"非法输入"与"工况不可行"两类打回。"""

from __future__ import annotations


class CoolingTowerError(Exception):
    """核算服务领域错误基类。"""

    code = "cooling_tower_error"
    reason = "冷却塔核算错误"

    def __init__(self, reason: str | None = None, *, detail: dict | None = None):
        super().__init__(reason or self.reason)
        if reason is not None:
            self.reason = reason
        self.detail = detail or {}


class ValidationError(CoolingTowerError):
    """非法输入：在积分开始之前拦截。"""

    code = "invalid_input"
    reason = "输入参数不合法"


class InfeasibleError(CoolingTowerError):
    """工况越过可行区（如某处饱和焓不高于空气焓），积分不允许继续。"""

    code = "infeasible_operating_condition"
    reason = "工况越过可行区，无有效传质驱动力"
