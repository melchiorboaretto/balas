#pragma once

#include "tensorflow/lite/micro/kernels/micro_ops.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "input.h"
#include "output.h"

#define TENSOR_ARENA_SIZE GEN_TENSOR_ARENA_SIZE
#define N_OPS GEN_N_OPS

class MyModel {
    private:
        const tflite::Model* model;
        tflite::MicroMutableOpResolver<N_OPS> resolver;
        tflite::MicroInterpreter interpreter;
    public:
        MyModel();
        void run_inference(ModelInput& input, ModelOutput& output);
        // run_inference em três etapas, para cronometrar só invoke(): a
        // quantização da entrada e da saída não faz parte da inferência
        // (o MLPerf Tiny também mede só a execução do modelo).
        void set_input(ModelInput& input);
        void invoke();
        void get_output(ModelOutput& output);
        void print_outputs(ModelOutput& output);
        int get_input_size();
        int get_output_size();
        int get_arena_used_bytes();
};



