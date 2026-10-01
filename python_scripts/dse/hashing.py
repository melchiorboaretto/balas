import hashlib
import json

def generate_hp_hash(hp_list: list) -> str:
    hp_str = json.dumps(hp_list)
    return hashlib.md5(hp_str.encode("utf-8")).hexdigest()[:12]

def sample_hyperparameters_for_seed(grid: dict, seed: int) -> tuple[dict, list, str, str]:
    config = {}
    hp_list = []
    variant_parts = []

    for key in sorted(grid.keys()):
        choices = grid[key]
        hash_input = f"{seed}_{key}".encode("utf-8")
        hash_val = hashlib.sha1(hash_input).hexdigest()
        index = int(hash_val, 16) % len(choices)
        val = choices[index]
        config[key] = val
        hp_list.append(val)
        variant_parts.append(f"{key}-{val}")

    hash_id = generate_hp_hash(hp_list)
    variant_name = "_".join(variant_parts)

    return config, hp_list, hash_id, variant_name
