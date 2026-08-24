#include <cstdint>

#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>

#include "input.h"
#include "model.h"
#include "output.h"
#include "serial_io.h"
#include "timer.h"

namespace {
const gpio_dt_spec status_led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);
}

extern "C" {
volatile uint32_t balas_runtime_stage = 0;
}

int main()
{
    balas_runtime_stage = 1;
    if (!serial_init()) {
        balas_runtime_stage = 0xE001;
        return 1;
    }
    if (gpio_is_ready_dt(&status_led)) {
        gpio_pin_configure_dt(&status_led, GPIO_OUTPUT_INACTIVE);
    }

    balas_runtime_stage = 2;
    MyModel model;
    balas_runtime_stage = 3;
    ModelInput input(model.get_input_size());
    balas_runtime_stage = 4;
    ModelOutput output(model.get_output_size());
    balas_runtime_stage = 5;

    while (true) {
        serial_read(reinterpret_cast<uint8_t *>(input.data), input.size);
        balas_runtime_stage = 6;
        gpio_pin_toggle_dt(&status_led);
        start_timing();
        const bool inference_ok = model.run_inference(input, output);
        int32_t inference_time_us = inference_ok ? stop_timing() : -1;
        balas_runtime_stage = inference_ok ? 7 : 0xE007;
        serial_write(reinterpret_cast<const uint8_t *>(&inference_time_us), sizeof(inference_time_us));
    }
    return 0;
}
