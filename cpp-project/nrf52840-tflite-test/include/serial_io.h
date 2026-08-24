#pragma once

#include <cstddef>
#include <cstdint>

bool serial_init();
void serial_read(uint8_t *dst, std::size_t n_bytes);
void serial_write(const uint8_t *src, std::size_t n_bytes);
