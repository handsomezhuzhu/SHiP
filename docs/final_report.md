# MPPPB（MICRO 2017）复现与 TA-MPPPB 改进技术报告

> 论文：Daniel A. Jiménez, Elvira Teran, *Multiperspective Reuse Prediction*, MICRO-50, 2017.
> 课程：《并行计算机体系结构》期末大作业（程序复现、基准测试与原创优化）。

---

## 摘要

本项目在现代 ChampSim（`develop @ 410cee62d9`）上对 **MPPPB（Multiperspective Placement, Promotion and Bypass）** 的 **Single-Core Static MDPP** 架构进行了高保真复现，覆盖**无硬件预取器**与**开启硬件预取器（`L1D: next_line + L2C: ip_stride`）**两套完整实验矩阵（每套均含 8 条 DPC-3 SPEC CPU2006 trace，50M warmup + 150M simulation），并针对现代 ChampSim 虚存/回写混合流量暴露出的微架构瓶颈提出了零额外 SRAM 开销的原创改进 **TA-MPPPB（Translation- & Access-Aware MPPPB）**。

核心量化成果（相对各自 `LRU` 基线的 8-trace 几何平均）：
1. **无硬件预取器复现**：
   - `SHiP-PC`：**+4.30% IPC**（All-MPKI -3.69%，Demand-MPKI -8.07%）；
   - `MPPPB (author1)`：**+4.44% IPC**（All-MPKI -7.43%，Demand-MPKI -9.02%）；
   - `MPPPB (c4 参数寻优)`：**+4.53% IPC**（All-MPKI -7.87%，Demand-MPKI -9.32%）；
   - **`TA-MPPPB (ta_nopref)`**：**+4.56% IPC**（Demand-MPKI **-9.60%**）；
   - **`TA-MPPPB (ta_c4)`**：**+4.71% IPC**（Demand-MPKI **-9.90%**）。
2. **开启硬件预取器对照（`L1D next_line + L2C ip_stride`）**：
   - `SHiP_pref`：**+2.56% IPC**（Demand-MPKI -5.82%，LOAD+RFO MPKI -7.15%）；
   - `MPPPB (author2)`：**+1.66% IPC**（Demand-MPKI -5.49%，LOAD+RFO MPKI -6.71%）；
   - **`TA-MPPPB (ta_pref)`**：**+2.60% IPC**（Demand-MPKI **-5.85%**，LOAD+RFO MPKI **-7.22%**），相对原版 `author2` 提升 **+0.92%**，并反超 `SHiP_pref`。

---

## 1. 论文机理与复现基准架构

LLC 替换策略的核心任务是在缓存行插入、命中与逐出瞬间判断该行在未来是否会被复用。MPPPB 提出使用由 **7 类参数化特征 × 16 条特征表**构成的多视角感知机（权重为 6-bit 有符号整数 `-32 .. +31`），联合 **64 组 × 18 路真 LRU 地址采样器（1/32 sets）** 与选择性门限训练，统一输出正/负“dead”置信度并驱动三大缓存决策：
1. **Bypass（准入旁路）**：若预测 dead 置信度高于动态/静态旁路阈值（由 set-dueling PSEL 控制是否启用 bypass），则跳过 LLC 分配（`find_victim` 返回 `NUM_WAY`）；
2. **Placement（分级插入）**：根据预测置信度区间，将准入块分别插入 Static MDPP 16 位置序列中的特定位置 `π1 / π2 / π3`；
3. **Promotion（最小扰动提升）**：命中时仅当重测置信度满足提升阈值 `τ4` 时采用单核 `vecmdpp` 最小扰动向 MRU 方向移动，否则保持原位以减少长距流对 MRU 栈的冲击。

论文针对单核与多核采用了不同底座：**单核使用 Static MDPP**（16 位置、树状 PLRU、真 bypass），多核使用 SRRIP（+8.3%，需 1000 个 4 核 mix）。因此，**单核复现的正确科学对照必须是 Static MDPP 底座**（本项目早期曾在 4 级 SRRIP 上探索过一次基线，得到 +3.76% IPC，因与论文单核底座不一致，本文正式实验与对照均以 Single-Core Static MDPP 为唯一标准）。

---

## 2. 复现实现与对齐验证

### 2.1 ChampSim 模块与对齐修复

代码实现于 [`champsim_modules/mpppb/mpppb.h`](../champsim_modules/mpppb/mpppb.h) 与 [`champsim_modules/mpppb/mpppb.cc`](../champsim_modules/mpppb/mpppb.cc)（基于 ChampSim `develop @ 410cee62d9`，2 MiB 16-way 2048-set LLC）。开发过程中修复了 13 项可能导致失真的实现差异（详见 [`docs/review_mpppb_code.md`](review_mpppb_code.md)）：
- 修正训练不等式与权重初值问题、反转错误方向导致的 placement 倒置、补齐 `insert/bias`（`X=1`）特征、对齐 `pc_ring` 历史移位时序与采样器 partial tag 掩码；
- 将原固定分配改为可真实不分配缓存行的真 bypass（`find_victim` 返回 `NUM_WAY`）；
- 为每个 set 维护按地址索引的 pending confidence 状态，消除多未完成 miss 并发填充时的置信度覆盖，在 `429.mcf` 2M 窗口 86,629 次 fill 上实现 pending 队列 100% 匹配。

### 2.2 `author1`、`c4` 与 `author2` 配置设定

通过 `MPPPB_PROFILE` 环境变量提供可切换的无侵入配置（`MPPPB_IMPROVE` 默认为 `0`，确保原版复现行为与历史数据严格可复现）：
- **`author1`（无预取器作者原参数）**：启用 Static MDPP（16 位置、`vecmdpp`、树状 PLRU）、CRC2 `single_1` 16 特征、训练阈值 `threshold=128`、deadzone `109/135`、placement `-15→0 / 35→12 / 44→15`、promotion 阈值 `82`、bypass set-dueling（leader 32/64、threshold `56/256`）。
- **`c4`（无预取器参数搜索最优点）**：保持全部机制不变，依据 18 组 5M+5M 搜索结果（[`docs/results_mdpp_search.md`](results_mdpp_search.md)）调整 bypass 阈值窗口为 `30/150`。
- **`author2`（开启硬件预取器作者参数）**：配合 `configs/champsim_mpppb_mdpp_pref.json`（开启 `L1D: next_line` 与 `L2C: ip_stride`），使用作者针对硬件预取环境标定的特征组与阈值配置。

---

## 3. Single-Core Static MDPP 无预取器复现

在无硬件预取器模式下，全部 8 条 SPEC CPU2006 trace（50M warmup + 150M sim）的复现数据如下（详见 [`docs/results_mdpp_author1.md`](results_mdpp_author1.md) 与 [`docs/results_mdpp_validate.md`](results_mdpp_validate.md)）：

| Trace | `LRU` IPC | `SHiP-PC` IPC | `MPPPB (author1)` IPC | `Δ vs LRU` | `MPPPB (c4)` IPC | `Δ vs LRU` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `400.perlbench-41B` | 1.3182 | 1.3459 | 1.3592 | +3.11% | **1.3600** | +3.17% |
| `403.gcc-16B` | **2.1750** | 2.1747 | 2.1741 | -0.04% | 2.1740 | -0.05% |
| `410.bwaves-945B` | 3.0102 | 3.0102 | 3.0102 | +0.00% | 3.0102 | +0.00% |
| `429.mcf-22B` | 0.3193 | 0.3242 | **0.3250** | +1.79% | 0.3249 | +1.75% |
| `437.leslie3d-134B` | 0.6252 | 0.6232 | **0.6255** | +0.05% | 0.6238 | -0.22% |
| `450.soplex-92B` | 0.3097 | 0.3544 | 0.3577 | +15.50% | **0.3587** | **+15.82%** |
| `470.lbm-1274B` | **0.6150** | 0.6129 | 0.6142 | -0.13% | 0.6107 | -0.70% |
| `483.xalancbmk-127B` | 0.2588 | **0.3076** | 0.3024 | +16.85% | 0.3061 | +18.28% |
| **Geomean vs `LRU`** | **1.0000** | **+4.30%** | **+4.44%** | **+4.44%** | **+4.53%** | **+4.53%** |
| **All-MPKI / Demand-MPKI** | 0 / 0 | -3.69% / -8.07% | -7.43% / -9.02% | — | **-7.87% / -9.32%** | — |

复现验证表明：Static MDPP 在 `450.soplex`（+15.82%）、`483.xalancbmk`（+18.28%）和 `400.perlbench`（+3.17%）上取得了最大收益，总体超越 `SHiP-PC`（+4.53% vs +4.30% IPC，Demand-MPKI 降幅 -9.32% vs -8.07%），且总 miss 降低幅度（7.87%）与 CRC2 竞赛中 MPPPB 单核约 6.5% 的 miss 降幅处于同一量级。绝对 IPC 幅度低于原文 +9.0% 主要源自模拟器前端宽度、指令窗口、8-trace 切片集与后续第 4 节所述的硬件预取与虚存访问流差异。

---

## 4. 开启硬件预取器对照复现（`L1D next_line + L2C ip_stride`）与瓶颈诊断

为对照论文“含流式硬件预取器”场景，我们在现代 ChampSim 中构造了标准双层预取配置（`L1D: next_line` + `L2C: ip_stride`，`50M + 150M`，完整数据见 [`docs/results_mdpp_pref.md`](results_mdpp_pref.md)）：

| Trace | `LRU_pref` IPC | `SHiP_pref` IPC | `Δ vs LRU_pref` | `MPPPB (author2)` IPC | `Δ vs LRU_pref` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `400.perlbench-41B` | 1.3735 | 1.3929 | +1.41% | **1.4005** | **+1.97%** |
| `403.gcc-16B` | **2.2054** | 2.2052 | -0.01% | 2.2044 | -0.05% |
| `410.bwaves-945B` | 2.9747 | 2.9747 | +0.00% | 2.9747 | +0.00% |
| `429.mcf-22B` | 0.4503 | **0.4546** | +0.96% | 0.4521 | +0.40% |
| `437.leslie3d-134B` | **1.3478** | 1.3476 | -0.01% | 1.3146 | -2.46% |
| `450.soplex-92B` | 0.4848 | **0.5080** | +4.77% | 0.5014 | +3.43% |
| `470.lbm-1274B` | **0.6518** | 0.6513 | -0.07% | 0.6423 | -1.46% |
| `483.xalancbmk-127B` | 0.3258 | **0.3720** | +14.20% | 0.3654 | +12.18% |
| **Geomean vs `LRU_pref`** | **1.0000** | **+2.56%** | **+2.56%** | **+1.66%** | **+1.66%** |
| **Demand-MPKI / LOAD+RFO MPKI** | 0 / 0 | -5.82% / -7.15% | — | -5.49% / -6.71% | — |

### 关键微架构诊断

对比无预取与开启预取两套复现，发现两个重要现象：
1. **基线加速与空间收敛**：开启预取后 `LRU` 在 `437.leslie3d`（0.6252 → 1.3478）、`450.soplex`（0.3097 → 0.4848）、`429.mcf`（0.3193 → 0.4503）上明显提速，替换策略可用绝对收益空间收窄。
2. **原版 `author2` 在现代 ChampSim 反被 `SHiP_pref` 拉开差距（+1.66% vs +2.56%）的根因**：
   现代 ChampSim 对 LLC 发送的 **MMU 页表游走请求（`TRANSLATION`）** 与 **L2C 脏块写回请求（`WRITE`）** 的 **`ip` 字段均为 `0`**，同时叠加大量 `L2C ip_stride` 预取流量：
   - **Zero-IP 结构性桶冲突与历史污染**：16 张感知机表中 14 张依赖 PC 索引，所有 `ip == 0` 的 `TRANSLATION`/`WRITE`/`PREFETCH` 请求集中哈希到桶 0，并将 `0` 不断推入 `pc_ring`；
   - **`TRANSLATION` 被灾难性旁路**：`author2` 在 `429.mcf` 上将 `TRANSLATION` 命中压低到 **385 / 170,392（0.23%）**，在 `437.leslie3d` 上降至 **1,175 / 8,417**，在 `483.xalancbmk` 上仍有 **95,119** 次页表游走未命中；
   - **旁路门限对称失配**：对高代价页表、`WRITE` 写回通道与高噪声 L2C 预取采用完全相同的 `thresh` 门槛，导致在 `437.leslie3d`（-2.46%）与 `470.lbm`（-1.46%）上出现明显性能回退。

---

## 5. 原创改进：TA-MPPPB（Translation- & Access-Aware MPPPB）

### 5.1 独创性与设计机制

与已有文献中主要面向通用特征缩减或新增采样器/预取签名比特表的思路（`MS-MPPPB`、`DS-MPPPB`、`Fit-MPPPB` 等）不同，**TA-MPPPB** 聚焦于现代处理器虚存页表游走、多级缓存回写与预取请求在 **Zero-IP 空间**引发的预测器混淆问题，**无需增加任何额外 SRAM 存储比特（仍为 60.41 KiB）**，通过环境变量 `MPPPB_IMPROVE=1` 启用（详见 [`docs/results_ta_mpppb.md`](results_ta_mpppb.md)）：

1. **页表游走（`TRANSLATION`）旁路免疫与伪 PC 解耦**：
   - `can_bypass` 中绝不旁路 `TRANSLATION`，插入时固定放置于 MRU（`idx = 0`）且命中时直接提升至 MRU；
   - 为 `ip == 0` 的 `TRANSLATION` 与 `ip == 0` 的 `PREFETCH` 构造确定物理页号伪指令地址 `0x9e3779b9ULL ^ (block >> 6U)` 作为 `eff_ip`，打破桶 0 拥塞；并在 `update_histories` 中阻止 `pc == 0` 进入 `pc_ring` 历史轨迹。
2. **保留创建者特征的写回（`WRITE`）采样反馈与写回旁路放宽**：
   - 在 `visit_sampler` 中当 L2C `WRITE` 命中此前由 `LOAD`/`RFO` 创建的采样项时，保留 `learn_reuse (-1)` 对原创建者特征键的负向 dead 权重修正，但在 LRU 移位后通过 `s.line[0] = previous` **复原创建者的键与复用分数**，避免 `ip == 0` 覆盖原创建指令语义；未命中采样器时不分配新项；
   - 适度放宽 `WRITE` 旁路阈值（无预取器 `thresh - 10`，有预取器 `thresh - 5`），减少不再读回的写回块驱逐关键读行。
3. **预取（`PREFETCH`）准入收紧**：
   - 将 `PREFETCH` 旁路阈值上调至 `thresh + 18`，使低自信度的投机预取行优先旁路 LLC，释放集合容量。

### 5.2 全量改进效果评估

#### A. 开启硬件预取器下反超 `SHiP_pref`（vs `LRU_pref` / `author2`）

| 策略 | Geomean IPC vs `LRU_pref` | 相对原版 `author2` 增益 | Demand-MPKI 变化 | LOAD+RFO MPKI 变化 | 典型单 trace 亮点 |
| --- | ---: | ---: | ---: | ---: | --- |
| `SHiP_pref` | +2.56% | — | -5.82% | -7.15% | `483.xalan`: 0.3720 |
| `MPPPB (author2)` | +1.66% | 0.00% | -5.49% | -6.71% | `483.xalan`: 0.3654, `470.lbm`: 0.6423 (-1.46%) |
| **`TA-MPPPB (ta_pref)`** | **+2.60%** | **+0.92%** | **-5.85%** | **-7.22%** | `470.lbm`: **0.6710 (+4.47%)**；`483.xalan`: **0.3721 (+1.82%)**；`450.soplex`: **0.5066 (+1.02%)** |

在开启预取器模式下，TA-MPPPB 将 `483.xalancbmk` 页表命中由 51.3%（100,068/195,187）大幅拉升至 **96.4%（188,010/195,083）**，将 `429.mcf` 页表命中由 0.23% 提升至 **16.4%（27,995/170,426）**，并使 `470.lbm` 从亏损 `-1.46%` 逆转为 **`+2.94%`**（相对 `author2` 净胜 **`+4.47%`**），整体以 **+2.60%** 超越原版 `+1.66%` 及 `SHiP_pref` `+2.56%`。

#### B. 无硬件预取器下全线提升（vs `LRU`）

- **`ta_nopref`（基于 `author1`）**：Geomean IPC 由 `+4.44%` 提升至 **`+4.56%`**，Demand-MPKI 由 `-9.02%` 降至 **`-9.60%`**（`470.lbm` +1.60%）；
- **`ta_c4`（基于 `c4`）**：Geomean IPC 由 `+4.53%` 提升至 **`+4.71%`**，Demand-MPKI 由 `-9.32%` 降至 **`-9.90%`**（`470.lbm` +2.19%，`437.leslie3d` +0.47%）。

### 5.3 关键消融：Write-Sampler Starvation 问题修复（v1 vs v2）

在初版 v1 中我们直接跳过 `WRITE` 对采样器的访问，虽缓解了零 IP 污染，却导致 `450.soplex-92B` 在无预取器下暴跌 `-2.47%`（`0.3577 → 0.3489`），使 `v1 ta_nopref` 仅得 `+4.25%`（低于基线）。日志与命中结构定位显示，在非包容 LLC 下 **91%–97% 的 L2C 写回会命中早期 `LOAD`/`RFO` 建立的采样器条目**；完全跳过导致 `learn_reuse (-1)` 训练枯竭（Write-Sampler Starvation）。v2 改用“**触发 `learn_reuse (-1)` 后原位还原创建者表项**”后，全面消除回归并实现三套配置同步正增长：

| 方案版本 | `ta_nopref` Geomean | `ta_c4` Geomean | `ta_pref` Geomean | `450.soplex` (`no-pref / c4 / pref`) |
| --- | ---: | ---: | ---: | --- |
| 原版静态基线 (`author1 / c4 / author2`) | +4.44% | +4.53% | +1.66% | 0.3577 / 0.3587 / 0.5014 |
| TA-MPPPB v1（直接跳过 WRITE 采样） | +4.25% | +4.55% | +2.48% | 0.3489 / 0.3498 / 0.4978 |
| **TA-MPPPB v2（保留创建者反馈）** | **+4.56%** | **+4.71%** | **+2.60%** | **0.3584 / 0.3588 / 0.5066** |

---

## 6. 多核可行性分析与局限性说明

论文多核评估使用 4 核、8 MB LLC、SRRIP、1000 个多道程序 mix、每线程 1B cycles（合计 4B cycles/run）。按实测仿真速率约 20 万 cycles/s 估算，完整 3000 次仿真需约 16,800 CPU-hours（即使 20 vCPU 并行仍需 ~35 天），受课程算力周期所限，本文聚焦单核 Static MDPP 全量复现（含无预取/有预取及原创改进共百余次 200M-instruction 全流程仿真），同时列出缩减版多核可行配置（10–30 个 4-trace mix × 200M cycles + 共享 256 组采样器与 Table 2 多核特征，约 ~33 CPU-hours）作为后续扩展方向。

---

## 7. 总结与实验产物索引

1. 完成 **MPPPB Single-Core Static MDPP** 在现代 ChampSim 下的完整复现：无预取器最优 `c4` 取得 **+4.53% IPC / -9.32% Demand-MPKI**；开启 `L1D next_line + L2C ip_stride` 预取器后原版 `author2` 为 **+1.66% IPC**，揭示了零 IP `TRANSLATION`/`WRITE`/`PREFETCH` 流量导致的性能折损机制。
2. 提出并实现零额外 SRAM 开销原创改进 **TA-MPPPB（`MPPPB_IMPROVE=1`）**，通过实验消融定位并解决 Write-Sampler Starvation 问题，最终将无预取器性能推升至 **+4.56%（`author1` 底座）/ +4.71%（`c4` 底座）**，并将开启预取器性能提升至 **+2.60% IPC（相对 `author2` +0.92%，反超 `SHiP_pref`）**。
3. **产物索引**：
   - 核心源码：[`champsim_modules/mpppb/mpppb.h`](../champsim_modules/mpppb/mpppb.h)、[`champsim_modules/mpppb/mpppb.cc`](../champsim_modules/mpppb/mpppb.cc)
   - 实验配置：[`configs/champsim_mpppb_mdpp.json`](../configs/champsim_mpppb_mdpp.json)、[`configs/champsim_mpppb_mdpp_pref.json`](../configs/champsim_mpppb_mdpp_pref.json)、[`configs/champsim_lru_pref.json`](../configs/champsim_lru_pref.json)、[`configs/champsim_ship_pref.json`](../configs/champsim_ship_pref.json)
   - 专题详报：[`docs/results_mdpp_author1.md`](results_mdpp_author1.md)、[`docs/results_mdpp_validate.md`](results_mdpp_validate.md)、[`docs/results_mdpp_pref.md`](results_mdpp_pref.md)、[`docs/results_ta_mpppb.md`](results_ta_mpppb.md)
   - 汇总结果与校验：[`results/mdpp_pref_results.csv`](../results/mdpp_pref_results.csv)、[`results/ta_mpppb_results.csv`](../results/ta_mpppb_results.csv)、[`scripts/verify_results.py`](../scripts/verify_results.py)
