"""Testes de correção. Rodar com:  python -m pytest -q   (ou  python tests/test_basico.py)

1. Exemplo de seis pacientes: 345 mg / 45 mg de sobra; ótimo = 3 frascos (BUD 6 h) e 5 (BUD 1 h).
2. Verificador detecta violações de capacidade, de BUD e de atribuição.
3. Em instâncias pequenas aleatórias, o MILP coincide com a força bruta (enumeração de
   todas as partições) e o GRASP-VNS nunca fica abaixo do ótimo nem gera solução inviável.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tbppbud.construtivo import ffd_temporal, sem_compartilhamento  # noqa: E402
from tbppbud.instancia import Instancia, TipoFrasco, exemplo_seis_pacientes  # noqa: E402
from tbppbud.metaheuristicas import grasp, grasp_vns, vns  # noqa: E402
from tbppbud.milp import resolver_milp  # noqa: E402
from tbppbud.solucao import Solucao, verificar  # noqa: E402


def particoes(itens):
    if not itens:
        yield []
        return
    primeiro, resto = itens[0], itens[1:]
    for p in particoes(resto):
        for k in range(len(p)):
            yield p[:k] + [[primeiro] + p[k]] + p[k + 1:]
        yield [[primeiro]] + p


def forca_bruta(inst: Instancia) -> float:
    melhor = float("inf")
    for p in particoes(list(range(inst.n))):
        custo = 0.0
        for bloco in p:
            ts = [inst.horarios[i] for i in bloco]
            if max(ts) - min(ts) > inst.bud + 1e-9:
                custo = float("inf"); break
            t = inst.tipo_mais_barato_para(sum(inst.doses[i] for i in bloco))
            if t is None:
                custo = float("inf"); break
            custo += inst.tipos[t].custo
        melhor = min(melhor, custo)
    return melhor


def test_exemplo_seis_pacientes():
    inst = exemplo_seis_pacientes(6)
    s = sem_compartilhamento(inst)
    assert s.sobra() == 345 and s.custo() == 30000 and abs(s.utilizacao() - 42.5) < 1e-9
    m = resolver_milp(inst, 60)
    assert m.otimo and m.custo == 15000 and m.solucao.sobra() == 45
    assert grasp_vns(inst, 1, dict(tempo_limite_s=5)).solucao.custo() == 15000
    inst1 = exemplo_seis_pacientes(1)
    assert resolver_milp(inst1, 60).custo == 25000  # BUD ativo: 5 frascos
    assert forca_bruta(inst1) == 25000


def test_verificador():
    inst = exemplo_seis_pacientes(6)
    s = Solucao(inst)
    k = s.abrir(0)
    for i in (0, 2):          # 60 + 45 = 105 > 100
        s.inserir(i, k)
    assert any("capacidade" in e for e in verificar(s))
    s = Solucao(inst)
    k = s.abrir(0)
    for i in (1, 5):          # 10h00 e 15h00 com BUD 1 h
        s.inserir(i, k)
    inst.bud = 60
    assert any("BUD" in e for e in verificar(s))
    assert any("atendido 0 vezes" in e for e in verificar(s))


def test_aleatorio_contra_forca_bruta():
    rng = random.Random(42)
    for rep in range(12):
        n = rng.randint(4, 7)
        tipos = [TipoFrasco(50, 2500), TipoFrasco(100, 5000), TipoFrasco(200, 9000)]
        inst = Instancia(nome=f"rand{rep}", doses=[float(rng.randint(10, 120)) for _ in range(n)],
                         horarios=[float(rng.randint(0, 40) * 15) for _ in range(n)],
                         tipos=tipos, bud=float(rng.choice([60, 120, 360])), t_max=600.0)
        inst.validar()
        otimo = forca_bruta(inst)
        m = resolver_milp(inst, 60)
        assert m.otimo and abs(m.custo - otimo) < 1e-6, (rep, m.custo, otimo)
        assert not verificar(m.solucao)
        for f in (grasp_vns, grasp, vns):
            r = f(inst, rep, dict(tempo_limite_s=3))
            assert not verificar(r.solucao)
            assert r.solucao.custo() >= otimo - 1e-6
        assert ffd_temporal(inst).custo() >= otimo - 1e-6


if __name__ == "__main__":
    test_exemplo_seis_pacientes(); test_verificador(); test_aleatorio_contra_forca_bruta()
    print("todos os testes passaram")
