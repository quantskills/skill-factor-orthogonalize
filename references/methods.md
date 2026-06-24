# 因子中性化 / 正交化方法

## 概念区分

| 名称 | 目标 | 常见控制变量 |
|---|---|---|
| 行业中性化 | 去掉行业配置影响 | industry one-hot |
| 市值中性化 | 去掉大/小盘暴露 | `log_mktcap` |
| 风格中性化 | 去掉常见风格风险 | beta、volatility、liquidity、momentum |
| 因子库正交化 | 去掉与旧因子的重复信息 | existing factor matrix |

## 推荐实现

```python
import numpy as np
import pandas as pd


def winsorize_zscore(x: pd.Series, n_mad: float = 5.0) -> pd.Series:
    """逐日截面稳健标准化。输入是一日所有股票的值。"""
    med = x.median()
    mad = (x - med).abs().median()
    if not np.isfinite(mad) or mad == 0:
        clipped = x.copy()
    else:
        lo, hi = med - n_mad * 1.4826 * mad, med + n_mad * 1.4826 * mad
        clipped = x.clip(lo, hi)
    std = clipped.std()
    if not np.isfinite(std) or std == 0:
        return clipped * np.nan
    return (clipped - clipped.mean()) / std


def residualize_one_day(y: pd.Series, x: pd.DataFrame,
                        weight: pd.Series | None = None) -> pd.Series:
    """y 是单日因子，x 是同日控制变量；返回同 index 的残差。"""
    data = pd.concat([y.rename("y"), x], axis=1).dropna()
    if len(data) < max(30, x.shape[1] * 3):
        return pd.Series(np.nan, index=y.index)

    yy = data["y"].to_numpy()
    xx = data.drop(columns="y").to_numpy()
    xx = np.column_stack([np.ones(len(xx)), xx])

    if weight is not None:
        ww = weight.reindex(data.index).fillna(1.0).to_numpy()
        sw = np.sqrt(np.maximum(ww, 0))
        beta = np.linalg.lstsq(xx * sw[:, None], yy * sw, rcond=None)[0]
    else:
        beta = np.linalg.lstsq(xx, yy, rcond=None)[0]

    resid = yy - xx @ beta
    out = pd.Series(np.nan, index=y.index)
    out.loc[data.index] = resid
    return out
```

## 控制变量构造

### 行业哑变量

行业分类必须是 T 日已知分类。行业重分类时，不要用未来版本回填历史。

```python
industry_x = pd.get_dummies(industry_t, prefix="ind", dtype=float)
industry_x = industry_x.drop(columns=industry_x.columns[:1])  # 避免完全共线
```

### 风格变量

所有风格变量先逐日 winsorize + z-score，再进入回归：

```python
style_x = pd.concat([
    winsorize_zscore(log_mktcap_t).rename("log_mktcap"),
    winsorize_zscore(beta_t).rename("beta"),
    winsorize_zscore(volatility_t).rename("volatility"),
    winsorize_zscore(liquidity_t).rename("liquidity"),
], axis=1)
```

### 旧因子库

旧因子矩阵进入回归前必须同 horizon、同 label kind、同 universe。不要把尚未上线或只在 test 段表现好的候选因子当作控制变量。

## 诊断指标

| 指标 | 计算 | 解读 |
|---|---|---|
| exposure_before/after | signal 与控制变量逐日相关均值 | after 应接近 0 |
| corr_to_old_factors | 与旧因子的 rank corr | 大于 0.6 说明重复度高 |
| ic_retention | `rank_ic_after / rank_ic_before` | 保留多少有效性 |
| coverage_change | 有效股票数变化 | 不应明显下降 |
| turnover_change | 残差因子换手变化 | 正交后常会上升 |

## 接受标准

正交后不是分数越高越好，而是“更独立且仍有收益”：

- 行业 / 市值 / 风格暴露显著下降
- 与旧因子最大相关性低于 0.6，严格库可用 0.4
- rank IC 保留率优先大于 50%
- Sharpe / MDD 没有明显恶化
- turnover 没有因残差噪声显著爆炸
