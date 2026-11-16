"""Calibração exploratória reduzida dos parâmetros do GRASP-VNS.

Protocolo desta cópia acelerada: um passe, três candidatos por parâmetro
(12 configurações no total), usando somente instances/calibracao e sementes
independentes do conjunto de teste. Não equivale à varredura original de
cinco candidatos em duas passadas.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
from multiprocessing import Pool

from comum import DIR_CFG, DIR_RES, anexar_csv, carregar_config, listar_instancias
from tbppbud.instancia import Instancia
from tbppbud.metaheuristicas import grasp_vns


FAIXAS = {
    "alfa": [0.1, 0.3, 0.5],
    "iteracoes_grasp": [50, 200, 500],
    "limite_estagnacao": [10, 20, 35],
    "intensidade_shaking": [1, 2, 3],
}


def _cpu_disponiveis() -> int:
    """Retorna CPUs lógicas permitidas pela afinidade, ou o total reportado pelo SO."""
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def _rodar(tarefa):
    """Executa uma (instância, semente, parâmetros); função de topo para o Pool."""
    caminho, semente, params = tarefa
    inst = Instancia.carregar(caminho)
    r = grasp_vns(inst, semente, params)
    return inst.nome, semente, r.solucao.custo(), r.tempo_s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sementes", nargs="*", type=int, default=[1, 2, 3])
    ap.add_argument("--passadas", type=int, default=1)
    ap.add_argument("--tempo", type=float, default=None, help="limite por execução (s)")
    ap.add_argument("--processos", type=int, default=None,
                    help="workers solicitados (limitados às CPUs permitidas pelo SO)")
    a = ap.parse_args()
    if a.passadas < 1:
        ap.error("--passadas deve ser pelo menos 1")

    cfg = carregar_config()
    cfg_base = json.loads((DIR_CFG / "experimento.json").read_text(encoding="utf-8"))
    atual = dict(cfg_base["heuristicas"]["parametros"])
    if a.tempo:
        atual["tempo_limite_s"] = a.tempo

    caminhos = listar_instancias("calibracao")
    insts = [Instancia.carregar(p) for p in caminhos]
    if not insts:
        raise SystemExit("sem instâncias de calibração — rode scripts/gerar_instancias.py")

    pedido = a.processos or cfg.get("paralelismo", {}).get("processos", 10)
    nproc = max(1, min(pedido, _cpu_disponiveis()))
    print(f"calibração reduzida: {len(insts)} instâncias x {len(a.sementes)} sementes; "
          f"{sum(map(len, FAIXAS.values()))} candidatos; {nproc}/{_cpu_disponiveis()} "
          "processos permitidos", flush=True)

    pool = Pool(nproc) if nproc > 1 else None
    melhor_conhecido = {}
    cache = {}

    def avaliar(params: dict, numero: int, total: int):
        chave = json.dumps(params, sort_keys=True)
        if chave in cache:
            return cache[chave]
        custos, tempos, linhas = {}, [], []
        tarefas = [(str(cam), semente, params) for cam in caminhos for semente in a.sementes]
        saidas = []
        if pool:
            iterator = pool.imap_unordered(_rodar, tarefas, chunksize=1)
        else:
            iterator = map(_rodar, tarefas)
        for concluidas, resultado in enumerate(iterator, 1):
            saidas.append(resultado)
            if concluidas == 1 or concluidas % 10 == 0 or concluidas == len(tarefas):
                print(f"[calibração {numero}/{total}] {concluidas}/{len(tarefas)} execuções "
                      "da configuração concluídas", flush=True)
        for nome, semente, custo, tempo in saidas:
            custos[(nome, semente)] = custo
            tempos.append(tempo)
            melhor_conhecido[nome] = min(melhor_conhecido.get(nome, custo), custo)
            linhas.append(dict(instancia=nome, semente=semente, custo=custo,
                               tempo_s=round(tempo, 3),
                               **{k: params[k] for k in FAIXAS}))
        anexar_csv(DIR_RES / "calibracao.csv", linhas)
        cache[chave] = (custos, st.mean(tempos))
        return cache[chave]

    def rpd(custos: dict) -> float:
        return st.mean(100 * (c - melhor_conhecido[n]) / melhor_conhecido[n]
                       for (n, _), c in custos.items())

    total_avaliacoes = a.passadas * sum(len(v) for v in FAIXAS.values())
    avaliacao_atual = 0
    try:
        for passada in range(a.passadas):
            for parametro, valores in FAIXAS.items():
                resultados = []
                for valor in valores:
                    avaliacao_atual += 1
                    params = dict(atual, **{parametro: valor})
                    print(f"iniciando {parametro}={valor} "
                          f"({avaliacao_atual}/{total_avaliacoes})", flush=True)
                    custos, tempo_medio = avaliar(params, avaliacao_atual, total_avaliacoes)
                    resultados.append((valor, custos, tempo_medio))
                avaliados = [(valor, rpd(custos), tempo)
                             for valor, custos, tempo in resultados]
                melhor = min(r for _, r, _ in avaliados)
                escolhido = min((item for item in avaliados if item[1] <= melhor + 0.01),
                                key=lambda item: item[2])
                atual[parametro] = escolhido[0]
                print(f"passada {passada + 1} | {parametro}: "
                      + ", ".join(f"{v}→{r:.3f}% ({t:.1f}s)" for v, r, t in avaliados)
                      + f"  ==> {escolhido[0]}", flush=True)
    except BaseException:
        if pool:
            pool.terminate()
            pool.join()
        raise
    else:
        if pool:
            pool.close()
            pool.join()

    saida = dict(
        parametros={k: atual[k] for k in FAIXAS},
        processos=nproc,
        criterio="RPD médio vs. melhor conhecido; desempate por tempo médio",
        sementes=a.sementes,
        instancias=[i.nome for i in insts],
        passadas=a.passadas,
        candidatos=FAIXAS,
        protocolo="calibracao exploratoria reduzida: 3 candidatos por parametro; nao equivalente a varredura original",
    )
    (DIR_CFG / "parametros_calibrados.json").write_text(
        json.dumps(saida, indent=1, ensure_ascii=False), encoding="utf-8")
    print("valores finais:", saida["parametros"], flush=True)


if __name__ == "__main__":
    main()
