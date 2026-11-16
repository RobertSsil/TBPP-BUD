"""Registra o ambiente computacional em environment.txt (Apêndice B)."""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from importlib import metadata

from comum import RAIZ


def versao(pacote: str) -> str:
    try:
        return metadata.version(pacote)
    except metadata.PackageNotFoundError:
        return "não instalado"


def cpu() -> str:
    try:
        if sys.platform == "win32":
            out = subprocess.run(["wmic", "cpu", "get", "name"], capture_output=True, text=True).stdout
            linhas = [l.strip() for l in out.splitlines() if l.strip() and l.strip() != "Name"]
            return linhas[0] if linhas else platform.processor()
        if sys.platform == "darwin":
            return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
        with open("/proc/cpuinfo") as f:
            for l in f:
                if l.startswith("model name"):
                    return l.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "desconhecido"


def main():
    linhas = [
        f"Sistema operacional: {platform.system()} {platform.release()} ({platform.version()})",
        f"Arquitetura: {platform.machine()}",
        f"Processador: {cpu()}",
        f"Núcleos lógicos: {os.cpu_count()}",
        f"Python: {platform.python_version()} ({platform.python_implementation()})",
        f"highspy (solver HiGHS): {versao('highspy')}",
        f"numpy: {versao('numpy')}",
        f"pandas: {versao('pandas')}",
        f"matplotlib: {versao('matplotlib')}",
        f"scipy: {versao('scipy')}",
        "Paralelismo: execuções sequenciais; MILP com 1 thread (config/experimento.json)",
    ]
    (RAIZ / "environment.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas))
    print("\nRAM: informe manualmente no texto (ex.: 16 GB LPDDR5X).")


if __name__ == "__main__":
    main()
