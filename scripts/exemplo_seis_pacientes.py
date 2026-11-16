"""Reproduz o exemplo de seis pacientes (Seção 6.1) para várias janelas BUD.

Mostra, para cada BUD, a solução sem compartilhamento, FFD temporal, GRASP, VNS,
GRASP-VNS e o ótimo do MILP. Com BUD = 6 h o ótimo usa 3 frascos; com BUD = 1 h,
a restrição temporal passa a ser ativa e o ótimo sobe para 5 frascos — o exemplo
que evidencia o efeito do BUD.

Uso:  python scripts/exemplo_seis_pacientes.py [--buds 6 2 1.5 1]
Saída: results/exemplo_seis_pacientes.json e .md
"""
from __future__ import annotations

import argparse
import json

from comum import DIR_RES
from tbppbud.construtivo import ffd_temporal, sem_compartilhamento
from tbppbud.instancia import exemplo_seis_pacientes
from tbppbud.metaheuristicas import grasp, grasp_vns, vns
from tbppbud.milp import resolver_milp
from tbppbud.solucao import verificar


def hhmm(minutos_desde_8h: float) -> str:
    m = int(round(480 + minutos_desde_8h))
    return f"{m // 60}h{m % 60:02d}"


def reais(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def grupos(sol) -> str:
    return " ".join("{" + ",".join(f"P{i+1}" for i in sorted(f.pacientes)) + "}"
                    for f in sorted(sol.frascos, key=lambda f: min(f.pacientes)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buds", nargs="*", type=float, default=[6, 2, 1.5, 1])
    ap.add_argument("--semente", type=int, default=1)
    a = ap.parse_args()
    saida, md = [], ["# Exemplo de seis pacientes\n"]
    for bud in a.buds:
        inst = exemplo_seis_pacientes(bud)
        p = dict(tempo_limite_s=10)
        sols = {
            "Sem compartilhamento": sem_compartilhamento(inst),
            "FFD temporal": ffd_temporal(inst),
            "GRASP": grasp(inst, a.semente, p).solucao,
            "VNS": vns(inst, a.semente, p).solucao,
            "GRASP-VNS": grasp_vns(inst, a.semente, p).solucao,
        }
        m = resolver_milp(inst, 60)
        sols["MILP (ótimo)" if m.otimo else f"MILP ({m.status})"] = m.solucao
        md.append(f"\n## BUD = {bud:g} h\n\n| Método | Frascos | Custo (R$) | Sobra (mg) | Utilização (%) | Agrupamento |\n|---|---|---|---|---|---|")
        reg = dict(bud_h=bud, metodos={})
        for nome, s in sols.items():
            assert not verificar(s), (nome, verificar(s))
            md.append(f"| {nome} | {s.n_frascos()} | {reais(s.custo())} | {s.sobra():.0f} | {s.utilizacao():.1f} | {grupos(s)} |")
            reg["metodos"][nome] = dict(s.to_dict(), agrupamento=grupos(s))
        md.append("\nJanelas da solução do MILP: " + "; ".join(
            f"{grupos_f} {hhmm(f.t_min)}–{hhmm(f.t_min + inst.bud)}"
            for f in m.solucao.frascos
            for grupos_f in ["{" + ",".join(f"P{i+1}" for i in sorted(f.pacientes)) + "}"]))
        saida.append(reg)
        print(f"BUD={bud:g}h  ótimo={m.solucao.n_frascos()} frascos  GRASP-VNS={sols['GRASP-VNS'].n_frascos()}  ->  {grupos(m.solucao)}")
    DIR_RES.mkdir(exist_ok=True)
    (DIR_RES / "exemplo_seis_pacientes.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    (DIR_RES / "exemplo_seis_pacientes.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("tabelas em results/exemplo_seis_pacientes.md")


if __name__ == "__main__":
    main()
