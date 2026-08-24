#pragma once

#include <cstddef>

class ModelInput {
public:
    float *data;
    int size;

    explicit ModelInput(int size_bytes)
        : data(new float[(size_bytes + sizeof(float) - 1) / sizeof(float)]),
          size(size_bytes)
    {
    }
};
