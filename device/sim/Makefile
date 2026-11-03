# 가상 ESP32 빌드: make -C device/sim  →  device/sim/guard_sim
GUARD = ../firmware/app/src/guard
CXXFLAGS = -O2 -std=c++17 -Wall -Wextra -I$(GUARD)

guard_sim: guard_sim.cpp $(GUARD)/guard.cpp $(GUARD)/guard.h $(GUARD)/model_data.h
	$(CXX) $(CXXFLAGS) guard_sim.cpp $(GUARD)/guard.cpp -o $@ -lm

clean:
	rm -f guard_sim
