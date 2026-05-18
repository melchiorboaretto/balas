/**
  ******************************************************************************
  * @file    balas_model_data_params.h
  * @author  AST Embedded Analytics Research Platform
  * @date    2026-05-18T14:54:26-0300
  * @brief   AI Tool Automatic Code Generator for Embedded NN computing
  ******************************************************************************
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  ******************************************************************************
  */

#ifndef BALAS_MODEL_DATA_PARAMS_H
#define BALAS_MODEL_DATA_PARAMS_H

#include "ai_platform.h"

/*
#define AI_BALAS_MODEL_DATA_WEIGHTS_PARAMS \
  (AI_HANDLE_PTR(&ai_balas_model_data_weights_params[1]))
*/

#define AI_BALAS_MODEL_DATA_CONFIG               (NULL)


#define AI_BALAS_MODEL_DATA_ACTIVATIONS_SIZES \
  { 43424, }
#define AI_BALAS_MODEL_DATA_ACTIVATIONS_SIZE     (43424)
#define AI_BALAS_MODEL_DATA_ACTIVATIONS_COUNT    (1)
#define AI_BALAS_MODEL_DATA_ACTIVATION_1_SIZE    (43424)



#define AI_BALAS_MODEL_DATA_WEIGHTS_SIZES \
  { 78744, }
#define AI_BALAS_MODEL_DATA_WEIGHTS_SIZE         (78744)
#define AI_BALAS_MODEL_DATA_WEIGHTS_COUNT        (1)
#define AI_BALAS_MODEL_DATA_WEIGHT_1_SIZE        (78744)



#define AI_BALAS_MODEL_DATA_ACTIVATIONS_TABLE_GET() \
  (&g_balas_model_activations_table[1])

extern ai_handle g_balas_model_activations_table[1 + 2];



#define AI_BALAS_MODEL_DATA_WEIGHTS_TABLE_GET() \
  (&g_balas_model_weights_table[1])

extern ai_handle g_balas_model_weights_table[1 + 2];


#endif    /* BALAS_MODEL_DATA_PARAMS_H */
