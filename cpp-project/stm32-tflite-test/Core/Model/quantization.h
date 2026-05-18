#pragma once

#include <cstdint>

void float32_to_int8(const float *float_values, int8_t *int8_values, int size, float scale, int zero_point);
void int8_to_float32(const int8_t *int8_values, float *float32_values, int length, float scale, int zero_point);

