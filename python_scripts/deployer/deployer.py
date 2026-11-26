import re
import subprocess
import sys

# Mensagens do GNU ld (MCUXpresso, CMake/STM32 e Zephyr usam arm-none-eabi-ld)
# quando o firmware não cabe na flash/RAM.
_MEMORY_OVERFLOW = re.compile(
    r"overflowed by \d+ bytes|will not fit in region|region [`'\"]?\S+[`'\"]? overflowed",
    re.IGNORECASE,
)


def _run_tee(cmd: list[str]) -> tuple[int, str]:
    """Roda o comando mostrando a saída ao vivo e devolvendo uma cópia dela."""
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace"
    )
    captured = []
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        captured.append(line)
    return proc.wait(), "".join(captured)


def classify_compile_output(output: str) -> str:
    """'memory_overflow' quando o linker reclama de região estourada, senão 'build_error'."""
    return "memory_overflow" if _MEMORY_OVERFLOW.search(output or "") else "build_error"


def compile_cpp_project():
    """Compila o firmware do alvo.

    Em caso de falha, a mensagem começa com ``compile.sh:`` (que o
    run_all_benchmarks trata como resultado, não como erro crítico) seguido do
    motivo: ``memory_overflow`` (o modelo não coube) ou ``build_error`` (outro
    problema: op ausente, toolchain, ambiente), para separar os dois na análise.
    """
    code, output = _run_tee(["./compile.sh"])
    if code != 0:
        reason = classify_compile_output(output)
        detail = next(
            (line.strip() for line in output.splitlines() if _MEMORY_OVERFLOW.search(line)),
            (output.strip().splitlines() or [""])[-1][:300],
        )
        raise RuntimeError(f"compile.sh: {reason} (exit {code}): {detail}")


def deploy_to_mcu():
    subprocess.run(["./deploy.sh"], check=True)
