# 逆流填料冷却塔 Merkel 焓差法核算服务

常驻 HTTP 服务（FastAPI），用 **Merkel 焓差法**评估机械通风逆流塔填料的
散热能力。只有接口，没有页面；不涉及水务工单与补水台账。

## 热工模型

沿水温自出口冷水 `t_c` 向入口热水 `t_h` 离散推进（逆流、自下而上）：

```
                 NTU = ∫[t_c → t_h]  c_pw · (L/G) / (h_s(t) − h_a(t))  dt
```

* **驱动力是焓差** `h_s(t) − h_a(t)`（kJ/kg 干空气），不是温差——
  这是热质耦合传递，不使用对数平均温差；
* `h_s(t)` 取当前**水温**对应的饱和湿空气焓（ASHRAE 2017 饱和蒸汽压公式，
  Lewis 因子取 1，湿球等焓进风）；
* `h_a(t)` 由微元能量衡算**逐段更新**，空气焓随填料高度真实变化：
  `h_a(t) = h_a1 + c_pw·(L/G)·(t − t_c)`；
  另有 `update_air=false` 对照模式，用于验证空气侧衡算的作用；
* 数值积分用 SciPy 的复合 Simpson（`scipy.integrate.simpson`），
  反求出口水温用 `scipy.optimize.brentq`；
* 逆流边界：`t_wb < t_c < t_h`。出水最低只能逼近进塔湿球，不可能低于它。

### 两类计算

1. **正算**：给定湿球、进水、出水、水气比 → 积分求填料**需要的 NTU**；
2. **反求**：给定湿球、进水、水气比、填料能力（NTU，或 `H × ka/L_d`）
   → 求实际出口水温、逼近度（`t_c − t_wb`）、冷却幅度、空气侧出口焓。

## 文件结构（按热工环节拆分）

| 文件 | 职责 |
| --- | --- |
| `app/psychrometrics.py` | 水温对应的饱和湿空气焓（饱和蒸汽压、含湿量、焓） |
| `app/air_balance.py` | 空气焓随填料高度逐段更新的能量衡算（与积分分开） |
| `app/merkel.py` | Merkel 焓差沿水温的数值积分 |
| `app/solver.py` | 给定填料能力收敛求解出口水温与逼近度 |
| `app/validation.py` | 非法输入在积分前拦截（带原因） |
| `app/profiles.py` | 命名工况档的运行期内存存取（带锁，不跨重启） |
| `app/errors.py` | 错误类型：非法输入 / 工况不可行 |
| `app/schemas.py` | HTTP 请求/响应契约 |
| `app/main.py` | 接口层：只做请求收发与结果编排 |

焓差积分（`merkel.py`）与空气衡算（`air_balance.py`）是两份独立文件；
所有沿水温推进的中间量都是各次调用的局部量，两套工况档并发求解互不污染。

## 一键构建运行（Python 3.12）

```bash
docker build -t cooling-tower-merkel .
docker run --rm -p 8000:8000 cooling-tower-merkel
# 容器一起来接口即可应答：
curl http://localhost:8000/health
```

本地开发：

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --port 8000
pytest
```

## 接口

| 方法/路径 | 说明 |
| --- | --- |
| `GET /health` | 存活检查 |
| `POST /merkel/required-ntu` | 正算所需传质单元数（`update_air` 可对照） |
| `POST /merkel/solve` | 给定填料能力反求出口水温/逼近度/空气出口焓 |
| `POST /profiles` | 建立命名工况档 |
| `GET /profiles`、`GET /profiles/{name}` | 列出/读取工况档 |
| `DELETE /profiles/{name}` | 删除工况档 |
| `POST /profiles/{name}/solve` | 按工况档反求（body 可临时覆盖参数，不写回档） |

### 算例（手算核对基准）

`t_wb=28 ℃，t_h=40 ℃，L/G=1.0，填料 NTU=1.2`：

```bash
curl -s -X POST localhost:8000/merkel/solve \
  -H 'Content-Type: application/json' \
  -d '{"t_wet_bulb":28,"t_hot":40,"l_to_g":1,"fill_ntu":1.2}'
# t_cold ≈ 31.89 ℃（落在 28 与 40 之间），逼近度 ≈ 3.89 ℃，
# h_air_in ≈ 89.74，h_air_out ≈ 123.67 kJ/kg 干空气
```

出水 32 ℃ 时正算所需 NTU ≈ **1.159**（Simpson 50 段起即收敛到该值）。

## 错误处理（均在积分前/积分中挡下，HTTP 422）

* 进塔湿球 ≥ 进水温度：无有效冷却驱动力；
* 水气比不为正；填料高度 / 传质能力（NTU 或 H·ka/L_d）不为正；
* 积分中某水温处 `h_s ≤ h_a`：工况越过可行区（pinch/驱动力反转），
  返回 `infeasible_operating_condition` 并给出 pinch 位置与两侧焓值，
  不带符号硬积出乱值。

错误响应统一形如：

```json
{"error": {"code": "invalid_input", "reason": "……中文原因……", "detail": {}}}
```

## 钉板物理关系（测试逐条把关）

* 同填料能力下增大 L/G → 冷却幅度下降、出口水温升高；
* 单独增强填料传质能力 → 出口水温下降、逼近度变小；
* 抬高进塔湿球 → 出口水温下限抬高，恒有 `t_c ≥ t_wb`；
* 空气焓更新 vs 固定：NTU ≈ 1.159 vs 0.814（同出水 32 ℃ 算例），
  差异显著，证明空气侧衡算起作用。
