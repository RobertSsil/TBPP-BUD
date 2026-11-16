"""Funções compartilhadas pelos scripts (caminhos, configuração, CSV)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

DIR_INST = RAIZ / "instances"
DIR_RES = RAIZ / "results"
DIR_CFG = RAIZ / "config"


def carregar_config(caminho: str | Path | None = None) -> dict:
    caminho = Path(caminho) if caminho else DIR_CFG / "experimento.json"
    with open(caminho, encoding="utf-8") as f:
        cfg = json.load(f)
    calib = DIR_CFG / "parametros_calibrados.json"
    if calib.exists() and cfg.get("usar_parametros_calibrados", True):
        with open(calib, encoding="utf-8") as f:
            cfg["heuristicas"]["parametros"].update(json.load(f)["parametros"])
    return cfg


def listar_instancias(conjunto: str = "teste") -> list[Path]:
    return sorted((DIR_INST / conjunto).rglob("*.json"))


def anexar_csv(caminho: Path, linhas: list[dict]) -> None:
    if not linhas:
        return
    caminho.parent.mkdir(parents=True, exist_ok=True)
    novo = not caminho.exists()
    with open(caminho, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        if novo:
            w.writeheader()
        w.writerows(linhas)


def ler_csv(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    with open(caminho, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
