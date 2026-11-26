import os
import time

from python_scripts.code_generator.generator import (
    generate_cpp_code,
    generate_nordic_tflm_code,
    generate_stm32_tflm_code,
)
from python_scripts.deployer.deployer import compile_cpp_project, deploy_to_mcu

# Atraso pós-deploy por placa (mesmos defaults do automator.py).
_POST_DEPLOY_DELAY_ENV = {
    "nxp": ("BALAS_NXP_POST_DEPLOY_DELAY_SEC", "3.0"),
    "stm32": ("BALAS_STM32_POST_DEPLOY_DELAY_SEC", "3"),
    "nordic": ("BALAS_NORDIC_POST_DEPLOY_DELAY_SEC", "2"),
}


class HardwareAdapter:
    """Adapta a geração de código, compilação e deploy para a placa alvo escolhida."""

    def __init__(self, target: str | None = None):
        self.target = target or os.environ.get("BALAS_TARGET", "nxp")
        self.stm32_backend = os.environ.get("BALAS_STM32_MODEL_BACKEND", "stedgeai")
        if self.target == "nordic":
            # Igual ao automator.py: sem isso o compile.sh gera o firmware de eco.
            os.environ.setdefault("BALAS_NORDIC_ENABLE_MODEL", "ON")

    def check_supported(self) -> None:
        """Falha cedo em combinações que mediriam o modelo errado."""
        if self.target == "stm32" and self.stm32_backend == "stedgeai":
            raise RuntimeError(
                "setup_failure: o backend stedgeai da STM32 usa o código pré-gerado em "
                "cpp-project/stm32-tflite-test/Core/Generated/EdgeAI e o loop de DSE não o "
                "regenera; todas as iterações mediriam o mesmo modelo. Use "
                "BALAS_STM32_MODEL_BACKEND=tflm (com scripts/build_tflm_stm32.sh) ou adicione "
                "um passo 'stedgeai generate' antes do compile.sh."
            )
        if self.target == "stm32" and os.environ.get("BALAS_STM32_ENABLE_MODEL", "OFF") not in (
            "ON", "1", "true", "TRUE"
        ):
            raise RuntimeError(
                "setup_failure: BALAS_STM32_ENABLE_MODEL não está ON; o compile.sh geraria o "
                "firmware de eco, sem modelo."
            )

    def generate_code(self, model_path: str, estimated_arena_bytes: int) -> None:
        """Invoca o gerador C++ adequado ao target selecionado."""
        if self.target == "stm32":
            generate_stm32_tflm_code(model_path, estimated_arena_bytes)
        elif self.target == "nordic":
            generate_nordic_tflm_code(model_path, estimated_arena_bytes)
        else:
            generate_cpp_code(model_path, estimated_arena_bytes)

    def compile(self) -> None:
        """Dispara a compilação via script de build do target."""
        compile_cpp_project()

    def deploy(self) -> None:
        """Dispara a gravação do firmware no microcontrolador."""
        deploy_to_mcu()

    def post_deploy_delay(self) -> None:
        env_name, default = _POST_DEPLOY_DELAY_ENV.get(self.target, _POST_DEPLOY_DELAY_ENV["nxp"])
        time.sleep(float(os.environ.get(env_name, default)))
