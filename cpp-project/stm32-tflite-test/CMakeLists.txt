cmake_minimum_required(VERSION 3.22)

project(stm32-tflite-test LANGUAGES C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CUBE_H7_PATH "${CMAKE_CURRENT_LIST_DIR}/../../external/STM32CubeH7" CACHE PATH "Path to STM32CubeH7 package")
set(NXP_TFLITE_PROJECT_PATH "${CMAKE_CURRENT_LIST_DIR}/../tflite-test" CACHE PATH "Path to the current NXP TFLite project")
option(BALAS_STM32_ENABLE_MODEL "Compile the STM32 MyModel port and link TensorFlow Lite Micro" OFF)

set(LINKER_SCRIPT "${CMAKE_CURRENT_LIST_DIR}/STM32H723ZGTX_FLASH.ld")
set(TARGET_NAME stm32-tflite-echo)

add_executable(${TARGET_NAME}
    Startup/startup_stm32h723zgtx.s
    Core/Src/main.c
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
        Core/Model/model.cpp
        Core/Model/quantization.cpp
    )
    target_include_directories(${TARGET_NAME} PRIVATE
        Core/Model
        ${NXP_TFLITE_PROJECT_PATH}
        ${NXP_TFLITE_PROJECT_PATH}/tensorflow/tensorflow_headers
        ${NXP_TFLITE_PROJECT_PATH}/tensorflow/third_party_headers/flatbuffers/include
        ${NXP_TFLITE_PROJECT_PATH}/tensorflow/third_party_headers/gemmlowp
        ${NXP_TFLITE_PROJECT_PATH}/tensorflow/third_party_headers/cmsis
        ${NXP_TFLITE_PROJECT_PATH}/tensorflow/third_party_headers/cmsis_nn
        ${NXP_TFLITE_PROJECT_PATH}/tensorflow/third_party_headers/kissfft
    )
    target_link_libraries(${TARGET_NAME} PRIVATE
        ${NXP_TFLITE_PROJECT_PATH}/tensorflow/libtensorflow-microlite.a
    )
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
