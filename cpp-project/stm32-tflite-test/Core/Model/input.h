#pragma once

#include <cstddef>
#include <cstdint>

class ModelInput {
public:
    float *data;
    int size;

    // size_bytes is the payload size in bytes; data must hold exactly that many
    // bytes. data is a float*, so allocate ceil(size_bytes / sizeof(float))
    // floats. Allocating new float[size_bytes] would reserve 4x the memory and
    // starve the stack on the 128 KB DTCM, corrupting memory during Invoke().
    explicit ModelInput(int size_bytes)
        : data(new float[(size_bytes + sizeof(float) - 1) / sizeof(float)]),
          size(size_bytes)
    {
    }
};
