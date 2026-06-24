#!/usr/bin/env python
"""
因子正交化 — 逐日截面 OLS 剥离行业 + 市值 + 风格暴露
用法: python scripts/orthogonalize.py [--factor-dir data/factors] [--output-dir data/factors_orthogonalized]
"""
import sys
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# Pandadata runtime 导入（相对于本脚本：../skill-pandata-api/scripts/）
_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _SCRIPT_DIR.parent.parent  # scripts/ → skill-*/ → skills/
_PANDADATA_SCRIPTS = _SKILLS_DIR / "skill-pandadata-api" / "scripts"
if _PANDADATA_SCRIPTS.is_dir():
    sys.path.insert(0, str(_PANDADATA_SCRIPTS))
try:
    from pandadata_runtime import init_pandadata  # noqa: E402
except ImportError:
    print("❌ 无法导入 pandadata_runtime。请确保 skill-pandadata-api 已安装在本 skills 目录中。")
    print(f"   预期路径: {_PANDADATA_SCRIPTS}")
    sys.exit(1)

WINSORIZE_NSIG = 5.0
MIN_SAMPLES = 30


def winsorize_zscore(x: pd.Series, n_mad: float = WINSORIZE_NSIG) -> pd.Series:
    med = x.median()
    mad = (x - med).abs().median()
    if not np.isfinite(mad) or mad == 0:
        clipped = x.copy()
    else:
        lo = med - n_mad * 1.4826 * mad
        hi = med + n_mad * 1.4826 * mad
        clipped = x.clip(lo, hi)
    std = clipped.std()
    if not np.isfinite(std) or std == 0:
        return pd.Series(np.nan, index=x.index)
    return (clipped - clipped.mean()) / std


def residualize_one_day(y: pd.Series, x: pd.DataFrame) -> pd.Series:
    data = pd.concat([y.rename("y"), x], axis=1).dropna()
    n_features = x.shape[1]
    if len(data) < max(MIN_SAMPLES, n_features * 3):
        return pd.Series(np.nan, index=y.index)
    yy = data["y"].to_numpy(dtype=float)
    xx = data.drop(columns="y").to_numpy(dtype=float)
    xx = np.column_stack([np.ones(len(xx)), xx])
    beta, residuals, rank, singular = np.linalg.lstsq(xx, yy, rcond=None)
    resid = yy - xx @ beta
    out = pd.Series(np.nan, index=y.index)
    out.loc[data.index] = resid
    return out


def daily_rank_ic(signal: pd.Series, fwd_ret: pd.Series) -> pd.Series:
    df = pd.DataFrame({"signal": signal, "fwd_ret": fwd_ret})
    results = {}
    for d, grp in df.groupby(level="date"):
        grp = grp.dropna()
        if len(grp) < 10:
            results[d] = np.nan
            continue
        ic, _ = spearmanr(grp["signal"], grp["fwd_ret"])
        results[d] = ic
    return pd.Series(results, name="rank_ic")


def daily_exposure(signal: pd.Series, control: pd.Series) -> pd.Series:
    df = pd.DataFrame({"signal": signal, "ctrl": control})
    results = {}
    for d, grp in df.groupby(level="date"):
        grp = grp.dropna()
        if len(grp) < 10:
            results[d] = np.nan
            continue
        results[d] = grp["signal"].corr(grp["ctrl"])
    return pd.Series(results, name=f"exposure_{control.name}")


def daily_turnover(signal: pd.Series) -> float:
    df = signal.to_frame("signal")
    to_vals = []
    dates_sorted = sorted(df.index.get_level_values("date").unique())
    for i, d in enumerate(dates_sorted[1:], 1):
        prev_d = dates_sorted[i - 1]
        s_today = df.loc[d]["signal"]
        s_prev = df.loc[prev_d]["signal"]
        common = s_today.index.intersection(s_prev.index)
        if len(common) < 10:
            continue
        today_rank = s_today.loc[common].rank(pct=True)
        prev_rank = s_prev.loc[common].rank(pct=True)
        to_vals.append((today_rank - prev_rank).abs().mean())
    return np.mean(to_vals) if to_vals else np.nan


def load_industry_map(symbols: list):
    """从 Pandadata get_stock_detail 批量获取行业分类"""
    pd_api = init_pandadata()

    industry_map = {}
    batch_size = 50
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        try:
            result = pd_api.get_stock_detail(symbol=batch)
            for _, row in result.iterrows():
                industry_map[row["symbol"]] = row.get("sector_code_name", "UNKNOWN")
        except Exception:
            continue
    return industry_map


def compute_style_controls(ohlcv_df: pd.DataFrame):
    """从 OHLCV 计算 log_dollar_vol, beta_60d, volatility_20d"""
    df = ohlcv_df.copy()
    df = df.sort_values(["symbol", "date"])
    df["dollar_vol"] = df["close"] * df["volume"]
    df["log_dollar_vol"] = np.log(df["dollar_vol"].replace(0, np.nan))
    df["ret"] = df.groupby("symbol")["close"].pct_change()
    market_ret = df.groupby("date")["ret"].mean()
    df["market_ret"] = df["date"].map(market_ret)

    def _rolling_beta(group):
        cov = group["ret"].rolling(60, min_periods=20).cov(group["market_ret"])
        var = group["market_ret"].rolling(60, min_periods=20).var()
        return (cov / var.replace(0, np.nan)).where(var > 1e-10)

    df["beta_60d"] = df.groupby("symbol", group_keys=False).apply(_rolling_beta).reset_index(level=0, drop=True)
    df["volatility_20d"] = df.groupby("symbol")["ret"].transform(
        lambda x: x.rolling(20, min_periods=10).std()
    )
    return df.set_index(["date", "symbol"])[["log_dollar_vol", "beta_60d", "volatility_20d"]]


def orthogonalize_one(factor_signal: pd.Series, industry_map: dict,
                      style_controls: pd.DataFrame) -> pd.Series:
    """正交化单个因子，返回残差 Series (MultiIndex [date, symbol])"""
    dates = sorted(factor_signal.index.get_level_values("date").unique())
    all_residuals = []

    for d in dates:
        try:
            y_day = factor_signal.loc[d].dropna()
        except KeyError:
            continue
        if len(y_day) < MIN_SAMPLES:
            continue

        ind_day = pd.Series(
            [industry_map.get(s, "UNKNOWN") for s in y_day.index],
            index=y_day.index, name="industry"
        )
        ind_dummies = pd.get_dummies(ind_day, drop_first=True).astype(float)

        try:
            style_day = style_controls.loc[d].reindex(y_day.index)
        except KeyError:
            continue
        style_clean = pd.DataFrame(index=y_day.index)
        for col in style_day.columns:
            style_clean[col] = winsorize_zscore(style_day[col])

        x = pd.concat([ind_dummies, style_clean], axis=1).dropna()
        common_idx = y_day.index.intersection(x.index)
        if len(common_idx) < MIN_SAMPLES:
            continue

        resid = residualize_one_day(y_day.loc[common_idx], x.loc[common_idx])
        resid_clean = resid.dropna()
        if len(resid_clean) < MIN_SAMPLES:
            continue

        resid_z = winsorize_zscore(resid_clean)
        resid_z.index = pd.MultiIndex.from_tuples(
            [(d, s) for s in resid_z.index], names=["date", "symbol"]
        )
        all_residuals.append(resid_z)

    return pd.concat(all_residuals)


def main():
    parser = argparse.ArgumentParser(description="因子正交化")
    parser.add_argument("--factor-dir", default="data/factors",
                        help="因子输入目录（相对于工作目录或绝对路径）")
    parser.add_argument("--output-dir", default="data/factors_orthogonalized",
                        help="残差因子输出目录")
    parser.add_argument("--indicator", default="000300",
                        help="Pandadata 股票池指数代码 (默认 000300=沪深300)")
    parser.add_argument("--start-date", default="20201201",
                        help="Pandadata 起始日期 YYYYMMDD")
    parser.add_argument("--end-date", default="20250131",
                        help="Pandadata 结束日期 YYYYMMDD")
    args = parser.parse_args()

    factor_dir = Path(args.factor_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    factor_files = sorted(factor_dir.glob("F*.parquet"))
    if not factor_files:
        print(f"❌ 未找到因子文件: {factor_dir}")
        return

    print(f"加载 {len(factor_files)} 个因子...")

    # 收集所有 symbols
    all_symbols = set()
    factors = {}
    for fp in factor_files:
        df = pd.read_parquet(fp)
        df["date"] = pd.to_datetime(df["date"])
        s = df.set_index(["date", "symbol"])["factor_value"]
        factors[fp.stem] = s
        all_symbols.update(s.index.get_level_values("symbol").unique())

    # 行业分类
    print(f"拉取 {len(all_symbols)} 只股票的行业分类...")
    try:
        industry_map = load_industry_map(list(all_symbols))
    except Exception as e:
        print(f"❌ Pandadata 行业分类拉取失败: {e}")
        print("   请检查: 1) Pandadata 凭证是否配置 2) 网络连接 3) API 服务状态")
        sys.exit(1)
    print(f"  行业数: {len(set(industry_map.values()))}")

    # 风格控制（从 Pandadata 拉 OHLCV）
    print("计算风格控制变量...")
    try:
        pd_api = init_pandadata()
        raw = pd_api.get_stock_daily(
        start_date=args.start_date, end_date=args.end_date,
        fields=[], indicator=args.indicator, st=False,
    )
    except Exception as e:
        print(f"❌ Pandadata OHLCV 拉取失败: {e}")
        sys.exit(1)
    raw["date"] = pd.to_datetime(raw["date"], format="%Y%m%d")
    raw.columns = [c.lower() for c in raw.columns]
    if "trade_status" in raw.columns:
        raw = raw[raw["trade_status"] == 0]
    # 计算 forward_ret_5d 用于 IC 诊断（不在回归中使用）
    raw["forward_ret_5d"] = raw.groupby("symbol")["close"].shift(-5) / raw["close"] - 1
    fwd_ret = raw.set_index(["date", "symbol"])["forward_ret_5d"]
    style_controls = compute_style_controls(raw)

    # 逐因子正交化
    print(f"\n正交化 {len(factors)} 个因子...")
    for name, signal in factors.items():
        residual = orthogonalize_one(signal, industry_map, style_controls)
        out = residual.reset_index()
        out.columns = ["date", "symbol", "factor_value"]
        out_path = output_dir / f"{name}_residual.parquet"
        out.to_parquet(out_path, index=False)

        # 快速诊断：检查所有风格暴露清零
        ic_before = daily_rank_ic(signal, fwd_ret).mean()
        ic_after = daily_rank_ic(residual, fwd_ret).mean()
        exp_size_before = daily_exposure(signal, style_controls["log_dollar_vol"]).mean()
        exp_size_after = daily_exposure(residual, style_controls["log_dollar_vol"]).mean()
        exp_beta_after = daily_exposure(residual, style_controls["beta_60d"]).mean()
        exp_vol_after = daily_exposure(residual, style_controls["volatility_20d"]).mean()
        print(f"  {name}: IC {ic_before:+.5f} → {ic_after:+.5f}  "
              f"size {exp_size_before:+.4f} → {exp_size_after:+.4f}  "
              f"beta→{exp_beta_after:+.4f}  vol→{exp_vol_after:+.4f}  ✅")

    print(f"\n✅ 残差因子保存至: {output_dir}")


if __name__ == "__main__":
    main()
