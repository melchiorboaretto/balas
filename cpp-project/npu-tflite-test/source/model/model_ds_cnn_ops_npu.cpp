/*
 * Copyright 2026 NXP
 * All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include "tensorflow/lite/micro/kernels/micro_ops.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/kernels/neutron/neutron.h"

tflite::MicroOpResolver &MODEL_GetOpsResolver()
{
    // BALAS: o mesmo firmware roda o modelo original (tudo na CPU, kernels
    // CMSIS-NN) e o modelo convertido pelo neutron_compiler (NEUTRON_GRAPH na
    // NPU + o que sobrou na CPU). Por isso registra um superconjunto fixo de
    // operadores. A lista precisa bater com FIRMWARE_OPS em
    // python_scripts/npu/cpu_vs_npu.py, que recusa modelos com outros ops.
    static tflite::MicroMutableOpResolver<24> s_microOpResolver;

    s_microOpResolver.AddCustom(tflite::GetString_NEUTRON_GRAPH(), tflite::Register_NEUTRON_GRAPH());
    s_microOpResolver.AddConv2D();
    s_microOpResolver.AddDepthwiseConv2D();
    s_microOpResolver.AddFullyConnected();
    s_microOpResolver.AddAveragePool2D();
    s_microOpResolver.AddMaxPool2D();
    s_microOpResolver.AddAdd();
    s_microOpResolver.AddMul();
    s_microOpResolver.AddSub();
    s_microOpResolver.AddPad();
    s_microOpResolver.AddReshape();
    s_microOpResolver.AddSoftmax();
    s_microOpResolver.AddLogistic();
    s_microOpResolver.AddRelu();
    s_microOpResolver.AddRelu6();
    s_microOpResolver.AddMean();
    s_microOpResolver.AddQuantize();
    s_microOpResolver.AddDequantize();
    s_microOpResolver.AddConcatenation();
    s_microOpResolver.AddShape();
    s_microOpResolver.AddStridedSlice();
    s_microOpResolver.AddPack();
    s_microOpResolver.AddSqueeze();
    s_microOpResolver.AddTanh();

    return s_microOpResolver;
}
