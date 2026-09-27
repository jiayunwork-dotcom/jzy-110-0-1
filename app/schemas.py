"""HTTP 接口的请求/响应数据契约（Pydantic v2）。

字段只做形状与类型约束；"湿球>=进水""水气比为正"等业务规则
统一由 :mod:`app.validation` 在积分前拦截，返回带中文原因的错误响应。
"""

from __future__ import annotations

from typing import Optional, Literal

from pydantic import BaseModel, Field


# ---------- 正算：求所需传质单元数 ----------

class RequiredNtuRequest(BaseModel):
    t_wet_bulb: float = Field(..., description="进塔空气湿球温度 ℃")
    t_hot: float = Field(..., description="进水温度 ℃")
    t_cold: float = Field(..., description="出口（冷）水温 ℃")
    l_to_g: float = Field(..., description="水与空气质量流量之比 L/G", gt=0)
    pressure: float = Field(101325.0, description="大气压 Pa")
    n_steps: int = Field(200, description="沿水温离散段数（偶数，自动取整）", ge=4)
    update_air: bool = Field(
        True,
        description="空气焓是否随填料高度逐段更新；false 为固定进塔焓的对照做法",
    )
    keep_nodes: bool = Field(False, description="是否返回沿水温的逐段中间量")


class NodesPayload(BaseModel):
    temps: list[float]
    h_sat: list[float]
    h_air: list[float]
    driving_force: list[float]


class RequiredNtuResponse(BaseModel):
    ntu: float = Field(..., description="所需传质单元数（水流量基准）")
    t_cold: float
    t_hot: float
    l_to_g: float
    h_air_in: float = Field(..., description="进塔空气焓 kJ/kg 干空气")
    h_air_out: float = Field(..., description="出塔空气焓（能量衡算）kJ/kg 干空气")
    update_air: bool
    min_driving_force: float
    pinch_temperature: float
    nodes: Optional[NodesPayload] = None


# ---------- 反求：给定填料能力求出口水温 ----------

class SolveOutletRequest(BaseModel):
    t_wet_bulb: float = Field(..., description="进塔空气湿球温度 ℃")
    t_hot: float = Field(..., description="进水温度 ℃")
    l_to_g: float = Field(..., description="水与空气质量流量之比 L/G", gt=0)
    fill_ntu: Optional[float] = Field(None, description="填料传质单元数")
    fill_height: Optional[float] = Field(None, description="填料高度 m")
    ka_ld: Optional[float] = Field(None, description="体积传质系数 ka/L_d 1/m")
    pressure: float = Field(101325.0, description="大气压 Pa")
    n_steps: int = Field(200, ge=4)


class SolveOutletResponse(BaseModel):
    t_cold: float = Field(..., description="实际出口（冷）水温 ℃")
    approach: float = Field(..., description="逼近度 t_c - t_wb ℃")
    range: float = Field(..., description="冷却幅度 t_h - t_c ℃")
    t_hot: float
    t_wet_bulb: float
    fill_ntu: float = Field(..., description="生效的填料传质单元数")
    required_ntu: float
    h_air_in: float
    h_air_out: float = Field(..., description="空气侧出口焓 kJ/kg 干空气")
    l_to_g: float
    iterations: int


# ---------- 工况档 ----------

class ProfileRequest(BaseModel):
    name: str = Field(..., description="工况档名称")
    t_wet_bulb: float
    t_hot: float
    l_to_g: float = Field(..., gt=0)
    fill_ntu: Optional[float] = None
    fill_height: Optional[float] = None
    ka_ld: Optional[float] = None
    pressure: float = 101325.0
    n_steps: int = Field(200, ge=4)


class ProfileResponse(BaseModel):
    name: str
    t_wet_bulb: float
    t_hot: float
    l_to_g: float
    fill_ntu: Optional[float]
    fill_height: Optional[float]
    ka_ld: Optional[float]
    fill_ntu_effective: Optional[float]
    pressure: float
    n_steps: int


class ProfileSolveOverride(BaseModel):
    """用工况档求解时允许临时覆盖的参数。"""

    t_wet_bulb: Optional[float] = None
    t_hot: Optional[float] = None
    l_to_g: Optional[float] = None
    fill_ntu: Optional[float] = None
    fill_height: Optional[float] = None
    ka_ld: Optional[float] = None
    pressure: Optional[float] = None
    n_steps: Optional[int] = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
