import hashlib
import json


def generate_hp_hash(hp_list: list) -> str:
    """Gera um Hash MD5 determinístico de 12 caracteres a partir da lista de hiperparâmetros."""
    hp_str = json.dumps(hp_list)
    return hashlib.md5(hp_str.encode("utf-8")).hexdigest()[:12]


def sample_hyperparameters_for_seed(grid: dict, seed: int) -> tuple[dict, list, str, str]:
    """Amostra hiperparâmetros de forma 100% determinística via SHA-1 (independente de OS/Python)."""
    config = {}
    
    # Para cada hiperparâmetro, gera um hash SHA-1 único baseado na semente + nome da chave
    for key, choices in grid.items():
        hash_input = f"{seed}_{key}".encode("utf-8")
        hash_val = hashlib.sha1(hash_input).hexdigest()
        index = int(hash_val, 16) % len(choices)
        config[key] = choices[index]

    hp_list = [
        config["channels_1"],
        config["kernel_1"],
        config["channels_2"],
        config["kernel_2"],
        config["channels_3"],
        config["kernel_3"],
    ]

    hash_id = generate_hp_hash(hp_list)
    variant_name = (
        f"ic_c1-{config['channels_1']}_k1-{config['kernel_1']}_"
        f"c2-{config['channels_2']}_k2-{config['kernel_2']}_"
        f"c3-{config['channels_3']}_k3-{config['kernel_3']}"
    )

    return config, hp_list, hash_id, variant_name
