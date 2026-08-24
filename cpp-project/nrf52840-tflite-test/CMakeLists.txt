cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nrf52840_tflite_test LANGUAGES C CXX)

option(BALAS_NORDIC_ENABLE_MODEL "Build the BALAS TFLM profiling firmware" OFF)

target_include_directories(app PRIVATE
    include
)

target_sources(app PRIVATE
    src/serial_io.cpp
    src/timer.cpp
)

if(BALAS_NORDIC_ENABLE_MODEL)
    target_sources(app PRIVATE
        src/main_model.cpp
        Model/model.cpp
        Model/quantization.cpp
    )
    target_include_directories(app PRIVATE Model)
    target_compile_definitions(app PRIVATE BALAS_NORDIC_ENABLE_MODEL=1)
else()
    target_sources(app PRIVATE src/main_bringup.cpp)
endif()

target_compile_features(app PRIVATE cxx_std_17)
target_compile_options(app PRIVATE
    $<$<COMPILE_LANGUAGE:CXX>:-fno-exceptions>
    $<$<COMPILE_LANGUAGE:CXX>:-fno-rtti>
)
