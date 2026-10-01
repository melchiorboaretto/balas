import importlib
from types import ModuleType

# Mapeamento dos nomes dos benchmarks para os arquivos Python na pasta builders/
BUILDER_MAP = {
    "cifar_ten": "python_scripts.dse.builders.cifar_ten",
    "visual_wake_words": "python_scripts.dse.builders.visual_wake_words",
    "keyword_spotting": "python_scripts.dse.builders.keyword_spotting",
    "anomaly_detection": "python_scripts.dse.builders.anomaly_detection",
}

def get_builder_module(benchmark_name: str) -> ModuleType:
    """Carrega dinamicamente o módulo construtor Keras/TFLite para o benchmark especificado."""
    if benchmark_name not in BUILDER_MAP:
        valid_options = ", ".join(sorted(BUILDER_MAP.keys()))
        raise ValueError(
            f"Benchmark desconhecido: '{benchmark_name}'. "
            f"Opções válidas registradas em builders/: {valid_options}"
        )

    module_path = BUILDER_MAP[benchmark_name]
    return importlib.import_module(module_path)
