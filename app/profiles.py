"""工况档存取一环——运行期间可靠存取，不跨重启保留。

工况档只保存"进气与填料的常用命名参数"。求解所需的中间焓值、水温
都是各次函数调用的局部量，从不进入这里，因此两套工况档同时求解时
中间状态彼此隔离、互不污染。访问用锁保护，可被并发 HTTP 请求可靠使用。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, asdict
from typing import Optional

from .errors import ValidationError


@dataclass(frozen=True)
class Profile:
    """命名工况档：进气与填料参数。"""

    name: str
    t_wet_bulb: float          # 进塔湿球温度 ℃
    t_hot: float               # 进水温度 ℃
    l_to_g: float              # 水气质量流量比 L/G
    fill_ntu: Optional[float] = None   # 填料传质单元数（直接给能力）
    fill_height: Optional[float] = None  # 填料高度 m
    ka_ld: Optional[float] = None       # 体积传质系数 1/m
    pressure: float = 101325.0  # 大气压 Pa
    n_steps: int = 200          # 焓差积分离散段数

    def effective_fill_ntu(self) -> Optional[float]:
        """生效的填料 NTU：优先直接值，否则 H * ka/L_d。"""
        if self.fill_ntu is not None:
            return self.fill_ntu
        if self.fill_height is not None and self.ka_ld is not None:
            return self.fill_height * self.ka_ld
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fill_ntu_effective"] = self.effective_fill_ntu()
        return d


class ProfileStore:
    """内存工况档表（进程级单例，带锁）。"""

    def __init__(self) -> None:
        self._profiles: dict[str, Profile] = {}
        self._lock = threading.Lock()

    def put(self, profile: Profile) -> Profile:
        if not profile.name or not profile.name.strip():
            raise ValidationError("工况档名称不能为空")
        with self._lock:
            self._profiles[profile.name] = profile
        return profile

    def get(self, name: str) -> Profile:
        with self._lock:
            if name not in self._profiles:
                raise ValidationError(f"工况档 '{name}' 不存在",
                                      detail={"name": name})
            return self._profiles[name]

    def delete(self, name: str) -> None:
        with self._lock:
            if name not in self._profiles:
                raise ValidationError(f"工况档 '{name}' 不存在",
                                      detail={"name": name})
            del self._profiles[name]

    def list(self) -> list[Profile]:
        with self._lock:
            return list(self._profiles.values())

    def reset(self) -> None:
        """清空（仅供测试）。"""
        with self._lock:
            self._profiles.clear()


# 进程内单例
store = ProfileStore()
