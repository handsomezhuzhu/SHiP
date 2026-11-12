# SHiP++ 精读笔记与复现方案

论文：V. Young, C.-C. Chou, A. Jaleel, M. Qureshi,
*SHiP++: Enhancing Signature-Based Hit Predictor for Improved Cache Performance*,
CRC-2 Workshop @ ISCA 2017（第 2 名）。
本地：`papers/pdf/shipplusplus_crc17.pdf`（4 页扩展摘要）。

## 1. 一句话

在 SHiP 的 SHCT 框架上做 5 处增强：**更宽的插入点选择、更节制的 SHCT 训练、写回感知、
预取/需求分离的签名与提升策略**。单核无预取配置下相对 LRU 提升 6.2%（SHiP 为 3.8%），
相对 SHiP 提升 2.2%；开销 <20 KB。

## 2. 基线：RRIP + SHiP

- 每行 2-bit RRPV，命中置 0；miss 时从 way 0 开始找 RRPV=3 的行，找不到则全组 +1 再找。
- 插入点：RRPV=2（高优先级，SRRIP）或 3（低优先级）。
- SHiP：每行（只对采样组）附加 **14-bit 签名**（miss PC 的 hash）和 **R（reuse）位**；
  16K 项、3-bit 饱和计数器的 SHCT。
  - 行被命中：R 置 1，SHCT[sig] **递增**；
  - 行被逐出且 R=0：SHCT[sig] **递减**；
  - 插入：SHCT[sig]==0 → RRPV=3，否则 RRPV=2。

> 注意方向：论文的 SHCT 计的是"复用证据"，值越大越值得留在 cache。
> ChampSim 自带的 `replacement/ship` 用的是相反语义（命中递减、逐出递增，
> 饱和时插入 RRPV=3），两者不等价，复现时**不能直接拿它当 SHiP++ 基线**，
> 但可以当作 SHiP 的参考实现之一。

## 3. SHiP++ 的 5 处增强

| # | 名称 | 做法 |
|---|---|---|
| 1 | Improved Cache Insertion | SHCT 饱和到最大值（7）→ 直接插 RRPV=0；SHCT==0 → RRPV=3；其余 → RRPV=2 |
| 2 | Improved SHCT Training | 只在行的**第一次**复用时（R: 0→1）递增 SHCT，后续重复命中不再训练，避免"热行"过度训练 |
| 3 | Writeback-Aware RRPV | 写回（writeback）插入一律 RRPV=3，不让非需求数据长期占坑 |
| 4 | Prefetch-Aware SHCT | 签名改为 `(PC << 1) + is_prefetch`，demand / prefetch 共用一张 SHCT 但独立学习 |
| 5 | Prefetch-Aware RRPV | 每行加 `is_prefetched` 位；demand 首次命中预取行 → RRPV=3 并清位；prefetch 命中预取行 → 不改 RRPV |

## 4. 开销（Table 1）

| 组件 | 单核无预取 (C1) | 单核有预取 (C2) | 四核 8MB 无预取 (C3) | 四核 8MB 有预取 (C4) |
|---|---|---|---|---|
| RRPV (2b/line) | 8 KB | 8 KB | 32 KB | 32 KB |
| is_prefetched (1b/line) | 0 | 4 KB | 0 | 16 KB |
| SHCT (16K×3b/core) | 6 KB | 6 KB | 24 KB | 24 KB |
| 采样组签名+R（64 组） | 1.9 KB | 1.9 KB | 2.1 KB | 2.1 KB |
| 采样组 ID（64 项） | 128 B | 128 B | 128 B | 128 B |
| **合计** | **16 KB** | **20 KB** | **76 KB** | **92 KB** |

CRC-2 的预算是单核 32 KB / 四核 128 KB，均满足。

## 5. 原文实验设置

- 模拟器：ChampSim CRC2 版本
- benchmark：SPEC2006 中 MPKI ≥ 0.5 的 17 个 workload
- warmup 10 M 指令，timing 阶段每个 benchmark ≥100 M 指令
- 配置：C1(1 core/2 MB/no prefetch)、C2(1 core/2 MB/L1+L2 prefetch)、
  C3(4 core/8 MB/no prefetch)、C4(4 core/8 MB/prefetch)
- 指标：IPC，几何平均，归一化到 LRU
- 结果：C1 — SHiP 3.9%、SHiP++ 6.2%；C2 — SHiP++ 相对 LRU 4.6%、相对 SHiP 2.2%

## 6. 在 ChampSim（2026 develop）上的复现映射

### 6.1 需要的接口

ChampSim replacement 模块需实现（见 `replacement/ship/ship.h`）：

- `find_victim(cpu, instr_id, set, blocks, ip, addr, type)`
- `replacement_cache_fill(cpu, set, way, addr, ip, victim_addr, type)`
- `update_replacement_state(cpu, set, way, addr, ip, victim_addr, type, hit)`

`access_type` 可区分 `LOAD / RFO / WRITE / PREFETCH / TRANSLATION`：
`PREFETCH` 即预取，`WRITE` 即写回插入。

### 6.2 结构

```
SHCT[core][16384] : 3-bit 饱和计数器
rrpv[set][way]    : 2-bit
sampler[64 sets]  : {valid, addr, ip, R, is_prefetched}
PSEL?             : 不需要（SHiP++ 不 dueling）
```

采样：ChampSim 的 `msl::categorizer` / `get_num_samples` 已经提供 1/32 采样；
SHiP++ 用 64 个采样组（2 MB LLC / 2048 sets 时 1/32 正好 64 组）。

### 6.3 实现要点与坑

1. **SHCT 语义**：按论文"复用越多值越大"。插入时 0→3、7→0、其余→2。
   注意别照抄 ChampSim `ship` 的反向计数。
2. **只在第一次复用时训练**：用行内 R 位判断；命中时若 R==0 才 `SHCT++` 并置 R=1。
3. **采样组与非采样组**：所有组都要维护 RRPV；只有采样组的行需要签名+R 位
   （否则开销会变大）。插入时的预测用 SHCT[sig]，对所有组生效。
4. **写回**：`type == WRITE` 的 fill 直接 RRPV=3，且不要用 SHCT 预测。
5. **预取签名**：`sig = ((ip & 0x3fff) << 1) | is_prefetch`，再对 SHCT 取模。
6. **预取命中**：
   - demand 命中 `is_prefetched==1` 的行：RRPV=3、清 is_prefetched（仅第一次）；
   - prefetch 命中：RRPV 不变。
7. **多核**：每核私有 SHCT；采样组行需记录 core_id 才能更新正确的 SHCT。

### 6.4 复现计划

| 阶段 | 产出 |
|---|---|
| M1 | `replacement/shipp` 模块实现 + 单核 C1 配置跑通 |
| M2 | 用同一组 trace 跑 LRU / SRRIP / SHiP / SHiP++，对比 IPC 与 LLC MPKI |
| M3 | 拆解每个 enhancement 的贡献（消融实验） |
| M4 | 4 核共享 LLC 实验（对应 C3/C4） |
| M5 | 偏差分析：SPEC2006→2017、ChampSim 版本差异、采样数、trace 长度 |

### 6.5 验收标准（合理的复现目标）

- 趋势一致：SHiP++ > SHiP > LRU 的几何平均 IPC（允许个别 benchmark 反向）；
- 幅度不要求完全等于 6.2%/2.2%，但要在报告里解释差异来源；
- 至少给出 8 个以上 workload 的逐项数据 + 几何平均；
- 消融实验能说明"插入点"和"训练策略"各自贡献最大。

## 7. 可做的改进方向（Technical Report 加分项）

1. **SHCT 压缩**：16K×3b 的 SHCT 可以用 8K 项 + 哈希或两级表，观察精度损失；
   对应 CacheFit (2026) 对面积/功耗的批评。
2. **自适应采样**：固定 64 组在 phase change 时可能失效，可做动态采样或按冲突率调整。
3. **训练信号的延迟**：把"第一次复用"改成"首次 demand 复用 / 首次远距离复用"，
   或引入 Expected Hit Count 的软标签。
4. **预取器协同**：SHiP++ 只区分 demand/prefetch，未考虑预取准确率；
   可把预取器置信度并入签名。
5. **多核公平性**：共享 LLC 下按核 SHCT 可能加剧不公平，可尝试全局 SHCT + core-aware 插入。