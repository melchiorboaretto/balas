import subprocess
import sys

from python_scripts.config import find_stm32tflm

# Último recurso, usado só se nem o stm32tflm nem o fallback analítico funcionarem.
_LAST_RESORT_ARENA = 32768


def _warn(message: str) -> None:
    print(f"⚠️  [arena_estimator] {message}", file=sys.stderr)


def estimate_tensor_arena_size(model_path: str) -> int:
    """Estima a arena do TFLM (bytes) para um .tflite quantizado.

    1. Usa o ``stm32tflm`` (ST) quando disponível, como antes.
    2. Sem ele, usa uma estimativa por liveness: pico dos tensores de ativação
       vivos ao mesmo tempo + overhead persistente do TFLM + maior scratch do
       CMSIS-NN. Pesos e biases ficam na flash e não entram na conta.

    O fallback antigo somava todos os tensores do modelo (inclusive os pesos) e
    multiplicava por 1,25: para o ResNet8 de referência dava ~248 KB, contra
    ~55-57 KB reais, o que fazia modelos que cabem falharem na compilação das
    placas com pouca RAM.
    """
    stm32tflm_bin = find_stm32tflm()
    if stm32tflm_bin:
        try:
            result = subprocess.run(
                [stm32tflm_bin, model_path],
                capture_output=True,
                text=True,
                check=True,
            )
            for line in result.stdout.splitlines():
                if line.startswith("Ram:"):
                    return int(line.split(":")[1].strip())
            _warn(f"stm32tflm não imprimiu 'Ram:'; usando a estimativa por liveness.")
        except Exception as exc:
            _warn(f"stm32tflm falhou ({exc}); usando a estimativa por liveness.")

    try:
        from python_scripts.dse.tflite_inspect import estimate_tflm_arena, inspect_tflite

        return estimate_tflm_arena(inspect_tflite(model_path))
    except Exception as exc:
        _warn(f"estimativa por liveness falhou ({exc}); usando {_LAST_RESORT_ARENA} B.")
        return _LAST_RESORT_ARENA
