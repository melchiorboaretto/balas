#include "timer.h"

#include "main.h"

static uint32_t start_cycle_count = 0;

static void dwt_init()
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

void start_timing()
{
    if ((DWT->CTRL & DWT_CTRL_CYCCNTENA_Msk) == 0U) {
        dwt_init();
    }
    start_cycle_count = DWT->CYCCNT;
}

int stop_timing()
{
    const uint32_t elapsed_cycles = DWT->CYCCNT - start_cycle_count;
    const uint32_t cycles_per_us = SystemCoreClock / 1000000U;
    if (cycles_per_us == 0U) {
        return static_cast<int>(elapsed_cycles);
    }
    return static_cast<int>(elapsed_cycles / cycles_per_us);
}

