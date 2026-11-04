#!/usr/bin/env python3
"""
Verificador de Ambiente para NXP MCXN947 (CPU e NPU eIQ Neutron) no B.A.L.A.S.

Verifica:
  1. Dependências do Python (TensorFlow, NumPy, PySerial, etc.)
  2. MCUXpresso IDE e Toolchain ARM (arm-none-eabi-gcc, LinkServer)
  3. Projeto de Firmware NPU (cpp-project/npu-tflite-test e bibliotecas Neutron)
  4. Compilador da NPU (neutron_compiler 3.2.2 / eIQ Neutron SDK)
  5. Configuração local (.balas.env) e detecção da placa serial
  6. Permissões de usuário no Linux (grupo dialout e acesso USB)

Uso:
  python_scripts/npu/check_environment.py
"""

import grp
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def check_mark(status: bool) -> str:
    if status:
        return f"{Colors.GREEN}[OK]{Colors.RESET}"
    return f"{Colors.RED}[FALTA]{Colors.RESET}"


def warn_mark() -> str:
    return f"{Colors.YELLOW}[AVISO]{Colors.RESET}"


def check_python_packages() -> dict:
    results = {}
    packages = ["tensorflow", "numpy", "serial"]
    for pkg in packages:
        try:
            __import__(pkg)
            results[pkg] = True
        except ImportError:
            results[pkg] = False
    return results


def check_toolchain() -> dict:
    mcux_bin = os.environ.get("MCUXPRESSO_IDE_BIN", "/usr/local/mcuxpressoide/ide/mcuxpressoide")
    toolchain_bin = os.environ.get("MCUX_TOOLCHAIN_BIN", "/usr/local/mcuxpressoide/ide/tools/bin")
    gcc = Path(toolchain_bin) / "arm-none-eabi-gcc"

    # LinkServer
    linkserver_candidates = [
        os.environ.get("LINKSERVER_ROOT", ""),
        "/usr/local/mcuxpressoide/ide/plugins/com.nxp.mcuxpresso.tools.linux_*/tools/bin/LinkServer",
    ]
    linkserver_found = shutil.which("LinkServer") is not None
    if not linkserver_found:
        import glob
        for cand in linkserver_candidates:
            if cand and glob.glob(cand):
                linkserver_found = True
                break

    return {
        "ide_installed": Path(mcux_bin).exists(),
        "ide_path": mcux_bin,
        "gcc_installed": gcc.exists() or shutil.which("arm-none-eabi-gcc") is not None,
        "gcc_path": str(gcc) if gcc.exists() else shutil.which("arm-none-eabi-gcc") or "não encontrado",
        "linkserver_installed": linkserver_found,
    }


def check_firmware_project() -> dict:
    firmware_dir = REPO_ROOT / "cpp-project" / "npu-tflite-test"
    lib_driver = firmware_dir / "eiq" / "neutron" / "mcxn" / "libNeutronDriver.a"
    lib_firmware = firmware_dir / "eiq" / "neutron" / "mcxn" / "libNeutronFirmware.a"
    model_header = firmware_dir / "source" / "model" / "model_data.h"

    return {
        "project_exists": firmware_dir.exists(),
        "lib_driver_exists": lib_driver.exists(),
        "lib_firmware_exists": lib_firmware.exists(),
        "model_header_exists": model_header.exists(),
    }


def check_neutron_compiler() -> dict:
    compiler_env = os.environ.get("NEUTRON_COMPILER")
    candidates = [
        compiler_env if compiler_env else None,
        str(Path.home() / "venvs" / "neutron" / "bin" / "neutron_compiler"),
        str(Path.home() / "neutron-env" / "bin" / "neutron_compiler"),
        shutil.which("neutron_compiler"),
    ]
    found_path = None
    for cand in candidates:
        if cand and Path(cand).exists():
            found_path = cand
            break

    version_str = ""
    if found_path:
        try:
            out = subprocess.check_output([found_path, "--version"], stderr=subprocess.STDOUT, text=True)
            version_str = out.strip()
        except Exception:
            version_str = "instalado (versão não retornada)"

    return {
        "found": found_path is not None,
        "path": found_path or "não encontrado",
        "version": version_str,
    }


def check_permissions_and_hardware() -> dict:
    # Dialout group
    user = os.environ.get("USER", "")
    in_dialout = False
    try:
        user_groups = [g.gr_name for g in grp.getgrall() if user in g.gr_mem]
        # Also check current process groups
        current_gids = os.getgroups()
        current_gnames = [grp.getgrgid(gid).gr_name for gid in current_gids]
        in_dialout = "dialout" in user_groups or "dialout" in current_gnames
    except Exception:
        in_dialout = False

    # .balas.env
    env_file = REPO_ROOT / ".balas.env"
    serial_port = None
    target = None
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("BALAS_SERIAL_PORT="):
                serial_port = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("BALAS_TARGET="):
                target = line.split("=", 1)[1].strip().strip('"').strip("'")

    port_accessible = False
    if serial_port:
        port_accessible = Path(serial_port).exists()

    return {
        "in_dialout": in_dialout,
        "env_file_exists": env_file.exists(),
        "serial_port": serial_port or "/dev/ttyACM0 (padrão)",
        "port_accessible": port_accessible,
        "target": target or "nxp (padrão)",
    }


def run_diagnostics() -> bool:
    print(f"\n{Colors.BOLD}{'=' * 75}{Colors.RESET}")
    print(f"{Colors.BOLD}🔍 B.A.L.A.S — Diagnóstico de Ambiente NXP MCXN947 (CPU & NPU){Colors.RESET}")
    print(f"{Colors.BOLD}{'=' * 75}{Colors.RESET}\n")

    all_critical_ok = True

    # 1. Python
    print(f"{Colors.BOLD}1. Pacotes Python:{Colors.RESET}")
    py_pkgs = check_python_packages()
    for pkg, ok in py_pkgs.items():
        print(f"   {check_mark(ok)} {pkg}")
        if not ok:
            all_critical_ok = False
            print(f"      👉 Instale com: pip install {pkg}")

    # 2. Toolchain MCUXpresso
    print(f"\n{Colors.BOLD}2. Ferramentas de Compilação MCUXpresso:{Colors.RESET}")
    tc = check_toolchain()
    print(f"   {check_mark(tc['ide_installed'])} IDE MCUXpresso: {tc['ide_path']}")
    if not tc["ide_installed"]:
        all_critical_ok = False
        print("      👉 Instale a IDE MCUXpresso 25.6 ou superior (ver docs/026_tutorial-npu-mcxn947.md)")

    print(f"   {check_mark(tc['gcc_installed'])} Compilador ARM GCC: {tc['gcc_path']}")
    if not tc["gcc_installed"]:
        all_critical_ok = False
        print("      👉 arm-none-eabi-gcc não encontrado na toolchain.")

    print(f"   {check_mark(tc['linkserver_installed'])} LinkServer (gravador MCU-Link)")
    if not tc["linkserver_installed"]:
        print(f"      {warn_mark()} LinkServer não detectado no PATH. O deploy na placa pode falhar.")

    # 3. Firmware NPU
    print(f"\n{Colors.BOLD}3. Projeto Firmware NPU (cpp-project/npu-tflite-test):{Colors.RESET}")
    fw = check_firmware_project()
    print(f"   {check_mark(fw['project_exists'])} Diretório do projeto C++")
    print(f"   {check_mark(fw['lib_driver_exists'])} libNeutronDriver.a (Driver NPU)")
    print(f"   {check_mark(fw['lib_firmware_exists'])} libNeutronFirmware.a (Microcódigo NPU)")
    if not (fw["project_exists"] and fw["lib_driver_exists"] and fw["lib_firmware_exists"]):
        all_critical_ok = False
        print("      👉 Bibliotecas Neutron ausentes em eiq/neutron/mcxn/.")

    # 4. Neutron Compiler
    print(f"\n{Colors.BOLD}4. Compilador eIQ Neutron (NPU Converter 3.2.2):{Colors.RESET}")
    nc = check_neutron_compiler()
    print(f"   {check_mark(nc['found'])} neutron_compiler: {nc['path']}")
    if nc["found"]:
        if nc["version"]:
            print(f"      Versão detectada: {nc['version']}")
    else:
        all_critical_ok = False
        print("      👉 O compilador da NPU não foi encontrado.")
        print("         Para instalar no seu virtualenv:")
        print("         pip install eiq-neutron-sdk --index-url https://eiq.nxp.com/repository/ --extra-index-url https://pypi.org/simple")
        print("         Ou aponte para um venv existente com: export NEUTRON_COMPILER=/caminho/para/neutron_compiler")

    # 5. Permissões e Conexão Hardware
    print(f"\n{Colors.BOLD}5. Hardware e Permissões Linux:{Colors.RESET}")
    hw = check_permissions_and_hardware()
    print(f"   {check_mark(hw['env_file_exists'])} Arquivo .balas.env configurado")
    print(f"   {check_mark(hw['in_dialout'])} Usuário no grupo 'dialout' (necessário para serial sem sudo)")
    if not hw["in_dialout"]:
        print("      👉 Adicione seu usuário ao grupo com: sudo usermod -a -G dialout $USER (e reinicie a sessão).")

    print(f"   Porta serial configurada: {hw['serial_port']}")
    if hw["port_accessible"]:
        print(f"   {check_mark(True)} Placa detectada na porta serial!")
    else:
        print(f"   {warn_mark()} Placa não detectada ou inacessível no caminho acima.")
        print("      (Normal caso a placa não esteja plugada no momento. Para rodar simulações no PC, use --sem-placa).")

    # Resumo final
    print(f"\n{Colors.BOLD}{'=' * 75}{Colors.RESET}")
    if all_critical_ok:
        print(f"{Colors.GREEN}{Colors.BOLD}🎉 Tudo pronto! O ambiente está configurado para executar testes CPU e NPU.{Colors.RESET}")
    else:
        print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  Algumas dependências estão pendentes. Siga as instruções acima antes de rodar na placa.{Colors.RESET}")
        print("   Dica: você ainda pode rodar validações no PC com o parâmetro --sem-placa.")
    print(f"{Colors.BOLD}{'=' * 75}{Colors.RESET}\n")

    return all_critical_ok


if __name__ == "__main__":
    success = run_diagnostics()
    sys.exit(0 if success else 1)

