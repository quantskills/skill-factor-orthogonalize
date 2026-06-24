---
name: factor-orthogonalize
description: Use when an agent needs to neutralize or orthogonalize a quantitative factor
  against industry, size, style exposures, or an existing factor library before evaluating,
  combining, or accepting the signal.
quantSkills:
  project_type: skill
  category: factor
  tags:
  - factor-orthogonalization
  - neutralization
  - style-exposure
  - residual-factor
  - factor-correlation
  - daily-cross-sectional-regression
  - industry-neutral
  - size-neutral
  - pandadata
  platforms:
  - claude-code
  - codex
  - openclaw
  - cursor
  status: stable
  validation_level: production
  maintainer_type: community
  summary_zh: 逐日截面 OLS 正交化：剥离行业(L1 one-hot) + 市值(log_dollar_vol) + 风格(beta/volatility) + 旧因子暴露，输出残差因子与暴露清零诊断报告。已对接 Pandadata 获取行业分类(sector_code_name)和风格控制变量。
  summary_en: Daily cross-sectional OLS orthogonalization against industry one-hot dummies, size (log dollar volume), style (beta, volatility), and legacy factor exposures. Outputs residual signal with exposure-zeroing diagnostics. Integrated with Pandadata for sector classification and style controls.
  license: GPL-3.0
  repository: https://github.com/quantskills/skill-factor-orthogonalize
---

# Factor Orthogonalize

> 给定一个截面信号 `[date × symbol]`，把可解释的行业 / 市值 / 风格 / 旧因子暴露剥离掉，输出**残差因子**和正交前后诊断报告。

## 核心规则

1. **先定义要剥离什么**：行业、市值、风格、已有因子库不能混在一句“正交化”里含糊带过。
2. **逐日截面回归**：每个交易日单独在可交易股票池内做回归，不做 pooled 回归。
3. **残差才是新因子**：输出 `residual_signal[date × symbol]`，并重新做截面标准化。
4. **不能向收益正交**：严禁把 forward return、label、未来收益、test 段统计量放进控制变量。
5. **保真度必须报告**：正交后 IC / Sharpe / turnover / coverage 变化必须和原始因子并排展示。
6. **项目已有 neutralize / orthogonalize 工具优先调用**：不要另写一个口径不一致的“近似版”。

## 工作流（标准 7 步）

```
1. 校验信号契约：shape、date/symbol、NaN、截面 std、覆盖率
2. 明确控制变量：industry / log_mktcap / beta / volatility / liquidity / existing factors
3. 对齐同一时点可得数据：T 日信号只能用 T 日已知暴露
4. 截面预处理：winsorize → z-score → mask 不可交易股票
5. 逐日回归：signal_t = X_t beta_t + residual_t
6. 残差标准化：对 residual_t 做 z-score，保留原始 mask
7. 输出正交诊断，并调用 factor-evaluate 重新评价残差因子
```

## 接口映射

| 本 skill 概念 | 你的项目对应 |
|---|---|
| 原始信号 | `[date × symbol]` 浮点 DataFrame |
| 控制变量 | 行业哑变量、风格暴露、已有因子矩阵 |
| 股票池 mask | 可交易 / 非停牌 / 非涨跌停 / universe |
| 残差因子 | 正交后的 `[date × symbol]` DataFrame |
| 因子评价 | 调 `factor-evaluate` 或项目内 `primary_score()` |

## 按需加载

| 何时读 | 文件 |
|---|---|
| 想看回归与残差实现 | `references/methods.md` |
| 输出报告格式 | `references/report-format.md` |
| 常见误区与危险信号 | `references/anti-patterns.md` |

## 依赖

> Agent 执行本 skill 前必须确保以下 Python 包可用。若缺失，自动安装后再继续。

| 包 | 用途 | 最低版本 |
|---|---|---|
| `numpy` | 矩阵运算、`np.linalg.lstsq` 逐日回归 | ≥1.24 |
| `pandas` | DataFrame 截面操作、groupby-apply | ≥2.0 |
| `scipy` | `spearmanr` — 计算 rank IC（pandas `corr(method="spearman")` 依赖 scipy） | ≥1.10 |
| `pyarrow` | 读写 `.parquet` 因子文件 | ≥10.0 |

一键安装：

```bash
pip install numpy pandas scipy pyarrow
```

Agent 应在首次执行时检测环境，若缺少上述包则用项目包管理器（pip / uv / conda）自动补装。

## 项目实现

- **`scripts/orthogonalize.py`**：独立可运行的批量正交化脚本
  ```bash
  # 默认路径
  python scripts/orthogonalize.py

  # 自定义路径
  python scripts/orthogonalize.py --factor-dir data/factors --output-dir data/factors_orthogonalized
  ```
  输入：`data/factors/F*.parquet`
  输出：
  - `data/factors_orthogonalized/F*_residual.parquet` — 残差因子
  - 控制台输出暴露清零诊断（log_dollar_vol / beta / volatility 暴露前后对比）

**关键设计决策**：
- 行业用 `get_stock_detail` 批量查询（50 只/批），用 `sector_code_name` L1 分类做 one-hot，drop_first 为 True
- 风格变量用 `winsorize_zscore(5×MAD)` 预处理，避免极端值扭曲回归
- 残差后重新 `winsorize_zscore` 标准化，确保截面均值为 0、标准差为 1
- 每日样本 <30 的日期自动跳过

## 管线连接

```
Pandadata(get_stock_detail) → 行业分类
Pandadata(get_stock_daily)  → OHLCV → log_dollar_vol / beta_60d / volatility_20d
data/factors/F*.parquet     → 原始因子信号
                                    ↓
                          orthogonalize_real.py
                          逐日 OLS 残差化
                                    ↓
                  data/factors_orthogonalized/F*_residual.parquet
                                    ↓
                          skill-factor-decay（衰减分析）
                          skill-factor-blend（因子合并）
```

## QA 检查清单

- [ ] 控制变量全部是 T 日已知信息？
- [ ] 行业、市值、风格、旧因子分别列明了吗？
- [ ] 是逐日截面回归，不是全样本 pooled 回归？
- [ ] 正交后重新 z-score，且没有改变 universe mask？
- [ ] 报告包含正交前后 IC / Sharpe / turnover / coverage 对比？
- [ ] 没有用 test 段结果调控制变量或筛因子？

## 跨工具适配

- Cursor → `agents/cursor-rule.mdc`
- 无原生 skill 机制 → `agents/portable-loader.md`

---

## 项目边界（量化研究合规声明）

> 按 QUANTSKILLS 社区规则 §8 声明。

- **数据来源**：本 skill 不附带任何市场数据；行业分类、市值、风格暴露、行情面板等由使用者自行准备，数据合法性与许可由使用者负责。
- **假设与参数**：默认使用逐日截面 OLS / WLS 残差化，控制变量在 T 日可得；这些是假设条件下的研究流程，不等同于真实交易。
- **已知限制**：正交化会降低信号强度，不能证明残差因子未来有效；控制变量缺失、行业分类变更、极端小样本截面会造成残差不稳定。
- **风险边界**：正交后评分、相关性和暴露诊断仅反映历史数据 + 假设条件下的统计表现，不代表未来表现。
- **用途定位**：仅供量化研究、教育与方法论参考。不构成任何形式的投资建议、交易信号或获利保证。
