#include "serial_io.h"

#include "main.h"

void serial_read(uint8_t *dst, unsigned long n_bytes)
{
    __HAL_UART_CLEAR_FLAG(&huart3, UART_CLEAR_OREF | UART_CLEAR_NEF | UART_CLEAR_FEF | UART_CLEAR_PEF);
    HAL_UART_Receive(&huart3, dst, static_cast<uint16_t>(n_bytes), HAL_MAX_DELAY);
}

void serial_write(uint8_t *src, unsigned long n_bytes)
{
    HAL_UART_Transmit(&huart3, src, static_cast<uint16_t>(n_bytes), HAL_MAX_DELAY);
}

