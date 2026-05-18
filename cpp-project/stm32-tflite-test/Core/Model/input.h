#pragma once

#include <cstddef>
#include <cstdint>

class ModelInput {
public:
    float *data;
    int size;

    explicit ModelInput(int size_bytes)
        : data(new float[size_bytes]),
          size(size_bytes)
    {
    }
};
