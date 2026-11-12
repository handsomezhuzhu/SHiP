#include "shipp.h"

#include <algorithm>
#include <cassert>

#include "champsim.h"

namespace
{
std::size_t shct_index(champsim::address ip, bool is_prefetch)
{
  using namespace champsim::data::data_literals;
  const auto pc = ip.slice_lower<32_b>().to<std::size_t>();
  return ((pc << 1U) | (is_prefetch ? 1U : 0U)) % shipp::SHCT_PRIME;
}

void saturating_inc(uint8_t& c)
{
  if (c < shipp::SHCT_MAX)
    ++c;
}

void saturating_dec(uint8_t& c)
{
  if (c > 0)
    --c;
}
} // namespace

shipp::shipp(CACHE* cache)
    : replacement(cache), NUM_SET(cache->NUM_SET), NUM_WAY(cache->NUM_WAY),
      sampler(champsim::msl::get_num_samples(NUM_SET) * NUM_CPUS * static_cast<std::size_t>(NUM_WAY)),
      rrpv_values(static_cast<std::size_t>(NUM_SET * NUM_WAY), maxRRPV),
      prefetched(static_cast<std::size_t>(NUM_SET * NUM_WAY), 0),
      set_categorizer(champsim::msl::get_sample_rate(NUM_SET)), sampler_tag_bits(cache->OFFSET_BITS)
{
  SHCT.resize(NUM_CPUS);
  for (auto& table : SHCT)
    table.fill(0);
}

int& shipp::get_rrpv(long set, long way) { return rrpv_values.at(static_cast<std::size_t>(set * NUM_WAY + way)); }

uint8_t& shipp::get_prefetched(long set, long way) { return prefetched.at(static_cast<std::size_t>(set * NUM_WAY + way)); }

// 与 SRRIP 相同的受害者选择：找 RRPV 最大的行，必要时整体 aging
long shipp::find_victim(uint32_t, uint64_t, long set, const champsim::cache_block*, champsim::address, champsim::address, access_type)
{
  auto begin = std::next(std::begin(rrpv_values), set * NUM_WAY);
  auto end = std::next(begin, NUM_WAY);

  auto victim = std::max_element(begin, end);
  if (auto rrpv_update = maxRRPV - *victim; rrpv_update != 0)
    for (auto it = begin; it != end; ++it)
      *it += rrpv_update;

  assert(begin <= victim);
  assert(victim < end);
  return std::distance(begin, victim);
}

// 每次访问都会调用：命中/缺失都在这里维护采样器与 RRPV
void shipp::update_replacement_state(uint32_t triggering_cpu, long set, long way, champsim::address full_addr, champsim::address ip,
                                     champsim::address, access_type type, uint8_t hit)
{
  using namespace champsim::data::data_literals;
  const bool is_prefetch = (type == access_type::PREFETCH);

  // 采样器：只对采样组维护签名 + R 位，用于训练 SHCT
  if (set_categorizer.get_sample_category(set) == 0) {
    auto s_idx = set / champsim::msl::get_sample_rate(NUM_SET);
    auto s_set_begin = std::next(std::begin(sampler), s_idx * NUM_WAY + champsim::msl::get_num_samples(NUM_SET) * NUM_WAY * triggering_cpu);
    auto s_set_end = std::next(s_set_begin, NUM_WAY);

    auto match = std::find_if(s_set_begin, s_set_end, [addr = full_addr, shamt = sampler_tag_bits](auto x) {
      return x.valid && x.address.slice_upper(shamt) == addr.slice_upper(shamt);
    });

    if (match != s_set_end) {
      // 第一次复用才训练（Enhancement 2）
      if (!match->R) {
        saturating_inc(SHCT[triggering_cpu][match->sig]);
        match->R = true;
      }
      match->last_used = access_count++;
    } else {
      // 采样器中被替换的行没有被复用 -> 减弱它的签名
      if (match->valid && !match->R)
        saturating_dec(SHCT[triggering_cpu][match->sig]);

      match->valid = true;
      match->address = full_addr;
      match->R = false;
      match->is_prefetch = is_prefetch;
      match->sig = shct_index(ip, is_prefetch);
      match->last_used = access_count++;
    }
  }

  if (hit) {
    if (is_prefetch) {
      // 预取命中预取行：不给高优先级（Enhancement 5）
    } else if (get_prefetched(set, way)) {
      // demand 首次命中预取行：降级并清除标记
      get_rrpv(set, way) = maxRRPV;
      get_prefetched(set, way) = false;
    } else {
      get_rrpv(set, way) = 0;
    }
  }
}

// 行填入时决定插入位置
void shipp::replacement_cache_fill(uint32_t triggering_cpu, long set, long way, champsim::address, champsim::address ip, champsim::address, access_type type)
{
  get_prefetched(set, way) = false;

  // 写回插入不再占用高优先级（Enhancement 3）
  if (type == access_type::WRITE) {
    get_rrpv(set, way) = maxRRPV;
    return;
  }

  const bool is_prefetch = (type == access_type::PREFETCH);
  const auto sig = shct_index(ip, is_prefetch);
  const auto c = SHCT[triggering_cpu][sig];

  // Enhancement 1: 更宽的插入点
  if (c >= SHCT_MAX)
    get_rrpv(set, way) = 0;
  else if (c == 0)
    get_rrpv(set, way) = maxRRPV;
  else
    get_rrpv(set, way) = maxRRPV - 1;

  get_prefetched(set, way) = is_prefetch;
}