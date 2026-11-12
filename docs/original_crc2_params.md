# 原始 MPPPB（CRC2 2017）参数摘录

来源：CRC2 官网 *Participants and Publications* 的 MPPPB 提交
`Multiperspective.zip` → `dancrc2.cc` → `set_parameters()`。
论文正文（MICRO-50 / CRC-2 短版）**没有给出 τ/π 的具体数值**，
只说“τ0 先穷举，τ1–τ3 和 π1–π3 用随机搜索”。

> 该文件是竞赛提交代码，不是论文模拟器的逐行复刻；
> 采样组数、set-dueling 等与论文正文有差异，使用时要注明。

## 1. 四套配置的硬编码值

| 配置 | 场景 | 底座 | bypass（τ0） | promotion（τ4） | placement `plv`（阈值→位置） | 默认放置 | training `threshold` | sampler 组数 | 特征集 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 单核 2 MB，无预取 | **MDPP** | dt1=56 / dt2=256（set-dueling） | 82 | -15→0，35→12，44→15（PLRU index） | 0 | 128 | 80 | `single_1` ≈ Table 1(a) |
| 2 | 单核 2 MB，有预取 | **MDPP** | dt1=42 / dt2=48 | 178 | 同上 | 0 | 128 | 80 | `single_2` |
| 3 | 4 核 8 MB，无预取 | **SRRIP** | dt1=27 / dt2=229 | 256 | -230→1，12→2，22→3（RRPV） | 2 | 0 | 308 | `multi_3` |
| 4 | 4 核 8 MB，有预取 | **SRRIP** | dt1=100 / dt2=154 | 256 | -111→0，-110→2，20→3（RRPV） | 2 | 0 | 337 | `multi_4` |

其它固定参数：

| 参数 | 值 |
|---|---|
| `dan_init_weight` | **1**（权重初值不是 0） |
| `dan_counter_width` | 6 bit（−32…+31） |
| `dan_predictor_index_bits` | 8 |
| `dan_predictor_tables` | 16 |
| `dan_sampler_assoc` | 18 |
| `dan_sampler_tag_bits` | 16 |
| `dan_samplers` | 配置 1/2：80；配置 3：308；配置 4：337 |
| `leaders1 / leaders2` | 32 / 64（set-dueling 的 leader set 边界） |
| `dan_record_types` | 27（LOAD+RFO+WRITEBACK+PREFETCH） |
| `dan_ignore_prefetch` | 1 |
| MDPP 提升向量 `vecmdpp` | `{0,1,2,3,4,5,6,7,0,1,2,3,0,1,0,0}` |

## 2. 关键语义（和我们现在实现不同）

1. **bypass 不是单一阈值**：代码里 `dan_bypass_threshold`（48 / −3）
   在 `dan_dt2 != 0` 时**不被使用**；实际是 set-dueling：
   `leaders1` 用 `dt1`，`leaders2` 用 `dt2`，其余 set 由 `psel` 决定用哪个。
   论文正文只描述“τ0 穷举搜索”，这是 CRC2 版本的增强。
2. **training 不是简单 `conf>0/<0`**：
   - `prediction = conf >= dan_threshold`（单核 128，多核 0）；
   - `correct = (prediction == d)`；
   - 只在 `!correct`，或置信度落在 deadzone
     （`-theta2 < conf < theta`，单核 theta=109/theta2=135，多核 0/0）时训练；
   - dead 只训练 `assoc == pos` 的特征；live 只训练 `assoc > pos` 的特征；
   - 权重初值 **1**。
3. **placement 的位置语义不同**：
   - 单核 MDPP 的 `plv` 值是 **PLRU index**（0…15 的树路径），
     不是线性 recency 位置；提升用 `vecmdpp` 做最小扰动，不是简单 MRU。
   - 多核 SRRIP 的 `plv` 值才是 RRPV 0…3。
4. **采样器组数**：代码是 80 / 308 / 337，论文写 64 / 256；
   代码用可逆矩阵 `mm` 把 cache set 打散到 sampler set。
5. **特征集**：代码有 4 套 × 16 = 64 个特征；
   `single_1` 接近论文 **Table 1(a)**，而我们 Matrix-1 用的是
   **Table 1(b)**。两者不同，不能直接假设结果一致。

## 3. 对我们的意义

- 我们现在猜的 c 组（250/150/75/0/100，π=3/3/2）与作者的实际值差很远；
  尤其单核作者用 `promotion=82`、`bypass≈56/256`、
  placement `-15→0 / 35→12 / 44→15`、`threshold=128`、权重初值 1。
- 多核作者用 SRRIP，τ/π 是 `22→3 / 12→2 / -230→1`，默认 2，
  bypass 27/229；我们多核可以用这组，不需要 MDPP。
- 但这些值只有在实现 **MDPP + 原始训练语义（init 1、deadzone、threshold 128）**
  后才有意义；直接套到我们当前 4 级 SRRIP + 0 阈值训练上，含义不同。
- 下一步建议：先按 `dancrc2.cc` 的 config 1 语义实现单核 MDPP，
  再用 config 3 的 SRRIP 参数做多核；不要继续用 c 组猜。

## 4. 引用

- CRC2 2017, *Participants and Publications*:
  <https://crc2.ece.tamu.edu/?page_id=53>
- MPPPB 提交 ZIP:
  <https://www.dropbox.com/s/k4x1bx7u5sklmbt/Multiperspective.zip?dl=1>
- 代码文件：`dancrc2.cc`（29 262 B），`set_parameters()`、`block_is_dead()`、
  `get_prediction()`、`update_plru_mdpp()`。
- 论文：D. Jiménez, E. Teran, *Multiperspective Reuse Prediction*,
  MICRO-50, 2017, §3.7/§4.3/§5.3。