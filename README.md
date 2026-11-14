# MPPPB（MICRO 2017）复现与 TA-MPPPB 原创改进

《并行计算机体系结构》课程期末大作业（程序复现与微架构改进方向）。本项目在现代 ChampSim 上完整复现了 **MPPPB（Multiperspective Reuse Prediction, Jiménez & Teran, MICRO-50 2017）** 的 **Single-Core Static MDPP** 架构（同时覆盖无硬件预取器与开启硬件预取器两种对照场景），并针对现代虚存与多级缓存交互下的 Zero-IP 冲突与访问语义失配问题，提出了零额外 SRAM 开销的原创改进方案 **TA-MPPPB（Translation- & Access-Aware MPPPB）**。

---

## 1. 核心实验总览（8 条 DPC-3 SPEC CPU2006 Trace，50M Warmup + 150M Sim）

所有运行均在云端并行集群完成并通过 [`scripts/verify_results.py`](scripts/verify_results.py) 全量校验（`bad NONE`，指令数 ∈ `[150,000,000, 150,000,020]`）。

### 1.1 无硬件预取器对照（基于 `author1` 与调优 `c4` 底座）

| 策略 / 配置 | Geomean IPC 增益 (vs `LRU`) | Geomean All-MPKI 变化 | Geomean Demand-MPKI 变化 | 说明与详报 |
| --- | ---: | ---: | ---: | --- |
| `LRU` | 0.00% | 0.00% | 0.00% | 传统基线 (`configs/champsim_lru.json`) |
| `SHiP-PC` | +4.30% | -3.69% | -8.07% | 同族对比基线 (`configs/champsim_ship.json`) |
| `MPPPB (author1)` | +4.44% | -7.43% | -9.02% | 原作者静态 MDPP 参数（[`results_mdpp_author1.md`](docs/results_mdpp_author1.md)） |
| **`TA-MPPPB (ta_nopref)`** | **+4.56%** | -0.55% | **-9.60%** | 本文原创改进（基于 `author1`，`MPPPB_IMPROVE=1`） |
| `MPPPB (c4)` | +4.53% | **-7.87%** | -9.32% | bypass 阈值搜索最优静态组（[`results_mdpp_validate.md`](docs/results_mdpp_validate.md)） |
| **`TA-MPPPB (ta_c4)`** | **+4.71%** | -0.89% | **-9.90%** | 本文原创改进（基于 `c4`，`MPPPB_IMPROVE=1`） |

> 注：本项目早期探索曾评估过 SRRIP 底座（`Matrix-1`，MPPPB +3.76% IPC vs SHiP +4.30%）；因论文单核主体采用 **Static MDPP**（真 bypass + 16 位置树状 PLRU 最小扰动提升），最终全套对照与改进均以 **Single-Core Static MDPP** 为唯一权威基准。

### 1.2 开启硬件预取器对照（`L1D: next_line` + `L2C: ip_stride`）

| 策略 / 配置 | Geomean IPC 增益 (vs `LRU_pref`) | Geomean Demand-MPKI 变化 | Geomean LOAD+RFO MPKI 变化 | 说明与详报 |
| --- | ---: | ---: | ---: | --- |
| `LRU_pref` | 0.00% | 0.00% | 0.00% | 开启 L1D/L2C 预取器基线 (`configs/champsim_lru_pref.json`) |
| `SHiP_pref` | +2.56% | -5.82% | -7.15% | 同族对比基线 (`configs/champsim_ship_pref.json`) |
| `MPPPB (author2)` | +1.66% | -5.49% | -6.71% | 作者预取配置复现（[`results_mdpp_pref.md`](docs/results_mdpp_pref.md)） |
| **`TA-MPPPB (ta_pref)`** | **+2.60%** (**超 `author2` +0.92%**) | **-5.85%** | **-7.22%** | 本文原创改进（反超 `SHiP_pref`，[`results_ta_mpppb.md`](docs/results_ta_mpppb.md)） |

---

## 2. 原创改进核心：TA-MPPPB（零额外 SRAM 开销）

针对现有 MPPPB 后续改进（如 MS-MPPPB / DS-MPPPB / Fit-MPPPB / 预取签名位扩展）未处理的**现代虚存+回写体系结构中 `ip == 0` 特征坍缩问题**，TA-MPPPB 在保持原有 **60.41 KiB** 静态预测器/采样器存储零增长的前提下提出三项协同机制（实现于 [`champsim_modules/mpppb/mpppb.h`](champsim_modules/mpppb/mpppb.h) 与 [`champsim_modules/mpppb/mpppb.cc`](champsim_modules/mpppb/mpppb.cc)）：

1. **页表游走（`TRANSLATION`）防旁路与伪指令页号解耦**：永不旁路页表填回、将其插入并命中提升至 MRU，对 `ip == 0` 的 `TRANSLATION`/`PREFETCH` 构造页号伪 PC `0x9e3779b9 ^ (block >> 6)` 避免 PC 表桶 0 冲突，并禁止 `pc == 0` 污染 `pc_ring` 移位历史。
2. **保留创建者特征的写回（`WRITE`）采样学习**：修复“跳过写回导致 91%–97% 写回命中损失负权重训练（Write-Sampler Starvation）”问题——在 `WRITE` 命中采样器时先回传 `learn_reuse (-1)` 信用再恢复原创建者（`LOAD`/`RFO`）的采样项状态（`s.line[0] = previous`），同时适度放宽脏写回旁路阈值以释放读缓存空间。
3. **预取（`PREFETCH`）自适应准入收紧**：在开启硬件预取器时提高 `PREFETCH` 旁路门槛（`thresh + 18`），抑制低价值猜测预取行驱逐高价值需求行与页表行。

---

## 3. 目录结构与核心文档

```text
.
├── champsim_modules/mpppb/   # Static MDPP 核心实现与 TA-MPPPB (MPPPB_IMPROVE=1)
├── configs/                  # 无预取与有预取对照配置文件（LRU / SHiP / MPPPB）
├── docs/
│   ├── final_report.md       # 期末最终技术报告（复现与原创改进完整论述）
│   ├── results_mdpp_author1.md  # 无预取器 author1 复现详报
│   ├── results_mdpp_validate.md # 无预取器 8-trace c4/author1 验证报告
│   ├── results_mdpp_pref.md     # 开启硬件预取器对照复现报告
│   ├── results_ta_mpppb.md      # TA-MPPPB 原创改进与 v1/v2 消融报告
│   ├── review_mpppb_code.md     # 13 处复现 Bug 排查与对齐校验记录
│   └── papers.md / decision.md / baselines.md / benchmark.md
├── results/                  # 各实验阶段汇总 CSV 与 raw JSON/log 归档
└── scripts/                  # 编译、云端调度、校验 (verify_results.py) 与汇总脚本
```

---

## 4. 环境与构建运行方式

- **仿真器版本**：ChampSim `develop` @ `410cee62d9c429c043ea611325ce00e6c303be2a`
- **默认基线环境**（需已运行 [`scripts/build_champsim.sh`](scripts/build_champsim.sh) 与 [`scripts/get_traces.sh`](scripts/get_traces.sh)）：

```bash
# 1. 编译无预取器与开启硬件预取器的 ChampSim 二进制
./scripts/build_mpppb.sh

# 2. 运行原版 Static MDPP（如 author1 无预取 / author2 开启预取）
MPPPB_PROFILE=author1 ./env/ChampSim/bin/champsim_mpppb_mdpp \
  --warmup-instructions 50000000 --simulation-instructions 150000000 \
  traces/450.soplex-92B.champsimtrace.xz

MPPPB_PROFILE=author2 ./env/ChampSim/bin/champsim_mpppb_mdpp_pref \
  --warmup-instructions 50000000 --simulation-instructions 150000000 \
  traces/483.xalancbmk-127B.champsimtrace.xz

# 3. 启用 TA-MPPPB 原创改进（仅需追加 MPPPB_IMPROVE=1）
MPPPB_PROFILE=author2 MPPPB_IMPROVE=1 ./env/ChampSim/bin/champsim_mpppb_mdpp_pref \
  --warmup-instructions 50000000 --simulation-instructions 150000000 \
  traces/470.lbm-1274B.champsimtrace.xz

# 4. 校验并汇总全部实验结果
python scripts/summarize_champsim.py results/raw/ta_mpppb results/ta_mpppb_results.csv
python scripts/verify_results.py --root results/raw/ta_mpppb \
  --policies ta_nopref ta_c4 ta_pref --baseline ta_nopref \
  --csv results/ta_mpppb_results.csv --min-instr 150000000 --max-instr 150000020
```

---

## 5. 相关文献脉络

详见 [`docs/papers.md`](docs/papers.md)：
```text
SHiP (MICRO'11)
 ├─ SHiP++ (CRC-2 @ ISCA'17)
 ├─ Perceptron Reuse Prediction (MICRO'16)
 │   └─ MPPPB (MICRO'17)  ──► 本项目复现主体 + TA-MPPPB 原创改进
 ├─ Hawkeye (ISCA'16) ─► Glider (MICRO'19) ─► Mockingjay (HPCA'22)
 └─ RLR (HPCA'21)
```
