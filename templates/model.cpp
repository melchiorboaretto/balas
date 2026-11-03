// model.cpp — improved, safer version
#include "model.h"
#include "fsl_common.h"
#include <new>      // for std::nothrow
#include <cstring>  // for memcpy
#include <cstdint>

#include "model_data.h"
#include "quantization.h"

// Put arena in non-cacheable RAM and align
static uint8_t tensor_arena[TENSOR_ARENA_SIZE] __ALIGNED(16);

MyModel::MyModel() : 
    model(tflite::GetModel(model_data)),
    interpreter(model, resolver, tensor_arena, TENSOR_ARENA_SIZE)
{


    // Load model (make sure model_binary is const and linked into flash)
    if (model == nullptr) {

        while (1) {}
    }
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        // not necessarily fatal, but good to know
    }


GEN_RESOLVER_OPS


    TfLiteStatus allocation_status = interpreter.AllocateTensors();
    if (allocation_status != kTfLiteOk) {
        while (1) {}
    }
}


void MyModel::run_inference(ModelInput& input, ModelOutput& output) {
    set_input(input);
    invoke();
    get_output(output);
}

void MyModel::set_input(ModelInput& input) {
    TfLiteTensor* in_t = interpreter.input_tensor(0);
    float32_to_int8(input.data, in_t->data.int8, input.size, in_t->params.scale, in_t->params.zero_point);
}

void MyModel::invoke() {
    TfLiteStatus invoke_status = interpreter.Invoke();

    if (invoke_status != kTfLiteOk) {
    	while(1) {}
    }
}

void MyModel::get_output(ModelOutput& output) {
    TfLiteTensor* out_t = interpreter.output_tensor(0);
    int8_to_float32(out_t->data.int8, output.data, output.size, out_t->params.scale, out_t->params.zero_point);
}

void MyModel::print_outputs(ModelOutput& output) {

}



int MyModel::get_input_size() {
	return interpreter.input(0)->bytes;
//	return interpreter.inputs_size();
}
int MyModel::get_output_size() {
	return interpreter.output(0)->bytes;
//	return interpreter.outputs_size();
}
int MyModel::get_arena_used_bytes() {
    return interpreter.arena_used_bytes();
}