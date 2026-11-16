"""Representação e geração de instâncias do TBPP-BUD.

Uma instância contém:
  * pacientes i com dose d_i (mg) e horário t_i (minutos desde a abertura do serviço);
  * tipos de frasco t com capacidade V_t (mg) e custo c_t (R$);
  * janela BUD Delta (minutos);
  * horizonte T_max (minutos).

Os horários são relativos ao início do expediente (por padrão, 8h00 = minuto 0).
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class TipoFrasco:
    capacidade: float  # mg
    custo: float       # R$


@dataclass
class Instancia:
    nome: str
    doses: list[float]
    horarios: list[float]
    tipos: list[TipoFrasco]
    bud: float                 # Delta, em minutos
    t_max: float               # horizonte, em minutos
    classe: str = ""
    semente: int | None = None
    meta: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    @property
    def n(self) -> int:
        return len(self.doses)

    def tipos_compativeis(self, i: int) -> list[int]:
        """Índices dos tipos de frasco com capacidade suficiente para a dose de i."""
        return [k for k, tp in enumerate(self.tipos) if tp.capacidade + 1e-9 >= self.doses[i]]

    def tipo_mais_barato_para(self, carga: float) -> int | None:
        """Tipo de menor custo cuja capacidade comporta a carga (None se nenhum)."""
        melhor, melhor_c = None, math.inf
        for k, tp in enumerate(self.tipos):
            if tp.capacidade + 1e-9 >= carga and tp.custo < melhor_c:
                melhor, melhor_c = k, tp.custo
        return melhor

    def validar(self) -> None:
        assert len(self.doses) == len(self.horarios), "doses e horários com tamanhos diferentes"
        cap_max = max(tp.capacidade for tp in self.tipos)
        for i, d in enumerate(self.doses):
            assert d > 0, f"dose não positiva no paciente {i}"
            assert d <= cap_max + 1e-9, (
                f"dose {d} do paciente {i} excede o maior frasco ({cap_max}); "
                "o modelo assume dose proveniente de um único frasco")
        for t in self.horarios:
            assert 0 <= t <= self.t_max, "horário fora do horizonte"

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d: dict) -> "Instancia":
        d = dict(d)
        d["tipos"] = [TipoFrasco(**tp) for tp in d["tipos"]]
        return Instancia(**d)

    def salvar(self, caminho: str | Path) -> None:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)

    @staticmethod
    def carregar(caminho: str | Path) -> "Instancia":
        with open(caminho, encoding="utf-8") as f:
            return Instancia.from_dict(json.load(f))


# ----------------------------------------------------------------------
# Gerador parametrizável
# ----------------------------------------------------------------------
TAMANHOS_PADRAO = [10, 25, 50, 100, 200, 500]


def gerar_instancia(n: int, bud_horas: float, semente: int, *, classe: str = "",
                    nome: str | None = None,
                    tamanhos_frasco: list[float] = TAMANHOS_PADRAO,
                    custo_por_mg: float = 50.0,
                    expediente_min: float = 600.0,
                    intervalo_agenda_min: float = 15.0,
                    dose_mg_m2: float = 50.0,
                    sc_media: float = 1.8, sc_desvio: float = 0.2,
                    sc_min: float = 1.3, sc_max: float = 2.4) -> Instancia:
    """Gera uma instância sintética.

    * Horários: sorteados uniformemente entre os slots da agenda
      (expediente de `expediente_min` minutos, slots de `intervalo_agenda_min`).
    * Doses: dose = dose_mg_m2 x superfície corporal (SC), com SC ~ Normal(sc_media, sc_desvio)
      truncada em [sc_min, sc_max]; arredondada para 1 mg. A dosagem por superfície
      corporal é a prática usual para antineoplásicos.
    * Frascos: tamanhos em `tamanhos_frasco` com custo proporcional (custo_por_mg x capacidade).
      Com 50 R$/mg, o frasco de 100 mg custa R$ 5.000,00, como no exemplo do texto.
    """
    rng = random.Random(semente)
    n_slots = int(expediente_min // intervalo_agenda_min)
    horarios = [rng.randint(0, n_slots) * intervalo_agenda_min for _ in range(n)]
    doses = []
    for _ in range(n):
        sc = min(sc_max, max(sc_min, rng.gauss(sc_media, sc_desvio)))
        doses.append(float(round(dose_mg_m2 * sc)))
    tipos = [TipoFrasco(float(v), float(custo_por_mg * v)) for v in tamanhos_frasco]
    inst = Instancia(
        nome=nome or f"{classe or 'inst'}_n{n}_bud{bud_horas:g}h_s{semente}",
        doses=doses, horarios=horarios, tipos=tipos,
        bud=bud_horas * 60.0, t_max=expediente_min, classe=classe, semente=semente,
        meta=dict(dose_mg_m2=dose_mg_m2, sc_media=sc_media, sc_desvio=sc_desvio,
                  custo_por_mg=custo_por_mg, intervalo_agenda_min=intervalo_agenda_min,
                  bud_horas=bud_horas))
    inst.validar()
    return inst


def exemplo_seis_pacientes(bud_horas: float = 6.0) -> Instancia:
    """Exemplo didático do texto: frascos de 100 mg a R$ 5.000,00; horários a partir das 8h00."""
    horarios_h = [8.5, 10.0, 11.5, 13.0, 14.5, 15.0]
    inst = Instancia(
        nome=f"exemplo6_bud{bud_horas:g}h",
        doses=[60.0, 35.0, 45.0, 50.0, 40.0, 25.0],
        horarios=[(h - 8.0) * 60.0 for h in horarios_h],
        tipos=[TipoFrasco(100.0, 5000.0)],
        bud=bud_horas * 60.0, t_max=600.0, classe="exemplo")
    inst.validar()
    return inst
