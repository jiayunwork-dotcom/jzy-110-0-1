"""冷却塔 Merkel 焓差法核算服务。

模块按热工环节拆分：

* ``psychrometrics`` —— 与水温对应的饱和湿空气焓取值
* ``air_balance``    —— 空气焓随填料高度逐段更新的能量衡算
* ``merkel``         —— Merkel 焓差沿水温的数值积分（所需传质单元数）
* ``solver``         —— 给定填料能力反向求解出口水温与逼近度
* ``validation``     —— 非法输入在积分前拦截
* ``profiles``       —— 运行期工况档存取
"""

__all__ = [
    "psychrometrics",
    "air_balance",
    "merkel",
    "solver",
    "validation",
    "profiles",
]
