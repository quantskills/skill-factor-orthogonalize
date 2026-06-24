# skill-factor-orthogonalize

[简体中文](./README.md) | [English](./README.en.md)

逐日截面 OLS 正交化：剥离行业(L1 one-hot) + 市值(log_dollar_vol) + 风格(beta/volatility) + 旧因子暴露，输出残差因子与暴露清零诊断报告。

`role: skill` `output: residual factor + diag report` `paradigm: daily cross-sectional OLS`


---

`skill-factor-orthogonalize` 是 PandaAI Quant Skills 提供的**因子正交化 Skill**。给定一个截面因子信号 `[date × symbol]`，通过逐日 OLS 回归剥离行业、市值、风格和旧因子暴露，输出残差因子。

## 🎯 这个 Skill 解决什么问题

原始因子可能包含的是"行业偏好"而不是"选股能力"：

- 动量因子可能只是在买大市值股票（暴露 log_mktcap = 0.50）
- 反转因子可能只是在买高波动股票（暴露 volatility = 0.60）
- 价值因子可能在特定行业上有系统性偏向（行业暴露不均）

**这些暴露不剥离，因子评估和合并的结论都会失真。** 本 Skill 逐日截面回归，确保每个交易日独立剥离暴露，残差后重新 z-score 标准化。

## ⚡ 7 步工作流

```
1. 校验信号契约：shape、date/symbol、NaN、截面 std、覆盖率
2. 明确控制变量：industry / log_mktcap / beta / volatility / existing factors
3. 对齐同一时点可得数据：T 日信号只能用 T 日已知暴露
4. 截面预处理：MAD-based winsorize (5σ) → z-score → mask 不可交易股票
5. 逐日回归：signal_t = X_t β_t + residual_t（np.linalg.lstsq）
6. 残差标准化：对 residual_t 做 z-score，保留原始 mask
7. 输出正交诊断：暴露清零 + IC 保留率 + turnover + coverage
```

## 🗃️ 输入要求

- 因子信号：`[date, symbol, factor_value]` parquet 文件
- 行业分类：从 Pandadata `get_stock_detail` 批量拉取（sector_code_name, L1 分类）
- 风格控制：`log_dollar_vol`、`beta_60d`、`volatility_20d`（基于 OHLCV 日线自动计算）

## 📦 项目脚本

```bash
# 批量正交化 data/factors/ 下所有因子
python orthogonalize_real.py
```

输入：`data/factors/F*.parquet`
输出：
- `data/factors_orthogonalized/F*_residual.parquet` — 残差因子
- `data/orthogonalize_report.txt` — 暴露清零 + IC 保留率对比表

## 🔗 管线定位

```
因子评估 → 正交化(本Skill) → 衰减分析 → 因子合并
```

位于因子评估之后、衰减分析之前的质量把控节点。

## 📦 仓库内容

```
skill-factor-orthogonalize/
├── SKILL.md
├── README.md / README.en.md
├── references/
│   ├── methods.md
│   ├── report-format.md
│   └── anti-patterns.md
└── agents/
    ├── cursor-rule.mdc
    └── portable-loader.md
```

## 与其它 Skill 的关系

| Skill | 用途 |
|---|---|
| skill-factor-evaluate | 给原始或残差因子打分 |
| skill-factor-orthogonalize | 剥离风格 / 行业 / 旧因子暴露 |
| skill-factor-decay | 分析残差因子的 IC 衰减与半衰期 |
| skill-factor-blend | 把多个低相关残差因子合成复合 Alpha |

## 项目状态与边界

- **项目状态**：Community Project，未经官方审核 / 认证 / 背书
- **数据来源**：本仓库不附带任何市场数据或行业分类
- **核心假设**：逐日截面回归；控制变量在 T 日可得；残差每日标准化
- **风险边界**：残差因子表现只反映历史统计，不代表未来表现
- **用途**：仅供量化研究、教育与方法论参考，不构成投资建议

## 📜 License

GPL-3.0. Copyright (C) 2026 QuantSkills.
