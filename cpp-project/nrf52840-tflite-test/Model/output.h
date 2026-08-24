#pragma once

class ModelOutput {
public:
    float *data;
    int size;

    explicit ModelOutput(int element_count)
        : data(new float[element_count]),
          size(element_count)
    {
    }
};
