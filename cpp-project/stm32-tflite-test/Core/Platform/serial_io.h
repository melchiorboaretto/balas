#pragma once

#include <cstdint>

void serial_read(uint8_t *dst, unsigned long n_bytes);
void serial_write(uint8_t *src, unsigned long n_bytes);

