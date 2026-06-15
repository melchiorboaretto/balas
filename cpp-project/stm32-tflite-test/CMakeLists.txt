cmake_minimum_required(VERSION 3.22)

project(stm32-tflite-test LANGUAGES C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CUBE_H7_PATH "${CMAKE_CURRENT_LIST_DIR}/../../external/STM32CubeH7" CACHE PATH "Path to STM32CubeH7 package")
set(NXP_TFLITE_PROJECT_PATH "${CMAKE_CURRENT_LIST_DIR}/../tflite-test" CACHE PATH "Path to the current NXP TFLite project")
set(STEDGEAI_ROOT "$ENV{HOME}/opt/st/x-cube-ai/10.2.0/stedgeai-linux-10.2.0" CACHE PATH "Path to the ST Edge AI package")
set(TFLM_STM32_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../external/tflm-stm32" CACHE PATH "Path to the generated STM32 TFLM package")
set(TFLM_STM32_SRC_DIR "${TFLM_STM32_ROOT}/src/tflite-micro" CACHE PATH "Path to the STM32 TFLM source checkout")
set(BALAS_STM32_MODEL_BACKEND "stedgeai" CACHE STRING "STM32 inference backend: stedgeai or tflm")
set_property(CACHE BALAS_STM32_MODEL_BACKEND PROPERTY STRINGS stedgeai tflm)
option(BALAS_STM32_ENABLE_MODEL "Compile the STM32 MyModel port" OFF)
option(BALAS_STM32_MODEL_BOOT_MARKER "Emit debug UART bytes while starting the model firmware" OFF)

set(LINKER_SCRIPT "${CMAKE_CURRENT_LIST_DIR}/STM32H723ZGTX_FLASH.ld")
set(TARGET_NAME stm32-tflite-test)

add_executable(${TARGET_NAME}
    Startup/startup_stm32h723zgtx.s
    Core/Src/stm32h7xx_hal_msp.c
    Core/Src/stm32h7xx_it.c
    Core/Src/system_stm32h7xx.c
    Core/Src/syscalls.c
    Core/Src/sysmem.c
    ${CUBE_H7_PATH}/Drivers/STM32H7xx_HAL_Driver/Src/stm32h7xx_hal.c
    ${CUBE_H7_PATH}/Drivers/STM32H7xx_HAL_Driver/Src/stm32h7xx_hal_cortex.c
    ${CUBE_H7_PATH}/Drivers/STM32H7xx_HAL_Driver/Src/stm32h7xx_hal_gpio.c
    ${CUBE_H7_PATH}/Drivers/STM32H7xx_HAL_Driver/Src/stm32h7xx_hal_pwr.c
    ${CUBE_H7_PATH}/Drivers/STM32H7xx_HAL_Driver/Src/stm32h7xx_hal_pwr_ex.c
    ${CUBE_H7_PATH}/Drivers/STM32H7xx_HAL_Driver/Src/stm32h7xx_hal_rcc.c
    ${CUBE_H7_PATH}/Drivers/STM32H7xx_HAL_Driver/Src/stm32h7xx_hal_rcc_ex.c
    ${CUBE_H7_PATH}/Drivers/STM32H7xx_HAL_Driver/Src/stm32h7xx_hal_uart.c
    ${CUBE_H7_PATH}/Drivers/STM32H7xx_HAL_Driver/Src/stm32h7xx_hal_uart_ex.c
)

set_target_properties(${TARGET_NAME} PROPERTIES SUFFIX ".elf")

if(BALAS_STM32_ENABLE_MODEL)
    target_sources(${TARGET_NAME} PRIVATE Core/Src/main_model.cpp)
else()
    target_sources(${TARGET_NAME} PRIVATE Core/Src/main.c)
endif()

target_compile_definitions(${TARGET_NAME} PRIVATE
    STM32H723xx
    USE_HAL_DRIVER
)

target_include_directories(${TARGET_NAME} PRIVATE
    Core/Inc
    ${CUBE_H7_PATH}/Drivers/STM32H7xx_HAL_Driver/Inc
    ${CUBE_H7_PATH}/Drivers/STM32H7xx_HAL_Driver/Inc/Legacy
    ${CUBE_H7_PATH}/Drivers/CMSIS/Device/ST/STM32H7xx/Include
    ${CUBE_H7_PATH}/Drivers/CMSIS/Core/Include
)

if(BALAS_STM32_ENABLE_MODEL)
    target_sources(${TARGET_NAME} PRIVATE
        Core/Model/quantization.cpp
        Core/Platform/serial_io.cpp
        Core/Platform/timer.cpp
    )
    target_include_directories(${TARGET_NAME} PRIVATE
        Core/Model
        Core/Platform
    )
    if(BALAS_STM32_MODEL_BACKEND STREQUAL "stedgeai")
        target_sources(${TARGET_NAME} PRIVATE
            Core/Model/model_stedgeai.cpp
            Core/Generated/EdgeAI/balas_model.c
            Core/Generated/EdgeAI/balas_model_data.c
            Core/Generated/EdgeAI/balas_model_data_params.c
        )
        target_compile_definitions(${TARGET_NAME} PRIVATE BALAS_STM32_USE_STEDGEAI=1)
        target_include_directories(${TARGET_NAME} PRIVATE
            Core/Generated/EdgeAI
            ${STEDGEAI_ROOT}/Middlewares/ST/AI/Inc
        )
        target_link_libraries(${TARGET_NAME} PRIVATE
            ${STEDGEAI_ROOT}/Middlewares/ST/AI/Lib/GCC/STM32H7/NetworkRuntime1020_CM7_GCC.a
        )
    elseif(BALAS_STM32_MODEL_BACKEND STREQUAL "tflm")
        set(TFLM_STM32_DOWNLOADS_DIR "${TFLM_STM32_SRC_DIR}/tensorflow/lite/micro/tools/make/downloads")
        set(TFLM_STM32_LIB "${TFLM_STM32_ROOT}/package/lib/libtensorflow-microlite.a")
        set(TFLM_STM32_BUILD_INFO "${TFLM_STM32_ROOT}/package/build-info.env")
        if(NOT EXISTS "${TFLM_STM32_LIB}")
            message(FATAL_ERROR "STM32 TFLM library not found: ${TFLM_STM32_LIB}. Run scripts/build_tflm_stm32.sh first.")
        endif()
        if(EXISTS "${TFLM_STM32_BUILD_INFO}")
            file(STRINGS "${TFLM_STM32_BUILD_INFO}" TFLM_STM32_OPT_LINE REGEX "^TFLM_OPTIMIZED_KERNEL_DIR=")
            string(REGEX REPLACE "^TFLM_OPTIMIZED_KERNEL_DIR=(.*)$" "\\1" TFLM_STM32_OPTIMIZED_KERNEL_DIR "${TFLM_STM32_OPT_LINE}")
        else()
            set(TFLM_STM32_OPTIMIZED_KERNEL_DIR "none")
        endif()
        if(TFLM_STM32_OPTIMIZED_KERNEL_DIR STREQUAL "" OR TFLM_STM32_OPTIMIZED_KERNEL_DIR STREQUAL "none")
            set(TFLM_STM32_GEN_DIR "${TFLM_STM32_SRC_DIR}/gen/cortex_m_generic_cortex-m7+fp_default_gcc")
        else()
            set(TFLM_STM32_GEN_DIR "${TFLM_STM32_SRC_DIR}/gen/cortex_m_generic_cortex-m7+fp_default_${TFLM_STM32_OPTIMIZED_KERNEL_DIR}_gcc")
        endif()
        target_sources(${TARGET_NAME} PRIVATE
            Core/Model/model.cpp
        )
        target_include_directories(${TARGET_NAME} PRIVATE
            ${TFLM_STM32_SRC_DIR}
            ${TFLM_STM32_GEN_DIR}/genfiles
            ${TFLM_STM32_DOWNLOADS_DIR}/flatbuffers/include
            ${TFLM_STM32_DOWNLOADS_DIR}/gemmlowp
            ${TFLM_STM32_DOWNLOADS_DIR}/cmsis/CMSIS/Core/Include
            ${TFLM_STM32_DOWNLOADS_DIR}/cmsis_nn
            ${TFLM_STM32_DOWNLOADS_DIR}/cmsis_nn/Include
            ${TFLM_STM32_DOWNLOADS_DIR}/kissfft
        )
        target_link_libraries(${TARGET_NAME} PRIVATE
            ${TFLM_STM32_LIB}
        )
    else()
        message(FATAL_ERROR "Unsupported BALAS_STM32_MODEL_BACKEND=${BALAS_STM32_MODEL_BACKEND}")
    endif()
    if(BALAS_STM32_MODEL_BOOT_MARKER)
        target_compile_definitions(${TARGET_NAME} PRIVATE BALAS_STM32_MODEL_BOOT_MARKER=1)
    endif()
endif()

set(CPU_FLAGS
    -mcpu=cortex-m7
    -mthumb
    -mfpu=fpv5-d16
    -mfloat-abi=hard
)

target_compile_options(${TARGET_NAME} PRIVATE
    ${CPU_FLAGS}
    -ffunction-sections
    -fdata-sections
    -Wall
    -Wextra
    $<$<COMPILE_LANGUAGE:CXX>:-fno-exceptions>
    $<$<COMPILE_LANGUAGE:CXX>:-fno-rtti>
)

target_link_options(${TARGET_NAME} PRIVATE
    ${CPU_FLAGS}
    -T${LINKER_SCRIPT}
    -Wl,-Map=${TARGET_NAME}.map
    -Wl,--gc-sections
    -Wl,--print-memory-usage
    --specs=nano.specs
    --specs=nosys.specs
)

add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
    COMMAND ${CMAKE_SIZE} $<TARGET_FILE:${TARGET_NAME}>
    COMMAND ${CMAKE_OBJCOPY} -O ihex $<TARGET_FILE:${TARGET_NAME}> ${TARGET_NAME}.hex
    COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:${TARGET_NAME}> ${TARGET_NAME}.bin
)
