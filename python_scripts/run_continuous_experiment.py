import argparse
import os
from pathlib import Path
import sys
import time
import numpy as np

# REPO_ROOT aponta para a raiz do repositório (balas/)
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Imports dos utilitários do BALAS
from python_scripts.arena_estimator.estimator import estimate_tensor_arena_size
from python_scripts.config import repo_root
from python_scripts.mac_calculator.mac_calculator import count_macs
from python_scripts.profiler.profiler import send_array_and_get_int

# Imports do pacote modular DSE
from python_scripts.dse.builders import get_builder_module
from python_scripts.dse.checkpoint import CheckpointManager
from python_scripts.dse.config_loader import load_dse_config
from python_scripts.dse.hashing import sample_hyperparameters_for_seed
from python_scripts.dse.hardware import HardwareAdapter

def main():
    parser = argparse.ArgumentParser(
        description="Loop de teste contínuo em TinyML (Agnóstico a Hardware e Benchmark)"
    )
    parser.add_argument(
        "--config-toml",
        default="configs/cifar_10.toml",
        help="Caminho do arquivo TOML de configuração",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Placa alvo (nxp, stm32, nordic). Se omitido, usa BALAS_TARGET.",
    )
    parser.add_argument(
        "--benchmark",
        default=None,
        help="Nome do benchmark (cifar_ten, visual_wake_words, keyword_spotting, anomaly_detection).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Número máximo de iterações para esta execução.",
    )
    parser.add_argument(
        "--serial-device",
        default=None,
        help="Porta serial do microcontrolador (ex: /dev/ttyACM2). Se omitido, usa a porta do ambiente.",
    )
    parser.add_argument(
        "--profiling-samples",
        type=int,
        default=None,
        help="Quantidade de amostras para testar na serial por modelo.",
    )
    args = parser.parse_args()

    # 1. Ajusta variável de ambiente para o hardware target, se especificada
    if args.target:
        os.environ["BALAS_TARGET"] = args.target

    # 2. Instancia o adaptador de hardware
    hardware = HardwareAdapter(target=args.target)

    # 3. Carrega as configurações do TOML (com precedência para --serial-device da CLI)
    dse_cfg = load_dse_config(args.config_toml, serial_override=args.serial_device)

    # 4. Sobrescreve quantidade de amostras de profiling via CLI, se informado
    if args.profiling_samples:
        dse_cfg["profiling_samples"] = args.profiling_samples

    # 5. Resolve o gerador de modelos (builder) dinamicamente
    benchmark_name = args.benchmark or dse_cfg.get("benchmark", "cifar_ten")
    builder_module = get_builder_module(benchmark_name)

    # 6. Prepara o gerenciador de checkpoint e banco de dados CSV/JSON
    checkpoint = CheckpointManager(dse_cfg["output_csv"], dse_cfg["output_map"])

    tmp_dir = Path("/tmp/balas_continuous_models")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 7. Prepara amostras de profiling em memória baseadas no input_shape exato do benchmark
    input_shape = dse_cfg["input_shape"]
    num_elements = int(np.prod(input_shape))
    samples = [
        np.random.uniform(0.0, 1.0, size=(num_elements,)).astype(np.float32)
        for _ in range(dse_cfg["profiling_samples"])
    ]

    print("🔄 Loop de Execução Contínua Inicializado.")
    print(f"🎯 Placa Alvo (Hardware Target): {hardware.target.upper()}")
    print(f"🧬 Benchmark Selecionado: {benchmark_name}")
    print(f"🔌 Porta Serial Resolvedora: {dse_cfg['serial_device']}")
    print(f"📐 Formato de Entrada (Input Shape): {input_shape} ({num_elements} floats)")
    print(f"📦 Modelos já processados no histórico: {len(checkpoint.completed_hashes)}")
    print(f"📄 Salvando resultados em: {dse_cfg['output_csv']}")
    print(f"🔑 Salvando mapeamento de hashes em: {dse_cfg['output_map']}\n")

    iteration = 0
    try:
        while True:
            # Verifica se atingiu o limite de iterações configurado
            if args.max_iterations and iteration >= args.max_iterations:
                print(f"🏁 Alcançado limite máximo de {args.max_iterations} iterações.")
                break

            seed = dse_cfg["base_seed"] + iteration
            config, hp_list, hash_id, variant_name = sample_hyperparameters_for_seed(
                dse_cfg["grid"], seed
            )

            # --- CHECKPOINT: Se o Hash já foi testado, PULA ---
            if checkpoint.is_completed(hash_id):
                iteration += 1
                continue

            print(
                f"[{time.strftime('%H:%M:%S')}] 🚀 Modelo #{iteration+1} | Hash: {hash_id} | Variante: {variant_name}"
            )
            print(f"   Hiperparâmetros: {hp_list}")

            error_msg = ""
            estimated_arena = None
            macs = None
            durations = None

            try:
                # PASSO A: Constrói e quantiza o modelo .tflite via builder dinâmico
                tflite_path = builder_module.build_and_quantize_model(
                    config,
                    variant_name,
                    tmp_dir,
                    input_shape=dse_cfg["input_shape"],
                    num_classes=dse_cfg.get("num_classes"),
                )

                # PASSO B: Estima Arena de RAM e calcula MACs
                estimated_arena = estimate_tensor_arena_size(str(tflite_path))
                macs = count_macs(str(tflite_path))

                # PASSO C: Atualiza C++, Compila e faz Deploy
                hardware.generate_code(str(tflite_path), estimated_arena)
                hardware.compile()
                hardware.deploy()

                # Atraso essencial de pós-deploy para a MCU reiniciar e estabilizar a LPUART
                post_deploy_delay = float(os.environ.get("BALAS_NXP_POST_DEPLOY_DELAY_SEC", "3.0"))
                time.sleep(post_deploy_delay)

                # PASSO D: Transmite amostras via UART e mede as latências individuais
                durations = []
                for sample in samples:
                    dur_us = send_array_and_get_int(dse_cfg["serial_device"], sample)
                    durations.append(dur_us)

                avg_us = float(np.mean(durations))
                std_us = float(np.std(durations))
                print(
                    f"   ✅ Sucesso! Arena: {estimated_arena} B | MACs: {macs} | Média MCU: {avg_us:.1f} µs (±{std_us:.1f} µs)"
                )

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
        print(
            f"💾 Checkpoint gravado com segurança. Total no banco: {len(checkpoint.completed_hashes)}"
        )

if __name__ == "__main__":
    main()
