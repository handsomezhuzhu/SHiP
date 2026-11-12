#ifndef REPLACEMENT_MPPPB_H
#define REPLACEMENT_MPPPB_H

#include <array>
#include <cstdint>
#include <vector>

#include "cache.h"
#include "modules.h"
#include "msl/bits.h"
#include "msl/stat_methods.h"

// MPPPB: Multiperspective Perceptron Predictor with Bypass
// Jiménez & Teran, "Multiperspective Reuse Prediction", MICRO-50, 2017.
//
// 结构：
//   - 16 个参数化特征（论文 Table 1(b)，单线程版本）
//   - 每个特征一张 6-bit 有符号权重表，预测值 = 各表权重之和（正 = dead）
//   - 64 个采样组（1/32 sets，2 MB LLC），18-way，LRU 管理，存 partial tag /
//     上次 confidence / 特征索引向量 / 位置。采样率固定 1/32（论文：2 MB→64 组，
//     8 MB→256 组），不沿用 ChampSim msl 的 set-dueling 采样率。
//   - 训练：采样块被访问（且位置 < A）→ live，权重 -1；
//           位置越过该特征的 A 参数或被逐出 → dead，权重 +1
//   - 预测结果驱动 bypass / placement / promotion
//
// 当前版本（v0）说明：
//   * 底层替换暂时用 SRRIP（论文单核用 static MDPP，见 notes_mpppb.md 的 TODO）
//   * bypass 用 "插入到 RRPV=3 + 标记为 bypass" 近似（ChampSim 的 fill 路径
//     不支持真正跳过分配）
//   * 阈值/位置是占位默认值，需用 trace 搜索（论文未给出具体数值）
struct mpppb : public champsim::modules::replacement {
  enum feature_kind { F_PC, F_ADDR, F_BIAS, F_BURST, F_INSERT, F_LASTMISS, F_OFFSET };

  struct feature_spec {
    feature_kind kind;
    int A;   // 训练用的 recency cutoff
    int B;   // 起始 bit
    int E;   // 结束 bit
    int W;   // 第 W 个最近的 PC（PC 特征）
    bool X;  // 是否与当前 PC 异或
    int bits;  // 索引位宽（<=8）
    int size;  // 表大小
  };

  struct sample_entry {
    bool valid = false;
    uint16_t tag = 0;
    int16_t conf = 0;
    std::array<uint8_t, 16> idx{};
  };

  struct core_state {
    std::array<std::vector<int8_t>, 16> tables;             // 每个特征的权重表
    std::vector<std::array<sample_entry, 18>> sampler;      // num_samples × 18
    std::array<uint64_t, 32> pc_hist{};                     // PC 历史
    uint64_t hist_count = 0;
    uint8_t last_miss = 0;
  };

  static constexpr int NUM_FEATURES = 16;
  static constexpr int SAMPLER_WAYS = 18;
  static constexpr int MAX_RRPV = 3;
  static constexpr int MAX_WEIGHT = 31;
  static constexpr int MIN_WEIGHT = -32;

  // 阈值（正 = dead）。论文未给出数值，先给可调的默认值。
  int tau_bypass = 150;  // conf >= tau_bypass -> bypass
  int tau_p1 = 100;      // conf >= tau_p1 -> position π1
  int tau_p2 = 50;
  int tau_p3 = 0;        // conf <  tau_p3 -> MRU
  int tau_promote = 0;   // 命中时 conf >= 该值 -> 不提升

  long NUM_SET, NUM_WAY;
  long sample_rate_, num_samples_;

  std::vector<feature_spec> features;
  std::vector<core_state> cores;

  std::vector<int> rrpv_values;
  std::vector<uint8_t> bypassed;

  // 每个 set 上一次 miss 的预测结果（fill 时使用）
  std::vector<int16_t> pending_conf;

  // 每个 set 的 MRU 地址 / lastmiss，用于 burst/lastmiss 特征
  std::vector<uint64_t> mru_addr;
  std::vector<uint8_t> last_miss;

  explicit mpppb(CACHE* cache);

  long find_victim(uint32_t triggering_cpu, uint64_t instr_id, long set, const champsim::cache_block* current_set,
                   champsim::address ip, champsim::address full_addr, access_type type);
  void replacement_cache_fill(uint32_t triggering_cpu, long set, long way, champsim::address full_addr,
                              champsim::address ip, champsim::address victim_addr, access_type type);
  void update_replacement_state(uint32_t triggering_cpu, long set, long way, champsim::address full_addr,
                                champsim::address ip, champsim::address victim_addr, access_type type, uint8_t hit);

private:
  int& get_rrpv(long set, long way);
  uint8_t& get_bypassed(long set, long way);
  void build_features();
  uint8_t feature_index(const feature_spec& f, uint32_t cpu, uint64_t ip, uint64_t addr, bool insert, long set);
  int predict(uint32_t cpu, long set, uint64_t ip, uint64_t addr, bool insert, std::array<uint8_t, NUM_FEATURES>& idx);
  void sampler_update(uint32_t cpu, long set, uint64_t ip, uint64_t addr, bool insert, int conf,
                      const std::array<uint8_t, NUM_FEATURES>& idx);
  void train_dead(core_state&, const sample_entry&);
  void train_live(core_state&, const sample_entry&, int pos);
};

#endif