/*
 * Firmware de medição CPU x NPU do BALAS para a FRDM-MCXN947.
 *
 * Baseado no exemplo tflm_kws do MCUXpresso SDK 26.09. Roda o modelo de
 * source/model/model_data.h (gerado por python_scripts/npu/cpu_vs_npu.py):
 *   - modelo original  -> tudo na CPU (kernels CMSIS-NN do TFLM da NXP);
 *   - modelo convertido pelo neutron_compiler -> NEUTRON_GRAPH na NPU e o
 *     que sobrou (SOFTMAX, PAD...) na CPU.
 *
 * Protocolo serial (115200 8N1): o firmware espera o PC mandar 'r' e então
 * imprime linhas BALAS_*. Esperar o 'r' evita perder a saída enquanto o PC
 * ainda está abrindo a porta depois da gravação.
 *
 *   BALAS_INFO model=<nome> core_mhz=<f> arena_total=<B> arena_used=<B> model_bytes=<B> input_bytes=<n> output_bytes=<n>
 *   BALAS_RUN <i> cycles=<c> us=<us>
 *   BALAS_OUTPUT <bytes da saída int8 em hex>
 *   BALAS_RESULT runs=<n> avg_us=<us> min_us=<us> max_us=<us>
 *   BALAS_ERROR <motivo>
 *   BALAS_DONE
 *
 * Tempo de cada inferência = só Invoke() (sem preparar entrada nem ler saída).
 * cycles vem do DWT (preciso, mas dá a volta em ~28 s a 150 MHz); us vem do
 * SysTick (resolução de ~1 us, sem esse limite). O script usa cycles quando a
 * inferência dura menos de 20 s e us acima disso.
 *
 * Copyright 2020-2022 NXP (exemplo original)
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include "board_init.h"
#include "fsl_debug_console.h"
#include "fsl_device_registers.h"
#include "model.h"
#include "timer.h"

#ifndef BALAS_WARMUP_RUNS
#define BALAS_WARMUP_RUNS 1
#endif
#ifndef BALAS_TIMED_RUNS
#define BALAS_TIMED_RUNS 10
#endif

static void cycle_counter_init(void)
{
#ifdef DCB
    DCB->DEMCR |= DCB_DEMCR_TRCENA_Msk;
#else
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
#endif
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

static uint32_t tensor_bytes(const tensor_dims_t* dims, tensor_type_t type)
{
    uint32_t n = 1;
    for (uint32_t i = 0; i < dims->size; i++)
    {
        n *= dims->data[i];
    }
    switch (type)
    {
        case kTensorType_FLOAT32: return n * 4;
        case kTensorType_INT16: return n * 2;
        default: return n;
    }
}

static void wait_for_start(void)
{
    for (;;)
    {
        int c = GETCHAR();
        if (c == 'r')
        {
            return;
        }
    }
}

int main(void)
{
    BOARD_Init();
    TIMER_Init();
    cycle_counter_init();

    PRINTF("\r\nBALAS_BOOT\r\n");
    wait_for_start();

    if (MODEL_Init() != kStatus_Success)
    {
        PRINTF("BALAS_ERROR model_init_failed\r\nBALAS_DONE\r\n");
        for (;;) {}
    }

    tensor_dims_t inputDims;
    tensor_type_t inputType;
    uint8_t* input = MODEL_GetInputTensorData(&inputDims, &inputType);
    uint32_t inputBytes = tensor_bytes(&inputDims, inputType);

    tensor_dims_t outputDims;
    tensor_type_t outputType;
    uint8_t* output = MODEL_GetOutputTensorData(&outputDims, &outputType);
    uint32_t outputBytes = tensor_bytes(&outputDims, outputType);

    const float coreMhz = SystemCoreClock / 1000000.0f;
    PRINTF("BALAS_INFO model=%s core_mhz=%u arena_total=%u arena_used=%u model_bytes=%u input_bytes=%u output_bytes=%u\r\n",
           MODEL_GetModelName(), (unsigned)(SystemCoreClock / 1000000u), (unsigned)MODEL_GetArenaTotalBytes(),
           (unsigned)MODEL_GetArenaUsedBytes(), (unsigned)MODEL_GetModelBytes(), (unsigned)inputBytes,
           (unsigned)outputBytes);

    for (;;)
    {
        /* Entrada fixa e determinística, igual à que o PC usa para conferir a
         * saída: byte i = (i * 37) & 0xFF. */
        for (uint32_t i = 0; i < inputBytes; i++)
        {
            input[i] = (uint8_t)((i * 37u) & 0xFFu);
        }

        for (int i = 0; i < BALAS_WARMUP_RUNS; i++)
        {
            if (MODEL_RunInference() != kStatus_Success)
            {
                PRINTF("BALAS_ERROR invoke_failed\r\nBALAS_DONE\r\n");
                for (;;) {}
            }
        }

        uint64_t totalUs = 0;
        uint32_t minUs = 0xFFFFFFFFu;
        uint32_t maxUs = 0;
        for (int i = 0; i < BALAS_TIMED_RUNS; i++)
        {
            uint32_t startUs = (uint32_t)TIMER_GetTimeInUS();
            uint32_t startCycles = DWT->CYCCNT;
            status_t status = MODEL_RunInference();
            uint32_t cycles = DWT->CYCCNT - startCycles;
            uint32_t us = (uint32_t)TIMER_GetTimeInUS() - startUs;
            if (status != kStatus_Success)
            {
                PRINTF("BALAS_ERROR invoke_failed\r\nBALAS_DONE\r\n");
                for (;;) {}
            }
            if (us < 20000000u)
            {
                us = (uint32_t)(cycles / coreMhz + 0.5f);
            }
            totalUs += us;
            minUs = us < minUs ? us : minUs;
            maxUs = us > maxUs ? us : maxUs;
            PRINTF("BALAS_RUN %d cycles=%u us=%u\r\n", i, (unsigned)cycles, (unsigned)us);
        }

        /* Hex feito à mão: o PRINTF do debug_console_lite não aceita "%02x". */
        static const char kHex[] = "0123456789abcdef";
        PRINTF("BALAS_OUTPUT ");
        for (uint32_t i = 0; i < outputBytes; i++)
        {
            PUTCHAR(kHex[output[i] >> 4]);
            PUTCHAR(kHex[output[i] & 0xF]);
        }
        PRINTF("\r\n");
        PRINTF("BALAS_RESULT runs=%d avg_us=%u min_us=%u max_us=%u\r\n", BALAS_TIMED_RUNS,
               (unsigned)(totalUs / BALAS_TIMED_RUNS), (unsigned)minUs, (unsigned)maxUs);
        PRINTF("BALAS_DONE\r\n");

        wait_for_start();
    }
}
