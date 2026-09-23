import argparse
from pathlib import Path
import sys
import time
import numpy as np

# REPO_ROOT aponta para a raiz do repositório (balas/)
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Imports dos utilitários originais do BALAS (respeitando a árvore do repositório)
from python_scripts.arena_estimator.estimator import estimate_tensor_arena_size
from python_scripts.code_generator.generator import generate_cpp_code
from python_scripts.config import repo_root
from python_scripts.deployer.deployer import compile_cpp_project, deploy_to_mcu
from python_scripts.mac_calculator.mac_calculator import count_macs
from python_scripts.profiler.profiler import send_array_and_get_int

# Imports do pacote modular DSE
from python_scripts.dse.builder import build_and_quantize_model
from python_scripts.dse.checkpoint import CheckpointManager
from python_scripts.dse.config_loader import load_dse_config
from python_scripts.dse.hashing import sample_hyperparameters_for_seed


def main():
    parser = argparse.ArgumentParser(description="Loop de teste contínuo em TinyML para NXP MCXN947")
    parser.add_argument("--config-toml", default="configs/continuous_search.toml", help="Caminho do arquivo TOML")
    args = parser.parse_args()

    # 1. Carrega as configurações do TOML
    dse_cfg = load_dse_config(args.config_toml)
    
    # 2. Prepara o gerenciador de checkpoint
    checkpoint = CheckpointManager(dse_cfg["output_csv"], dse_cfg["output_map"])
    
    tmp_dir = Path("/tmp/balas_continuous_models")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 3. Carrega o dataset de testes para profiling serial
    dataset_dir = repo_root() / "testdata/sanity-model/profiling_dataset"
    sample_files = sorted(dataset_dir.glob("*.bin"))[: dse_cfg["profiling_samples"]]
    samples = [np.fromfile(f, dtype=np.float32) for f in sample_files]

    print("🔄 Loop de Execução Contínua Inicializado.")
    print(f"📦 Modelos já processados no histórico: {len(checkpoint.completed_hashes)}")
    print(f"📄 Salvando resultados em: {dse_cfg['output_csv']}")
    print(f"🔑 Salvando mapeamento de hashes em: {dse_cfg['output_map']}\n")

    iteration = 0
    try:
        while True:
            seed = dse_cfg["base_seed"] + iteration
            config, hp_list, hash_id, variant_name = sample_hyperparameters_for_seed(
                dse_cfg["grid"], seed
            )

            # --- CHECKPOINT: Se o Hash já foi testado, PULA ---
            if checkpoint.is_completed(hash_id):
                iteration += 1
                continue

            print(f"[{time.strftime('%H:%M')}] 🚀 Modelo #{iteration+1} | Hash: {hash_id} | Variante: {variant_name}")
            print(f"   Hiperparâmetros: {hp_list}")

            error_msg = ""
            estimated_arena = None
            macs = None
            durations = None

            try:
                # PASSO A: Constrói e quantiza o modelo .tflite
                tflite_path = build_and_quantize_model(
                    config,
                    variant_name,
                    tmp_dir,
                    input_shape=dse_cfg["input_shape"],
                    num_classes=dse_cfg["num_classes"],
                )

                # PASSO B: Estima Arena de RAM e calcula MACs
                estimated_arena = estimate_tensor_arena_size(str(tflite_path))
                macs = count_macs(str(tflite_path))

                # PASSO C: Atualiza C++, Compila e faz Deploy na placa NXP MCXN947
                generate_cpp_code(str(tflite_path), estimated_arena)
                compile_cpp_project()
                deploy_to_mcu()
                time.sleep(1.0)

                # PASSO D: Transmite amostras via UART e mede as latências individuais
                durations = []
                for sample in samples:
                    dur_us = send_array_and_get_int(dse_cfg["serial_device"], sample)
                    durations.append(dur_us)

                avg_us = float(np.mean(durations))
                print(f"   ✅ Sucesso! Arena: {estimated_arena} B | MACs: {macs} | Média MCU: {avg_us:.1f} µs")

            except Exception as e:
                error_msg = str(e)
                print(f"   ⚠️ Falha no ciclo: {error_msg}")

            # PASSO E: Grava o resultado incremental no CSV e JSON
            checkpoint.save_result(
                iteration=iteration,
                hash_id=hash_id,
                variant_name=variant_name,
                hp_list=hp_list,
                config=config,
                error_msg=error_msg,
                arena_estimated=estimated_arena,
                macs=macs,
                durations=durations,
            )

            iteration += 1
            print("-" * 75)

    except KeyboardInterrupt:
        print("\n\n🛑 Interrupção pelo usuário (Ctrl+C).")
        print(f"💾 Checkpoint gravado com segurança. Total no banco: {len(checkpoint.completed_hashes)}")


if __name__ == "__main__":
    main()
