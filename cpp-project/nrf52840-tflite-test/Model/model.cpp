#include "model.h"

#include <cstdint>

#include "model_data.h"
#include "quantization.h"

namespace {
alignas(16) uint8_t tensor_arena[TENSOR_ARENA_SIZE];
}

MyModel::MyModel()
    : model(tflite::GetModel(model_data)),
      resolver(),
      interpreter(model, resolver, tensor_arena, TENSOR_ARENA_SIZE),
      ready(false)
{
    if (model == nullptr || model->version() != TFLITE_SCHEMA_VERSION) {
        return;
    }

// BALAS_GENERATED_RESOLVER_OPS_BEGIN
	resolver.AddConv2D();
	resolver.AddAdd();
	resolver.AddAveragePool2D();
	resolver.AddShape();
	resolver.AddStridedSlice();
	resolver.AddPack();
	resolver.AddReshape();
	resolver.AddFullyConnected();
	resolver.AddSoftmax();
// BALAS_GENERATED_RESOLVER_OPS_END

    ready = interpreter.AllocateTensors() == kTfLiteOk;
}

bool MyModel::run_inference(ModelInput &input, ModelOutput &output)
{
    if (!ready) {
        return false;
    }
    TfLiteTensor *input_tensor = interpreter.input_tensor(0);
    TfLiteTensor *output_tensor = interpreter.output_tensor(0);
    if (input_tensor == nullptr || output_tensor == nullptr) {
        return false;
    }

    const int input_count = input.size / static_cast<int>(sizeof(float));
    float32_to_int8(
        input.data,
        input_tensor->data.int8,
        input_count,
        input_tensor->params.scale,
        input_tensor->params.zero_point);

    if (interpreter.Invoke() != kTfLiteOk) {
        return false;
    }

    int8_to_float32(
        output_tensor->data.int8,
        output.data,
        output.size,
        output_tensor->params.scale,
        output_tensor->params.zero_point);
    return true;
}

int MyModel::get_input_size()
{
    if (!ready) {
        return 0;
    }
    TfLiteTensor *tensor = interpreter.input_tensor(0);
    return tensor == nullptr ? 0 : tensor->bytes * static_cast<int>(sizeof(float));
}

int MyModel::get_output_size()
{
    if (!ready) {
        return 0;
    }
    TfLiteTensor *tensor = interpreter.output_tensor(0);
    return tensor == nullptr ? 0 : tensor->bytes;
}

int MyModel::get_arena_used_bytes()
{
    return interpreter.arena_used_bytes();
}
