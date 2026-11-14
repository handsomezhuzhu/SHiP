#include "mpppb.h"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iterator>

#include "champsim.h"

namespace
{
struct probe_counters {
  long fills = 0;
  long matched = 0;
  long unmatched = 0;
  long bypassed = 0;
  long demand_bypass = 0;
  long pref_bypass = 0;
  long write_fills = 0;
  long trans_access = 0;
  long trans_hit = 0;
  long trans_fills = 0;
  long promoted = 0;
  long kept = 0;
  std::array<long, 6> bucket{};
};

probe_counters g_probe;

constexpr int kVecMdpp[16] = {0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 2, 3, 0, 1, 0, 0};

void probe_bucket(int score)
{
  if (score < -100)
    ++g_probe.bucket[0];
  else if (score < 0)
    ++g_probe.bucket[1];
  else if (score < 50)
    ++g_probe.bucket[2];
  else if (score < 100)
    ++g_probe.bucket[3];
  else if (score < 150)
    ++g_probe.bucket[4];
  else
    ++g_probe.bucket[5];
}
// Extract an inclusive bit range. Bit 0 is the least significant bit.
std::uint64_t slice_bits(std::uint64_t value, int low, int high)
{
  const int width = high - low + 1;
  if (width <= 0)
    return 0;
  if (low >= 64)
    return 0;
  if (width >= 64 - low)
    return value >> low;
  return (value >> low) & ((std::uint64_t{1} << width) - 1);
}

// Compress a value into `width` bits. Values wider than the index are
// XOR-folded, then passed through an odd multiplier so that structured bit
// patterns (aligned PCs, strides) spread over the table.
std::uint64_t compress_bits(std::uint64_t value, int width)
{
  if (width <= 0)
    return 0;
  const std::uint64_t mask = (width >= 64) ? ~std::uint64_t{0} : ((std::uint64_t{1} << width) - 1);
  std::uint64_t folded = 0;
  for (int shift = 0; shift < 64; shift += width)
    folded ^= (value >> shift);
  folded &= mask;
  folded = (folded * 0x9dU) & mask;
  return folded;
}

// Set the tree path that selects leaf `idx` for `way` (16-way MDPP).
std::uint16_t plru_assign(std::uint16_t P, int way, int idx)
{
  std::uint32_t x = static_cast<std::uint32_t>(way) + 15U;
  for (int i = 0; i < 4; ++i) {
    const bool odd = (x & 1U) != 0;
    x = (x - 1U) >> 1U;
    const bool val = (odd == (((idx >> (3 - i)) & 1) != 0));
    if (val)
      P = static_cast<std::uint16_t>(P | (1U << x));
    else
      P = static_cast<std::uint16_t>(P & ~(1U << x));
  }
  return P;
}
} // namespace

mpppb::mpppb(CACHE* cache)
    : replacement(cache), sets_(cache->NUM_SET), ways_(cache->NUM_WAY),
      rrpv_(static_cast<std::size_t>(cache->NUM_SET) * cache->NUM_WAY, kMaxRrpv),
      first_victim_(static_cast<std::size_t>(cache->NUM_SET) * cache->NUM_WAY, 0),
      mru_block_(static_cast<std::size_t>(cache->NUM_SET), 0),
      miss_last_(static_cast<std::size_t>(cache->NUM_SET), 0),
      in_flight_(static_cast<std::size_t>(cache->NUM_SET))
{
  // Number of set-index bits, used to separate the block tag from the set.
  while ((std::uint64_t{1} << set_bits_) < static_cast<std::uint64_t>(sets_) && set_bits_ < 31)
    ++set_bits_;
  sampled_sets_ = (static_cast<std::size_t>(sets_) + kSampleStride - 1) / kSampleStride;

  // Profile selection must happen before describe_features().
  auto read_env = [](const char* name, int& slot) {
    if (const char* text = std::getenv(name)) {
      char* end = nullptr;
      const long parsed = std::strtol(text, &end, 10);
      if (end != text)
        slot = static_cast<int>(parsed);
    }
  };
  if (const char* profile = std::getenv("MPPPB_PROFILE"); profile != nullptr) {
    if (std::strcmp(profile, "author1") == 0) {
      // CRC2 config 1: single core, 2 MB LLC, no prefetcher, static MDPP.
      author_ = true;
      use_mdpp_ = true;
      direct_index_ = true;
      author_train_ = true;
      bypass_duel_ = true;
      train_threshold_ = 128;
      theta_ = 109;
      theta2_ = 135;
      promotion_threshold_ = 82;
      bypass_dt1_ = 56;
      bypass_dt2_ = 256;
      leaders1_ = 32;
      leaders2_ = 64;
      init_weight_ = 1;
      plv_[0][0] = -15;
      plv_[0][1] = 0;
      plv_[1][0] = 35;
      plv_[1][1] = 12;
      plv_[2][0] = 44;
      plv_[2][1] = 15;
    } else if (std::strcmp(profile, "author2") == 0) {
      // CRC2 config 2: single core, 2 MB LLC, with prefetcher, static MDPP.
      author_ = true;
      author2_ = true;
      use_mdpp_ = true;
      direct_index_ = true;
      author_train_ = true;
      bypass_duel_ = true;
      train_threshold_ = 128;
      theta_ = 109;
      theta2_ = 135;
      promotion_threshold_ = 178;
      bypass_dt1_ = 42;
      bypass_dt2_ = 48;
      leaders1_ = 32;
      leaders2_ = 64;
      init_weight_ = 1;
      plv_[0][0] = -15;
      plv_[0][1] = 0;
      plv_[1][0] = 35;
      plv_[1][1] = 12;
      plv_[2][0] = 44;
      plv_[2][1] = 15;
    }
  }
  if (const char* imp = std::getenv("MPPPB_IMPROVE"); imp != nullptr && imp[0] != '\0' && std::strcmp(imp, "0") != 0)
    improve_ = true;
  if (const char* base = std::getenv("MPPPB_BASE"); base != nullptr && std::strcmp(base, "mdpp") == 0)
    use_mdpp_ = true;
  read_env("MPPPB_TRAIN_THRESHOLD", train_threshold_);
  read_env("MPPPB_THETA", theta_);
  read_env("MPPPB_THETA2", theta2_);
  read_env("MPPPB_PROMOTE", promotion_threshold_);
  read_env("MPPPB_DT1", bypass_dt1_);
  read_env("MPPPB_DT2", bypass_dt2_);
  read_env("MPPPB_LEADERS1", leaders1_);
  read_env("MPPPB_LEADERS2", leaders2_);
  read_env("MPPPB_INIT_WEIGHT", init_weight_);
  read_env("MPPPB_PLV0T", plv_[0][0]);
  read_env("MPPPB_PLV0P", plv_[0][1]);
  read_env("MPPPB_PLV1T", plv_[1][0]);
  read_env("MPPPB_PLV1P", plv_[1][1]);
  read_env("MPPPB_PLV2T", plv_[2][0]);
  read_env("MPPPB_PLV2P", plv_[2][1]);
  if (const char* duel = std::getenv("MPPPB_BYPASS_DUEL"); duel != nullptr)
    bypass_duel_ = std::strcmp(duel, "0") != 0;

  describe_features();
  read_env("MPPPB_TAU_BYPASS", thr_bypass_);
  read_env("MPPPB_TAU_P1", thr_pos1_);
  read_env("MPPPB_TAU_P2", thr_pos2_);
  read_env("MPPPB_TAU_P3", thr_pos3_);
  read_env("MPPPB_TAU_PROMOTE", thr_keep_);
  read_env("MPPPB_POS1", pos1_);
  read_env("MPPPB_POS2", pos2_);
  read_env("MPPPB_POS3", pos3_);
  pos1_ = std::clamp(pos1_, 0, kMaxRrpv);
  pos2_ = std::clamp(pos2_, 0, kMaxRrpv);
  pos3_ = std::clamp(pos3_, 0, kMaxRrpv);

  if (thr_bypass_ < thr_pos1_ || thr_pos1_ < thr_pos2_ || thr_pos2_ < thr_pos3_)
    std::fprintf(stderr, "mpppb: warning: thresholds are not monotone (bypass=%d p1=%d p2=%d p3=%d)\n", thr_bypass_,
                 thr_pos1_, thr_pos2_, thr_pos3_);

  plru_.assign(static_cast<std::size_t>(sets_), 0);
  cores_.resize(NUM_CPUS);
  for (auto& core : cores_) {
    core.table.resize(kFeatureCount);
    for (int f = 0; f < kFeatureCount; ++f)
      core.table[f].assign(plan_[f].entries, static_cast<std::int8_t>(init_weight_));
    core.sampler.assign(sampled_sets_, {});
  }
}

mpppb::~mpppb()
{
  if (const char* env = std::getenv("MPPPB_STATS"); env != nullptr && env[0] != '0' && env[0] != '\0') {
    std::fprintf(stderr,
                 "mpppb: fills=%ld matched=%ld unmatched=%ld bypass=%ld promote=%ld keep=%ld "
                 "buckets(<-100,-100..-1,0..49,50..99,100..149,>=150)=%ld,%ld,%ld,%ld,%ld,%ld\n",
                 g_probe.fills, g_probe.matched, g_probe.unmatched, g_probe.bypassed, g_probe.promoted, g_probe.kept,
                 g_probe.bucket[0], g_probe.bucket[1], g_probe.bucket[2], g_probe.bucket[3], g_probe.bucket[4],
                 g_probe.bucket[5]);
    std::fprintf(stderr,
                 "mpppb_ta: demand_bypass=%ld pref_bypass=%ld write_fills=%ld trans_access=%ld trans_hit=%ld trans_fills=%ld\n",
                 g_probe.demand_bypass, g_probe.pref_bypass, g_probe.write_fills, g_probe.trans_access, g_probe.trans_hit,
                 g_probe.trans_fills);
  }
}

void mpppb::describe_features()
{
  if (author2_) {
    // CRC2 config 2 feature table (`single_2`, Table 2(b) of mpppb_crc17.pdf).
    auto add_x = [this](view kind, int a, int b, int e, int w, std::uint8_t xm) {
      int entries = 256;
      if (kind == view::offset)
        entries = (xm != 0) ? 256 : (1 << std::max(0, e - b));
      else if (kind != view::pc && kind != view::address)
        entries = (xm & 1U) ? 256 : ((xm & 2U) ? 4 : 2);
      plan_.push_back(feature{kind, a, b, e, w, (xm & 1U) != 0, xm, 0, static_cast<std::uint16_t>(entries)});
    };
    add_x(view::insert, 15, 0, 0, 0, 0);
    add_x(view::insert, 16, 0, 0, 0, 1);
    add_x(view::insert, 6, 0, 0, 0, 1);
    add_x(view::offset, 14, 0, 7, 0, 2);
    add_x(view::bias, 17, 0, 0, 0, 3);
    add_x(view::burst, 8, 0, 0, 0, 2);
    add_x(view::pc, 6, 5, 48, 0, 3);
    add_x(view::lastmiss, 15, 0, 0, 0, 2);
    add_x(view::address, 17, 1, 32, 0, 2);
    add_x(view::pc, 17, 6, 20, 0, 1);
    add_x(view::pc, 6, 4, 11, 2, 2);
    add_x(view::bias, 13, 0, 0, 0, 2);
    add_x(view::offset, 8, 1, 6, 0, 2);
    add_x(view::pc, 6, 5, 77, 4, 1);
    add_x(view::address, 11, 8, 19, 0, 0);
    add_x(view::address, 16, 8, 16, 0, 0);
    return;
  }

  if (author_) {
    // CRC2 config 1 feature table (`single_1`, close to Table 1(a)).
    auto add_a = [this](view kind, int a, int b, int e, int w, bool mix) {
      int entries = 256;
      if (kind == view::offset)
        entries = mix ? 256 : (1 << std::max(0, e - b));
      else if (kind != view::pc && kind != view::address)
        entries = mix ? 256 : 2;
      plan_.push_back(feature{kind, a, b, e, w, mix, static_cast<std::uint8_t>(mix ? 1 : 0), 0, static_cast<std::uint16_t>(entries)});
    };
    add_a(view::offset, 15, 1, 6, 0, true);
    add_a(view::pc, 7, 14, 43, 11, false);
    add_a(view::pc, 16, 3, 11, 16, true);
    add_a(view::insert, 16, 0, 0, 0, true);
    add_a(view::offset, 10, 0, 6, 0, true);
    add_a(view::pc, 10, 1, 53, 10, false);
    add_a(view::bias, 16, 0, 0, 0, false);
    add_a(view::insert, 8, 0, 0, 0, true);
    add_a(view::pc, 17, 6, 20, 0, true);
    add_a(view::burst, 6, 11, 22, 9, false);
    add_a(view::lastmiss, 9, 0, 0, 0, false);
    add_a(view::pc, 17, 6, 20, 0, true);
    add_a(view::insert, 16, 2, 47, 2, false);
    add_a(view::insert, 17, 0, 0, 0, true);
    add_a(view::pc, 16, 8, 16, 5, false);
    add_a(view::pc, 17, 6, 20, 14, true);
    return;
  }

  // Table 1(b) of the paper (single-thread set).
  auto add = [this](view kind, int a, int b, int e, int w, bool mix) {
    int width = 1;
    if (kind == view::pc || kind == view::address || kind == view::offset)
      width = e - b + 1;

    int bits = 0;
    if (kind == view::bias)
      bits = mix ? 8 : 0;
    else if (kind == view::offset)
      bits = 6; // offset features never index more than 64 weights
    else if (mix || width > 8)
      bits = 8;
    else
      bits = width;

    plan_.push_back(feature{kind, a, b, e, w, mix, static_cast<std::uint8_t>(mix ? 1 : 0), static_cast<std::uint8_t>(bits),
                            static_cast<std::uint16_t>(std::uint16_t{1} << bits)});
  };

  add(view::address, 11, 8, 19, 0, false);
  add(view::bias, 6, 0, 0, 0, true);
  add(view::insert, 15, 0, 0, 0, false);
  add(view::insert, 16, 0, 0, 0, true);
  add(view::insert, 6, 0, 0, 0, true);
  add(view::offset, 15, 1, 6, 0, true);
  add(view::offset, 15, 3, 7, 0, false);
  add(view::pc, 11, 2, 24, 4, true);
  add(view::pc, 15, 14, 32, 6, false);
  add(view::pc, 15, 5, 28, 0, true);
  add(view::pc, 16, 0, 16, 8, true);
  add(view::pc, 17, 6, 20, 0, true);
  add(view::pc, 6, 12, 14, 10, true);
  add(view::pc, 7, 1, 24, 11, false);
  add(view::pc, 7, 14, 43, 11, false);
  add(view::pc, 8, 1, 61, 11, false);
}

std::vector<std::int8_t>& mpppb::weights(std::size_t cpu, int slot)
{
  return cores_.at(cpu).table.at(static_cast<std::size_t>(slot));
}

std::uint8_t mpppb::index_of(const feature& f, const core_view& st, long set, std::uint64_t ip,
                             std::uint64_t addr, std::uint64_t block, bool insert, access_type type)
{
  // Disambiguate zero-IP prefetches by 4KB page context under TA-MPPPB
  // so they do not alias into a single weight [0].
  const std::uint64_t eff_ip =
      (improve_ && type == access_type::PREFETCH && ip == 0) ? (0x9e3779b9ULL ^ (block >> 6U)) : ip;

  if (direct_index_) {
    // Author-code indexing: direct bit extraction (e is exclusive), XOR PC,
    // then modulo the table size. No XOR folding.
    std::uint64_t raw = 0;
    const int width = f.e - f.b;
    const std::uint64_t mask = (width <= 0) ? 0 : ((width >= 64) ? ~std::uint64_t{0} : ((std::uint64_t{1} << width) - 1));
    switch (f.kind) {
    case view::pc: {
      std::uint64_t chosen = eff_ip;
      if (f.w > 0) {
        const auto depth = static_cast<std::uint64_t>(f.w);
        chosen = (st.stamps >= depth) ? st.pc_ring[(st.stamps - depth) % st.pc_ring.size()] : 0;
      }
      raw = (chosen >> f.b) & mask;
      break;
    }
    case view::address:
      raw = (addr >> f.b) & mask;
      break;
    case view::offset:
      raw = ((addr & 63U) >> f.b) & mask;
      break;
    case view::bias:
      raw = 0;
      break;
    case view::burst:
      raw = burst_now_;
      break;
    case view::insert:
      raw = insert ? 1 : 0;
      break;
    case view::lastmiss:
      raw = miss_last_.at(static_cast<std::size_t>(set)) ? 1 : 0;
      break;
    }
    if (f.x_mask & 1U)
      raw ^= eff_ip;
    if ((f.x_mask & 2U) != 0 && type == access_type::PREFETCH)
      raw ^= 2ULL;
    return static_cast<std::uint8_t>(raw % f.entries);
  }

  std::uint64_t raw = 0;

  switch (f.kind) {
  case view::pc: {
    std::uint64_t chosen = eff_ip;
    if (f.w > 0) {
      const auto depth = static_cast<std::uint64_t>(f.w);
      chosen = (st.stamps >= depth) ? st.pc_ring[(st.stamps - depth) % st.pc_ring.size()] : 0;
    }
    raw = slice_bits(chosen, f.b, f.e);
    if (f.mix_pc)
      raw ^= eff_ip;
    break;
  }
  case view::address:
  case view::offset:
    raw = slice_bits(addr, f.b, f.e);
    if (f.mix_pc)
      raw ^= eff_ip;
    break;
  case view::bias:
    // A global counter (X=0) or a PC-indexed predictor (X=1).
    raw = f.mix_pc ? eff_ip : 0;
    break;
  case view::burst:
    raw = (block == mru_block_.at(static_cast<std::size_t>(set))) ? 1 : 0;
    if (f.mix_pc)
      raw ^= eff_ip;
    break;
  case view::insert:
    raw = insert ? 1 : 0;
    if (f.mix_pc)
      raw ^= eff_ip;
    break;
  case view::lastmiss:
    raw = miss_last_.at(static_cast<std::size_t>(set)) ? 1 : 0;
    if (f.mix_pc)
      raw ^= eff_ip;
    break;
  }

  return static_cast<std::uint8_t>(compress_bits(raw, f.bits));
}

std::int16_t mpppb::predict(core_view& st, long set, std::uint64_t ip, std::uint64_t addr,
                            std::uint64_t block, bool insert, access_type type,
                            std::array<std::uint8_t, kFeatureCount>& key)
{
  int total = 0;
  for (int f = 0; f < kFeatureCount; ++f) {
    key[static_cast<std::size_t>(f)] = index_of(plan_[f], st, set, ip, addr, block, insert, type);
    total += st.table[static_cast<std::size_t>(f)][key[static_cast<std::size_t>(f)]];
  }
  return static_cast<std::int16_t>(std::clamp(total, -256, 255));
}

void mpppb::nudge(core_view& st, int slot, std::uint8_t index, int delta)
{
  auto& cell = st.table.at(static_cast<std::size_t>(slot)).at(index);
  const int updated = static_cast<int>(cell) + delta;
  cell = static_cast<std::int8_t>(std::clamp(updated, kMinWeight, kMaxWeight));
}

void mpppb::learn_reuse(core_view& st, const item& old, int position)
{
  if (author_train_) {
    // Author-code perceptron rule: train if wrong, or if inside the dead zone.
    const bool predicted_dead = old.score >= train_threshold_;
    const bool correct = !predicted_dead;
    const bool deadzone = (old.score < 0) ? (old.score > -theta2_) : (old.score < theta_);
    if (correct && !deadzone)
      return;
    for (int f = 0; f < kFeatureCount; ++f)
      if (position < plan_[static_cast<std::size_t>(f)].a)
        nudge(st, f, old.key[static_cast<std::size_t>(f)], -1);
    return;
  }

  // Mistake-driven perceptron: a live block must be predicted live (score < 0).
  // A score of exactly 0 is treated as a miss so that training can bootstrap
  // from the all-zero tables.
  if (old.score < 0)
    return;
  for (int f = 0; f < kFeatureCount; ++f)
    if (position < plan_[static_cast<std::size_t>(f)].a)
      nudge(st, f, old.key[static_cast<std::size_t>(f)], -1);
}

void mpppb::learn_demote(core_view& st, const item& old, int new_position)
{
  if (author_train_) {
    const bool predicted_dead = old.score >= train_threshold_;
    const bool correct = predicted_dead;
    const bool deadzone = (old.score < 0) ? (old.score > -theta2_) : (old.score < theta_);
    if (correct && !deadzone)
      return;
    for (int f = 0; f < kFeatureCount; ++f)
      if (new_position == plan_[static_cast<std::size_t>(f)].a)
        nudge(st, f, old.key[static_cast<std::size_t>(f)], +1);
    return;
  }

  // A block falling past a feature's associativity cutoff is dead for it.
  // Symmetrically, a dead block must be predicted dead (score > 0); 0 counts
  // as a miss.
  if (old.score > 0)
    return;
  for (int f = 0; f < kFeatureCount; ++f)
    if (new_position == plan_[static_cast<std::size_t>(f)].a)
      nudge(st, f, old.key[static_cast<std::size_t>(f)], +1);
}

void mpppb::visit_sampler(core_view& st, long set, std::uint16_t ptag, std::int16_t score,
                          const std::array<std::uint8_t, kFeatureCount>& key, access_type type)
{
  auto& s = st.sampler.at(static_cast<std::size_t>(set / kSampleStride));

  int hit = -1;
  for (int i = 0; i < static_cast<int>(s.line.size()); ++i)
    if (s.line[static_cast<std::size_t>(i)].used && s.line[static_cast<std::size_t>(i)].ptag == ptag) {
      hit = i;
      break;
    }

  if (hit >= 0) {
    const item previous = s.line[static_cast<std::size_t>(hit)];
    learn_reuse(st, previous, hit);
    for (int q = hit; q > 0; --q) {
      const item moved = s.line[static_cast<std::size_t>(q - 1)];
      if (moved.used)
        learn_demote(st, moved, q);
      s.line[static_cast<std::size_t>(q)] = moved;
    }
    if (improve_ && type == access_type::WRITE) {
      // Preserve creator LOAD/RFO feature key & score at MRU instead of overwriting
      // with a zero-IP WRITE key.
      s.line[0] = previous;
      return;
    }
  } else {
    for (int q = static_cast<int>(s.line.size()) - 1; q > 0; --q) {
      const item moved = s.line[static_cast<std::size_t>(q - 1)];
      if (moved.used)
        learn_demote(st, moved, q);
      s.line[static_cast<std::size_t>(q)] = moved;
    }
  }

  s.line[0] = item{true, ptag, score, key};
}

std::uint16_t mpppb::partial_tag(std::uint64_t block) const
{
  return static_cast<std::uint16_t>((block >> set_bits_) & 0xffffU);
}

std::int16_t mpppb::take_score(long set, std::uint64_t block, bool& found)
{
  auto& q = in_flight_.at(static_cast<std::size_t>(set));
  const auto match = std::find_if(std::begin(q), std::end(q), [block](const pending_hit& p) { return p.block == block; });
  found = (match != std::end(q));
  if (!found) {
    // A fill whose miss was not recorded (e.g. dropped at the cap). Fall back
    // to the default placement rather than to another block's prediction.
    return 0;
  }
  const auto score = match->score;
  q.erase(match);
  return score;
}

int mpppb::plru_index(long set, long way) const
{
  const std::uint16_t P = plru_.at(static_cast<std::size_t>(set));
  std::uint32_t x = static_cast<std::uint32_t>(way) + 15U;
  int idx = 0;
  for (int i = 0; i < 4; ++i) {
    const bool odd = (x & 1U) != 0;
    x = (x - 1U) >> 1U;
    if ((((P >> x) & 1U) != 0) == odd)
      idx |= 1 << (3 - i);
  }
  return idx;
}

void mpppb::plru_set(long set, long way, int idx)
{
  auto& P = plru_.at(static_cast<std::size_t>(set));
  P = plru_assign(P, static_cast<int>(way), idx);
}

bool mpppb::plru_would_change(long set, long way, int idx) const
{
  const std::uint16_t P = plru_.at(static_cast<std::size_t>(set));
  return plru_assign(P, static_cast<int>(way), idx) != P;
}

long mpppb::plru_victim(long set) const
{
  const std::uint16_t P = plru_.at(static_cast<std::size_t>(set));
  std::uint32_t x = 0;
  int a = 15;
  while (a != 0) {
    x = (((P >> x) & 1U) != 0) ? (2U * x + 1U) : (2U * x + 2U);
    a /= 2;
  }
  return static_cast<long>(x) - 15;
}

std::int16_t mpppb::peek_score(long set, std::uint64_t block, bool& found) const
{
  const auto& q = in_flight_.at(static_cast<std::size_t>(set));
  const auto it = std::find_if(std::begin(q), std::end(q), [block](const pending_hit& p) { return p.block == block; });
  found = (it != std::end(q));
  return found ? it->score : 0;
}

void mpppb::drop_pending(long set, std::uint64_t block)
{
  auto& q = in_flight_.at(static_cast<std::size_t>(set));
  const auto it = std::find_if(std::begin(q), std::end(q), [block](const pending_hit& p) { return p.block == block; });
  if (it != std::end(q))
    q.erase(it);
}

int mpppb::bypass_limit(long set) const
{
  if (!bypass_duel_)
    return thr_bypass_;
  if (set < leaders1_)
    return bypass_dt1_;
  if (set < leaders2_)
    return bypass_dt2_;
  return (psel_ >= 0) ? bypass_dt2_ : bypass_dt1_;
}

long mpppb::find_victim(uint32_t, uint64_t, long set, const champsim::cache_block*, champsim::address,
                        champsim::address full_addr, access_type type)
{
  if (use_mdpp_ && ways_ == kMdppWays) {
    const bool allow_bypass = (type != access_type::WRITE) && (!improve_ || type != access_type::TRANSLATION);
    if (allow_bypass) {
      const auto block = full_addr.to<std::uint64_t>() >> 6U;
      bool found = false;
      const auto score = peek_score(set, block, found);
      if (found && score >= bypass_limit(set)) {
        drop_pending(set, block);
        ++g_probe.bypassed;
        if (type == access_type::PREFETCH)
          ++g_probe.pref_bypass;
        else
          ++g_probe.demand_bypass;
        return ways_; // skip allocation (true bypass)
      }
    }
    return plru_victim(set);
  }

  const auto base = static_cast<std::size_t>(set) * static_cast<std::size_t>(ways_);

  // Bypass approximation: a line that was predicted dead-on-arrival is the
  // first candidate for eviction.
  for (long way = 0; way < ways_; ++way)
    if (first_victim_.at(base + static_cast<std::size_t>(way)) != 0)
      return way;

  auto begin = std::next(std::begin(rrpv_), static_cast<std::ptrdiff_t>(base));
  auto end = std::next(begin, ways_);
  auto victim = std::max_element(begin, end);
  if (const int bump = kMaxRrpv - *victim; bump != 0)
    for (auto it = begin; it != end; ++it)
      *it = static_cast<std::int8_t>(*it + bump);

  return static_cast<long>(std::distance(begin, victim));
}

void mpppb::replacement_cache_fill(uint32_t, long set, long way, champsim::address full_addr, champsim::address,
                                   champsim::address, access_type type)
{
  if (use_mdpp_ && ways_ == kMdppWays) {
    if (way >= ways_)
      return; // bypass: no allocation
    const auto block = full_addr.to<std::uint64_t>() >> 6U;
    if (improve_ && type == access_type::TRANSLATION) {
      drop_pending(set, block);
      ++g_probe.fills;
      ++g_probe.trans_fills;
      plru_set(set, way, 0);
      return;
    }
    bool found = false;
    const auto score = take_score(set, block, found);
    ++g_probe.fills;
    if (type == access_type::WRITE)
      ++g_probe.write_fills;
    if (found)
      ++g_probe.matched;
    else
      ++g_probe.unmatched;
    probe_bucket(score);
    int newidx = 0;
    if (score >= plv_[2][0])
      newidx = plv_[2][1];
    else if (score >= plv_[1][0])
      newidx = plv_[1][1];
    else if (score >= plv_[0][0])
      newidx = plv_[0][1];
    plru_set(set, way, newidx);
    return;
  }

  const auto raw = full_addr.to<std::uint64_t>();
  const auto block = raw >> 6U;
  const auto slot = static_cast<std::size_t>(set) * static_cast<std::size_t>(ways_) + static_cast<std::size_t>(way);

  if (type == access_type::PREFETCH) {
    rrpv_.at(slot) = static_cast<std::int8_t>(kMaxRrpv - 1);
    first_victim_.at(slot) = 0;
    return;
  }

  bool found = false;
  const std::int16_t score = take_score(set, block, found);
  ++g_probe.fills;
  if (found)
    ++g_probe.matched;
  else
    ++g_probe.unmatched;
  probe_bucket(score);

  if (score >= thr_bypass_) {
    ++g_probe.bypassed;
    rrpv_.at(slot) = static_cast<std::int8_t>(kMaxRrpv);
    first_victim_.at(slot) = 1;
  } else if (score >= thr_pos1_) {
    rrpv_.at(slot) = static_cast<std::int8_t>(pos1_);
    first_victim_.at(slot) = 0;
  } else if (score >= thr_pos2_) {
    rrpv_.at(slot) = static_cast<std::int8_t>(pos2_);
    first_victim_.at(slot) = 0;
  } else if (score >= thr_pos3_) {
    rrpv_.at(slot) = static_cast<std::int8_t>(pos3_);
    first_victim_.at(slot) = 0;
  } else if (score < thr_keep_) {
    rrpv_.at(slot) = 0;
    first_victim_.at(slot) = 0;
    mru_block_.at(static_cast<std::size_t>(set)) = block;
  } else {
    rrpv_.at(slot) = static_cast<std::int8_t>(pos3_);
    first_victim_.at(slot) = 0;
  }
}

void mpppb::update_replacement_state(uint32_t triggering_cpu, long set, long way, champsim::address full_addr,
                                     champsim::address ip, champsim::address, access_type type, uint8_t hit)
{
  const auto raw = full_addr.to<std::uint64_t>();
  const auto block = raw >> 6U;
  const auto pc = ip.to<std::uint64_t>();
  const bool insertion = (hit == 0);

  if (ways_ == kMdppWays && type == access_type::TRANSLATION) {
    ++g_probe.trans_access;
    if (!insertion)
      ++g_probe.trans_hit;
    if (improve_) {
      if (!insertion && way < ways_) {
        const int cur = plru_index(set, way);
        plru_set(set, way, kVecMdpp[cur]);
        ++g_probe.promoted;
      }
      miss_last_.at(static_cast<std::size_t>(set)) = insertion ? 1 : 0;
      return;
    }
  }

  auto& core = cores_.at(triggering_cpu);
  std::array<std::uint8_t, kFeatureCount> key{};

  if (author_ && ways_ == kMdppWays) {
    burst_now_ = 0;
    if (!insertion && way < ways_) {
      const int cur = plru_index(set, way);
      const int nxt = kVecMdpp[cur];
      burst_now_ = plru_would_change(set, way, nxt) ? 0 : 1;
    }
  }

  const std::int16_t score = predict(core, set, pc, raw, block, insertion, type, key);

  if (set % kSampleStride == 0)
    visit_sampler(core, set, partial_tag(block), score, key, type);

  if (insertion) {
    if (author_ && bypass_duel_) {
      if (set < leaders1_)
        psel_ = std::min(1023, psel_ + 1);
      else if (set < leaders2_)
        psel_ = std::max(-1023, psel_ - 1);
    }
    auto& q = in_flight_.at(static_cast<std::size_t>(set));
    if (q.size() >= kPendingCap)
      q.pop_front();
    q.push_back(pending_hit{block, score});
  } else if (author_ && ways_ == kMdppWays) {
    if (way < ways_ && score <= promotion_threshold_) {
      const int cur = plru_index(set, way);
      plru_set(set, way, kVecMdpp[cur]);
      ++g_probe.promoted;
    } else {
      ++g_probe.kept;
    }
  } else {
    const auto slot = static_cast<std::size_t>(set) * static_cast<std::size_t>(ways_) + static_cast<std::size_t>(way);
    first_victim_.at(slot) = 0; // a reuse disproves dead-on-arrival
    if (score < thr_keep_) {
      rrpv_.at(slot) = 0;
      mru_block_.at(static_cast<std::size_t>(set)) = block;
      ++g_probe.promoted;
    } else {
      ++g_probe.kept;
    }
  }

  if (!improve_ || pc != 0) {
    core.pc_ring[core.stamps % core.pc_ring.size()] = pc;
    ++core.stamps;
  }
  miss_last_.at(static_cast<std::size_t>(set)) = insertion ? 1 : 0;
}