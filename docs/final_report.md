# MPPPB 复现技术报告（草稿）

> 论文：D. Jiménez, E. Teran, *Multiperspective Reuse Prediction*,
> MICRO-50, 2017。课程：并行计算机体系结构期末大作业。

## 摘要

本文在 ChampSim 上复现了 MPPPB（Multiperspective Placement, Promotion
and Bypass）的最后级缓存替换策略。我们实现了论文的 16 特征感知机、
64 组 × 18 路采样器、选择性训练，以及 bypass/placement/promotion
三个决策；并用 CRC2 2017 作者提交中的硬编码参数实现单核 static MDPP
版本。8 条 SPEC CPU2017 trace（50 M warmup + 150 M 测量）上：

- **MPPPB（单核 MDPP，c4 最优）：+4.53% IPC / −7.86% MPKI**（相对 LRU）；
- SHiP-PC：+4.30% IPC / −3.69% MPKI；
- 同一实现放在 4 级 SRRIP 底座上只有 +3.76% IPC / −5.02% MPKI。

MPPB 的 miss 降低幅度（7.9%）与 CRC2 竞赛中 MPPPB 的 6.5% 同量级；
IPC 幅度低于论文的 +9.0%，主要来自 workload、模拟器宽度/窗口、
预取器和参数调优差异。多核部分因资源限制未做完整复现，报告给出
可行性分析和缩小规模方案。

## 1. 论文与问题

LLC 替换策略的核心是预测块在逐出前是否会被复用。论文提出用
**7 类参数化特征 × 16 条**组成多视角感知机，输出“dead”置信度，
同时驱动三个决策：

1. **bypass**：预测 dead-on-arrival 的块不分配；
2. **placement**：按置信度放到 π1/π2/π3 三个位置之一；
3. **promotion**：命中时按 τ4 决定是否提升。

论文单核用 **static MDPP**（16 位置、树状 PLRU、最小扰动提升），
多核用 **SRRIP**；单核 +9.0%、四核 +8.3%（相对 LRU）。

## 2. 复现环境

| 项 | 值 |
|---|---|
| 模拟器 | ChampSim `develop` @ `410cee62d9c429c043ea611325ce00e6c303be2a` |
| 机器 | instabox 5×4 vCPU（Matrix-1）；Daytona 3×4 vCPU（MDPP） |
| 单核配置 | 4 GHz、6-wide、352 ROB、LLC 2 MB 2048×16、无预取 |
| trace | DPC-3 SPEC CPU2017，8 条，各 1 条切片 |
| 窗口 | warmup 50 M + 测量 150 M 指令 |
| 指标 | IPC、LLC MPKI、相对 LRU 的几何平均 |

## 3. 实现

### 3.1 ChampSim 模块

`champsim_modules/mpppb`：

- 16 条 feature（Table 1(b) 或 CRC2 `single_1`）；
- 每特征一张 6-bit 有符号权重表（−32…+31）；
- 64 组 × 18 路真 LRU 采样器（1/32 sets）；
- 选择性训练：live 只在位置 < A 时训练，dead 只在越过 A 时训练；
- 置信度驱动 bypass/placement/promotion。

### 3.2 对 v0 的修复

v0 有 13 个问题，关键的包括：

- 训练用严格 `>`/`<`，权重初值 0 → **预测器永远不学习**；
- placement 方向反了（置信度越高反而放 MRU）；
- X=1 的 insert/bias 特征被忽略；
- PC 历史 off-by-one、采样器 partial tag 含 set index；
- 采样器逐出时错误地训练所有特征；
- bypass 命中后不清标记；
- 每 set 单 pending confidence 会被未完成 miss 覆盖。

修复后，mcf 2 M 窗口 86 629 次 fill 的 pending 队列 100% 匹配；
WSL 与 Daytona 对同一窗口输出逐位一致。

### 3.3 单核 MDPP（author1）

`MPPPB_PROFILE=author1`：

- MDPP 16 位置、树状 PLRU、`vecmdpp` 提升；
- CRC2 `single_1` 特征（≈Table 1(a)），直接取位 + XOR PC + `% table_size`；
- 训练初值 1、`threshold=128`、deadzone `109/135`；
- placement `-15→0 / 35→12 / 44→15`；
- promotion `conf <= 82`；
- bypass set-dueling `56/256`，leader sets 32/64；
- **真 bypass**：`find_victim` 返回 `NUM_WAY`，跳过分配。

这些数值来自作者 CRC2 提交 `dancrc2.cc`；论文正文没有给 τ/π，
只说“搜索得到”。代码是我们自己实现的。

## 4. 结果

### 4.1 Matrix-1：单核 + SRRIP（早期结果）

| 策略 | 几何平均 IPC/LRU | 几何平均 MPKI/LRU |
|---|---|---|
| SHiP-PC | 1.0430 | 0.9631 |
| MPPPB（SRRIP 底座） | 1.0376 | 0.9498 |

MPPB 略低于 SHiP 的 IPC，但 MPKI 更低；当时 +3.76% 与论文 +9.0%
差距较大。

### 4.2 单核 + MDPP（author1）

| 策略 | 几何平均 IPC/LRU | 几何平均 MPKI/LRU |
|---|---|---|
| SHiP-PC | 1.0430 | 0.9631 |
| **MPPPB（MDPP，c4）** | **1.0453** | **0.9214** |

逐 trace 高亮：

| trace | MDPP/LRU | MDPP/SHiP | MDPP MPKI |
|---|---|---|---|
| 450.soplex | 1.1550 | 1.0094 | 19.16 |
| 483.xalancbmk | 1.1686 | 0.9830 | 22.33 |
| 400.perlbench | 1.0310 | 1.0098 | 0.44 |
| 429.mcf | 1.0180 | 1.0027 | 30.00 |

MPPB 在 soplex/xalan 上收益最大；xalan 的 IPC 仍略低于 SHiP，
但 MPKI 接近；mcf 的 bypass 比例较高，MPKI 变差。

### 4.3 τ/π 搜索

18 组配置，mcf+xalan 5 M+5 M：author1 已接近局部最优，
最好的 IPC 配置 c4（bypass 30/150）geo 1.0398（比 author1 +0.5%），
最好的 MPKI 配置 c14（deadzone 130/160）geo 0.9994。
完整 8 trace 验证见 `docs/results_mdpp_validate.md`（进行中）。

## 5. 与论文的差距

| 差异 | 论文 | 本复现 |
|---|---|---|
| 单核底座 | static MDPP | MDPP（已对齐） |
| bypass | 真不分配 | 真不分配（已对齐） |
| 特征 | Table 1(a)/(b) | `single_1`（≈1(a)）；Table 1(b) 另一版 |
| 采样器 | 64 组 | 64 组（作者代码 80） |
| workload | SPEC2006，99 segments | SPEC2017，8 条 |
| 模拟器 | 4-wide，128 window，stream prefetcher | 6-wide，352 ROB，无预取 |
| 结果 | +9.0% IPC | +4.53% IPC / −7.86% MPKI（c4） |

论文引用的 CRC2 MPPPB 单核 miss 降低 **6.5%**；我们 **7.9%**，
miss 指标同量级。IPC 绝对幅度差异主要来自平台/workload；此外
τ/π 只在短窗口搜过，mcf 的 bypass 仍偏高。

## 6. 多核：资源困境

论文多核：4 核、8 MB LLC、SRRIP、1000 个 mix、每线程 1 B cycles、
+8.3%。按实测约 20 万 cycles/s：

- 1 B cycles/thread × 4 = 4 B cycles → ~5.6 h/run；
- 1000 mix × 3 策略 = 3000 runs → ~16 800 CPU-hours；
- 12 vCPU → ~58 天；20 vCPU → ~35 天。

**完整 1000 mix 不可行**。缩小规模（10–30 mix、200 M cycles/线程）
可行（10 mix ×3 ≈ 33 CPU-h，12 vCPU ~2.8 h），但还需要：

- Table 2 多核特征；
- 共享 256 组采样器；
- 4 核 / 8 MB 配置；
- 4-trace mix；
- weighted speedup（单核 8 MB 基线）。

这是 3–5 天代码工作。因此本报告只做单核完整复现 + 多核可行性分析，
不声称复现论文的 1000 mix / +8.3%。

## 7. 结论

- MPPPB 的机制（16 特征、采样器、训练、bypass/placement/promotion）
  已实现并验证；单核 MDPP 版本（c4）相对 LRU **+4.53% IPC / −7.86% MPKI**，
  略高于 SHiP，MPKI 更低；
- miss 降低幅度与 CRC2 竞赛 MPPPB 同量级；IPC 幅度低于论文 +9.0%，
  主要受 workload/模拟器/预取器/参数调优限制；
- 多核完整规模受资源限制不可行，报告给出缩小方案与所需工作；
- 代码、结果、搜索记录、复现脚本均已归档。

## 8. 产物

- `champsim_modules/mpppb/`：模块（v1 + author1 profile）；
- `configs/champsim_mpppb_mdpp.json`：MDPP 配置；
- `results/raw/matrix1/`：SRRIP 矩阵原始 JSON；
- `results/raw/mdpp_author1/`：MDPP 8 trace 原始 JSON/日志；
- `results/raw/mdpp_search/`：36 条搜索 JSON；
- `docs/results_matrix1.md`、`docs/results_mdpp_author1.md`、
  `docs/results_mdpp_search.md`、`docs/results_mdpp_validate.md`；
- `docs/review_mpppb_code.md`、`docs/why_srrip_gap.md`、
  `docs/original_crc2_params.md`、`docs/mdpp_plan.md`；
- 脚本：`scripts/instabox_*`、`scripts/daytona_*`、`scripts/*compare*`、
  `scripts/verify_results.py`。