"""Modelo MILP do TBPP-BUD (Seções 5.2 a 5.6), resolvido com HiGHS (highspy).

  min  sum_k c_k z_k
  s.a. sum_k x_ik = 1                               para todo i
       sum_i d_i x_ik <= V_k z_k                    para todo k
       tau_k <= t_i + M (1 - x_ik)                  para todo i, k
       t_i <= tau_k + Delta + M (1 - x_ik)          para todo i, k
       0 <= tau_k <= T_max z_k                      para todo k
       z_k >= z_{k+1}  (cópias do mesmo tipo)       quebra de simetria
       x, z binárias; tau contínua

Escolhas de implementação (documentadas para a reprodutibilidade):
  * Conjunto K de frascos potenciais = cópias de cada tipo t. Número de cópias:
      u_t = min( #pacientes com d_i <= V_t , floor(UB / c_t) ),
    em que UB é o custo de uma solução viável (FFD temporal). É um limite válido:
    nenhuma solução de custo <= UB usa mais de floor(UB / c_t) frascos do tipo t.
  * x_ik só é criada se d_i <= V_k (as demais são fixas em 0).
  * M = T_max: é o menor valor que torna as duas restrições redundantes quando x_ik = 0,
    pois tau_k e t_i pertencem a [0, T_max].
  * Se Delta >= T_max, as restrições temporais são redundantes e são omitidas
    (o problema vira um bin packing com tipos de frasco).
  * Uma solução heurística pode ser passada como solução inicial (warm start).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np

from .instancia import Instancia
from .solucao import Solucao


@dataclass
class ResultadoMILP:
    status: str
    custo: float | None          # melhor solução inteira encontrada
    limite_inferior: float | None  # dual bound do branch-and-bound
    gap_solver: float | None     # gap relatado pelo HiGHS (fração)
    tempo_s: float
    otimo: bool
    n_variaveis: int
    n_restricoes: int
    solucao: Solucao | None


def limite_inferior_volumetrico(inst: Instancia) -> float:
    """LB trivial: cada mg custa ao menos min_t (c_t / V_t)."""
    razao = min(tp.custo / tp.capacidade for tp in inst.tipos)
    return razao * sum(inst.doses)


def resolver_milp(inst: Instancia, tempo_limite_s: float = 3600.0,
                  solucao_inicial: Solucao | None = None, ub: float | None = None,
                  threads: int = 1, verbose: bool = False, semente: int = 0,
                  quebra_simetria: bool = True) -> ResultadoMILP:
    import highspy

    n, tipos = inst.n, inst.tipos
    d = np.array(inst.doses, dtype=float)
    t = np.array(inst.horarios, dtype=float)
    M = float(inst.t_max)
    usar_tempo = inst.bud < inst.t_max

    if ub is None:
        from .construtivo import ffd_temporal
        ub = ffd_temporal(inst).custo()

    # ---------------- frascos potenciais
    frascos = []  # (tipo, copia)
    for k, tp in enumerate(tipos):
        cabem = int(np.sum(d <= tp.capacidade + 1e-9))
        u = min(cabem, int(math.floor(ub / tp.custo + 1e-9)))
        frascos += [(k, c) for c in range(u)]
    m = len(frascos)

    # ---------------- colunas: z_k (m), tau_k (m), x_ik (pares compatíveis)
    col_cost, col_lb, col_ub, integral = [], [], [], []
    z_idx = list(range(m))
    for (k, _) in frascos:
        col_cost.append(tipos[k].custo); col_lb.append(0.0); col_ub.append(1.0); integral.append(1)
    tau_idx = list(range(m, 2 * m))
    for _ in frascos:
        col_cost.append(0.0); col_lb.append(0.0); col_ub.append(M); integral.append(0)
    x_idx = {}
    for kk, (k, _) in enumerate(frascos):
        cap = tipos[k].capacidade
        for i in range(n):
            if d[i] <= cap + 1e-9:
                x_idx[(i, kk)] = len(col_cost)
                col_cost.append(0.0); col_lb.append(0.0); col_ub.append(1.0); integral.append(1)
    ncol = len(col_cost)

    # ---------------- linhas (formato esparso por linha)
    r_lo, r_up, starts, idx, val = [], [], [], [], []

    def linha(lo, up, coefs):
        starts.append(len(idx))
        for j, v in coefs:
            idx.append(j); val.append(v)
        r_lo.append(lo); r_up.append(up)

    inf = highspy.kHighsInf
    por_paciente = {i: [] for i in range(n)}
    por_frasco = {kk: [] for kk in range(m)}
    for (i, kk), j in x_idx.items():
        por_paciente[i].append(j)
        por_frasco[kk].append((i, j))
    for i in range(n):                                       # atribuição
        linha(1.0, 1.0, [(j, 1.0) for j in por_paciente[i]])
    for kk, (k, _) in enumerate(frascos):                    # capacidade
        linha(-inf, 0.0, [(j, d[i]) for i, j in por_frasco[kk]] + [(z_idx[kk], -tipos[k].capacidade)])
    if usar_tempo:
        for kk in range(m):
            for i, j in por_frasco[kk]:
                # tau_k + M x_ik <= t_i + M
                linha(-inf, t[i] + M, [(tau_idx[kk], 1.0), (j, M)])
                # -tau_k + M x_ik <= M + Delta - t_i
                linha(-inf, M + inst.bud - t[i], [(tau_idx[kk], -1.0), (j, M)])
        for kk in range(m):                                  # tau_k <= T_max z_k
            linha(-inf, 0.0, [(tau_idx[kk], 1.0), (z_idx[kk], -M)])
    if quebra_simetria:
        for kk in range(m - 1):
            if frascos[kk][0] == frascos[kk + 1][0]:
                linha(-inf, 0.0, [(z_idx[kk + 1], 1.0), (z_idx[kk], -1.0)])
    nrow = len(r_lo)

    h = highspy.Highs()
    h.setOptionValue("output_flag", bool(verbose))
    h.setOptionValue("time_limit", float(tempo_limite_s))
    h.setOptionValue("threads", int(threads))
    h.setOptionValue("random_seed", int(semente))
    h.setOptionValue("mip_rel_gap", 1e-6)
    h.addVars(ncol, np.array(col_lb), np.array(col_ub))
    h.changeColsCost(ncol, np.arange(ncol, dtype=np.int32), np.array(col_cost))
    h.changeColsIntegrality(ncol, np.arange(ncol, dtype=np.int32),
                            np.array([highspy.HighsVarType.kInteger if v else highspy.HighsVarType.kContinuous
                                      for v in integral]))
    h.addRows(nrow, np.array(r_lo), np.array(r_up), len(idx),
              np.array(starts, dtype=np.int32), np.array(idx, dtype=np.int32), np.array(val))

    # ---------------- warm start
    if solucao_inicial is not None:
        x0 = np.zeros(ncol)
        usados = {k: 0 for k in range(len(tipos))}
        base = {}
        pos = 0
        for kk, (k, c) in enumerate(frascos):
            if c == 0:
                base[k] = kk
        ok = True
        for f in sorted(solucao_inicial.frascos, key=lambda f: f.tipo):
            k = f.tipo
            if k not in base:
                ok = False; break
            kk = base[k] + usados[k]
            if kk >= m or frascos[kk][0] != k:
                ok = False; break
            usados[k] += 1
            x0[z_idx[kk]] = 1.0
            x0[tau_idx[kk]] = f.t_min
            for i in f.pacientes:
                x0[x_idx[(i, kk)]] = 1.0
        if ok:
            sol0 = highspy.HighsSolution()
            sol0.col_value = list(x0)
            sol0.value_valid = True
            h.setSolution(sol0)

    t0 = time.perf_counter()
    h.run()
    tempo = time.perf_counter() - t0
    status = h.modelStatusToString(h.getModelStatus())
    info = h.getInfo()
    tem_sol = info.primal_solution_status == 2  # kSolutionStatusFeasible
    custo = info.objective_function_value if tem_sol else None
    lb = info.mip_dual_bound if np.isfinite(info.mip_dual_bound) else None
    otimo = h.getModelStatus() == highspy.HighsModelStatus.kOptimal

    sol = None
    if tem_sol:
        xv = np.array(h.getSolution().col_value)
        sol = Solucao(inst)
        for kk, (k, _) in enumerate(frascos):
            if xv[z_idx[kk]] > 0.5:
                pac = [i for i, j2 in por_frasco[kk] if xv[j2] > 0.5]
                if pac:
                    f = sol.abrir(k)
                    for i in pac:
                        sol.inserir(i, f)
    return ResultadoMILP(status, custo, lb, info.mip_gap if tem_sol else None, tempo, otimo,
                         ncol, nrow, sol)
