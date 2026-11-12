# MPPPB 模块代码审查（2026-11-12）

审查对象：`champsim_modules/mpppb/{mpppb.h,mpppb.cc}`（v0），对照
`papers/pdf/mpppb_micro17.pdf`（MICRO-50, 2017）与
`papers/pdf/mdpp_hpca16.pdf`。

结论：**v0 能编译、能跑，但不是论文语义的正确实现**。主要问题集中在
特征索引、训练条件、放置位置映射和 bypass 语义。下面按严重程度列出，
修复状态在最后一列。

## A. 会导致结果方向错误的 bug（必修）

| # | 位置 | 问题 | 论文依据 | 修复 |
|---|---|---|---|---|
| A1 | `replacement_cache_fill` | 置信度越高（越"dead"）反而插到 RRPV=0（MRU）：`conf>=tau_p1 -> 0`，`conf<tau_p3 -> 0`，中间两档才 1/2 | §3.6：conf 超过 τ0 才 bypass；超过 τ1/τ2/τ3 分别放到 π1/π2/π3；低于 τ4 才放 MRU。置信度越高应越接近被逐出 | π1→RRPV=3，π2→2，π3→1，否则→0 |
| A2 | `feature_index` | `insert(16,1)`、`insert(6,1)`、`bias(6,1)` 的 X=1 被忽略：insert 仍是 2 项表，bias 用 `ip & 0xff` | §3.2：X=true 时把"当前访存指令 PC"与特征位异或；§3.4：用 PC/地址/XOR 的特征生成 8-bit 索引（256 项） | X=1 时索引位宽 8、表 256 项，先 XOR 当前 PC 再折叠 |
| A3 | `feature_index` F_PC | PC 历史下标 `hist_count-1-W`，比"第 W 个最近"多退一条 | §3.2：W=0 是当前指令，W=1 是上一条 | 改为 `hist_count-W`（W≥1） |
| A4 | `sampler_update` | 采样器 LRU 逐出时把"所有特征"+1；论文明确说逐出本身不训练 | §3.8："Evictions from the sampler have no special significance"；只在放置/命中、以及块被降级越过某个 A 时训练 | 删除逐出时的全特征 +1 |
| A5 | `train_live/train_dead` | 无条件更新权重，没有用采样条目里保存的 9-bit confidence 做"预测错才训练" | §3.8 + §3.1：perceptron 规则，sum 对 dead 仍 <0 或对 live 仍 >0 才调整 | 用条目内 `conf`：live 仅当 conf>0 时 −1；dead 仅当 conf<0 时 +1 |
| A6 | `feature_index` F_PC/F_ADDR | 所有特征都过一遍 `mix64`（Murmur finalizer），包括本来 ≤8 bit 的 offset；索引分布与论文的"取 B..E 位"不一致 | §3.4：PC/地址/XOR 特征生成 8-bit 索引；offset 最多 64 项 | 位宽 ≤ 索引位宽时直接取位；超过时用 XOR 折叠；去掉 Murmur |
| A7 | 采样器 partial tag | `(addr>>6)&0xffff` 把 set index 位也算进 tag；2048 set 时只有约 5 bit 真正区分块，别名严重 | §3.3：16-bit partial tag | 用 set index 之上的 tag 位：`addr >> (OFFSET_BITS + log2(NUM_SET))` |
| A8 | hit 路径 | bypass 标记从不清除，被 bypass 的行一旦被命中仍然"优先逐出" | bypass 的语义是"预测不会再被用"；命中即推翻该预测 | 命中时清 bypass 标记 |
| A9 | `pending_conf` | 每个 set 只存一个 confidence；同一 set 多个未完成 miss 会互相覆盖，fill 用错预测 | — | 每 set 一个按地址匹配的小队列，fill 时按地址取 |
| A10 | `F_BURST` | 用 `mru_addr[set] == addr`，而 `mru_addr` 是"上一次任意访问地址"，不是 MRU 块 | §3.2(4)：burst 当且仅当本次访问的是 MRU 块 | 改为每 set 维护 `mru_block_` |

> 以上 A1–A10 已在重写版 `champsim_modules/mpppb/{mpppb.h,mpppb.cc}` 中修复。
> 另外补了两个实现层面的修正：
> - A11：训练条件从严格 `>`/`<` 改为 `>=`/`<=`。权重初值全 0 时严格不等式会让
>   预测器**永远不学习**（v0 的隐蔽致命 bug）；0 视为一次错误，才能自举。
> - A12：`replacement_cache_fill` 的置信度改为按 `(set, block)` 队列匹配；
>   实测 mcf 2 M 窗口 86 629 次 fill 全部命中，无覆盖。
> - A13：为让 offset 特征能看到块内偏移，给 ChampSim 的
>   `cache.cc` 打了 2 行补丁，把未对齐地址传给 replacement 模块
>   （`find_victim` 本来就已经收到未对齐地址）。补丁位置有注释，可单独回退。

## B. 保真度/建模偏差（需在报告里写明）

| # | 内容 | 现状 | 论文 | 处理 |
|---|---|---|---|---|
| B1 | 底座替换策略 | SRRIP（4 个位置） | 单核 static MDPP（16 个位置 + 树状 pseudo-LRU） | v1 保留 SRRIP，报告明确；MDPP 作为 v2 |
| B2 | bypass | 插入到 RRPV=3 并标记优先逐出，块仍占 LLC | 真正不分配（bypass 到核内 cache） | 近似，报告写明 |
| B3 | PC 历史 | 只记录 LLC 访问 | 每个 memory access 都更新 | 近似，报告写明 |
| B4 | τ0..τ4, π1..π3 | 占位默认 150/100/50/0/0 | 论文未给数值，搜索得到 | 保留环境变量覆盖，需搜索并记录 |
| B5 | 采样组数 | 64 组（1/32 sets） | 2MB→64 组，8MB→256 组 | 一致 |
| B6 | 权重表项数 | 按索引位宽生成 | 8-bit 表 256 项、offset ≤64、单 bit 2 项、bias 1 项 | 修复后一致 |
| B7 | 写回 fill | `type==WRITE` 一律低优先级、不预测 | 写分配 miss 也应由预测器决定 | 删除该特判；PREFETCH 才走默认位置 |
| B8 | 采样器条目 | int16 conf + 16B idx | 9-bit conf + 118-bit idx + 4-bit recency | 位宽按实现放宽，不影响功能 |

## C. 代码质量与可维护性

- `feature_spec.bits` 字段从未使用；`size` 与位宽冗余。
- `pending_conf`、`mru_addr`、`last_miss` 三套 per-set 状态命名混乱（`last_miss` 既是成员又是局部）。
- `sampler_update` 的 hit/miss 两个分支重复了 20 行移位代码。
- 环境变量阈值没有做 `τ0 ≥ τ1 ≥ τ2 ≥ τ3` 的校验，搜索脚本可能生成非法组合。
- `tune_mpppb.py` 用 `/tmp` 固定路径 + 随机数，Windows/WSL 下要注意。
- **抄袭风险**：v0 的 `find_victim`/`update_replacement_state` 骨架与 ChampSim 自带 `ship.cc`/`srrip.cc` 高度相似（模块 API 必需的部分除外）。本次重写改为"预测器 / 采样器 / 放置"三段式结构，命名和注释全部重做；论文没有公开代码，特征参数属于论文事实，不构成代码抄袭。

## D. 重写后的实现要点

1. `predictor`：16 条 `feature` 描述（表 1(b)），每条含 A/B/E/W/X 与索引位宽；
   权重表按需 1/2/32/64/256 项。
2. `sampler`：64 组 × 18 路，真 LRU；条目保存 partial tag、上次 confidence、
   特征索引向量；只在 sampled set 上更新。
3. 训练：live（位置 < A 且 conf>0）−1；demote 越过 A（且 conf<0）+1；
   饱和 [−32,+31]；采样器逐出不训练。
4. 决策：conf ≥ τ0 → bypass 近似；τ1/τ2/τ3 → 位置 3/2/1；< τ4 → MRU；
   hit 且 conf ≥ τ4 → 不提升。
5. 历史：LLC 访问 PC 环形缓冲、每 set 的 lastmiss 与 MRU tag。
6. 待定预测按 (set, addr) 队列匹配，消除 fill 乱序覆盖。

## E. 验证计划

| 步骤 | 内容 | 判据 |
|---|---|---|
| E1 | 编译（WSL Ubuntu / instabox） | `bin/champsim_mpppb` 生成 |
| E2 | 单元级 sanity | 单 set 手工 trace：冷启动 fill 的 RRPV 符合 τ 分档；采样器 18 路 LRU 位置正确 |
| E3 | 冒烟 | 2M warmup + 5M sim，mcf/bwaves，无 crash，MPKI 合理 |
| E4 | 小窗口对比 | 20M+20M，LRU/SHiP/MPPPB，mcf/xalancbmk |
| E5 | 正式矩阵 | 50M warmup + 150M，8 trace × 3 策略 |
| E6 | 阈值搜索 | 2 条 trace，20M 窗口，随机 20–30 组；报告记录 |