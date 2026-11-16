"""tbppbud — Compartilhamento de frascos de quimioterápicos com restrição de BUD.

Módulos:
  instancia        instâncias e gerador sintético
  solucao          estrutura de solução e verificador de viabilidade
  construtivo      sem compartilhamento, FFD temporal, construção GRASP
  busca            vizinhanças Swap/Shift/Merge/Resize, VND e shaking
  metaheuristicas  GRASP, VNS e GRASP-VNS
  milp             modelo exato (HiGHS)
"""
__version__ = "1.0.0"
