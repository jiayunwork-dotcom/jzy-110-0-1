# 机械通风冷却塔 Merkel 核算服务

用 Merkel 焓差法评估逆流填料的散热能力。纯 HTTP 接口，无页面，只做冷却塔的热质传递核算。

## 模型

传质单元数（冷却数）沿水温自出口向进口积分：

```
NTU = ∫_{T_out}^{T_in} c_pw·dT / (h_sat(T) − h_air(T))
```

- 驱动力：水温 T 对应的**饱和湿空气焓**减去当前高度的**空气焓**（路易斯因子取 1）。
- 空气焓**随填料高度逐段更新**，不固定：逆流塔能量衡算
  `h_air(T) = h_air,in + (L/G)·c_pw·(T − T_out)`，
  在 T_out 端（填料底部）等于进塔空气焓，T_in 端（顶部）等于出塔空气焓。
- 进塔空气焓取进塔湿球温度对应的饱和焓。
- 边界对应关系：逆流工况下出口水温低于进水、高于进塔湿球；出水最低只能逼近湿球。
- 反算出口水温时，在 (湿球, 进水) 内用 brentq 收敛：逼近可行区边界所需 NTU 发散，
  冷却幅趋于零时 NTU 趋于零，可行区内 NTU 随出口水温严格单调下降，根唯一。
  积分途中若某水温处饱和焓不高于空气焓（操作线穿越饱和曲线），按不可行明确报错。

## 目录结构（按环节拆分）

| 文件 | 环节 |
|---|---|
| `app/psychrometrics.py` | 与水温对应的饱和湿空气焓取值 |
| `app/merkel.py` | Merkel 焓差沿水温的数值积分 |
| `app/air_balance.py` | 空气焓随填料高度逐段更新的能量衡算（另含诊断用固定模式） |
| `app/solver.py` | 出口水温与逼近度的收敛求解 |
| `app/profiles.py` | 工况档存取（进程内、线程安全、不跨重启保留） |
| `app/validation.py` | 参数校验 |
| `app/main.py` / `app/schemas.py` | 接口层：只做请求收发与结果编排 |

## 接口

- `POST /merkel/ntu` — 正算：给 `twb_c / t_inlet_c / t_outlet_c / water_air_ratio`，求所需传质单元数。
- `POST /merkel/solve` — 反算：给 `twb_c / t_inlet_c / water_air_ratio / fill_ntu`，求出口水温、逼近度、冷却幅、出塔空气焓。
- `POST /profiles`、`GET /profiles`、`GET/DELETE /profiles/{name}` — 工况档登记与查询。
- `POST /profiles/{name}/solve` — 按工况档求解；多档并行求解互不影响。
- `GET /health`。

两个计算接口都接受可选的 `air_enthalpy_mode`：`energy_balance`（默认，逐段更新空气焓）
或 `fixed`（诊断对照：固定进塔焓，可用来验证空气侧衡算确实起作用）。

非法输入在积分前返回 422 并说明原因：湿球高于或等于进水（无有效冷却驱动力）、
水气比不为正、填料传质能力不为正、出口水温越界；积分途中越过可行区返回
`infeasible_operating_point`。

### 示例

```bash
curl -X POST localhost:8000/merkel/solve -H 'Content-Type: application/json' -d '{
  "twb_c": 20.0, "t_inlet_c": 35.0, "water_air_ratio": 1.0, "fill_ntu": 1.5
}'
# → t_outlet_c ≈ 25.804 °C，approach_c ≈ 5.804 °C，h_air_exit ≈ 95.91 kJ/kg
```

## 运行

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Docker

```bash
docker build -t cooling-tower-merkel .
docker run -p 8000:8000 cooling-tower-merkel
```

容器起来后 Merkel 核算接口即在 `:8000` 对外应答（Python 3.12 / FastAPI）。

## 测试

```bash
pip install -r requirements-dev.txt
pytest
```

测试钉住的热工关系：水气比增大 → 出口水温升高；填料传质能力增强 → 出口水温下降、
逼近度变小；出口水温始终不低于进塔湿球；抬高湿球 → 出水下限跟着抬高；空气焓逐段
更新与固定不更新给出可区分结果；预置逆流基准算例（湿球 20 °C / 进水 35 °C /
水气比 1.0 / KaV/L=1.5 → 出口水温 ≈ 25.804 °C）钉入回归；非法输入与不可行工况
带原因打回；双工况档并行求解隔离。
