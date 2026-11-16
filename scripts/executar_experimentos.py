"""Executa os experimentos computacionais e grava os resultados por instância e semente.

Para cada instância do conjunto de teste:
  1. referências determinísticas: sem compartilhamento (C_ref) e FFD temporal;
  2. modelo exato (MILP/HiGHS) com limite de tempo, uma vez por instância;
  3. para cada semente: GRASP-VNS; depois GRASP isolado e VNS isolado com o MESMO
     tempo de parede gasto pelo GRASP-VNS naquela instância e semente (orçamento igual);
  4. (opcional) ablação das vizinhanças.

Os resultados vão para results/ e a execução é retomável: o que já foi feito é pulado.

Uso:
    python scripts/executar_experimentos.py                      # tudo, conforme config
    python scripts/executar_experimentos.py --classes pequena    # só uma classe
    python scripts/executar_experimentos.py --sem-milp           # pula o modelo exato
    python scripts/executar_experimentos.py --tempo-milp 300 --sementes 1 2 3
    python scripts/executar_experimentos.py --tempo-heur 10 --max-instancias 5   # teste rápido
    python scripts/executar_experimentos.py --processos 10       # instâncias em paralelo
    python scripts/executar_experimentos.py --ablacao            # só a ablação
    python scripts/executar_experimentos.py --so-milp --processos 4   # só o MILP, em paralelo

Paralelismo: por padrão usa config 'paralelismo.processos' (10). O número é limitado aos
núcleos lógicos e, nas fases com MILP, à RAM livre (~0,8 GB por MILP). Processos paralelos
disputam CPU; os tempos medidos ficam maiores do que numa execução isolada, mas todos os
métodos são afetados da mesma forma. Informe no texto o número de processos usado.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from multiprocessing import Pool

from comum import DIR_RES, anexar_csv, carregar_config, ler_csv, listar_instancias
from tbppbud.construtivo import ffd_temporal, sem_compartilhamento
from tbppbud.instancia import Instancia
from tbppbud.metaheuristicas import grasp, grasp_vns, vns
from tbppbud.milp import limite_inferior_volumetrico, resolver_milp
from tbppbud.solucao import verificar

DIR_SOL = DIR_RES / "solucoes"


def _csv(tipo: str, nome: str):
    """Um CSV por instância e por tipo (execucoes, milp, referencias, ablacao):
    evita disputa de escrita entre processos paralelos."""
    return DIR_RES / tipo / f"{nome}.csv"


def _linha(inst: Instancia, metodo: str, semente, res, extra=None) -> dict:
    s = res.solucao
    erros = verificar(s)
    if erros:
        raise RuntimeError(f"{inst.nome}/{metodo}/{semente}: solução inviável: {erros[:3]}")
    d = dict(instancia=inst.nome, classe=inst.classe, n=inst.n, bud_h=inst.bud / 60,
             metodo=metodo, semente=semente, custo=s.custo(), n_frascos=s.n_frascos(),
             sobra_mg=round(s.sobra(), 3), utilizacao=round(s.utilizacao(), 4),
             tempo_s=round(res.tempo_s, 4), tempo_ate_melhor_s=round(res.tempo_ate_melhor_s, 4),
             iteracoes=res.iteracoes, viavel=1)
    d.update({f"mov_{k}": v for k, v in res.movimentos.items()})
    if extra:
        d.update(extra)
    return d


def ram_livre_gb() -> float | None:
    """Memória física disponível (GB), sem dependências externas. None se não souber."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MEMSTAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMSTAT(); st.dwLength = ctypes.sizeof(MEMSTAT)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return st.ullAvailPhys / 2 ** 30
        with open("/proc/meminfo") as f:
            for linha in f:
                if linha.startswith("MemAvailable"):
                    return int(linha.split()[1]) / 2 ** 20
    except Exception:
        pass
    return None


def cpus_disponiveis() -> int:
    """CPUs lógicas visíveis ao processo, respeitando afinidade/contêiner quando possível."""
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def definir_processos(pedido: int | None, cfg: dict, roda_milp: bool) -> int:
    """Limita workers às CPUs permitidas e, para MILP, à RAM livre estimada."""
    par = cfg.get("paralelismo", {})
    n = pedido or par.get("processos", 10)
    n = max(1, min(n, cpus_disponiveis()))
    if roda_milp:
        gb_por = float(par.get("memoria_por_milp_gb", 0.8))
        livre = ram_livre_gb()
        if livre is not None:
            limite = max(1, int((livre - 1.0) // gb_por))  # reserva 1 GB para o sistema
            if limite < n:
                print(f"aviso: {livre:.1f} GB de RAM livres; MILP limitado a {limite} processos "
                      f"(~{gb_por:g} GB cada). Ajuste 'paralelismo.memoria_por_milp_gb' se necessário.",
                      flush=True)
                n = limite
    return n


def processar_instancia(args) -> str:
    caminho, cfg, opc = args
    inst = Instancia.carregar(caminho)
    CSV_EXEC, CSV_MILP = _csv("execucoes", inst.nome), _csv("milp", inst.nome)
    CSV_REF, CSV_ABL = _csv("referencias", inst.nome), _csv("ablacao", inst.nome)
    feitos = {(r["instancia"], r["metodo"], r["semente"]) for r in ler_csv(CSV_EXEC)}
    feitos_milp = {r["instancia"] for r in ler_csv(CSV_MILP)}
    feitos_ref = {r["instancia"] for r in ler_csv(CSV_REF)}
    hp = dict(cfg["heuristicas"]["parametros"])

    # ---------------- referências determinísticas
    if inst.nome not in feitos_ref and not opc["ablacao"]:
        t0 = time.perf_counter(); ref = sem_compartilhamento(inst); t_ref = time.perf_counter() - t0
        t0 = time.perf_counter(); ffd = ffd_temporal(inst); t_ffd = time.perf_counter() - t0
        assert not verificar(ref) and not verificar(ffd)
        anexar_csv(CSV_REF, [dict(instancia=inst.nome, classe=inst.classe, n=inst.n, bud_h=inst.bud / 60,
                                  custo_sem_compart=ref.custo(), frascos_sem_compart=ref.n_frascos(),
                                  sobra_sem_compart=ref.sobra(), custo_ffd=ffd.custo(),
                                  frascos_ffd=ffd.n_frascos(), sobra_ffd=ffd.sobra(),
                                  tempo_ffd_s=round(t_ffd, 5),
                                  lb_volumetrico=limite_inferior_volumetrico(inst))])

    # ---------------- modelo exato
    if cfg["milp"]["executar"] and not opc["sem_milp"] and not opc["ablacao"] and inst.nome not in feitos_milp:
        tl = opc["tempo_milp"] or cfg["milp"]["tempo_limite_s"]
        ws = ffd_temporal(inst) if cfg["milp"].get("warm_start") == "FFD" else None
        m = resolver_milp(inst, tl, solucao_inicial=ws, threads=cfg["milp"]["threads"])
        if m.solucao is not None:
            erros = verificar(m.solucao)
            if erros:
                raise RuntimeError(f"MILP inviável em {inst.nome}: {erros[:3]}")
        anexar_csv(CSV_MILP, [dict(instancia=inst.nome, classe=inst.classe, n=inst.n, bud_h=inst.bud / 60,
                                   status=m.status, otimo=int(m.otimo), custo=m.custo,
                                   limite_inferior=m.limite_inferior, gap_solver=m.gap_solver,
                                   tempo_s=round(m.tempo_s, 2), tempo_limite_s=tl,
                                   n_variaveis=m.n_variaveis, n_restricoes=m.n_restricoes)])

    if opc.get("so_milp"):
        return inst.nome
    sementes = opc["sementes"] or cfg["heuristicas"]["sementes"]

    # ---------------- ablação
    if opc["ablacao"]:
        feitos_abl = {(r["instancia"], r["metodo"], r["semente"]) for r in ler_csv(CSV_ABL)}
        for var, viz in cfg["ablacao"]["variantes"].items():
            for sem in cfg["ablacao"]["sementes"]:
                if (inst.nome, var, str(sem)) in feitos_abl:
                    continue
                p = dict(hp, vizinhancas=viz)
                r = grasp_vns(inst, sem, p, nome=var)
                anexar_csv(CSV_ABL, [_linha(inst, var, sem, r)])
        return inst.nome

    # ---------------- heurísticas
    for sem in sementes:
        linhas = []
        chave = (inst.nome, "GRASP-VNS", str(sem))
        if chave in feitos:
            tempo_gv = float(next(r["tempo_s"] for r in ler_csv(CSV_EXEC)
                                  if (r["instancia"], r["metodo"], r["semente"]) == chave))
        else:
            r = grasp_vns(inst, sem, hp)
            tempo_gv = r.tempo_s
            linhas.append(_linha(inst, "GRASP-VNS", sem, r))
            DIR_SOL.mkdir(parents=True, exist_ok=True)
            with open(DIR_SOL / f"{inst.nome}_GRASP-VNS_s{sem}.json", "w", encoding="utf-8") as f:
                json.dump(r.solucao.to_dict(), f, indent=1)
        orc = tempo_gv if cfg["heuristicas"]["orcamento_igual"] else hp["tempo_limite_s"]
        if "GRASP" in cfg["heuristicas"]["metodos"] and (inst.nome, "GRASP", str(sem)) not in feitos:
            p = dict(hp, tempo_limite_s=orc)
            if cfg["heuristicas"]["orcamento_igual"]:
                p["iteracoes_grasp"] = 10 ** 9  # para pelo tempo, não pelas iterações
            linhas.append(_linha(inst, "GRASP", sem, grasp(inst, sem, p)))
        if "VNS" in cfg["heuristicas"]["metodos"] and (inst.nome, "VNS", str(sem)) not in feitos:
            p = dict(hp, tempo_limite_s=orc)
            linhas.append(_linha(inst, "VNS", sem,
                                 vns(inst, sem, p, ate_o_prazo=cfg["heuristicas"]["orcamento_igual"])))
        anexar_csv(CSV_EXEC, linhas)
    return inst.nome


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--classes", nargs="*")
    ap.add_argument("--sementes", nargs="*", type=int)
    ap.add_argument("--sem-milp", action="store_true")
    ap.add_argument("--tempo-milp", type=float)
    ap.add_argument("--tempo-heur", type=float, help="sobrescreve tempo_limite_s das heurísticas")
    ap.add_argument("--max-instancias", type=int)
    ap.add_argument("--processos", type=int, default=None,
                    help="processos em paralelo (padrão: config 'paralelismo.processos' ou 10)")
    ap.add_argument("--ablacao", action="store_true")
    ap.add_argument("--so-milp", action="store_true", help="roda apenas referências e MILP")
    a = ap.parse_args()
    cfg = carregar_config(a.config)
    if a.tempo_heur:
        cfg["heuristicas"]["parametros"]["tempo_limite_s"] = a.tempo_heur
    insts = listar_instancias("teste")
    if not insts:
        raise SystemExit("nenhuma instância em instances/teste — rode scripts/gerar_instancias.py")
    if a.classes:
        insts = [p for p in insts if p.parent.name in a.classes]
    if a.max_instancias:
        insts = insts[:a.max_instancias]
    opc = dict(sem_milp=a.sem_milp, tempo_milp=a.tempo_milp, sementes=a.sementes, ablacao=a.ablacao, so_milp=a.so_milp)
    DIR_RES.mkdir(exist_ok=True)
    tarefas = [(p, cfg, opc) for p in insts]
    roda_milp = cfg["milp"]["executar"] and not a.sem_milp and not a.ablacao
    nproc = definir_processos(a.processos, cfg, roda_milp)
    opc["processos"] = nproc
    fase = "milp" if a.so_milp else "ablacao" if a.ablacao else "heuristicas" if a.sem_milp else "completo"
    registro = dict(config=cfg, opcoes=opc, fase=fase, inicio=time.strftime("%Y-%m-%d %H:%M:%S"),
                    python=platform.python_version(), nucleos_logicos=cpus_disponiveis(),
                    ram_livre_gb=ram_livre_gb())
    for nome_arq in ("config_usada.json", f"config_usada_{fase}.json"):
        with open(DIR_RES / nome_arq, "w", encoding="utf-8") as f:
            json.dump(registro, f, ensure_ascii=False, indent=1)
    print(f"{len(tarefas)} instâncias | {nproc} processo(s) em paralelo | "
          f"{cpus_disponiveis()} CPUs lógicas disponíveis | RAM livre: {ram_livre_gb() or 0:.1f} GB", flush=True)
    t0 = time.perf_counter()
    if nproc > 1:
        with Pool(nproc) as pool:
            for i, nome in enumerate(pool.imap_unordered(processar_instancia, tarefas), 1):
                print(f"[{i}/{len(tarefas)}] {nome}  ({time.perf_counter()-t0:.0f}s)", flush=True)
    else:
        for i, t in enumerate(tarefas, 1):
            nome = processar_instancia(t)
            print(f"[{i}/{len(tarefas)}] {nome}  ({time.perf_counter()-t0:.0f}s)", flush=True)
    print("concluído. Rode: python analysis/analisar_resultados.py")


if __name__ == "__main__":
    main()
