# SHiP 方向论文复现 — MPPPB（MICRO 2017）

《并行计算机体系结构》课程期末大作业（程序复现与运行方向）。
最终目标：在 2027-01-14 前完成 **MPPPB（Multiperspective Reuse Prediction, MICRO 2017）**
的复现 + Benchmark 数据 + Technical Report。
SHiP 作为同族对照基线（SHiP++ 不参与本轮实验）。

## 1. 选题定位

**SHiP = Signature-based Hit Predictor**，Wu, Jaleel, Martonosi, Steely, Emer，MICRO 2011。
核心思想：用 load PC（或 PC+offset、指令序列）作为签名，用一个 Signature History Counter
Table（SHCT）学习每种签名的再引用行为，在 miss 时预测新插入行的 RRPV，从而把
"不会再被用到"的流式数据插到更易被替换的位置。SHiP 本身不改变 SRRIP 的命中提升和
受害者选择逻辑，属于"插入策略"层面的工作。

> 注意：作业要求复现**近十年**（2016 以后）的论文，SHiP 原文（2011）不在范围内。
> 因此实际复现对象应从 SHiP 的后续工作中选择，见 `docs/candidates.md`。

## 2. 当前进度

| 项目 | 状态 |
|---|---|
| 收集 SHiP 系论文（26 篇，含 MPPPB / Hawkeye / Glider / SHiP++ 等） | ✅ 见 `docs/papers.md` |
| ChampSim 编译环境（含 vcpkg 依赖） | ✅ 已编译通过 |
| SPEC CPU2017 ChampSim trace（8 条） | ✅ 见 `docs/benchmark.md` |
| 论文选定：MPPPB（MICRO 2017） | ✅ 见 `docs/decision.md` |
| MPPPB ChampSim 模块 v0（16 特征 / 采样器 / 训练 / 阈值决策） | ✅ 编译 + 冒烟通过，见 `docs/notes_mpppb.md` |
| 实验基线：LRU + SHiP-PC + MPPPB（SHiP++ 已移除） | ✅ 配置见 `docs/baselines.md` |
| 阈值/位置搜索（论文未给数值） | 🚧 下一步 |
| static MDPP 底座 / 真 bypass | ⏳ |
| 完整 Benchmark + 技术报告 | ⏳ |

## 3. 目录结构

```
.
├── docs/                  # 文献调研、选题对比、实验记录
│   ├── baselines.md       # LRU / SHiP-PC / MPPPB 的确切配置
│   ├── papers.md          # 已收集论文清单（含来源链接）
│   ├── candidates.md      # 各候选论文的复现难度/依赖/风险对比
│   ├── decision.md        # 最终选题与决策记录
│   ├── notes_mpppb.md     # MPPPB 精读笔记与复现方案
│   ├── reading-plan.md    # 论文主题分类与阅读优先级
│   └── benchmark.md       # trace 清单、仿真参数、初步结果
├── papers/                # 论文 PDF（gitignore，可重新下载）
│   └── manifest.tsv       # 下载清单
├── env/                   # ChampSim 源码与 Python venv（gitignore）
├── traces/                # ChampSim trace（gitignore，体积大）
├── champsim_modules/      # 自研替换策略模块（mpppb）
├── configs/               # 各替换策略的 ChampSim 配置
├── scripts/               # 下载、编译、批量实验脚本
├── sim/                   # 自研轻量 trace-driven LLC 模拟器
└── results/               # 实验输出（csv/图）
```

## 4. 环境

- CPU: 24 核，内存 61 GB，磁盘可用 ~160 GB
- OS: Linux (x86-64)，g++ 16.2.1
- cmake 由 `env/venv` 提供（系统未装），vcpkg 依赖已编译进 `env/ChampSim/vcpkg_installed`
- ChampSim: `develop` 分支，commit `410cee62d9c429c043ea611325ce00e6c303be2a` (2026-09-04)

### 从零重建

```bash
# 1. 论文（能公开下载的部分；其余见 docs/papers.md 的"待获取"列）
./scripts/fetch_papers.sh

# 2. ChampSim（会 clone 到 env/ChampSim 并编译 vcpkg 依赖，约 10 分钟）
./scripts/build_champsim.sh

# 2b. 编译自研策略（MPPPB）
./scripts/build_mpppb.sh

# 3. Benchmark trace（约 3.4 GB）
./scripts/get_traces.sh
```

## 5. ChampSim 快速运行

```bash
cd env/ChampSim
./bin/champsim \
  --warmup-instructions 200000000 \
  --simulation-instructions 500000000 \
  ../../traces/410.bwaves-945B.champsimtrace.xz
```

ChampSim 自带 `lru`、`srrip`、`drrip`、`random`、`ship`；
本项目最终只跑 **LRU / SHiP-PC（`ship`）/ MPPPB** 三条，配置见 `docs/baselines.md`。

批量跑策略 × trace 的脚本见 `scripts/run_matrix.sh`（🚧 待补）。

## 6. 参考文献

见 `docs/papers.md`。核心脉络：

```
SHiP (MICRO'11)
 ├─ SHiP++ (CRC-2 @ ISCA'17)        改进 SHCT 训练与预测粒度
 ├─ Perceptron Reuse Prediction (MICRO'16)
 │   └─ MPPPB (MICRO'17)            多视角感知机
 ├─ Hawkeye (ISCA'16)               用 Belady 最优解做在线监督学习
 │   ├─ Glider (MICRO'19)           SVM + 离线 LSTM 特征
 │   └─ Mockingjay (HPCA'22)        多分类复用距离预测
 └─ RLR (HPCA'21)                   低成本、无 PC 的替代方案
```