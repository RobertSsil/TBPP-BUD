"""Vizinhanças (Swap, Shift, Merge, Consolidar, Resize), VND e perturbação (shaking).

Avaliação de uma solução: chave lexicográfica (custo, -concentração).
  * O custo é a função objetivo do modelo.
  * A concentração sum_k (carga_k / V_max)^2 é um critério secundário opcional
    (parâmetro `criterio_secundario`). Sem ele, Swap nunca altera a avaliação e Shift só
    melhora quando esvazia um frasco, porque o custo depende apenas dos frascos abertos.
    Com ele, movimentos que concentram doses em menos frascos são aceitos mesmo sem
    reduzir o custo imediatamente, criando oportunidades de Merge e Consolidar.

Vizinhanças:
  swap        troca dois pacientes de frascos diferentes
  shift       move um paciente para outro frasco (fecha a origem se ela esvaziar)
  merge       move todo o conteúdo de um frasco para outro frasco já aberto
  consolidar  junta vários frascos temporalmente compatíveis em UM frasco novo do tipo
              mais barato que comporta a soma (generaliza o Merge para tipos maiores)
  resize      troca o tipo de um frasco pelo tipo mais barato que ainda comporta a carga

Todas as vizinhanças preservam capacidade e BUD; nenhuma solução inviável é aceita.
"""
from __future__ import annotations

import random
import time

from .solucao import Solucao, EPS

VIZINHANCAS_DISPONIVEIS = ("swap", "shift", "merge", "consolidar", "resize")


def _span_com(s: Solucao, k: int, entra: int | None = None, sai: int | None = None) -> float:
    """Amplitude temporal do frasco k após (opcionalmente) retirar `sai` e inserir `entra`."""
    h = s.inst.horarios
    ts = [h[p] for p in s.frascos[k].pacientes if p != sai]
    if entra is not None:
        ts.append(h[entra])
    return (max(ts) - min(ts)) if ts else 0.0


_ESCALA = [1.0]  # V_max da instância corrente (definido em Busca.vnd)


def _quad(carga: float, cap: float) -> float:
    """Contribuição de um frasco ao critério secundário (independe do tipo)."""
    return (carga / _ESCALA[0]) ** 2


class Busca:
    def __init__(self, vizinhancas=("merge", "consolidar", "shift", "resize", "swap"),
                 criterio_secundario: bool = True, estrategia: str = "first",
                 rng: random.Random | None = None, prazo: float | None = None):
        for v in vizinhancas:
            assert v in VIZINHANCAS_DISPONIVEIS, f"vizinhança desconhecida: {v}"
        assert estrategia in ("first", "best")
        self.vizinhancas = list(vizinhancas)
        self.sec = criterio_secundario
        self.estrategia = estrategia
        self.rng = rng or random.Random(0)
        self.prazo = prazo  # time.perf_counter() limite (None = sem limite)
        self.contagem = {v: 0 for v in VIZINHANCAS_DISPONIVEIS}  # movimentos aceitos

    # -------------------------------------------------------------- utilidades
    def _esgotado(self) -> bool:
        return self.prazo is not None and time.perf_counter() >= self.prazo

    def _melhora(self, dcusto: float, dquad: float) -> bool:
        if dcusto < -EPS:
            return True
        if self.sec and abs(dcusto) <= EPS and dquad > 1e-12:
            return True
        return False

    @staticmethod
    def _valor(dcusto: float, dquad: float) -> tuple[float, float]:
        return (dcusto, -dquad)

    def _ordem(self, m: int) -> list[int]:
        idx = list(range(m))
        if self.estrategia == "first":
            self.rng.shuffle(idx)
        return idx

    # -------------------------------------------------------------- Shift
    def _shift(self, s: Solucao):
        inst = s.inst
        tipos, d, h = inst.tipos, inst.doses, inst.horarios
        melhor = None
        pacientes = self._ordem(inst.n)
        destinos = self._ordem(len(s.frascos))
        for i in pacientes:
            a = s.frasco_de[i]
            fa = s.frascos[a]
            cap_a = tipos[fa.tipo].capacidade
            esvazia = len(fa.pacientes) == 1
            for b in destinos:
                if b == a:
                    continue
                if not s.cabe(i, b):
                    continue
                fb = s.frascos[b]
                cap_b = tipos[fb.tipo].capacidade
                dcusto = -tipos[fa.tipo].custo if esvazia else 0.0
                dquad = (_quad(fb.carga + d[i], cap_b) - _quad(fb.carga, cap_b)
                         + (0.0 if esvazia else _quad(fa.carga - d[i], cap_a))
                         - _quad(fa.carga, cap_a))
                if self._melhora(dcusto, dquad):
                    mov = (self._valor(dcusto, dquad), ("shift", i, a, b))
                    if self.estrategia == "first":
                        return mov
                    if melhor is None or mov[0] < melhor[0]:
                        melhor = mov
        return melhor

    # -------------------------------------------------------------- Swap
    def _swap(self, s: Solucao):
        inst = s.inst
        tipos, d = inst.tipos, inst.doses
        if not self.sec:
            return None  # sem critério secundário, o Swap nunca altera a avaliação
        melhor = None
        fr = self._ordem(len(s.frascos))
        for ia, a in enumerate(fr):
            fa = s.frascos[a]
            cap_a = tipos[fa.tipo].capacidade
            for b in fr[ia + 1:]:
                fb = s.frascos[b]
                cap_b = tipos[fb.tipo].capacidade
                for i in fa.pacientes:
                    for j in fb.pacientes:
                        if abs(d[i] - d[j]) <= EPS:
                            continue
                        na = fa.carga - d[i] + d[j]
                        nb = fb.carga - d[j] + d[i]
                        if na > cap_a + EPS or nb > cap_b + EPS:
                            continue
                        dquad = (_quad(na, cap_a) + _quad(nb, cap_b)
                                 - _quad(fa.carga, cap_a) - _quad(fb.carga, cap_b))
                        if not self._melhora(0.0, dquad):
                            continue
                        if _span_com(s, a, entra=j, sai=i) > inst.bud + EPS:
                            continue
                        if _span_com(s, b, entra=i, sai=j) > inst.bud + EPS:
                            continue
                        mov = (self._valor(0.0, dquad), ("swap", i, a, j, b))
                        if self.estrategia == "first":
                            return mov
                        if melhor is None or mov[0] < melhor[0]:
                            melhor = mov
        return melhor

    # -------------------------------------------------------------- Merge
    def _merge(self, s: Solucao):
        inst = s.inst
        tipos = inst.tipos
        melhor = None
        fr = self._ordem(len(s.frascos))
        for a in fr:
            fa = s.frascos[a]
            for b in fr:
                if a == b:
                    continue
                fb = s.frascos[b]
                cap_b = tipos[fb.tipo].capacidade
                if fa.carga + fb.carga > cap_b + EPS:
                    continue
                if max(fa.t_max, fb.t_max) - min(fa.t_min, fb.t_min) > inst.bud + EPS:
                    continue
                dcusto = -tipos[fa.tipo].custo
                dquad = (_quad(fa.carga + fb.carga, cap_b) - _quad(fb.carga, cap_b)
                         - _quad(fa.carga, tipos[fa.tipo].capacidade))
                if self._melhora(dcusto, dquad):
                    mov = (self._valor(dcusto, dquad), ("merge", a, b))
                    if self.estrategia == "first":
                        return mov
                    if melhor is None or mov[0] < melhor[0]:
                        melhor = mov
        return melhor

    # -------------------------------------------------------------- Consolidar
    def _consolidar(self, s: Solucao):
        """Para cada frasco-âncora a e cada tipo t maior que o de a, abre (virtualmente) um
        frasco novo do tipo t na janela [t_min(a), t_min(a) + Delta] e o preenche, em ordem
        decrescente de carga, com frascos inteiros cuja amplitude cabe nessa janela.
        Delta custo = c_t - soma dos custos dos frascos absorvidos."""
        inst = s.inst
        tipos = inst.tipos
        fr = s.frascos
        if len(fr) < 2:
            return None
        ordem_carga = sorted(range(len(fr)), key=lambda k: -fr[k].carga)
        melhor = None
        for a in self._ordem(len(fr)):
            fa = fr[a]
            for inicio in {fa.t_min, max(0.0, fa.t_max - inst.bud)}:
                fim = inicio + inst.bud
                if fa.t_min < inicio - EPS or fa.t_max > fim + EPS:
                    continue
                for t, tp in enumerate(tipos):
                    if tp.capacidade <= tipos[fa.tipo].capacidade + EPS:
                        continue
                    carga, custo_abs, grupo, quad_antes = fa.carga, tipos[fa.tipo].custo, [a], _quad(fa.carga, 0)
                    for b in ordem_carga:
                        if b == a:
                            continue
                        fb = fr[b]
                        if fb.t_min < inicio - EPS or fb.t_max > fim + EPS:
                            continue
                        if carga + fb.carga > tp.capacidade + EPS:
                            continue
                        carga += fb.carga
                        custo_abs += tipos[fb.tipo].custo
                        quad_antes += _quad(fb.carga, 0)
                        grupo.append(b)
                    if len(grupo) < 2:
                        continue
                    dcusto = tp.custo - custo_abs
                    dquad = _quad(carga, 0) - quad_antes
                    if self._melhora(dcusto, dquad):
                        mov = (self._valor(dcusto, dquad), ("consolidar", tuple(grupo), t))
                        if self.estrategia == "first":
                            return mov
                        if melhor is None or mov[0] < melhor[0]:
                            melhor = mov
        return melhor

    # -------------------------------------------------------------- Resize
    def _resize(self, s: Solucao):
        """Troca o tipo de um frasco pelo tipo mais barato que ainda comporta sua carga."""
        inst = s.inst
        tipos = inst.tipos
        melhor = None
        for k in self._ordem(len(s.frascos)):
            f = s.frascos[k]
            t = inst.tipo_mais_barato_para(f.carga)
            if t is None or t == f.tipo:
                continue
            dcusto = tipos[t].custo - tipos[f.tipo].custo
            dquad = _quad(f.carga, tipos[t].capacidade) - _quad(f.carga, tipos[f.tipo].capacidade)
            if self._melhora(dcusto, dquad):
                mov = (self._valor(dcusto, dquad), ("resize", k, t))
                if self.estrategia == "first":
                    return mov
                if melhor is None or mov[0] < melhor[0]:
                    melhor = mov
        return melhor

    # -------------------------------------------------------------- aplicação
    @staticmethod
    def _aplicar(s: Solucao, mov) -> None:
        tipo = mov[0]
        if tipo == "shift":
            _, i, a, b = mov
            s.frascos[a].pacientes.remove(i)
            s.recalcular(a)
            s.inserir(i, b)
            if not s.frascos[a].pacientes:
                s.remover_vazios()
        elif tipo == "swap":
            _, i, a, j, b = mov
            s.frascos[a].pacientes.remove(i)
            s.frascos[b].pacientes.remove(j)
            s.frascos[a].pacientes.append(j)
            s.frascos[b].pacientes.append(i)
            s.frasco_de[i], s.frasco_de[j] = b, a
            s.recalcular(a)
            s.recalcular(b)
        elif tipo == "merge":
            _, a, b = mov
            for p in list(s.frascos[a].pacientes):
                s.inserir(p, b)
            s.frascos[a].pacientes = []
            s.remover_vazios()
        elif tipo == "consolidar":
            _, grupo, t = mov
            novo = s.abrir(t)
            for g in grupo:
                for p in list(s.frascos[g].pacientes):
                    s.inserir(p, novo)
                s.frascos[g].pacientes = []
            s.remover_vazios()
        elif tipo == "resize":
            _, k, t = mov
            s.frascos[k].tipo = t
        else:
            raise ValueError(tipo)

    # -------------------------------------------------------------- VND
    def vnd(self, s: Solucao) -> Solucao:
        """Variable Neighborhood Descent: percorre as vizinhanças na ordem dada e
        volta à primeira sempre que encontra melhora."""
        _ESCALA[0] = max(tp.capacidade for tp in s.inst.tipos)
        funcs = {"swap": self._swap, "shift": self._shift, "merge": self._merge,
                 "consolidar": self._consolidar, "resize": self._resize}
        j = 0
        while j < len(self.vizinhancas) and not self._esgotado():
            nome = self.vizinhancas[j]
            mov = funcs[nome](s)
            if mov is not None:
                self._aplicar(s, mov[1])
                self.contagem[nome] += 1
                j = 0
            else:
                j += 1
        return s

    # -------------------------------------------------------------- shaking
    def perturbar(self, s: Solucao, k: int) -> Solucao:
        """Realoca k pacientes aleatórios para frascos aleatórios viáveis (diferentes do atual).
        Se nenhum frasco aberto for viável, abre um novo frasco do tipo mais barato compatível."""
        s = s.copia()
        inst = s.inst
        for _ in range(k):
            i = self.rng.randrange(inst.n)
            a = s.frasco_de[i]
            destinos = [b for b in range(len(s.frascos)) if b != a and s.cabe(i, b)]
            s.frascos[a].pacientes.remove(i)
            s.recalcular(a)
            if destinos:
                s.inserir(i, self.rng.choice(destinos))
            else:
                b = s.abrir(inst.tipo_mais_barato_para(inst.doses[i]))
                s.inserir(i, b)
            if not s.frascos[a].pacientes:
                s.remover_vazios()
        return s
