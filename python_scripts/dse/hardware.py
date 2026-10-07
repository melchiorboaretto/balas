import os
from python_scripts.code_generator.generator import (
    generate_cpp_code,
    generate_nordic_tflm_code,
    generate_stm32_tflm_code,
)
from python_scripts.deployer.deployer import compile_cpp_project, deploy_to_mcu


class HardwareAdapter:
    """Adapta a geração de código, compilação e deploy para a placa alvo escolhida."""

    def __init__(self, target: str | None = None):
        self.target = target or os.environ.get("BALAS_TARGET", "nxp")

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
