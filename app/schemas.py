"""接口层请求/响应模型。"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .merkel import DEFAULT_SEGMENTS

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
Segments = Annotated[int, Field(ge=8, le=20000)]
AirEnthalpyMode = Literal["energy_balance", "fixed"]


class MerkelNtuRequest(BaseModel):
    """正算：给定出口水温，求填料需要的传质单元数。"""

    twb_c: FiniteFloat = Field(description="进塔空气湿球温度 °C")
    t_inlet_c: FiniteFloat = Field(description="进水温度 °C")
    t_outlet_c: FiniteFloat = Field(description="出口水温 °C")
    water_air_ratio: FiniteFloat = Field(description="水与空气质量流量之比 L/G")
    segments: Segments = DEFAULT_SEGMENTS
    air_enthalpy_mode: AirEnthalpyMode = Field(
        default="energy_balance",
        description="空气焓更新方式：energy_balance 逐段更新（正式），fixed 固定（诊断对照）",
    )


class MerkelNtuResponse(BaseModel):
    ntu: float = Field(description="所需传质单元数 KaV/L")
    min_driving_force_kj_per_kg: float
    h_air_inlet_kj_per_kg: float
    h_air_exit_kj_per_kg: float
    segments: int
    air_enthalpy_mode: str


class SolveRequest(BaseModel):
    """反算：给定填料传质能力，求出口水温、逼近度与出塔空气焓。"""

    twb_c: FiniteFloat = Field(description="进塔空气湿球温度 °C")
    t_inlet_c: FiniteFloat = Field(description="进水温度 °C")
    water_air_ratio: FiniteFloat = Field(description="水与空气质量流量之比 L/G")
    fill_ntu: FiniteFloat = Field(description="填料传质能力 KaV/L")
    segments: Segments = DEFAULT_SEGMENTS
    air_enthalpy_mode: AirEnthalpyMode = Field(
        default="energy_balance",
        description="空气焓更新方式：energy_balance 逐段更新（正式），fixed 固定（诊断对照）",
    )


class SolveResponse(BaseModel):
    t_outlet_c: float
    approach_c: float = Field(description="逼近度 = 出口水温 − 进塔湿球")
    cooling_range_c: float = Field(description="冷却幅 = 进水温度 − 出口水温")
    ntu: float = Field(description="积分核得的传质单元数（应等于填料能力）")
    h_air_inlet_kj_per_kg: float
    h_air_exit_kj_per_kg: float
    min_driving_force_kj_per_kg: float
    segments: int
    air_enthalpy_mode: str


class ProfileIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=64)]
    twb_c: FiniteFloat
    t_inlet_c: FiniteFloat
    water_air_ratio: FiniteFloat
    fill_ntu: FiniteFloat


class ProfileOut(ProfileIn):
    pass


class ProfileSolveResponse(SolveResponse):
    profile: str
