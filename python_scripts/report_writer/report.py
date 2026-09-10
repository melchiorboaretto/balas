import os
import csv
import hashlib

def calculate_file_hash(filepath: str, algorithm: str = "sha1") -> str:
    """
    Calcula o hash unico (SHA-1 por padrão) do arquivo do modelo .tflite.
    Lê em blocos de 64KB para suportar arquivos de qualquer tamanho.
    """
    hasher = hashlib.sha1() if algorithm == "sha1" else hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def append_inference_report(
    model_path,
    arena_size, 
    macs, 
    inference_times_us, 
    report_filepath, 
    voltage_v=3.3, 
    current_ma=8.55
):
    """
    Grava no CSV TODAS as medições individuais de inferência,
    incluindo o HASH único do modelo, o tempo em us e a energia em nanojoules (nJ).
    
    Fórmula de Energia: E (nJ) = V (Volts) * I (mA) * t (us)
    """
    file_exists = os.path.exists(report_filepath)
    model_hash = calculate_file_hash(model_path)

    with open(report_filepath, mode="a", newline="") as f:
        writer = csv.writer(f)
        
        # Cria o cabeçalho se o arquivo for novo
        if not file_exists:
            writer.writerow([
                "sample_idx",
                "model_hash",
                "arena_size",
                "macs",
                "inference_time_us",
                "energy_nj"
            ])

        # Grava CADA medição individualmente sem tirar médias
        for idx, time_us in enumerate(inference_times_us, start=1):
            energy_nj = voltage_v * current_ma * time_us
            writer.writerow([idx, model_hash, arena_size, macs, time_us, energy_nj])
