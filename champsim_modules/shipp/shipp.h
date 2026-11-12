#ifndef REPLACEMENT_SHIPP_H
#define REPLACEMENT_SHIPP_H

#include <array>
#include <cstdint>
#include <vector>

#include "cache.h"
#include "modules.h"
#include "msl/bits.h"
#include "msl/stat_methods.h"

// SHiP++: Enhancing Signature-Based Hit Predictor
// (Young, Chou, Jaleel, Qureshi, CRC-2 @ ISCA 2017)
//
// 实现要点：
//  - SHCT 为 16K 项 3-bit 饱和计数器，语义为"复用证据"（越大越值得保留）
//  - 只在行的第一次复用时训练 SHCT（R: 0 -> 1）
//  - 插入点：SHCT==7 -> RRPV=0；SHCT==0 -> RRPV=3；否则 RRPV=2
//  - 写回插入一律 RRPV=3
//  - 签名 = (PC << 1) | is_prefetch，demand/prefetch 分开学习
//  - demand 首次命中预取行 -> RRPV=3 并清除 prefetch 位；prefetch 命中不改 RRPV
struct shipp : public champsim::modules::replacement {
private:
  int& get_rrpv(long set, long way);
  uint8_t& get_prefetched(long set, long way);

public:
  static constexpr int maxRRPV = 3;
  static constexpr std::size_t SHCT_SIZE = 16384;
  static constexpr unsigned SHCT_PRIME = 16381;
  static constexpr unsigned SHCT_MAX = 7;

  struct sampler_entry {
    bool valid = false;
    bool R = false;            // 该行是否已经发生过一次复用
    bool is_prefetch = false;  // 该行是否由预取插入
    champsim::address address{};
    std::size_t sig = 0;
    uint64_t last_used = 0;
  };

  long NUM_SET, NUM_WAY;
  uint64_t access_count = 0;

  std::vector<sampler_entry> sampler;
  std::vector<int> rrpv_values;
  std::vector<uint8_t> prefetched;
  champsim::msl::categorizer<long> set_categorizer;
  champsim::data::bits sampler_tag_bits;

  // SHCT[cpu][signature]
  std::vector<std::array<uint8_t, SHCT_SIZE>> SHCT;

  explicit shipp(CACHE* cache);

  long find_victim(uint32_t triggering_cpu, uint64_t instr_id, long set, const champsim::cache_block* current_set, champsim::address ip,
                   champsim::address full_addr, access_type type);
  void replacement_cache_fill(uint32_t triggering_cpu, long set, long way, champsim::address full_addr, champsim::address ip, champsim::address victim_addr,
                              access_type type);
  void update_replacement_state(uint32_t triggering_cpu, long set, long way, champsim::address full_addr, champsim::address ip, champsim::address victim_addr,
                                access_type type, uint8_t hit);
};

#endif