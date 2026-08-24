#include "serial_io.h"

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/uart.h>

namespace {
const device *const uart_device = DEVICE_DT_GET(DT_NODELABEL(uart0));
}

bool serial_init()
{
    return device_is_ready(uart_device);
}

void serial_read(uint8_t *dst, std::size_t n_bytes)
{
    std::size_t received = 0;
    while (received < n_bytes) {
        unsigned char value = 0;
        if (uart_poll_in(uart_device, &value) == 0) {
            dst[received++] = static_cast<uint8_t>(value);
        }
    }
}

void serial_write(const uint8_t *src, std::size_t n_bytes)
{
    for (std::size_t index = 0; index < n_bytes; ++index) {
        uart_poll_out(uart_device, src[index]);
    }
}
