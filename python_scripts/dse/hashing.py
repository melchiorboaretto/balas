import hashlib
import json


def generate_hp_hash(hp_list: list) -> str:
    hp_str = json.dumps(hp_list)
    return hashlib.sha1(hp_str.encode("utf-8")).hexdigest()[:16]


def sample_hyperparameters_for_seed(
    grid: dict,
    seed: int,
    *,
    attempt: int = 0,
    canonicalize=None,
) -> tuple[dict, list, str, str]:
    """Sorteia um valor por chave do grid, de forma determinística por seed.

    - ``attempt`` > 0 gera um sorteio diferente para o mesmo seed (usado pela
      amostragem com restrição). ``attempt == 0`` reproduz exatamente o sorteio
      antigo, então TOMLs sem restrição mantêm os mesmos hashes.
    - ``canonicalize`` (opcional) recebe o config sorteado e devolve outro em que
      as chaves inativas (que não mudam o modelo) valem ``None``. O hash e o nome
      da variante usam o config canônico, para que modelos iguais tenham o
      mesmo hash.
    """
    config = {}
    for key in sorted(grid.keys()):
        choices = grid[key]
        prefix = f"{seed}" if attempt == 0 else f"{seed}#{attempt}"
        hash_val = hashlib.sha1(f"{prefix}_{key}".encode("utf-8")).hexdigest()
        config[key] = choices[int(hash_val, 16) % len(choices)]

    if canonicalize is not None:
        config = canonicalize(config)

    hp_list = []
    variant_parts = []
    for key in sorted(grid.keys()):
        val = config.get(key)
        hp_list.append(val)
        if val is not None:
            variant_parts.append(f"{key}-{val}")

    hash_id = generate_hp_hash(hp_list)
    variant_name = "_".join(variant_parts)

    return config, hp_list, hash_id, variant_name
