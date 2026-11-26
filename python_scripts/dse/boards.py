"""Orçamentos de memória das placas e regras de compatibilidade.

Os números servem para *estimar* (space_report, relatórios) se um modelo cabe
numa placa antes de compilar. A decisão final é sempre do link/AllocateTensors
na placa real: compile.sh falha quando o modelo não cabe.

Modelo de memória (o mesmo do firmware atual de cada placa):

* Flash: firmware sem modelo + bytes do .tflite (model_data.h).
* RAM: firmware sem arena + arena do TFLM + buffer de entrada em float32
  (as três placas recebem float32 pela serial e alocam ``new float[n]``,
  ou seja, 4 bytes por elemento de entrada).
* Heap: o ``new float[n]`` sai do heap. STM32 (``_sbrk`` até a pilha) e Nordic
  (picolibc com ``CONFIG_COMMON_LIBC_MALLOC_ARENA_SIZE=-1``) usam toda a RAM
  livre. A NXP (``tflite-test``) tem heap fixo de 32 KB no ``.cproject``
  (``Heap:Default;Post Data;0x8000``, configuração Debug usada pelo
  compile.sh): a entrada float de qualquer VWW (>= 64x64x3 -> 48 KB) não cabe.
  Para liberar, aumentar o heap no .cproject (ex.: 0x30000) e trocar
  ``input_heap_bytes`` abaixo.

Origem dos números (ver RELATORIO / docs):

* nordic: medido no build TFLM do repositório (``arm-none-eabi-size``):
  text 219.148 B com modelo de 46.928 B -> firmware ~172 KB; bss 119.423 B com
  arena de 81.920 B -> ~38 KB de RAM fora a arena (docs/024 traz 119.948 /
  219.632). RAM total 256 KiB, flash 1 MiB.
* stm32: linker STM32H723ZGTX_FLASH.ld usa só 128 KB de DTCM para .data/.bss/
  heap/stack e 1 MB de flash. RAM fora a arena estimada em ~10 KB (HAL + pilha +
  heap mínimo); o firmware ocupado de flash é estimado (sem build local).
* nxp: SRAM principal de 384 KB (0x60000) e PROGRAM_FLASH0 de 1 MB no .cproject
  (o MCUXpresso coloca .text/.rodata na primeira região de flash). Overhead de
  firmware estimado (sem build local).
"""

from __future__ import annotations

from dataclasses import dataclass

KB = 1024


@dataclass(frozen=True)
class Board:
    target: str
    name: str
    flash_bytes: int
    firmware_flash_bytes: int
    ram_bytes: int
    firmware_ram_bytes: int
    measured: bool
    notes: str = ""
    # Limite do heap de onde sai o buffer float de entrada (None = RAM livre).
    input_heap_bytes: int | None = None

    @property
    def model_flash_budget(self) -> int:
        return self.flash_bytes - self.firmware_flash_bytes

    @property
    def ram_budget(self) -> int:
        """RAM disponível para arena + buffer de entrada."""
        return self.ram_bytes - self.firmware_ram_bytes


BOARDS = {
    "nxp": Board(
        target="nxp",
        name="FRDM-MCXN947 (Cortex-M33 150 MHz)",
        flash_bytes=1024 * KB,
        firmware_flash_bytes=120 * KB,
        ram_bytes=384 * KB,
        firmware_ram_bytes=24 * KB,
        measured=False,
        notes="Overhead estimado; região PROGRAM_FLASH0 (1 MB) do .cproject.",
        input_heap_bytes=0x8000,
    ),
    "stm32": Board(
        target="stm32",
        name="NUCLEO-H723ZG (Cortex-M7 550 MHz)",
        flash_bytes=1024 * KB,
        firmware_flash_bytes=110 * KB,
        ram_bytes=128 * KB,
        firmware_ram_bytes=10 * KB,
        measured=False,
        notes="Linker atual usa só 128 KB de DTCM (o chip tem 564 KB).",
    ),
    "nordic": Board(
        target="nordic",
        name="nRF52840-DK (Cortex-M4F 64 MHz)",
        flash_bytes=1024 * KB,
        firmware_flash_bytes=172 * KB,
        ram_bytes=256 * KB,
        firmware_ram_bytes=40 * KB,
        measured=True,
        notes="Medido no build TFLM do repositório.",
    ),
}

# Ativações sem kernel int8 no ST Edge AI 4.1: o gerador insere conversões e
# roda o operador em float32 (docs da ST, "supported_ops_tflite").
STEDGEAI_FLOAT_ACTIVATIONS = frozenset({"sigmoid", "tanh", "hard_swish"})


def float_fallback(target: str, activation: str | None, stm32_backend: str | None = None) -> bool:
    """True se a ativação roda em float no alvo (só STM32 com backend stedgeai)."""
    if target != "stm32":
        return False
    backend = (stm32_backend or "stedgeai").lower()
    return backend == "stedgeai" and (activation or "relu") in STEDGEAI_FLOAT_ACTIVATIONS


def estimate_tflite_bytes(cost: dict) -> int:
    """Tamanho aproximado do .tflite a partir do custo analítico.

    Ajuste por mínimos quadrados (erro relativo) em 88 .tflite gerados pelos
    4 TOMLs de DSE: ~27 B por canal de saída (3 B a mais do bias int32 +
    escala float32 e zero-point int64 por canal) e ~461 B de metadados por
    operador. Erro máximo: 5,3% (IC), 6,5% (KWS), 4,5% (VWW), 14,4% (AD,
    sempre superestimando).
    """
    ops = len(cost.get("ops", ())) or 1
    channels = cost.get("output_channels") or 0
    return max(int(cost["params"]), int(0.935 * cost["params"] + 27 * channels + 461 * ops - 485))


def ram_required(arena_bytes: int, input_elements: int) -> int:
    return int(arena_bytes) + 4 * int(input_elements)


def fits(board: Board, tflite_bytes: int, arena_bytes: int, input_elements: int) -> dict:
    flash_ok = tflite_bytes <= board.model_flash_budget
    ram_ok = ram_required(arena_bytes, input_elements) <= board.ram_budget
    heap_ok = board.input_heap_bytes is None or 4 * int(input_elements) <= board.input_heap_bytes
    return {"flash_ok": flash_ok, "ram_ok": ram_ok, "heap_ok": heap_ok,
            "fits": flash_ok and ram_ok and heap_ok}
