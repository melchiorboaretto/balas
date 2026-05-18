#ifndef BALAS_STM32_MAIN_H
#define BALAS_STM32_MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32h7xx_hal.h"

extern UART_HandleTypeDef huart3;

void Error_Handler(void);

#ifdef __cplusplus
}
#endif

#endif

