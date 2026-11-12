# 单核 MDPP 复现计划（Daytona）

目标：把 Matrix-1 的“单核 + SRRIP + 猜的 τ/π”换成
“**单核 + static MDPP + 作者 CRC2 config 1 参数 + 作者训练语义**”，
再和已归档的 LRU / SHiP 结果对比，最后做一轮 τ/π 搜索。

## 1. 当前代码

- `MPPPB_PROFILE=author1`（`champsim_modules/mpppb`）：
  - 底座：MDPP，16 位置，树状 PLRU，`vecmdpp` 最小扰动提升；
  - 特征：CRC2 `single_1`（≈论文 Table 1(a)），直接取位 + XOR PC + `% table_size`；
  - 训练：权重初值 1，`threshold=128`，dead zone `theta=109 / theta2=135`；
  - placement：`plv = (-15→0, 35→12, 44→15)`；
  - promotion：`conf <= 82` 才提升；
  - bypass：set-dueling `dt1=56 / dt2=256`，leader sets 32/64，`psel`；
  - **真 bypass**：`find_victim` 返回 `NUM_WAY`，`handle_fill` 跳过分配；
  - 采样器：64 组（1/32 sets，论文值；作者代码 80，先按论文）。
- 默认（不设 profile）仍是 Matrix-1 的 SRRIP 路径，旧结果可复现。

## 2. 单核 MDPP 矩阵（进行中）

| 项 | 值 |
|---|---|
| 机器 | Daytona `daytona-large` 容器 ×3（4 vCPU / 8 GiB / 10 GB） |
| 账号 | 3 个 key，各 1 台 |
| 窗口 | warmup 50 M + 测量 150 M |
| 策略 | 仅 MPPPB-MDPP（LRU/SHiP 复用 Matrix-1 的 JSON） |
| trace 分配 | box1: mcf/xalan/soplex；box2: perlbench/gcc/lbm；box3: leslie3d/bwaves |
| 预计 | 3/3/2 并行，墙钟约 40–50 min；费用约 $1–2 |
| 结果 | `results/raw/mdpp_daytona/box{1,2,3}/results/*.json` |

## 3. 参数搜索（下一轮）

在 mcf + xalan 的 5 M+5 M 上搜，再全量验证：

| 维度 | 候选 |
|---|---|
| promotion τ4 | 60 / 82 / 100 / 120 |
| bypass dt1/dt2 | 40/200, 56/256, 80/320, 100/400 |
| placement plv | (-15,0,35,12,44,15) / (20,0,35,12,44,15) / (30,0,40,12,48,15) |
| training threshold | 96 / 128 / 160 |
| dead zone θ/θ2 | 90/120, 109/135, 130/160 |
| 特征集 | `single_1` vs Table 1(b)（后续加） |

环境变量已支持：`MPPPB_PROMOTE`、`MPPPB_DT1/DT2`、
`MPPPB_PLV0T/P`…`PLV2T/P`、`MPPPB_TRAIN_THRESHOLD`、`MPPPB_THETA/THETA2`、
`MPPPB_INIT_WEIGHT`、`MPPPB_BYPASS_DUEL`。

评估：先看 IPC（主指标），同时记录 MPKI/bypass 比例；
候选超过 author1 的 8 trace 几何平均才算改进。

## 4. 多核：先不做，但结论要写

论文多核：4 核、8 MB LLC、SRRIP、1000 个 mix、每线程 1 B cycles、+8.3%。
我们资源：

| 资源 | 可并行 4 核仿真 | 1000 mix × 3 策略 |
|---|---|---|
| Daytona 3×4 vCPU | 12 | ~7 天（按每线程 1 B cycles） |
| instabox 5×4 vCPU | 20 | ~5 天 |
| 本机 12 物理核 | 12 | ~7 天 |

**完整 1000 mix 不可行**。按实测约 20 万 cycles/s（ChampSim 单线程）
估算：

- 1 B cycles/thread × 4 核 = 4 B cycles → **5.6 h/run**；
- 1000 mix × 3 策略 = 3000 runs → **16 800 CPU-hours**；
- 12 vCPU → 1400 h ≈ **58 天**；20 vCPU → 840 h ≈ **35 天**。

缩小规模是可行的：

| 规模 | 每线程窗口 | CPU-hours | 12 vCPU 墙钟 |
|---|---|---|---|
| 10 mix × 3 | 200 M cycles | ~33 | ~2.8 h |
| 30 mix × 3 | 200 M cycles | ~99 | ~8.3 h |
| 30 mix × 3 | 500 M cycles | ~248 | ~21 h |
| 30 mix × 3 | 1 B cycles（论文） | ~495 | ~41 h |

但即使缩小，也要先补：Table 2 多核特征、共享 256 组采样器、
4 核 / 8 MB 配置、4-trace mix、weighted speedup（单核 8 MB 基线）。
这是 3–5 天的代码工作，不是“多跑几条”。

报告里会明确：**单核部分做了完整复现 + 参数搜索；多核因资源与时间限制，
只做可行性分析，不声称复现论文的 1000 mix / +8.3%。**

## 5. 交付

- `docs/why_srrip_gap.md`：第一次 +3.76% 的差距分析；
- `docs/original_crc2_params.md`：作者竞赛参数摘录；
- 单核 MDPP 结果表 + 相对 LRU/SHiP 的几何平均；
- 参数搜索记录；
- 多核资源困境与缩小规模方案。