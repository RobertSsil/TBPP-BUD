"""Estrutura de solução do TBPP-BUD e verificador independente de viabilidade.

Uma solução é uma lista de frascos abertos. Cada frasco guarda seu tipo e o
conjunto de pacientes atendidos. Como as doses são eventos pontuais, um grupo de
pacientes é temporalmente viável se, e somente se,

        max(t_i) - min(t_i) <= Delta,

e o instante de abertura pode ser qualquer tau em [max(t_i) - Delta, min(t_i)].
Adota-se tau = min(t_i) (abertura no horário do primeiro paciente do frasco).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .instancia import Instancia

EPS = 1e-9


@dataclass
class Frasco:
    tipo: int
    pacientes: list[int] = field(default_factory=list)
    carga: float = 0.0
    t_min: float = float("inf")
    t_max: float = float("-inf")

    def copia(self) -> "Frasco":
        return Frasco(self.tipo, list(self.pacientes), self.carga, self.t_min, self.t_max)


class Solucao:
    """Solução com estruturas auxiliares para avaliação incremental."""

    def __init__(self, inst: Instancia):
        self.inst = inst
        self.frascos: list[Frasco] = []
        self.frasco_de: list[int] = [-1] * inst.n  # índice do frasco de cada paciente

    # ------------------------------------------------------------ cópia
    def copia(self) -> "Solucao":
        s = Solucao.__new__(Solucao)
        s.inst = self.inst
        s.frascos = [f.copia() for f in self.frascos]
        s.frasco_de = list(self.frasco_de)
        return s

    # ------------------------------------------------------------ métricas
    def custo(self) -> float:
        tipos = self.inst.tipos
        return sum(tipos[f.tipo].custo for f in self.frascos)

    def n_frascos(self) -> int:
        return len(self.frascos)

    def capacidade_aberta(self) -> float:
        tipos = self.inst.tipos
        return sum(tipos[f.tipo].capacidade for f in self.frascos)

    def sobra(self) -> float:
        return self.capacidade_aberta() - sum(self.inst.doses)

    def utilizacao(self) -> float:
        cap = self.capacidade_aberta()
        return 100.0 * sum(self.inst.doses) / cap if cap > 0 else 0.0

    def concentracao(self) -> float:
        """Critério secundário: soma de (carga_k / V_max)^2. Maior = doses concentradas
        em menos frascos (com o mesmo total de doses)."""
        vmax = max(tp.capacidade for tp in self.inst.tipos)
        return sum((f.carga / vmax) ** 2 for f in self.frascos)

    def chave(self) -> tuple[float, float]:
        """Avaliação lexicográfica: menor custo; em empate, maior concentração."""
        return (round(self.custo(), 6), -round(self.concentracao(), 9))

    # ------------------------------------------------------------ manipulação
    def abrir(self, tipo: int) -> int:
        self.frascos.append(Frasco(tipo))
        return len(self.frascos) - 1

    def inserir(self, i: int, k: int) -> None:
        f = self.frascos[k]
        f.pacientes.append(i)
        f.carga += self.inst.doses[i]
        t = self.inst.horarios[i]
        f.t_min = min(f.t_min, t)
        f.t_max = max(f.t_max, t)
        self.frasco_de[i] = k

    def recalcular(self, k: int) -> None:
        f = self.frascos[k]
        d, h = self.inst.doses, self.inst.horarios
        f.carga = sum(d[i] for i in f.pacientes)
        if f.pacientes:
            f.t_min = min(h[i] for i in f.pacientes)
            f.t_max = max(h[i] for i in f.pacientes)
        else:
            f.t_min, f.t_max = float("inf"), float("-inf")

    def remover_vazios(self) -> None:
        self.frascos = [f for f in self.frascos if f.pacientes]
        for k, f in enumerate(self.frascos):
            for i in f.pacientes:
                self.frasco_de[i] = k

    # ------------------------------------------------------------ testes
    def cabe(self, i: int, k: int) -> bool:
        """Paciente i pode entrar no frasco k (capacidade e BUD)?"""
        f = self.frascos[k]
        inst = self.inst
        if f.carga + inst.doses[i] > inst.tipos[f.tipo].capacidade + EPS:
            return False
        t = inst.horarios[i]
        return max(f.t_max, t) - min(f.t_min, t) <= inst.bud + EPS

    # ------------------------------------------------------------ saída
    def aberturas(self) -> list[float]:
        return [f.t_min for f in self.frascos]

    def to_dict(self) -> dict:
        tipos = self.inst.tipos
        return dict(
            custo=self.custo(), n_frascos=self.n_frascos(), sobra=self.sobra(),
            utilizacao=self.utilizacao(),
            frascos=[dict(tipo=f.tipo, capacidade=tipos[f.tipo].capacidade,
                          abertura=f.t_min, validade=f.t_min + self.inst.bud,
                          pacientes=sorted(f.pacientes), carga=f.carga)
                     for f in self.frascos])

    def __repr__(self) -> str:
        grupos = ", ".join("{" + ",".join(f"P{i+1}" for i in sorted(f.pacientes)) + "}"
                           for f in self.frascos)
        return f"Solucao(custo={self.custo():.2f}, frascos={self.n_frascos()}: {grupos})"


def verificar(sol: Solucao) -> list[str]:
    """Verificação independente (recalcula tudo do zero). Retorna lista de violações."""
    inst = sol.inst
    erros = []
    vistos = [0] * inst.n
    for k, f in enumerate(sol.frascos):
        if not f.pacientes:
            erros.append(f"frasco {k} aberto sem pacientes")
            continue
        cap = inst.tipos[f.tipo].capacidade
        carga = sum(inst.doses[i] for i in f.pacientes)
        if carga > cap + EPS:
            erros.append(f"frasco {k}: carga {carga} > capacidade {cap}")
        ts = [inst.horarios[i] for i in f.pacientes]
        tau = min(ts)
        if max(ts) - tau > inst.bud + EPS:
            erros.append(f"frasco {k}: amplitude {max(ts)-tau} > BUD {inst.bud}")
        if not (0 - EPS <= tau <= inst.t_max + EPS):
            erros.append(f"frasco {k}: abertura fora do horizonte")
        for i in f.pacientes:
            vistos[i] += 1
    for i, v in enumerate(vistos):
        if v != 1:
            erros.append(f"paciente {i} atendido {v} vezes")
    return erros
