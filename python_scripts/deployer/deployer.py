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


# Linha que o compile.sh imprime (com exit 3) quando falta ferramenta, SDK ou
# projeto: problema da máquina, não do modelo.
ENV_ERROR_MARKER = "BALAS_ENV_ERROR:"


def classify_compile_output(output: str) -> str:
    """Motivo da falha do compile.sh.

    'env_error' quando o próprio compile.sh acusou ambiente quebrado,
    'memory_overflow' quando o linker reclama de região estourada, senão 'build_error'.
    """
    output = output or ""
    if ENV_ERROR_MARKER in output:
        return "env_error"
    return "memory_overflow" if _MEMORY_OVERFLOW.search(output) else "build_error"


def compile_cpp_project():
    """Compila o firmware do alvo.

    Em caso de falha, a mensagem começa com ``compile.sh:`` seguido do motivo:
    ``memory_overflow`` (o modelo não coube) ou ``build_error`` (op ausente,
    erro de compilação), que o run_all_benchmarks guarda como resultado; ou
    ``env_error`` (ferramenta/SDK ausente), que ele trata como erro crítico.
    """
    code, output = _run_tee(["./compile.sh"])
    if code != 0:
        reason = classify_compile_output(output)
        lines = output.splitlines()
        if reason == "env_error":
            marker = next(line for line in lines if ENV_ERROR_MARKER in line)
            detail = marker.split(ENV_ERROR_MARKER, 1)[1].strip()
        else:
            detail = next(
                (line.strip() for line in lines if _MEMORY_OVERFLOW.search(line)),
                (output.strip().splitlines() or [""])[-1],
            )
        raise RuntimeError(f"compile.sh: {reason} (exit {code}): {detail[:300]}")


def deploy_to_mcu():
    subprocess.run(["./deploy.sh"], check=True)
