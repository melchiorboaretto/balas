#include "main.h"

#include "input.h"
#include "model.h"
#include "output.h"
#include "serial_io.h"
#include "timer.h"

extern "C" {
UART_HandleTypeDef huart3;
}

static void MX_GPIO_Init(void);
static void MX_USART3_UART_Init(void);
static void MPU_Config(void);
static void CPU_CACHE_Enable(void);
static void SystemClock_Config(void);

int main(void)
{
    MPU_Config();
    CPU_CACHE_Enable();

    HAL_Init();
    SystemClock_Config();

    MX_GPIO_Init();
    MX_USART3_UART_Init();

#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
    const uint8_t init_marker = 'I';
    for (int i = 0; i < 20; ++i) {
        serial_write(const_cast<uint8_t *>(&init_marker), 1U);
        HAL_Delay(100);
    }
#endif

    // Determine the I/O sizes from a temporary model instance. The interpreter
    // is then rebuilt per inference (see loop below).
    int input_size_bytes;
    int output_size_bytes;
    {
        MyModel sizing_model;
        input_size_bytes = sizing_model.get_input_size();
        output_size_bytes = sizing_model.get_output_size();
    }

#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
    const uint8_t model_marker = 'M';
    for (int i = 0; i < 20; ++i) {
        serial_write(const_cast<uint8_t *>(&model_marker), 1U);
        HAL_Delay(100);
    }
#endif

    ModelInput input(input_size_bytes);
    ModelOutput output(output_size_bytes);

#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
    serial_write(reinterpret_cast<uint8_t *>(&input.size), sizeof(input.size));
#endif

    while (1) {
        HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0);
        serial_read(reinterpret_cast<uint8_t *>(input.data), input.size);
#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
        const uint8_t read_marker = 'R';
        serial_write(const_cast<uint8_t *>(&read_marker), 1U);
#endif
        // Rebuild the interpreter for every inference. This TFLM build corrupts
        // the persistent input-tensor metadata in the arena during Invoke(), so
        // a second Invoke() on the same interpreter would fault. Reconstructing
        // gives a clean arena each time, matching the verified "reset between
        // samples" behavior. AllocateTensors() runs outside start/stop_timing,
        // so it does not affect the measured inference latency.
        MyModel model;
        start_timing();
        model.run_inference(input, output);
#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
        const uint8_t invoke_marker = 'V';
        serial_write(const_cast<uint8_t *>(&invoke_marker), 1U);
#endif
        int inference_time_us = stop_timing();
        serial_write(reinterpret_cast<uint8_t *>(&inference_time_us), sizeof(inference_time_us));
#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
        const uint8_t write_marker = 'W';
        serial_write(const_cast<uint8_t *>(&write_marker), 1U);
#endif
    }
}

static void MX_USART3_UART_Init(void)
{
    huart3.Instance = USART3;
    huart3.Init.BaudRate = 115200;
    huart3.Init.WordLength = UART_WORDLENGTH_8B;
    huart3.Init.StopBits = UART_STOPBITS_1;
    huart3.Init.Parity = UART_PARITY_NONE;
    huart3.Init.Mode = UART_MODE_TX_RX;
    huart3.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart3.Init.OverSampling = UART_OVERSAMPLING_16;
    huart3.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
    huart3.Init.ClockPrescaler = UART_PRESCALER_DIV1;
    huart3.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;

    if (HAL_UART_Init(&huart3) != HAL_OK) {
        Error_Handler();
    }
    if (HAL_UARTEx_SetTxFifoThreshold(&huart3, UART_TXFIFO_THRESHOLD_1_8) != HAL_OK) {
        Error_Handler();
    }
    if (HAL_UARTEx_SetRxFifoThreshold(&huart3, UART_RXFIFO_THRESHOLD_1_8) != HAL_OK) {
        Error_Handler();
    }
    if (HAL_UARTEx_DisableFifoMode(&huart3) != HAL_OK) {
        Error_Handler();
    }
}

static void MX_GPIO_Init(void)
{
    __HAL_RCC_GPIOB_CLK_ENABLE();

    GPIO_InitTypeDef GPIO_InitStruct = {};
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0, GPIO_PIN_RESET);
    GPIO_InitStruct.Pin = GPIO_PIN_0;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
}

static void MPU_Config(void)
{
    MPU_Region_InitTypeDef MPU_InitStruct = {};

    HAL_MPU_Disable();

    MPU_InitStruct.Enable = MPU_REGION_ENABLE;
    MPU_InitStruct.BaseAddress = 0x00;
    MPU_InitStruct.Size = MPU_REGION_SIZE_4GB;
    MPU_InitStruct.AccessPermission = MPU_REGION_NO_ACCESS;
    MPU_InitStruct.IsBufferable = MPU_ACCESS_NOT_BUFFERABLE;
    MPU_InitStruct.IsCacheable = MPU_ACCESS_NOT_CACHEABLE;
    MPU_InitStruct.IsShareable = MPU_ACCESS_SHAREABLE;
    MPU_InitStruct.Number = MPU_REGION_NUMBER0;
    MPU_InitStruct.TypeExtField = MPU_TEX_LEVEL0;
    MPU_InitStruct.SubRegionDisable = 0x87;
    MPU_InitStruct.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;

    HAL_MPU_ConfigRegion(&MPU_InitStruct);
    HAL_MPU_Enable(MPU_PRIVILEGED_DEFAULT);
}

static void CPU_CACHE_Enable(void)
{
    SCB_EnableICache();
    SCB_EnableDCache();
}

static void SystemClock_Config(void)
{
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {};
    RCC_OscInitTypeDef RCC_OscInitStruct = {};

    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE0);
    while (!__HAL_PWR_GET_FLAG(PWR_FLAG_VOSRDY)) {
    }

    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    RCC_OscInitStruct.HSEState = RCC_HSE_BYPASS;
    RCC_OscInitStruct.HSIState = RCC_HSI_OFF;
    RCC_OscInitStruct.CSIState = RCC_CSI_OFF;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLM = 4;
    RCC_OscInitStruct.PLL.PLLN = 260;
    RCC_OscInitStruct.PLL.PLLFRACN = 0;
    RCC_OscInitStruct.PLL.PLLP = 1;
    RCC_OscInitStruct.PLL.PLLR = 2;
    RCC_OscInitStruct.PLL.PLLQ = 4;
    RCC_OscInitStruct.PLL.PLLVCOSEL = RCC_PLL1VCOWIDE;
    RCC_OscInitStruct.PLL.PLLRGE = RCC_PLL1VCIRANGE_1;
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
        Error_Handler();
    }

    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                                  RCC_CLOCKTYPE_D1PCLK1 | RCC_CLOCKTYPE_PCLK1 |
                                  RCC_CLOCKTYPE_PCLK2 | RCC_CLOCKTYPE_D3PCLK1;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.SYSCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_HCLK_DIV2;
    RCC_ClkInitStruct.APB3CLKDivider = RCC_APB3_DIV2;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_APB1_DIV2;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_APB2_DIV2;
    RCC_ClkInitStruct.APB4CLKDivider = RCC_APB4_DIV2;
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_3) != HAL_OK) {
        Error_Handler();
    }
}

extern "C" void Error_Handler(void)
{
    __disable_irq();
    while (1) {
        HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0);
        for (volatile uint32_t i = 0; i < 1000000U; ++i) {
        }
    }
}
