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

int main(void)
{
    HAL_Init();
    MX_GPIO_Init();
    MX_USART3_UART_Init();

#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
    const uint8_t init_marker = 'I';
    for (int i = 0; i < 20; ++i) {
        serial_write(const_cast<uint8_t *>(&init_marker), 1U);
        HAL_Delay(100);
    }
#endif

    MyModel model;

#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
    const uint8_t model_marker = 'M';
    for (int i = 0; i < 20; ++i) {
        serial_write(const_cast<uint8_t *>(&model_marker), 1U);
        HAL_Delay(100);
    }
#endif

    ModelInput input(model.get_input_size());
    ModelOutput output(model.get_output_size());

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

extern "C" void Error_Handler(void)
{
    __disable_irq();
    while (1) {
        HAL_GPIO_TogglePin(GPIOB, GPIO_PIN_0);
        for (volatile uint32_t i = 0; i < 1000000U; ++i) {
        }
    }
}
