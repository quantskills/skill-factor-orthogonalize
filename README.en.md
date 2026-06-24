# skill-factor-orthogonalize

[简体中文](./README.md) | [English](./README.en.md)

Daily cross-sectional OLS orthogonalization against industry one-hot dummies, size (log dollar volume), style (beta, volatility), and legacy factor exposures. Outputs residual signal with exposure-zeroing diagnostics.

`role: skill` `output: residual factor + diag report` `paradigm: daily cross-sectional OLS`


---

`skill-factor-orthogonalize` is an **factor orthogonalization Skill** provided by PandaAI Quant Skills. Given a cross-sectional factor signal `[date × symbol]`, it strips out industry, size, style, and legacy factor exposures via daily OLS regression, producing a residual factor signal.

## 🎯 What This Skill Solves

A raw factor may reflect "industry preference" rather than "stock-picking ability":

- A momentum factor might just be buying large-cap stocks (log_mktcap exposure = 0.50)
- A reversal factor might just be buying high-volatility stocks (volatility exposure = 0.60)
- A value factor might have systematic industry bias

**Without stripping these exposures, factor evaluation and blending conclusions are distorted.** This Skill runs daily cross-sectional regressions, ensuring each trading day's exposures are independently removed, followed by re-z-scoring.

## ⚡ 7-Step Workflow

```
1. Validate signal contract: shape, date/symbol, NaN, cross-sectional std, coverage
2. Define controls: industry dummies + log_dollar_vol + beta_60d + volatility_20d
3. Align T-day known information only (no forward-looking)
4. Preprocess: MAD-based winsorize (5σ) → z-score → mask untradeable
5. Daily regression: signal_t = X_t β_t + residual_t (np.linalg.lstsq)
6. Residual re-standardization: z-score residuals, preserve mask
7. Output diagnostics: exposure zeroing + IC retention + turnover + coverage
```

## 🗃️ Input Requirements

- Factor signal: `[date, symbol, factor_value]` parquet files
- Industry classification: from Pandadata `get_stock_detail` batch query (sector_code_name, L1)
- Style controls: `log_dollar_vol`, `beta_60d`, `volatility_20d` (auto-computed from OHLCV)

## 📦 Project Script

```bash
# Batch orthogonalize all factors under data/factors/
python orthogonalize_real.py
```

Input: `data/factors/F*.parquet`
Output:
- `data/factors_orthogonalized/F*_residual.parquet` — residual factor signals
- `data/orthogonalize_report.txt` — exposure zeroing + IC retention comparison table

## 🔗 Pipeline Position

```
Factor Evaluation → Orthogonalize (this Skill) → Decay Analysis → Factor Blending
```

Quality gate between factor evaluation and decay analysis.

## 📜 License

GPL-3.0. Copyright (C) 2026 QuantSkills.
