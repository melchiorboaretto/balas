#include "quantization.h"

#include <cmath>

void float32_to_int8(const float *float_values, int8_t *int8_values, int size, float scale, int zero_point)
{
    for (int index = 0; index < size; ++index) {
        int value = static_cast<int>(std::round(float_values[index] / scale + static_cast<float>(zero_point)));
        if (value > 127) {
            value = 127;
        } else if (value < -128) {
            value = -128;
        }
        int8_values[index] = static_cast<int8_t>(value);
    }
}

void int8_to_float32(const int8_t *int8_values, float *float32_values, int length, float scale, int zero_point)
{
    for (int index = 0; index < length; ++index) {
        float32_values[index] = scale * static_cast<float>(int8_values[index] - zero_point);
    }
}
