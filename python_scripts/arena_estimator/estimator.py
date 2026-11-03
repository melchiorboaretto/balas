import subprocess
from python_scripts.config import find_stm32tflm

def estimate_tensor_arena_size(model_path: str) -> int:
    """Runs stm32tflm with a quantized TFLite model and returns the RAM usage in bytes.
    If stm32tflm is not installed, falls back to estimating tensor arena memory
    from the TFLite model structure with alignment overhead.
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
        except Exception:
            pass

    # Fallback autônomo (não requer ferramenta externa da ST instalada):
    try:
        import numpy as np
        import tensorflow as tf

        interpreter = tf.lite.Interpreter(model_path=model_path)
        interpreter.allocate_tensors()
        tensor_details = interpreter.get_tensor_details()

        # Calcula o tamanho dos tensores de ativação
        total_activation_bytes = 0
        for t in tensor_details:
            shape = t.get("shape", [])
            dtype = t.get("dtype")
            itemsize = np.dtype(dtype).itemsize if dtype else 1
            n_bytes = int(np.prod(shape)) * itemsize
            total_activation_bytes += n_bytes

        # Adiciona margem de segurança para alinhamento (16 bytes) e cabeçalhos do TFLM
        return max(int(total_activation_bytes * 1.25) + 2048, 4096)
    except Exception:
        return 32768
