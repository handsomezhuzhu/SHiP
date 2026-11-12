#include "mpppb.h"

#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <cstring>

#include "champsim.h"

namespace
{
inline uint32_t mix64(uint64_t x)
{
  x ^= x >> 33U;
  x *= 0xff51afd7ed558ccdULL;
  x ^= x >> 33U;
  x *= 0xc4ceb9fe1a85ec53ULL;
  x ^= x >> 33U;
  return static_cast<uint32_t>(x);
}

inline uint64_t bits_between(uint64_t v, int b, int e)
{
  const int width = e - b + 1;
  if (width <= 0)
    return 0;
  if (width >= 63)
    return v >> b;
  return (v >> b) & ((1ULL << width) - 1ULL);
}
} // namespace

mpppb::mpppb(CACHE* cache)
    : replacement(cache), NUM_SET(cache->NUM_SET), NUM_WAY(cache->NUM_WAY),
      sample_rate_(NUM_SET >= 32 ? 32 : 1), num_samples_(NUM_SET >= 32 ? NUM_SET / 32 : NUM_SET),
      rrpv_values(static_cast<std::size_t>(NUM_SET * NUM_WAY), MAX_RRPV),
      bypassed(static_cast<std::size_t>(NUM_SET * NUM_WAY), 0),
      pending_conf(static_cast<std::size_t>(NUM_SET), 0),
      mru_addr(static_cast<std::size_t>(NUM_SET), 0),
      last_miss(static_cast<std::size_t>(NUM_SET), 0)
{
  build_features();

  // 阈值可用环境变量覆盖，方便批量搜索（论文未给出具体数值）
  auto env_int = [](const char* name, int& dst) {
    if (const char* v = std::getenv(name))
      dst = std::atoi(v);
  };
  env_int("MPPPB_TAU_BYPASS", tau_bypass);
  env_int("MPPPB_TAU_P1", tau_p1);
  env_int("MPPPB_TAU_P2", tau_p2);
  env_int("MPPPB_TAU_P3", tau_p3);
  env_int("MPPPB_TAU_PROMOTE", tau_promote);

  cores.resize(NUM_CPUS);
  for (auto& st : cores) {
    for (int i = 0; i < NUM_FEATURES; ++i)
      st.tables[i].assign(static_cast<std::size_t>(features[i].size), 0);
    st.sampler.assign(static_cast<std::size_t>(num_samples_), {});
  }
}

void mpppb::build_features()
{
  // 论文 Table 1(b)：单线程特征集
  features = {
      {F_ADDR, 11, 8, 19, 0, 0, 8, 256},
      {F_BIAS, 6, 0, 0, 0, 1, 8, 256},
      {F_INSERT, 15, 0, 0, 0, 0, 1, 2},
      {F_INSERT, 16, 0, 0, 0, 1, 1, 2},
      {F_INSERT, 6, 0, 0, 0, 1, 1, 2},
      {F_OFFSET, 15, 1, 6, 0, 1, 6, 64},
      {F_OFFSET, 15, 3, 7, 0, 0, 5, 32},
      {F_PC, 11, 2, 24, 4, 1, 8, 256},
      {F_PC, 15, 14, 32, 6, 0, 8, 256},
      {F_PC, 15, 5, 28, 0, 1, 8, 256},
      {F_PC, 16, 0, 16, 8, 1, 8, 256},
      {F_PC, 17, 6, 20, 0, 1, 8, 256},
      {F_PC, 6, 12, 14, 10, 1, 8, 256},
      {F_PC, 7, 1, 24, 11, 0, 8, 256},
      {F_PC, 7, 14, 43, 11, 0, 8, 256},
      {F_PC, 8, 1, 61, 11, 0, 8, 256},
  };
}

int& mpppb::get_rrpv(long set, long way) { return rrpv_values.at(static_cast<std::size_t>(set * NUM_WAY + way)); }

uint8_t& mpppb::get_bypassed(long set, long way) { return bypassed.at(static_cast<std::size_t>(set * NUM_WAY + way)); }

uint8_t mpppb::feature_index(const feature_spec& f, uint32_t cpu, uint64_t ip, uint64_t addr, bool insert, long set)
{
  auto& st = cores.at(cpu);
  uint64_t v = 0;

  switch (f.kind) {
  case F_PC: {
    uint64_t pc = ip;
    if (f.W > 0 && st.hist_count > static_cast<uint64_t>(f.W)) {
      const uint64_t back = static_cast<uint64_t>(f.W);
      pc = st.pc_hist[(st.hist_count - 1 - back) % st.pc_hist.size()];
    }
    v = bits_between(pc, f.B, f.E);
    if (f.X)
      v ^= ip;
    return static_cast<uint8_t>(mix64(v) & 0xffU);
  }
  case F_ADDR: {
    v = bits_between(addr, f.B, f.E);
    if (f.X)
      v ^= ip;
    return static_cast<uint8_t>(mix64(v) & 0xffU);
  }
  case F_BIAS:
    return f.X ? static_cast<uint8_t>(ip & 0xffU) : 0;
  case F_BURST:
    return static_cast<uint8_t>(mru_addr.at(static_cast<std::size_t>(set)) == addr);
  case F_INSERT:
    return insert ? 1 : 0;
  case F_LASTMISS:
    return last_miss.at(static_cast<std::size_t>(set));
  case F_OFFSET: {
    v = bits_between(addr, f.B, f.E);
    if (f.X)
      v ^= ip;
    return static_cast<uint8_t>(v & (static_cast<uint64_t>(f.size) - 1));
  }
  }
  return 0;
}

int mpppb::predict(uint32_t cpu, long set, uint64_t ip, uint64_t addr, bool insert, std::array<uint8_t, NUM_FEATURES>& idx)
{
  auto& st = cores.at(cpu);
  int sum = 0;
  for (int i = 0; i < NUM_FEATURES; ++i) {
    idx[i] = feature_index(features[i], cpu, ip, addr, insert, set);
    sum += st.tables[i][idx[i]];
  }
  return std::clamp(sum, -256, 255);
}

void mpppb::train_live(core_state& st, const sample_entry& e, int pos)
{
  for (int i = 0; i < NUM_FEATURES; ++i) {
    if (pos < features[i].A) {
      int8_t& w = st.tables[i][e.idx[i]];
      if (w > MIN_WEIGHT)
        --w;
    }
  }
}

void mpppb::train_dead(core_state& st, const sample_entry& e)
{
  for (int i = 0; i < NUM_FEATURES; ++i) {
    int8_t& w = st.tables[i][e.idx[i]];
    if (w < MAX_WEIGHT)
      ++w;
  }
}

void mpppb::sampler_update(uint32_t cpu, long set, uint64_t ip, uint64_t addr, bool insert, int conf,
                           const std::array<uint8_t, NUM_FEATURES>& idx)
{
  auto& st = cores.at(cpu);
  auto& s = st.sampler.at(static_cast<std::size_t>(set / sample_rate_));
  const uint16_t tag = static_cast<uint16_t>((addr >> 6U) & 0xffffU);

  int pos = -1;
  for (int q = 0; q < SAMPLER_WAYS; ++q)
    if (s[q].valid && s[q].tag == tag) {
      pos = q;
      break;
    }

  if (pos >= 0) {
    // 访问到一个采样块：训练为 live（只对位置 < A 的特征）
    train_live(st, s[pos], pos);

    // 移到 MRU，其余块后移；越过某特征的 A 时训练为 dead
    for (int q = pos; q > 0; --q) {
      const auto old = s[q - 1];
      const int new_pos = q;
      if (old.valid) {
        for (int i = 0; i < NUM_FEATURES; ++i)
          if (new_pos >= features[i].A && new_pos - 1 < features[i].A) {
            int8_t& w = st.tables[i][old.idx[i]];
            if (w < MAX_WEIGHT)
              ++w;
          }
      }
      s[q] = old;
    }
    s[0].valid = true;
    s[0].tag = tag;
    s[0].conf = static_cast<int16_t>(conf);
    s[0].idx = idx;
  } else {
    // 未命中：LRU 位置（17）的块被逐出 -> dead
    if (s[SAMPLER_WAYS - 1].valid)
      train_dead(st, s[SAMPLER_WAYS - 1]);

    for (int q = SAMPLER_WAYS - 1; q > 0; --q) {
      const auto old = s[q - 1];
      const int new_pos = q;
      if (old.valid) {
        for (int i = 0; i < NUM_FEATURES; ++i)
          if (new_pos >= features[i].A && new_pos - 1 < features[i].A) {
            int8_t& w = st.tables[i][old.idx[i]];
            if (w < MAX_WEIGHT)
              ++w;
          }
      }
      s[q] = old;
    }
    s[0].valid = true;
    s[0].tag = tag;
    s[0].conf = static_cast<int16_t>(conf);
    s[0].idx = idx;
  }
}

long mpppb::find_victim(uint32_t, uint64_t, long set, const champsim::cache_block*, champsim::address, champsim::address, access_type)
{
  auto begin = std::next(std::begin(rrpv_values), set * NUM_WAY);
  auto end = std::next(begin, NUM_WAY);

  // bypass 行优先逐出
  for (auto it = begin; it != end; ++it)
    if (get_bypassed(set, std::distance(begin, it)))
      return std::distance(begin, it);

  auto victim = std::max_element(begin, end);
  if (auto rrpv_update = MAX_RRPV - *victim; rrpv_update != 0)
    for (auto it = begin; it != end; ++it)
      *it += rrpv_update;

  return std::distance(begin, victim);
}

void mpppb::replacement_cache_fill(uint32_t, long set, long way, champsim::address, champsim::address, champsim::address, access_type type)
{
  // 写回：低优先级，不参与预测
  if (type == access_type::WRITE) {
    get_rrpv(set, way) = MAX_RRPV;
    get_bypassed(set, way) = 0;
    return;
  }

  const int conf = pending_conf.at(static_cast<std::size_t>(set));
  get_bypassed(set, way) = 0;

  if (conf >= tau_bypass) {
    // bypass 近似：插入到最易替换位置并标记，下次选 victim 优先逐出
    get_rrpv(set, way) = MAX_RRPV;
    get_bypassed(set, way) = 1;
  } else if (conf >= tau_p1) {
    get_rrpv(set, way) = 0;  // π1
  } else if (conf >= tau_p2) {
    get_rrpv(set, way) = 1;  // π2
  } else if (conf >= tau_p3) {
    get_rrpv(set, way) = 2;  // π3
  } else {
    get_rrpv(set, way) = 0;  // MRU
  }
}

void mpppb::update_replacement_state(uint32_t triggering_cpu, long set, long way, champsim::address full_addr,
                                     champsim::address ip, champsim::address, access_type type, uint8_t hit)
{
  const uint64_t ipv = ip.to<uint64_t>();
  const uint64_t addr = full_addr.to<uint64_t>();
  const bool insert = (hit == 0);
  auto& st = cores.at(triggering_cpu);

  std::array<uint8_t, NUM_FEATURES> idx{};
  const int conf = predict(triggering_cpu, set, ipv, addr, insert, idx);
  pending_conf.at(static_cast<std::size_t>(set)) = static_cast<int16_t>(conf);

  if (set % sample_rate_ == 0)
    sampler_update(triggering_cpu, set, ipv, addr, insert, conf, idx);

  // 更新历史 / set 状态（在当前访问的特征计算之后）
  st.pc_hist[st.hist_count % st.pc_hist.size()] = ipv;
  ++st.hist_count;
  last_miss.at(static_cast<std::size_t>(set)) = insert ? 1 : 0;
  mru_addr.at(static_cast<std::size_t>(set)) = addr;

  if (hit && conf < tau_promote)
    get_rrpv(set, way) = 0;
}