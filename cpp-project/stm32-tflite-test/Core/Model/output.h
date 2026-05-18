#pragma once

#include <cstddef>
#include <cstdint>

#define OUTPUT_SIZE 10

class ModelOutput {
public:
    float *data;
    int size;
    unsigned long inference_time_us;

    explicit ModelOutput(int size_bytes)
        : data(new float[size_bytes]),
          size(size_bytes),
          inference_time_us(0)
    {
    }
};
