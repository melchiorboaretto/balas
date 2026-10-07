from pathlib import Path
import sys

# File: balas/python_scripts/dse/config_loader.py
# parents[0] = python_scripts/dse
# parents[1] = python_scripts
# parents[2] = balas (raiz do repositório)
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import tomllib as toml_parser
except ImportError:
    import tomli as toml_parser

from python_scripts.config import default_serial_port, repo_root


def load_dse_config(toml_path, serial_override=None):
    with open(toml_path, "rb") as f:
        data = toml_parser.load(f)

    exp = data.get("experiment", {})
    specs = data.get("model_specs", {})

    # Converte lista em tupla (1, 640) se necessário
    raw_shape = specs.get("input_shape") or exp.get("input_shape")
    input_shape = tuple(raw_shape) if raw_shape else None

    serial_device = (
        serial_override
        or exp.get("serial_device")
        or default_serial_port()
    )

    return {
        "benchmark": exp.get("benchmark", "cifar_ten"),
        "base_seed": exp.get("base_seed", 72),
        "profiling_samples": exp.get("profiling_samples", 10),
        "output_csv": repo_root()
        / exp.get("output_csv", "artifacts/database.csv"),
        "output_map": repo_root() / exp.get("output_map", "artifacts/map.json"),
        "grid": data.get("hyperparameters", {}).get("grid", {}),
        "input_shape": input_shape,
        "num_classes": specs.get("num_classes") or exp.get("num_classes"),
        "serial_device": serial_device,
    }
