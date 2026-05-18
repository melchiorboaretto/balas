#include "model.h"

#include <cstdint>

#include "model_data.h"
#include "quantization.h"

#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
#include "serial_io.h"
#endif

#if defined(__GNUC__)
#define BALAS_ALIGNED(bytes) __attribute__((aligned(bytes)))
#else
#define BALAS_ALIGNED(bytes)
#endif

static uint8_t tensor_arena[TENSOR_ARENA_SIZE] BALAS_ALIGNED(16);

MyModel::MyModel()
    : model(tflite::GetModel(model_data)),
      resolver(),
      interpreter(model, resolver, tensor_arena, TENSOR_ARENA_SIZE)
{
    if (model == nullptr) {
        while (1) {
        }
    }

    if (model->version() != TFLITE_SCHEMA_VERSION) {
        while (1) {
        }
    }

    resolver.AddConv2D();
    resolver.AddAdd();
    resolver.AddAveragePool2D();
    resolver.AddShape();
    resolver.AddStridedSlice();
    resolver.AddPack();
    resolver.AddReshape();
    resolver.AddFullyConnected();
    resolver.AddSoftmax();

    if (interpreter.AllocateTensors() != kTfLiteOk) {
        while (1) {
        }
    }
}

void MyModel::run_inference(ModelInput &input, ModelOutput &output)
{
    TfLiteTensor *in_t = interpreter.input_tensor(0);
    TfLiteTensor *out_t = interpreter.output_tensor(0);

    const int input_float_count = input.size / static_cast<int>(sizeof(float));
#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
    uint8_t quantize_marker = 'Q';
    serial_write(&quantize_marker, 1U);
#endif
    float32_to_int8(input.data, in_t->data.int8, input_float_count, in_t->params.scale, in_t->params.zero_point);

#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
    uint8_t invoke_marker = 'G';
    serial_write(&invoke_marker, 1U);
#endif
    if (interpreter.Invoke() != kTfLiteOk) {
        while (1) {
        }
    }

#if defined(BALAS_STM32_MODEL_BOOT_MARKER)
    uint8_t done_marker = 'D';
    serial_write(&done_marker, 1U);
#endif
    int8_to_float32(out_t->data.int8, output.data, output.size, out_t->params.scale, out_t->params.zero_point);
}

void MyModel::print_outputs(ModelOutput &output)
{
    (void)output;
}

int MyModel::get_input_size()
{
    return interpreter.input(0)->bytes * static_cast<int>(sizeof(float));
}

int MyModel::get_output_size()
{
    return interpreter.output(0)->bytes;
}

int MyModel::get_arena_used_bytes()
{
    return interpreter.arena_used_bytes();
}
