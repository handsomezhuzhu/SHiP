# Single-Core Static MDPP With-Prefetcher Reproduction (`mdpp_pref`)

本文档记录在**启用硬件预取器**（L1D `next_line` + L2C `ip_stride`）条件下，对 **Single-Core Static MDPP (`MPPPB_PROFILE=author2`)** 与对照基线（`LRU_pref`、`SHiP-PC_pref`）的 8 条 SPEC CPU2006 trace 完整复现与对比分析。

## 1. 实验配置与可复现性

- **仿真器与构建**：Modern ChampSim（2 MiB 16-way 2048-set LLC，单核 4-wide OoO，`L1D: next_line` + `L2C: ip_stride` 硬件预取器）。
- **配置文件**：
  - 基线 LRU：`configs/champsim_lru_pref.json`
  - 对照 SHiP-PC：`configs/champsim_ship_pref.json`
  - MDPP `author2`：`configs/champsim_mpppb_mdpp_pref.json`（运行时环境变量 `MPPPB_PROFILE=author2`，对应作者带预取器的 16 组特征与阈值参数：启用预取特征且未启用 `MPP` 旁路优化或独立改进开关，与原始 MDPP 在无改进开关下保持 bit-identical）。
- **工作负载与窗口**：8 条 SPEC CPU2006 访存敏感代表性 trace，每条运行 **50M instructions warmup + 150M instructions simulation**（24 组 run 全部通过 `scripts/verify_results.py` 校验：`instructions` ∈ `[150,000,000, 150,000,020]`，`bad NONE`）。
- **汇总数据**：[`results/mdpp_pref_results.csv`](../results/mdpp_pref_results.csv)（原始输出位于 `results/raw/mdpp_pref/`）。

---

## 2. 逐 Trace 性能与缺失率对比（With-Prefetcher）

> 说明：由于 MPPPB 具有 LLC 旁路机制，L2C 写回（`WRITE`）和猜测性预取的旁路会增加“全请求 MPKI（All-MPKI）”，但核心阻塞由需求访问决定。下表同时给出：
> - **All-MPKI**：`LOAD + RFO + WRITE + PREFETCH + TRANSLATION` 全部 LLC miss / kInst；
> - **Demand-MPKI**：`LOAD + RFO + PREFETCH + TRANSLATION` 的 LLC miss / kInst；
> - **LOAD+RFO MPKI**：仅核心直接发射的需求读/写缺失（`LOAD + RFO`）/ kInst。

| Trace | `LRU_pref` IPC | `SHiP_pref` IPC | `ΔIPC vs LRU_pref` | `MPPPB (author2)` IPC | `ΔIPC vs LRU_pref` | `All-MPKI` (`LRU / SHiP / MPPPB`) | `Demand-MPKI` (`LRU / SHiP / MPPPB`) | `LOAD+RFO MPKI` (`LRU / SHiP / MPPPB`) |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `400.perlbench-41B` | 1.3735 | 1.3929 | +1.41% | **1.4005** | **+1.97%** | 0.777 / 0.681 / **0.660** | 0.775 / 0.673 / **0.626** | 0.352 / 0.278 / **0.258** |
| `403.gcc-16B` | **2.2054** | 2.2052 | -0.01% | 2.2044 | -0.05% | 0.216 / 0.218 / 0.219 | 0.215 / 0.217 / 0.217 | 0.095 / 0.095 / 0.096 |
| `410.bwaves-945B` | 2.9747 | 2.9747 | +0.00% | 2.9747 | +0.00% | 0.019 / 0.019 / 0.019 | 0.019 / 0.019 / 0.019 | 0.017 / 0.017 / 0.017 |
| `429.mcf-22B` | 0.4503 | **0.4546** | **+0.96%** | 0.4521 | +0.40% | 37.477 / 39.175 / 40.128 | 37.463 / **37.235** / 37.405 | 18.452 / **18.306** / 18.324 |
| `437.leslie3d-134B` | **1.3478** | 1.3476 | -0.01% | 1.3146 | -2.46% | 7.701 / 8.478 / 9.530 | 7.685 / **7.668** / 8.173 | 1.641 / **1.585** / 1.650 |
| `450.soplex-92B` | 0.4848 | **0.5080** | **+4.77%** | 0.5014 | +3.43% | 28.961 / **26.632** / 28.187 | 28.953 / **24.923** / 25.547 | 12.196 / **10.998** / 11.154 |
| `470.lbm-1274B` | **0.6518** | 0.6513 | -0.07% | 0.6423 | -1.46% | 28.608 / 34.098 / 30.822 | 28.608 / **28.576** / 28.637 | 25.019 / **24.988** / 25.010 |
| `483.xalancbmk-127B` | 0.3258 | **0.3720** | **+14.20%** | 0.3654 | +12.18% | 38.413 / **31.901** / 32.034 | 38.409 / **31.875** / 32.010 | 19.320 / **15.568** / 16.374 |
| **Geomean vs `LRU_pref`** | **1.0000** | **1.0256** | **+2.56%** | **1.0166** | **+1.66%** | **-0.93% (`SHiP`) / -0.05% (`MPPPB`)** | **-5.82% (`SHiP`) / -5.49% (`MPPPB`)** | **-7.15% (`SHiP`) / -6.71% (`MPPPB`)** |

---

## 3. 无预取器 vs 开启硬件预取器对照与成因分析

### 3.1 预取器对基准性能与替换策略收益空间的影响

对比本项目的无预取器实验（见 [`docs/results_mdpp_author1.md`](results_mdpp_author1.md)）与本次开启硬件预取器对照：

| 模式 | `LRU` 典型高访存 trace IPC 范围 | `SHiP-PC` Geomean IPC 增益 | `MPPPB (author1/2)` Geomean IPC 增益 |
| --- | --- | --- | --- |
| **无预取器** (`no-pref`) | `mcf` 0.3193, `leslie3d` 0.6252, `soplex` 0.3097, `xalancbmk` 0.2588 | **+4.30%** | **+4.44%** (`c4`: +4.53%) |
| **开启硬件预取器** (`L1D next_line + L2C ip_stride`) | `mcf` 0.4503, `leslie3d` 1.3478, `soplex` 0.4848, `xalancbmk` 0.3258 | **+2.56%** | **+1.66%** |

1. **基线抬升与收益空间压缩**：开启 `L1D next_line + L2C ip_stride` 后，`LRU` 基线在流式与规则跨步负载上大幅提速（如 `437.leslie3d` 从 `0.6252` 翻倍至 `1.3478`，`450.soplex` 从 `0.3097` 升至 `0.4848`，`429.mcf` 从 `0.3193` 升至 `0.4503`），原本依赖 LLC 缓存挽留的时间延迟被预取隐藏，因此 LLC 替换策略相对 `LRU_pref` 的几何平均加速比自然收敛（与 Jiménez & Teran, MICRO 2017 第 9、12 图关于有/无预取器收益收敛的趋势一致）。
2. **`MPPPB (author2)` 在现代 ChampSim 下落后于 `SHiP_pref`（+1.66% vs +2.56%）的微架构根因**：
   按“开启预取器”逐请求类型拆解 `results/raw/mdpp_pref` 中的命中统计，可以精确定位原始 `author2` 在现代 ChampSim（CRC2 → 现代分支的演进环境）中的三类退化源：

   | 请求类型 / 负载 | `LRU_pref` 命中 / 访问 | `SHiP_pref` 命中 / 访问 | `MPPPB (author2)` 命中 / 访问 | 退化表现 |
   | --- | --- | --- | --- | --- |
   | `TRANSLATION` (`429.mcf`) | 13,651 / 170,436 | 5,422 / 170,396 | **385 / 170,392** | 页表游走命中率跌至 **0.23%** |
   | `TRANSLATION` (`437.leslie3d`) | 4,278 / 8,424 | 3,146 / 8,419 | **1,175 / 8,417** | 丢掉大量页表复用 |
   | `TRANSLATION` (`450.soplex`) | 14,935 / 39,837 | 12,114 / 39,740 | **10,424 / 39,769** | 页表游走命中低于 SHiP 与 LRU |
   | `TRANSLATION` (`483.xalancbmk`) | 18,823 / 195,126 | 67,548 / 195,209 | **100,068 / 195,187** | 仍有近半（~48.7%）页表访问未命中 |
   | `PREFETCH` (`437.leslie3d`) | 171,403 / 1,073,798 | 166,396 / 1,073,513 | **102,616 / 1,073,794** | 对流式预取预测失准（-2.46% IPC） |
   | `WRITE` (`470.lbm`) | 3,199,911 / 3,199,911 | 2,371,587 / 3,199,901 | **2,872,220 / 3,199,912** | `470.lbm` IPC 下跌 `-1.46%` |

   深层原因在于：现代 ChampSim 向 LLC 发送的页表转换请求（`TRANSLATION`）以及 L2C 脏块写回（`WRITE`）所携带的指令指针 **`ip` 均为 `0`**，且大量 `ip == 0` 请求涌入感知器与采样器后：
   - **Zero-IP 桶冲突与特征污染**：16 张感知器特征表中有 14 张直接依赖 `pc`（包含 `pc_ring` 移位历史）。`ip == 0` 的 `TRANSLATION` 与 `WRITE` 一方面全部挤占 `pc == 0` 表项，另一方面还将大量 `0` 移入 `pc_ring`，稀释真实指令 PC 轨迹。
   - **关键页表游走（`TRANSLATION`）被误旁路**：在指针密集或大工作集程序（`mcf`、`soplex`、`xalancbmk`、`leslie3d`）中，页表项被 `ip == 0` 的负分波及并被 MPPPB 的旁路规则直接旁路，每次缺失都引发多级 PTW 停顿。
   - **预取与写回的旁路策略对称失配**：原始 MPPPB 对 `LOAD/RFO/WRITE/PREFETCH/TRANSLATION` 使用同一套 `thresh` 阈值（在写回或猜测性预取高占比环境下容易把高价值需求行或页表行挤出 LLC）。

上述定位直接催生了本项目的原创改进方案 **TA-MPPPB（Translation- & Access-Aware MPPPB）**，详见 [`docs/results_ta_mpppb.md`](results_ta_mpppb.md)。
