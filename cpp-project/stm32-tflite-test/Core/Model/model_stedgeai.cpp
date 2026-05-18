#include "model.h"

#include <cstddef>
#include <cstdint>

#include "balas_model.h"
#include "balas_model_data.h"
#include "balas_model_data_params.h"
#include "quantization.h"

#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
#include "serial_io.h"
#endif

#if defined(__GNUC__)
#define BALAS_ALIGNED(bytes) __attribute__((aligned(bytes)))
#else
#define BALAS_ALIGNED(bytes)
#endif

static ai_u8 activations[AI_BALAS_MODEL_DATA_ACTIVATIONS_SIZE] BALAS_ALIGNED(AI_BALAS_MODEL_ACTIVATIONS_ALIGNMENT);
static int8_t input_s8[AI_BALAS_MODEL_IN_1_SIZE] BALAS_ALIGNED(4);
static int8_t output_s8[AI_BALAS_MODEL_OUT_1_SIZE] BALAS_ALIGNED(4);

MyModel::MyModel()
    : network(AI_HANDLE_NULL),
      input_buffer(nullptr),
      output_buffer(nullptr)
{
    const ai_handle activations_map[] = {
        AI_HANDLE_PTR(activations),
    };
    const ai_handle weights_map[] = {
        ai_balas_model_data_weights_get(),
    };

    ai_error error = ai_balas_model_create_and_init(&network, activations_map, weights_map);
    if (error.type != AI_ERROR_NONE) {
        while (1) {
        }
    }

    input_buffer = ai_balas_model_inputs_get(network, nullptr);
    output_buffer = ai_balas_model_outputs_get(network, nullptr);
    if ((input_buffer == nullptr) || (output_buffer == nullptr)) {
        while (1) {
        }
    }

    input_buffer[0].data = AI_HANDLE_PTR(input_s8);
    output_buffer[0].data = AI_HANDLE_PTR(output_s8);
}

void MyModel::run_inference(ModelInput &input, ModelOutput &output)
{
    const int input_float_count = input.size / static_cast<int>(sizeof(float));
    if (input_float_count != AI_BALAS_MODEL_IN_1_SIZE || output.size < AI_BALAS_MODEL_OUT_1_SIZE) {
        while (1) {
        }
    }

#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
    uint8_t quantize_marker = 'Q';
    serial_write(&quantize_marker, 1U);
#endif
    float32_to_int8(input.data, input_s8, input_float_count, 1.0F, -128);

#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
    uint8_t invoke_marker = 'G';
    serial_write(&invoke_marker, 1U);
#endif
    const ai_i32 batch_count = ai_balas_model_run(network, input_buffer, output_buffer);
    if (batch_count != 1) {
        while (1) {
        }
    }

#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
    uint8_t done_marker = 'D';
    serial_write(&done_marker, 1U);
#endif
    int8_to_float32(output_s8, output.data, AI_BALAS_MODEL_OUT_1_SIZE, 0.00390625F, -128);
}

void MyModel::print_outputs(ModelOutput &output)
{
    (void)output;
}

int MyModel::get_input_size()
{
    return AI_BALAS_MODEL_IN_1_SIZE * static_cast<int>(sizeof(float));
}

int MyModel::get_output_size()
{
    return AI_BALAS_MODEL_OUT_1_SIZE;
}

int MyModel::get_arena_used_bytes()
{
    return AI_BALAS_MODEL_DATA_ACTIVATIONS_SIZE;
}
