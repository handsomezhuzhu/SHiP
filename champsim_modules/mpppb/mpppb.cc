#include "mpppb.h"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <iterator>

#include "champsim.h"

namespace
{
struct probe_counters {
  long fills = 0;
  long matched = 0;
  long unmatched = 0;
  long bypassed = 0;
  long promoted = 0;
  long kept = 0;
  std::array<long, 6> bucket{};
};

probe_counters g_probe;

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

  describe_features();

  // The five thresholds are not published. Environment overrides let the
  // search script drive them without rebuilding.
  auto read_env = [](const char* name, int& slot) {
    if (const char* text = std::getenv(name)) {
      char* end = nullptr;
      const long parsed = std::strtol(text, &end, 10);
      if (end != text)
        slot = static_cast<int>(parsed);
    }
  };
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

  cores_.resize(NUM_CPUS);
  for (auto& core : cores_) {
    core.table.resize(kFeatureCount);
    for (int f = 0; f < kFeatureCount; ++f)
      core.table[f].assign(plan_[f].entries, 0);
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
  }
}

void mpppb::describe_features()
{
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

    plan_.push_back(feature{kind, a, b, e, w, mix, static_cast<std::uint8_t>(bits),
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
                             std::uint64_t addr, std::uint64_t block, bool insert)
{
  std::uint64_t raw = 0;

  switch (f.kind) {
  case view::pc: {
    std::uint64_t chosen = ip;
    if (f.w > 0) {
      const auto depth = static_cast<std::uint64_t>(f.w);
      chosen = (st.stamps >= depth) ? st.pc_ring[(st.stamps - depth) % st.pc_ring.size()] : 0;
    }
    raw = slice_bits(chosen, f.b, f.e);
    if (f.mix_pc)
      raw ^= ip;
    break;
  }
  case view::address:
  case view::offset:
    raw = slice_bits(addr, f.b, f.e);
    if (f.mix_pc)
      raw ^= ip;
    break;
  case view::bias:
    // A global counter (X=0) or a PC-indexed predictor (X=1).
    raw = f.mix_pc ? ip : 0;
    break;
  case view::burst:
    raw = (block == mru_block_.at(static_cast<std::size_t>(set))) ? 1 : 0;
    if (f.mix_pc)
      raw ^= ip;
    break;
  case view::insert:
    raw = insert ? 1 : 0;
    if (f.mix_pc)
      raw ^= ip;
    break;
  case view::lastmiss:
    raw = miss_last_.at(static_cast<std::size_t>(set)) ? 1 : 0;
    if (f.mix_pc)
      raw ^= ip;
    break;
  }

  return static_cast<std::uint8_t>(compress_bits(raw, f.bits));
}

std::int16_t mpppb::predict(core_view& st, long set, std::uint64_t ip, std::uint64_t addr,
                            std::uint64_t block, bool insert, std::array<std::uint8_t, kFeatureCount>& key)
{
  int total = 0;
  for (int f = 0; f < kFeatureCount; ++f) {
    key[static_cast<std::size_t>(f)] = index_of(plan_[f], st, set, ip, addr, block, insert);
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
                          const std::array<std::uint8_t, kFeatureCount>& key)
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

long mpppb::find_victim(uint32_t, uint64_t, long set, const champsim::cache_block*, champsim::address, champsim::address,
                        access_type)
{
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
                                     champsim::address ip, champsim::address, access_type, uint8_t hit)
{
  const auto raw = full_addr.to<std::uint64_t>();
  const auto block = raw >> 6U;
  const auto pc = ip.to<std::uint64_t>();
  const bool insertion = (hit == 0);

  auto& core = cores_.at(triggering_cpu);
  std::array<std::uint8_t, kFeatureCount> key{};
  const std::int16_t score = predict(core, set, pc, raw, block, insertion, key);

  if (set % kSampleStride == 0)
    visit_sampler(core, set, partial_tag(block), score, key);

  if (insertion) {
    auto& q = in_flight_.at(static_cast<std::size_t>(set));
    if (q.size() >= kPendingCap)
      q.pop_front();
    q.push_back(pending_hit{block, score});
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

  core.pc_ring[core.stamps % core.pc_ring.size()] = pc;
  ++core.stamps;
  miss_last_.at(static_cast<std::size_t>(set)) = insertion ? 1 : 0;
}