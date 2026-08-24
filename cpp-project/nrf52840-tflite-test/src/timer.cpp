#include "timer.h"

#include <cstdint>

#include <zephyr/kernel.h>

namespace {
uint32_t start_cycles = 0;
}

void start_timing()
{
    start_cycles = k_cycle_get_32();
}

int stop_timing()
{
    const uint32_t elapsed_cycles = k_cycle_get_32() - start_cycles;
    return static_cast<int>(k_cyc_to_us_floor32(elapsed_cycles));
}
