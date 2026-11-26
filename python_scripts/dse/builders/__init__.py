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


def validate_grid(builder_module: ModuleType, grid: dict) -> list[str]:
    """Compara as chaves do grid do TOML com as chaves declaradas pelo builder.

    Retorna uma lista de avisos legíveis. Sem essa checagem, um grid
    desalinhado do builder é ignorado em silêncio: o modelo sai sempre com os
    valores default e o espaço de busca real fica menor do que o anunciado.
    """
    declared = set(getattr(builder_module, "GRID_KEYS", ()))
    legacy = set(getattr(builder_module, "LEGACY_GRID_KEYS", ()))
    # Chaves opcionais: aceitas, mas a ausência não gera aviso (o default
    # reproduz a referência do MLPerf Tiny).
    optional = set(getattr(builder_module, "OPTIONAL_GRID_KEYS", ()))
    if not declared:
        return []

    builder_name = builder_module.__name__.rsplit(".", 1)[-1]
    warnings = []

    unknown = sorted(set(grid) - declared - legacy - optional)
    if unknown:
        warnings.append(
            f"chaves do grid ignoradas pelo builder '{builder_name}': {unknown}"
        )

    # Chaves que ficam sem efeito por causa de outras chaves do grid (ex.: alpha
    # quando todas as larguras width_* estão no grid) não contam como ausentes.
    superseded = set()
    superseded_fn = getattr(builder_module, "superseded_keys", None)
    if callable(superseded_fn):
        superseded = set(superseded_fn(grid))

    missing = sorted(declared - set(grid) - superseded)
    if missing:
        warnings.append(
            f"chaves ausentes no grid, o builder '{builder_name}' usara os valores default: {missing}"
        )

    return warnings
