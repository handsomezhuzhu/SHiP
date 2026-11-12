# MPPPB 精读笔记与复现方案

论文：D. A. Jiménez, E. Teran, *Multiperspective Reuse Prediction*,
MICRO-50（2017），pp. 436–448，DOI `10.1145/3123939.3123942`。
本地：`papers/pdf/mpppb_micro17.pdf`（13 页）；CRC-2 短版 `mpppb_crc17.pdf`。
策略名：**MPPPB = Multiperspective Perceptron Predictor with Bypass**。

## 1. 一句话

用 **16 个参数化特征**（7 种类型 × 不同参数）索引 16 张 6-bit 权重表，求和得到
"这个块有多大概率已经 dead"的置信度；置信度同时驱动 **bypass、placement、promotion**
三个决策。预测器用一个 64 组 × 18 路的采样器在线训练。

## 2. 预测器结构

| 组件 | 规格 |
|---|---|
| 特征 | 7 种类型：`pc / address / bias / burst / insert / lastmiss / offset`，每类带参数 `(A, B, E, W, X)` |
| 权重表 | 每个特征一张表，6-bit 有符号（−32…+31） |
| 表大小 | PC/address/XOR 特征 256 项（8-bit 索引）；offset ≤64；单 bit 特征 2 项；bias 1 项 |
| 置信度 | 16 张表权重之和（论文用 9-bit 有符号保存） |
| 采样器 | 64 个采样组（1/32 sets，2 MB LLC），**18 路**，LRU 管理；与主 cache 结合度不同 |
| 采样条目 | 16-bit partial tag、9-bit 上次置信度、特征索引向量（单核 118 bit）、4-bit recency |
| 默认替换 | 单核：static MDPP（16 个位置，15 bit/set）；多核：SRRIP |

### 特征参数含义

- `A`：训练用的 recency cutoff（相当于"有效结合度"）；
- `B..E`：取 PC / 地址的哪些 bit；
- `W`：第 W 个最近的访存指令 PC（`W=0` 表示当前）；
- `X`：是否与当前 PC 异或（把特征"打散"到不同表项）。

论文 Table 1(b) 的单线程 16 个特征（本仓库 v0 直接采用）：

```
address(11,8,19,0)   bias(6,1)
insert(15,0)         insert(16,1)
insert(6,1)          offset(15,1,6,1)
offset(15,3,7,0)     pc(11,2,24,4,1)
pc(15,14,32,6,0)     pc(15,5,28,0,1)
pc(16,0,16,8,1)      pc(17,6,20,0,1)
pc(6,12,14,10,1)     pc(7,1,24,11,0)
pc(7,14,43,11,0)     pc(8,1,61,11,0)
```

## 3. 训练

采样器里每个块记录"插入时的特征索引向量"。训练是**按特征选择性**的：

- **live**：采样块被访问，且其 recency 位置 `< A_i` → 该特征权重 −1；
  位置已经 ≥ A_i 的，不训练为 live（因为若主 cache 结合度只有 A_i，它早该被逐出）。
- **dead**：块被 demote 到位置 `A_i` 时 → 该特征权重 +1；
  块被完全逐出采样器（位置 18）→ 所有特征 +1。
- 权重饱和在 [−32, +31]。

因此同一次访问可能让一些表 +1、一些表 −1、一些表不动。

## 4. 预测驱动三个决策

设置信度 `c`（正 = dead）：

- miss 且 `c > τ0` → **bypass**（不占 LLC）；
- 否则按 `τ1, τ2, τ3` 分档，插入到位置 `π1 / π2 / π3`；
- `c < τ4` → 插到 **MRU**；
- hit 且 `c > τ4` → **不提升**（保持原位置）。

论文明确说 `τ0…τ3, π1…π3` 是**搜索出来的**（先穷举 τ0，再随机搜索其余），
但**没有给出具体数值**——这是复现时最大的不确定点，需要我们自己调。

## 5. 开销与结果

- 单核 27.5 KB：采样器 20.67 KB + 16 张表 2.64 KB + 特征向量 0.44 KB + MDPP 3.75 KB；
- 四核 104 KB；
- 评测（论文自己的模拟器）：4-wide OoO、128-entry window、L1D 32 KB 8-way、
  L2 256 KB 8-way、L3 2 MB（多核 8 MB）、DRAM 200 cycles、stream prefetcher（16 streams）；
  SPEC CPU2006 的 99 个 segment + 其他 workload，simpoint 方法，
  单核 warmup 500 M 指令、测量 1 B 指令；多核按 FIESTA 方法混合 1000 组 workload；
- 结果：单核几何平均 **+9.0%** over LRU（Hawkeye +5.1%，Perceptron +6.3%）；
  四核加权 speedup **+8.3%**（Hawkeye +5.2%，Perceptron +5.8%）。

## 6. 在 ChampSim 上的复现映射

| 论文 | 本仓库 v0 | 备注 |
|---|---|---|
| 自研模拟器 | ChampSim develop | 流水线/cache 参数接近，但不完全一致 |
| SPEC CPU2006 99 segments | DPC-3 SPEC CPU2017 trace | 代际差异，已在 `docs/benchmark.md` 记录 |
| static MDPP（16 位置） | **SRRIP（4 位置）** | v0 先用 SRRIP；MDPP 列为 TODO |
| 真正的 bypass（不分配） | 插入到 RRPV=3 + bypass 标记，下次优先逐出 | ChampSim fill 路径不支持"跳过分配" |
| 阈值/位置 | 占位默认值（`tau_bypass=150, tau_p1=100, tau_p2=50, tau_p3=0, tau_promote=0`） | 需要 trace 搜索 |
| 采样器 64×18 | 64×18（1/32 sets） | 已实现 |
| 16 特征 | Table 1(b) 硬编码 | 可加 Table 1(a) / Table 2（多核） |

### 已知偏差

1. **MDPP vs SRRIP**：位置数从 16 降到 4，插入/提升的粒度变粗；
2. **bypass 近似**：多一次 fill，且"被 bypass 的行"仍可能被命中；
3. **阈值未调**：v0 的数值只是让程序能跑，不能作为最终结果；
4. **workload 代际**：SPEC2017 vs 2006，绝对收益不可直接对比；
5. **PC 历史**：v0 在 LLC 访问上更新历史；论文是"每个 memory access"更新，
   在 trace 里两者几乎等价，但严格说不同。

## 7. 当前 v0 状态

- 源码：`champsim_modules/mpppb/{mpppb.h,mpppb.cc}`
- 配置：`configs/champsim_mpppb.json`；编译：`scripts/build_mpppb.sh`
- 二进制：`env/ChampSim/bin/champsim_mpppb`（编译通过）
- 冒烟测试（warmup 2 M / sim 5 M）：

| trace | 策略 | IPC | LLC miss |
|---|---|---|---|
| 410.bwaves | LRU | 2.9545 | 526 |
| 410.bwaves | MPPPB(v0) | 2.9545 | 526 |
| 429.mcf | LRU | 0.4283 | 93 994 |
| 429.mcf | MPPPB(v0) | 0.4317 | 97 011 |

bwaves 的 LLC 几乎不缺失，两者相同；mcf 上 v0 的 IPC 略好但 miss 更多，
符合"阈值未调 + SRRIP 底座"的预期。**这组数字只用于验证环境，不是实验结果。**

## 8. 下一步（按优先级）

> 实验范围（已确认）：**MPPPB vs SHiP vs LRU**；SHiP++ 不再实现。
> 论文本身主要对比 LRU / Hawkeye / Perceptron（+ MIN oracle），SHiP 只作同族参照，
> 报告里需要说明这一差异。


1. **阈值/位置搜索**：固定 2 条 trace（mcf、xalancbmk）+ 20 M 指令，
   网格/随机搜索 `τ0..τ4` 与 `π1..π3`，目标是 LLC MPKI；
   可用 ChampSim 的 `--json` 批量跑，或把预测器移植到 `sim/llc_sim` 做快速搜索。
2. **实现 static MDPP**：16 个 recency 位置 + 树状 pseudo-LRU（论文 HPCA'16，
   本地 `mdpp_hpca16.pdf`），替换 v0 的 SRRIP 底座。
3. **真正的 bypass**：改 ChampSim `cache.cc` 的 fill 路径，或在 replacement 接口上
   增加"skip fill"能力（需要小改核心代码，单独分支）。
4. **换 Table 1(a) / Table 2**：单核两套特征可做交叉验证；多核用 Table 2。
5. **完整实验矩阵**：LRU / SRRIP / SHiP / MPPPB × 8 trace，
   单核 + 4 核，无预取 + `next_line` 预取。
6. **偏差分析**：SPEC2017 vs 2006、MDPP vs SRRIP、采样组数、trace 长度。

## 9. 复现验收标准

- MPPPB 的几何平均 IPC **高于 LRU 和 SHiP**；
- 论文的主对比是 Hawkeye（+5.1%）和 Perceptron（+6.3%）；若时间允许，补 Hawkeye 作为对照更贴近原文；
- 至少 8 个 workload 的逐项结果 + 几何平均；
- 阈值/位置搜索有记录（说明不是碰巧调出来的）；
- 对偏差（底座、workload、bypass 近似）有量化解释。