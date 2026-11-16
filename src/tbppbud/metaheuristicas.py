"""GRASP, VNS e GRASP-VNS para o TBPP-BUD.

Parâmetros (ver config/experimento.json):
  alfa                  parâmetro guloso da RCL
  iteracoes_grasp       número de iterações (reinícios) do GRASP
  limite_estagnacao     iterações VNS sem melhora antes de parar
  intensidade_shaking   k_max: o shaking realoca k = 1..k_max pacientes (VNS básico)
  vizinhancas           ordem das vizinhanças do VND
  criterio_secundario   usa ocupação quadrática para desempatar custo
  estrategia            "first" (primeira melhora) ou "best" (melhor melhora)
  funcao_gulosa         "descrita" ou "residual"
  tempo_limite_s        limite de tempo de parede por execução
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from .busca import Busca
from .construtivo import construir_grasp, ffd_temporal
from .instancia import Instancia
from .solucao import Solucao

PARAMETROS_PADRAO = dict(
    alfa=0.3, iteracoes_grasp=200, limite_estagnacao=20, intensidade_shaking=2,
    vizinhancas=["merge", "consolidar", "shift", "resize", "swap"], criterio_secundario=True,
    estrategia="first", funcao_gulosa="descrita", tempo_limite_s=60.0)


@dataclass
class Resultado:
    metodo: str
    solucao: Solucao
    tempo_s: float
    iteracoes: int
    tempo_ate_melhor_s: float
    historico: list[tuple[float, float]] = field(default_factory=list)  # (tempo, custo)
    movimentos: dict = field(default_factory=dict)


def _params(p: dict | None) -> dict:
    q = dict(PARAMETROS_PADRAO)
    if p:
        q.update(p)
    return q


def _vns(busca: Busca, s: Solucao, p: dict, prazo: float | None,
         reiniciar_sem_fim: bool = False, t0: float = 0.0, hist=None) -> Solucao:
    """VNS básico: shaking em N_k (k pacientes realocados), VND e critério de aceitação
    'move-or-not' (aceita só se melhorar). k volta a 1 após melhora.
    Para quando acumula `limite_estagnacao` iterações sem melhora, ou no prazo."""
    s = busca.vnd(s)
    k, estag = 1, 0
    kmax = max(1, int(p["intensidade_shaking"]))
    while not (prazo is not None and time.perf_counter() >= prazo):
        if estag >= p["limite_estagnacao"]:
            if not reiniciar_sem_fim:
                break
            estag = 0  # VNS isolado: continua até o orçamento de tempo
        s2 = busca.vnd(busca.perturbar(s, k))
        if s2.chave() < s.chave():
            s, k, estag = s2, 1, 0
            if hist is not None:
                hist.append((time.perf_counter() - t0, s.custo()))
        else:
            k = k + 1 if k < kmax else 1
            estag += 1
    return s


def grasp_vns(inst: Instancia, semente: int, params: dict | None = None,
              nome: str = "GRASP-VNS") -> Resultado:
    """Algoritmo 1: para cada iteração GRASP, constrói com RCL e refina com VNS."""
    p = _params(params)
    rng = random.Random(semente)
    t0 = time.perf_counter()
    prazo = t0 + p["tempo_limite_s"] if p["tempo_limite_s"] else None
    busca = Busca(p["vizinhancas"], p["criterio_secundario"], p["estrategia"], rng, prazo)
    melhor, t_melhor, hist, it = None, 0.0, [], 0
    while it < p["iteracoes_grasp"] and not busca._esgotado():
        s = construir_grasp(inst, p["alfa"], rng, p["funcao_gulosa"])
        s = _vns(busca, s, p, prazo)
        it += 1
        if melhor is None or s.chave() < melhor.chave():
            melhor, t_melhor = s, time.perf_counter() - t0
            hist.append((t_melhor, melhor.custo()))
    if melhor is None:  # prazo esgotado antes da 1a iteração
        melhor = construir_grasp(inst, p["alfa"], rng, p["funcao_gulosa"])
    return Resultado(nome, melhor, time.perf_counter() - t0, it, t_melhor, hist,
                     dict(busca.contagem))


def grasp(inst: Instancia, semente: int, params: dict | None = None,
          nome: str = "GRASP") -> Resultado:
    """GRASP isolado: construção com RCL + VND (busca local), sem shaking."""
    p = _params(params)
    rng = random.Random(semente)
    t0 = time.perf_counter()
    prazo = t0 + p["tempo_limite_s"] if p["tempo_limite_s"] else None
    busca = Busca(p["vizinhancas"], p["criterio_secundario"], p["estrategia"], rng, prazo)
    melhor, t_melhor, hist, it = None, 0.0, [], 0
    while it < p["iteracoes_grasp"] and not busca._esgotado():
        s = busca.vnd(construir_grasp(inst, p["alfa"], rng, p["funcao_gulosa"]))
        it += 1
        if melhor is None or s.chave() < melhor.chave():
            melhor, t_melhor = s, time.perf_counter() - t0
            hist.append((t_melhor, melhor.custo()))
    if melhor is None:
        melhor = construir_grasp(inst, p["alfa"], rng, p["funcao_gulosa"])
    return Resultado(nome, melhor, time.perf_counter() - t0, it, t_melhor, hist,
                     dict(busca.contagem))


def vns(inst: Instancia, semente: int, params: dict | None = None,
        nome: str = "VNS", ate_o_prazo: bool = False) -> Resultado:
    """VNS isolado: solução inicial simples (FFD temporal) + VNS.
    Com ate_o_prazo=True, continua até esgotar tempo_limite_s (orçamento igual)."""
    p = _params(params)
    rng = random.Random(semente)
    t0 = time.perf_counter()
    prazo = t0 + p["tempo_limite_s"] if p["tempo_limite_s"] else None
    busca = Busca(p["vizinhancas"], p["criterio_secundario"], p["estrategia"], rng, prazo)
    hist = []
    s0 = ffd_temporal(inst)
    hist.append((time.perf_counter() - t0, s0.custo()))
    s = _vns(busca, s0, p, prazo, reiniciar_sem_fim=ate_o_prazo and prazo is not None,
             t0=t0, hist=hist)
    t_melhor = hist[-1][0] if hist else 0.0
    return Resultado(nome, s, time.perf_counter() - t0, 1, t_melhor, hist, dict(busca.contagem))
