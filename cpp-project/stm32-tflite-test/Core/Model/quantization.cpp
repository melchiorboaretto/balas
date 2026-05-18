#include "quantization.h"

#include <cmath>
#include <cstdint>

void float32_to_int8(const float *float_values, int8_t *int8_values, int size, float scale, int zero_point)
{
    for (int i = 0; i < size; i++) {
        int value = static_cast<int>(std::round(float_values[i] / scale + static_cast<float>(zero_point)));
        if (value > 127) {
            value = 127;
        } else if (value < -128) {
            value = -128;
        }
        int8_values[i] = static_cast<int8_t>(value);
    }
}

void int8_to_float32(const int8_t *int8_values, float *float32_values, int length, float scale, int zero_point)
{
    for (int i = 0; i < length; i++) {
        float32_values[i] = scale * static_cast<float>(int8_values[i] - zero_point);
    }
}

