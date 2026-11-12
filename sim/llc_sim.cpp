// 轻量 trace-driven 缓存模拟器：L1D(32KB) -> L2(256KB) -> LLC(2MB)，
// 用于快速比较 LLC 插入策略（LRU / SRRIP / SHiP）。
//
// 只模拟容量与替换，不对流水线建模；指标是 LLC 访问/缺失（MPKI）。
// 输入：xz -dc <champsim trace> | ./llc_sim --policy ship --max-instr 200000000
//
// 说明：ChampSim 的 ship 实现使用 1/16 的 set sampling 来省 SHCT 开销；
// 这里为了简化与可读性，对全部访问更新 SHCT（相当于不做 sampling 的 SHiP）。

#include <algorithm>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

struct Instr {
  uint64_t ip;
  uint8_t is_branch;
  uint8_t branch_taken;
  uint8_t dst_reg[2];
  uint8_t src_reg[4];
  uint64_t dst_mem[2];
  uint64_t src_mem[4];
};
static_assert(sizeof(Instr) == 64, "champsim trace record must be 64 bytes");

struct Line {
  uint64_t tag = 0;
  uint64_t ip = 0;
  uint64_t stamp = 0;
  int16_t rrpv = 0;
  bool valid = false;
  bool used = false;
};

enum class Policy { LRU, SRRIP, SHIP };

class Cache {
 public:
  Cache(int sets, int ways, int max_rrpv = 3)
      : sets_(sets), ways_(ways), max_rrpv_(max_rrpv), lines_(size_t(sets) * ways) {}

  bool access(uint64_t addr, uint64_t ip, Policy pol, uint64_t& evicted_ip, bool& evicted_used) {
    const uint64_t tag = addr >> 6;
    const int set = int(tag % uint64_t(sets_));
    Line* base = &lines_[size_t(set) * ways_];

    for (int w = 0; w < ways_; ++w) {
      Line& l = base[w];
      if (l.valid && l.tag == tag) {
        // hit
        if (pol == Policy::LRU) {
          l.stamp = ++clock_;
        } else {
          l.rrpv = 0;  // SRRIP/SHiP 命中提升
          if (pol == Policy::SHIP && shct_[l.ip % SHCT_PRIME] > 0) shct_[l.ip % SHCT_PRIME] -= 1;
        }
        l.used = true;
        return true;
      }
    }

    // miss: 选 victim
    int victim = 0;
    if (pol == Policy::LRU) {
      for (int w = 1; w < ways_; ++w)
        if (base[w].stamp < base[victim].stamp) victim = w;
    } else {
      int maxv = -1;
      for (int w = 0; w < ways_; ++w)
        if (base[w].rrpv > maxv) { maxv = base[w].rrpv; victim = w; }
      if (maxv < max_rrpv_) {
        for (int w = 0; w < ways_; ++w) base[w].rrpv += int16_t(max_rrpv_ - maxv);
      }
    }

    Line& v = base[victim];
    evicted_ip = v.valid ? v.ip : 0;
    evicted_used = v.used;
    if (v.valid && pol == Policy::SHIP && !v.used) {
      auto& c = shct_[v.ip % SHCT_PRIME];
      if (c < SHCT_MAX) c += 1;
    }

    v.valid = true;
    v.tag = tag;
    v.ip = ip;
    v.used = false;
    if (pol == Policy::LRU) {
      v.stamp = ++clock_;
    } else if (pol == Policy::SRRIP) {
      v.rrpv = int16_t(max_rrpv_ - 1);  // 2
    } else {                            // SHiP: SHCT 饱和 => 插入到最易替换的位置
      v.rrpv = (shct_[ip % SHCT_PRIME] >= SHCT_MAX) ? int16_t(max_rrpv_) : int16_t(max_rrpv_ - 1);
    }
    return false;
  }

 private:
  static constexpr uint32_t SHCT_SIZE = 16384;
  static constexpr uint32_t SHCT_PRIME = 16381;
  static constexpr int SHCT_MAX = 7;

  int sets_, ways_, max_rrpv_;
  std::vector<Line> lines_;
  std::vector<int> shct_ = std::vector<int>(SHCT_SIZE, 0);
  uint64_t clock_ = 0;
};

struct Stats {
  uint64_t instr = 0, memops = 0;
  uint64_t l1_miss = 0, l2_miss = 0, llc_miss = 0;
};

int main(int argc, char** argv) {
  Policy pol = Policy::LRU;
  std::string pol_name = "lru";
  uint64_t max_instr = 0, warmup = 0;

  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    if (a == "--policy" && i + 1 < argc) {
      pol_name = argv[++i];
      if (pol_name == "lru") pol = Policy::LRU;
      else if (pol_name == "srrip") pol = Policy::SRRIP;
      else if (pol_name == "ship") pol = Policy::SHIP;
      else { std::fprintf(stderr, "unknown policy %s\n", pol_name.c_str()); return 1; }
    } else if (a == "--max-instr" && i + 1 < argc) {
      max_instr = std::strtoull(argv[++i], nullptr, 10);
    } else if (a == "--warmup" && i + 1 < argc) {
      warmup = std::strtoull(argv[++i], nullptr, 10);
    }
  }

  Cache l1(64, 8), l2(512, 8), llc(2048, 16);
  Stats st;
  Instr in;

  while (std::fread(&in, sizeof(Instr), 1, stdin) == 1) {
    if (max_instr && st.instr >= max_instr) break;
    const bool measured = st.instr >= warmup;

    for (uint64_t addr : in.src_mem) {
      if (!addr) continue;
      if (measured) st.memops++;
      uint64_t eip; bool eused;
      bool h1 = l1.access(addr, in.ip, Policy::LRU, eip, eused);
      if (h1) continue;
      if (measured) st.l1_miss++;
      bool h2 = l2.access(addr, in.ip, Policy::LRU, eip, eused);
      if (h2) continue;
      if (measured) st.l2_miss++;
      bool h3 = llc.access(addr, in.ip, pol, eip, eused);
      if (!h3 && measured) st.llc_miss++;
    }
    for (uint64_t addr : in.dst_mem) {
      if (!addr) continue;
      if (measured) st.memops++;
      uint64_t eip; bool eused;
      bool h1 = l1.access(addr, in.ip, Policy::LRU, eip, eused);
      if (h1) continue;
      if (measured) st.l1_miss++;
      bool h2 = l2.access(addr, in.ip, Policy::LRU, eip, eused);
      if (h2) continue;
      if (measured) st.l2_miss++;
      bool h3 = llc.access(addr, in.ip, pol, eip, eused);
      if (!h3 && measured) st.llc_miss++;
    }
    st.instr++;
  }

  const uint64_t n = st.instr > warmup ? st.instr - warmup : 1;
  std::printf("policy,instr,memops,l1_miss,l2_miss,llc_access,llc_miss,llc_mpki\n");
  std::printf("%s,%llu,%llu,%llu,%llu,%llu,%llu,%.4f\n", pol_name.c_str(),
              (unsigned long long)n, (unsigned long long)st.memops,
              (unsigned long long)st.l1_miss, (unsigned long long)st.l2_miss,
              (unsigned long long)st.l2_miss, (unsigned long long)st.llc_miss,
              double(st.llc_miss) * 1000.0 / double(n));
  return 0;
}