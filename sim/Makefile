CXX ?= g++
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra

all: llc_sim

llc_sim: llc_sim.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

clean:
	rm -f llc_sim

.PHONY: all clean