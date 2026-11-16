"""Heurísticas construtivas: sem compartilhamento (referência), FFD temporal e construção GRASP."""
from __future__ import annotations

import random

from .instancia import Instancia
from .solucao import Solucao


def ordem_ffd(inst: Instancia) -> list[int]:
    """Pacientes por dose decrescente, com desempate por horário crescente."""
    return sorted(range(inst.n), key=lambda i: (-inst.doses[i], inst.horarios[i], i))


def sem_compartilhamento(inst: Instancia) -> Solucao:
    """Cenário de referência C_ref: cada paciente abre o frasco mais barato que comporta sua dose."""
    s = Solucao(inst)
    for i in range(inst.n):
        k = s.abrir(inst.tipo_mais_barato_para(inst.doses[i]))
        s.inserir(i, k)
    return s


def ffd_temporal(inst: Instancia) -> Solucao:
    """First Fit Decreasing com teste de BUD: primeiro frasco aberto viável;
    se nenhum servir, abre o tipo mais barato que comporta a dose."""
    s = Solucao(inst)
    for i in ordem_ffd(inst):
        for k in range(len(s.frascos)):
            if s.cabe(i, k):
                s.inserir(i, k)
                break
        else:
            k = s.abrir(inst.tipo_mais_barato_para(inst.doses[i]))
            s.inserir(i, k)
    return s


def construir_grasp(inst: Instancia, alfa: float, rng: random.Random,
                    funcao_gulosa: str = "descrita") -> Solucao:
    """Construção gulosa randomizada (Seção 5.8).

    Para cada paciente (ordem FFD), os candidatos são:
      * frascos já abertos com capacidade residual e janela compatível;
      * a abertura de um novo frasco de cada tipo que comporta a dose.

    Função gulosa g(c):
      * "descrita": 0 para frasco aberto; c_t para abrir um frasco do tipo t
        (exatamente como no texto);
      * "residual": para frasco aberto, custo proporcional ao espaço que ficará ocioso
        (c_t x residual/V_t); para frasco novo, c_t. Diferencia frascos abertos entre si.

    RCL = {c : g(c) <= g_min + alfa (g_max - g_min)}; escolhe-se um candidato ao acaso.
    """
    s = Solucao(inst)
    tipos = inst.tipos
    for i in ordem_ffd(inst):
        cand: list[tuple[float, str, int]] = []
        for k, f in enumerate(s.frascos):
            if s.cabe(i, k):
                if funcao_gulosa == "residual":
                    tp = tipos[f.tipo]
                    resid = tp.capacidade - f.carga - inst.doses[i]
                    g = tp.custo * resid / tp.capacidade
                else:
                    g = 0.0
                cand.append((g, "aberto", k))
        for t in inst.tipos_compativeis(i):
            cand.append((tipos[t].custo, "novo", t))
        g_min = min(c[0] for c in cand)
        g_max = max(c[0] for c in cand)
        limiar = g_min + alfa * (g_max - g_min)
        rcl = [c for c in cand if c[0] <= limiar + 1e-9]
        _, natureza, idx = rng.choice(rcl)
        if natureza == "novo":
            idx = s.abrir(idx)
        s.inserir(i, idx)
    return s
