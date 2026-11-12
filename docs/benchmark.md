# Benchmark 环境与实验记录

## 1. 使用的 workload

采用 **DPC-3 公开的 SPEC CPU2017 ChampSim trace**（`https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu/`）。
选择依据：SPEC CPU2017 是当前体系结构论文的主流 suite，DPC-3 的 trace 格式与 ChampSim 直接兼容，
且已经做过指令数截断（每条 trace 覆盖若干十亿条指令），适合固定 warmup/sim 窗口做可重复实验。

`scripts/get_traces.sh` 下载的子集（覆盖不同 cache 行为）：

| trace | 文件大小 | 主要特征 |
|---|---|---|
| `410.bwaves-945B` | 49 MB | 计算密集、流式访存，LLC 压力很小（MPKI ~0.01） |
| `400.perlbench-41B` | 178 MB | 整数/分支密集，前端压力大 |
| `403.gcc-16B` | 384 MB | 整数，指令 footprint 大 |
| `429.mcf-22B` | 534 MB | 指针追逐、随机访存，LLC 缺失率高（MPKI ~30） |
| `450.soplex-92B` | 561 MB | 浮点 + 稀疏矩阵，cache 行为混合 |
| `483.xalancbmk-127B` | 648 MB | C++ 虚函数/大工作集，LLC 压力大 |
| `470.lbm-1274B` | 693 MB | 网格计算，流式访存 |
| `437.leslie3d-134B` | 306 MB | 流体力学，中等 LLC 压力（首次下载失败，重试中） |

> 注：DPC-3 每个 benchmark 有多个 trace 切片（文件名末尾数字不同）。这里每个 benchmark 取 1 条，
> 目的是先搭起可跑通的矩阵，而不是一次性追求覆盖率。后续可按需补 2–3 条/benchmark。

## 2. 两套实验平台

### A. ChampSim（主力，周期级、有 IPC）

- 版本：`develop` @ `410cee62d9c429c043ea611325ce00e6c303be2a`
- 配置：`configs/champsim_<policy>.json`
  - 1 核，4 GHz，6-wide，352-entry ROB
  - L1I 32 KB / L1D 32 KB（8/12-way，4/5 cycle）
  - L2 256 KB（1024 sets × 8 way，10 cycle）
  - **LLC 2 MB（2048 sets × 16 way，20 cycle）**，无 prefetcher
  - LLC 替换策略：`lru` / `srrip` / `ship`，以及自研模块 `mpppb`（MPPPB，v0）
- 编译：`scripts/build_policies.sh` → `env/ChampSim/bin/champsim_{lru,srrip,drrip,ship}`
- 运行：`scripts/run_champsim.sh`（默认 warmup 50 M、仿真 150 M 指令，6 路并行）
- 汇总：`scripts/summarize_champsim.py` → `results/champsim_results.csv`（IPC、LLC access/miss/MPKI）

### B. 自研轻量 trace-driven 模拟器（快速迭代策略）

`sim/llc_sim.cpp`：只模拟容量与替换，不建模流水线，用于在实现新策略时**秒级**看趋势。

- L1D 32 KB 8-way LRU → L2 256 KB 8-way LRU → LLC 2 MB 16-way（策略可换）
- 输入：`xz -dc trace | sim/llc_sim --policy {lru,srrip,ship}`
- 输出：LLC access / miss / MPKI
- 与 ChampSim 的差异：SHiP 的 SHCT 不做 set sampling、写回/预取/RFO 的处理被简化、
  没有流水线（因此只用于相对趋势，不作为最终性能数据）

## 3. 实验方法

- warmup：50 M 指令（填满 cache / 训练 SHCT，不计入统计）
- 仿真：150 M 指令（统计 LLC 缺失、IPC）
- 多核实验（后续）：4 核，每核一条 trace，共享 LLC
- 重复性：ChampSim 确定性仿真；同一 trace + 同一配置结果可复现

## 4. 初步结果（自研模拟器，100 M 指令统计窗口）

| trace | LRU MPKI | SRRIP MPKI | SHiP MPKI | SHiP 相对 LRU |
|---|---|---|---|---|
| 410.bwaves | 0.0122 | 0.0122 | 0.0122 | 0 %（LLC 几乎不缺失） |
| 429.mcf | 29.7613 | 29.6410 | **21.8852** | **−26.5 %** |

结论（预期内）：SHiP 的收益集中在 LLC 压力大的 workload；对 bwaves 这类流式/低缺失
workload 没有区别。这也说明后续实验必须包含 mcf、xalancbmk、lbm 等高 MPKI 的 trace，
否则策略差异会被淹没。

> ChampSim 的 4 策略 × 8 trace 矩阵正在后台运行，结果会写入 `results/champsim_results.csv`。

### MPPPB v0 冒烟（warmup 2 M / sim 5 M）

| trace | LRU IPC | MPPPB(v0) IPC | LRU LLC miss | MPPPB LLC miss |
|---|---|---|---|---|
| 410.bwaves | 2.9545 | 2.9545 | 526 | 526 |
| 429.mcf | 0.4283 | 0.4317 | 93 994 | 97 011 |

阈值未调、底座先用 SRRIP，所以这组数据只验证环境可用，不作为实验结果。
详见 `docs/notes_mpppb.md`。

## 5. 已知偏差与后续工作

- **benchmark 代际差异**：MPPPB/SHiP 原文用 SPEC CPU2006，本文用 SPEC CPU2017；
  策略排序和收益幅度可能不同，报告里需要单独解释。
- **trace 数量**：目前每 benchmark 1 条，统计噪声较大；最终实验建议每 benchmark 2–3 条。
- **预取器**：当前关闭预取，无法体现 SHiP 在 prefetch 污染下的问题；若要复现
  Harmony/PACMan 相关工作或提出改进，需要加 `next_line` / `spp_dev` 配置。
- **多核**：单核结果不能代表共享 LLC 下的表现，后续补 4 核实验。
- **写入策略**：ChampSim 默认 write-allocate + RFO，自研模拟器做了简化。

## 6. 复现命令

```bash
# 1) 编译策略二进制
./scripts/build_policies.sh

# 2) ChampSim 矩阵（后台）
nohup ./scripts/run_champsim.sh > results/champsim_run.log 2>&1 &

# 3) 快速趋势（自研模拟器）
./scripts/run_llc_sim.sh

# 4) 查看汇总
column -s, -t results/champsim_results.csv | less
```