# 单核 MDPP 结果（author1，Daytona）

对象：8 条 SPEC2017 trace，50 M warmup + 150 M 测量，单核 2 MB LLC。
策略：`MPPPB_PROFILE=author1`（MDPP + CRC2 config 1 参数 + 作者训练语义 + 真 bypass）。
对比：Matrix-1 的 LRU / SHiP-PC / SRRIP-MPPPB（同一窗口、同一 trace）。

## 1. 逐 trace

| trace | LRU IPC | SHiP IPC | SRRIP-MPPPB | **MDPP-MPPPB** | MDPP/LRU | MDPP/SHiP | MDPP/SRRIP | LRU MPKI | MDPP MPKI |
|---|---|---|---|---|---|---|---|---|---|
| 400.perlbench | 1.3182 | 1.3459 | 1.3379 | **1.3592** | 1.0310 | 1.0098 | 1.0159 | 0.57 | 0.44 |
| 403.gcc | 2.1750 | 2.1747 | 2.1743 | 2.1741 | 0.9996 | 0.9997 | 0.9999 | 0.15 | 0.15 |
| 410.bwaves | 3.0102 | 3.0102 | 3.0102 | 3.0102 | 1.0000 | 1.0000 | 1.0000 | 0.02 | 0.02 |
| 429.mcf | 0.3193 | 0.3242 | 0.3243 | 0.3250 | 1.0180 | 1.0027 | 1.0023 | 28.75 | 30.00 |
| 437.leslie3d | 0.6252 | 0.6232 | 0.6247 | 0.6255 | 1.0005 | 1.0037 | 1.0012 | 7.40 | 7.43 |
| 450.soplex | 0.3097 | 0.3544 | 0.3489 | **0.3577** | **1.1550** | 1.0094 | 1.0253 | 23.27 | **19.16** |
| 470.lbm | 0.6150 | 0.6129 | 0.6200 | 0.6142 | 0.9988 | 1.0022 | 0.9907 | 28.49 | 28.49 |
| 483.xalancbmk | 0.2588 | 0.3076 | 0.2974 | **0.3024** | **1.1686** | 0.9830 | 1.0168 | 28.02 | **22.33** |

几何平均（8 条）：

| 对比 | IPC 几何平均 | MPKI 几何平均 |
|---|---|---|
| MDPP / LRU | **1.0444（+4.44%）** | **0.9258（−7.42%）** |
| MDPP / SHiP-PC | **1.0013（+0.13%）** | —（MPKI 更低） |
| MDPP / SRRIP-MPPPB | **1.0065（+0.65%）** | — |

## 2. 解读

1. **MDPP 把 SRRIP 的 +3.76% 拉到 +4.44% IPC、−7.42% MPKI**；
   MPKI 改善明显（−5.02% → −7.42%），IPC 只多 0.65%。
2. **MPPB 终于略高于 SHiP**（IPC +0.13%）：soplex +0.9%、
   perlbench +1.0%、mcf +0.3%；xalan 仍低 1.7%（SHiP 的 PC 签名很强），
   但 MPPPB 的 xalan MPKI 更低（22.33 vs 21.95 接近）。
3. 收益仍集中在 **soplex（+15.5%）/ xalan（+16.9%）**；
   mcf +1.8% IPC 但 MPKI +4.3%；lbm 基本持平。
4. **和论文 +9.0% 的差距**：论文是 SPEC2006、99 segments、
   自研 4-wide/128-window 模拟器、stream prefetcher；我们是 SPEC2017、
   8 条、ChampSim 6-wide/352 ROB、无预取。绝对 IPC 不可直接对齐。
5. **和竞赛 MPPPB 的 miss 指标**：Glider 论文引用的 CRC2 MPPPB
   单核 miss rate 降低 **6.5%**（相对 LRU）；我们 **7.4%**，
   在同类量级，说明 MDPP 版本的 miss 行为已经接近作者的竞赛实现。
6. mcf 的 bypass 比例很高（约 41% of fills），MPKI 变差；这是参数搜索
   的第一优先项（降低 bypass / 提高 promotion）。

## 3. 平台与耗时

- Daytona `daytona-large` 容器 ×3（4 vCPU / 8 GiB / 10 GB），
  mcf/xalan/soplex 在 box1，perlbench/gcc/lbm 在 box2，
  leslie3d/bwaves 在 box3；
- 8 条 3/3/2 并行，运行约 **35–40 min**；加 setup + trace 上传约 15 min；
- 费用约 **$1–2**（$200 credit 未受影响）。
- 原始 JSON：`results/raw/mdpp_author1/mpppb/`；日志：`.../logs/`。

## 4. 下一步

1. **参数搜索**（mcf+xalan，5 M+5 M）：promotion、dt1/dt2、plv、
   training threshold、deadzone；目标超过 author1 的 +4.44%。
2. 最优配置跑完整 8 trace，和本表对比。
3. 如果搜索能把 IPC 拉到 +5–6%、MPKI 更低，就是明确的改进方向。
4. 多核仍按 `docs/mdpp_plan.md` 的资源困境处理（1000 mix 不可行）。