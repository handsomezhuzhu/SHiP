# c4 / c14 完整 8 trace 验证

对象：搜索中 IPC 最好的 **c4_highbypass** 与 MPKI 最好的 **c14_theta_high**，
在 50 M warmup + 150 M 测量、8 条 SPEC2017 上与 author1 / LRU / SHiP 对比。
16 条全部 `rc=0`，`instructions=150M`，`bad NONE`。

## 配置

| 名称 | 相对 author1 的覆盖 |
|---|---|
| author1 | 基线：promotion 82，bypass 56/256，plv -15/35/44，train 128，deadzone 109/135 |
| c4_highbypass | `MPPPB_DT1=30 MPPPB_DT2=150`（更激进 bypass） |
| c14_theta_high | `MPPPB_THETA=130 MPPPB_THETA2=160`（更宽 dead zone） |

## 逐 trace：c4

| trace | author1 IPC | c4 IPC | c4/author1 | c4/LRU | author1 MPKI | c4 MPKI |
|---|---|---|---|---|---|---|
| 400.perlbench | 1.3592 | 1.3600 | 1.0006 | 1.0316 | 0.44 | 0.43 |
| 403.gcc | 2.1741 | 2.1740 | 1.0000 | 0.9996 | 0.15 | 0.15 |
| 410.bwaves | 3.0102 | 3.0102 | 1.0000 | 1.0000 | 0.02 | 0.02 |
| 429.mcf | 0.3250 | 0.3249 | 0.9997 | 1.0177 | 30.00 | 29.93 |
| 437.leslie3d | 0.6255 | 0.6238 | 0.9974 | 0.9979 | 7.43 | 7.43 |
| 450.soplex | 0.3577 | **0.3587** | 1.0029 | **1.1583** | 19.16 | 19.18 |
| 470.lbm | 0.6142 | 0.6107 | 0.9942 | 0.9931 | 28.49 | 28.49 |
| 483.xalancbmk | 0.3024 | **0.3061** | 1.0123 | **1.1829** | 22.33 | 21.94 |

几何平均：

- **c4 / author1 IPC = 1.0009（+0.09%）**；MPKI = 0.9952（−0.48%）
- **c4 / LRU IPC = 1.0453（+4.53%）**；MPKI ≈ 0.9214（−7.86%）
- c4 / SHiP IPC ≈ 1.0022（+0.22%），MPKI 低于 SHiP（0.9214 vs 0.9631）

## 逐 trace：c14

| trace | c14/author1 | c14/LRU | c14 MPKI |
|---|---|---|---|
| 400.perlbench | 0.9985 | 1.0295 | 0.45 |
| 403.gcc | 1.0000 | 0.9996 | 0.15 |
| 410.bwaves | 1.0000 | 1.0000 | 0.02 |
| 429.mcf | 0.9999 | 1.0179 | 29.70 |
| 437.leslie3d | 1.0003 | 1.0007 | 7.43 |
| 450.soplex | 0.9991 | 1.1539 | 19.17 |
| 470.lbm | 0.9996 | 0.9984 | 28.49 |
| 483.xalancbmk | 0.9976 | 1.1658 | 22.40 |

几何平均：c14 / author1 IPC = **0.9994（−0.06%）**，
c14 / LRU = **1.0437（+4.37%）**；MPKI 与 author1 基本持平。
c14 的 MPKI 优势在完整窗口上没有保留（5 M 窗口的 0.9994 是短窗噪声）。

## 结论

1. **c4 是当前最优配置**：相对 LRU **+4.53% IPC / −7.86% MPKI**，
   相对 author1 仅 +0.09% IPC / −0.48% MPKI，属于“边际改进”。
2. **author1 已接近局部最优**；18 组 τ/π 搜索没有找到大幅提升，
   5 M 窗口的排名大多在噪声内。
3. **c4 在 soplex/xalan 上最好**（xalan +18.3% vs LRU，soplex +15.8%），
   lbm 略降（−0.7%），但几何平均仍略高于 author1。
4. **vs SHiP**：c4 IPC +0.22%，MPKI 明显更低（0.9214 vs 0.9631）；
   xalan 仍略低于 SHiP（0.3061 vs 0.3076），但差距很小。
5. **vs 论文**：论文 +9.0% IPC；我们 +4.53%。论文引用的 CRC2 MPPPB
   miss 降低 6.5%；我们 **7.9%**，miss 指标同量级。
   IPC 幅度差异主要来自 SPEC2017/8 条 vs SPEC2006/99 segments、
   ChampSim 6-wide/352 ROB vs 4-wide/128 window、无预取。
6. **改进方向**：τ/π 搜索已到边际；下一步应做预测器 ROC/准确率、
   Table 1(b) 特征对照、sampler 80 组、多核 Table 2；换底座/参数
   不太可能再把 IPC 大幅拉高。

## 产物

- 原始 JSON：`results/raw/mdpp_best/mpppb/`（c4，8 条）；
- 验证全部：`results/raw/mdpp_validate/box*/val/`（c4+c14，16 条）；
- CSV：`results/mdpp_best_results.csv`、`results/mdpp_validate.csv`。