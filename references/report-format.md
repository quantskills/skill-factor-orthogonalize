# 正交化报告输出格式

输出给用户时，必须同时展示“暴露是否剥离”和“alpha 是否保真”。不要只给一个残差因子文件名。

## 标准格式

```
=== Factor Orthogonalize Report ===
Factor       : f_liquidity_reversal_20
Horizon      : 5d
Period       : 2021-12-04 → 2024-12-03 (val, 3.0y)
Universe     : CSI All A, tradable mask

Controls:
  industry     : CITICS L1 one-hot
  size         : log_mktcap
  style        : beta, volatility, liquidity
  old factors  : f_amihud_20, f_momentum_60, f_value_ep

Exposure diagnostics:
                    before      after      verdict
  max industry abs  0.184       0.012      OK
  corr log_mktcap  -0.421      -0.018      OK
  corr beta         0.155       0.009      OK
  max old corr      0.673       0.284      OK

Signal quality:
                    raw         residual   delta
  rank IC mean      +0.041      +0.027     -0.014
  rank IC IR        +2.10       +1.36      -0.74
  Sharpe            +0.85       +0.72      -0.13
  max drawdown      -22.3%      -24.8%     -2.5pp
  ann turnover      33.5        41.2       +7.7
  coverage          94.1%       93.8%      -0.3pp

Verdict: ACCEPT AS RESIDUAL FACTOR
Reason : 主要风格暴露已剥离，IC 保留 64%，与旧因子最大相关性降到 0.284。
```

## 必含元素

1. **元信息**：Factor / Horizon / Period / Universe
2. **控制变量列表**：行业、市值、风格、旧因子分别列出
3. **暴露诊断**：正交前后 exposure / correlation 对比
4. **信号质量对比**：正交前后 IC / Sharpe / MDD / turnover / coverage
5. **结论**：accept、needs review、reject，并说明原因

## Verdict 规则

| Verdict | 条件 |
|---|---|
| ACCEPT AS RESIDUAL FACTOR | 暴露明显下降，IC 保留率可接受，风险指标未明显恶化 |
| NEEDS REVIEW | 暴露下降但 IC 损失过大，或 turnover 明显升高 |
| REJECT | 正交后 IC 接近 0、coverage 严重下降、或仍与旧因子高度相关 |

## 不要做的事

- 只说“已完成正交化”
- 只输出残差矩阵，不解释剥离了什么
- 不展示正交前后的 alpha 保真
- 正交后 score 降低就直接判失败，忽略独立性提升
