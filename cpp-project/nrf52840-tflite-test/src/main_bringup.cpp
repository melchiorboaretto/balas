#include <cstdint>

#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>

#include "serial_io.h"

namespace {
constexpr int32_t kBringupResponse = 52840;
const gpio_dt_spec status_led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);

void signal_boot()
{
    if (!gpio_is_ready_dt(&status_led)) {
        return;
    }
    if (gpio_pin_configure_dt(&status_led, GPIO_OUTPUT_INACTIVE) != 0) {
        return;
    }
    for (int index = 0; index < 4; ++index) {
        gpio_pin_toggle_dt(&status_led);
        k_msleep(100);
    }
}
}

int main()
{
    signal_boot();
    if (!serial_init()) {
        return 1;
    }

    while (true) {
        uint8_t request[4];
        serial_read(request, sizeof(request));
        gpio_pin_toggle_dt(&status_led);
        serial_write(reinterpret_cast<const uint8_t *>(&kBringupResponse), sizeof(kBringupResponse));
    }
    return 0;
}
