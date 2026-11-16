"""Gera as instâncias sintéticas (conjunto de teste e conjunto de calibração).

Uso:
    python scripts/gerar_instancias.py            # gera teste (90) e calibração
    python scripts/gerar_instancias.py --forcar   # sobrescreve arquivos existentes

O conjunto de calibração usa sementes diferentes do de teste, para que os
parâmetros não sejam ajustados nas mesmas instâncias em que são avaliados.
"""
from __future__ import annotations

import argparse
import random

from comum import DIR_INST, carregar_config
from tbppbud.instancia import gerar_instancia


def gerar(conjunto: str, cfg: dict, por_comb: int, semente_base: int, forcar: bool) -> int:
    g = cfg["gerador"]
    sc = g["superficie_corporal"]
    total = 0
    for ic, (classe, (n_min, n_max)) in enumerate(g["classes"].items()):
        for bud in g["bud_horas"]:
            for r in range(por_comb):
                semente = semente_base + 10000 * ic + 100 * int(bud) + r
                n = random.Random(semente).randint(n_min, n_max)
                nome = f"{classe}_bud{bud:g}h_{r:02d}_n{n}"
                caminho = DIR_INST / conjunto / classe / f"{nome}.json"
                if caminho.exists() and not forcar:
                    continue
                inst = gerar_instancia(
                    n, bud, semente, classe=classe, nome=nome,
                    tamanhos_frasco=g["tamanhos_frasco_mg"], custo_por_mg=g["custo_por_mg"],
                    expediente_min=g["expediente_min"], intervalo_agenda_min=g["intervalo_agenda_min"],
                    dose_mg_m2=g["dose_mg_m2"], sc_media=sc["media"], sc_desvio=sc["desvio"],
                    sc_min=sc["min"], sc_max=sc["max"])
                inst.salvar(caminho)
                total += 1
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forcar", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args()
    cfg = carregar_config(a.config)
    g = cfg["gerador"]
    n1 = gerar("teste", cfg, g["instancias_por_combinacao"], g["semente_base_teste"], a.forcar)
    n2 = gerar("calibracao", cfg, g["instancias_calibracao_por_classe"], g["semente_base_calibracao"], a.forcar)
    print(f"instâncias geradas: teste={n1}, calibração={n2} (em {DIR_INST})")


if __name__ == "__main__":
    main()
