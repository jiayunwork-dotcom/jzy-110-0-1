"""工况档存取：进程内命名参数集。

把常用的进气与填料参数命名成工况档反复调用。运行期间可靠存取
（线程安全），不跨重启保留。工况档为不可变对象，求解器也不持有
跨调用状态，多套工况档同时求解时中间焓值与水温彼此隔离。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class OperatingProfile:
    """一套命名的逆流工况参数。"""

    name: str
    twb_c: float
    t_inlet_c: float
    water_air_ratio: float
    fill_ntu: float


class ProfileNotFound(KeyError):
    """工况档不存在。"""


class ProfileStore:
    """线程安全的进程内工况档仓库。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, OperatingProfile] = {}

    def put(self, profile: OperatingProfile) -> OperatingProfile:
        with self._lock:
            self._items[profile.name] = profile
        return profile

    def get(self, name: str) -> OperatingProfile:
        with self._lock:
            try:
                return self._items[name]
            except KeyError:
                raise ProfileNotFound(f"工况档不存在: {name!r}") from None

    def remove(self, name: str) -> None:
        with self._lock:
            try:
                del self._items[name]
            except KeyError:
                raise ProfileNotFound(f"工况档不存在: {name!r}") from None

    def list(self) -> list[OperatingProfile]:
        with self._lock:
            return list(self._items.values())
