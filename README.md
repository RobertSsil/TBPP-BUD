# TBPP-BUD — Compartilhamento de frascos de quimioterápicos com restrição de BUD

Implementação completa do TCC *"Otimização do compartilhamento de frascos de quimioterápicos
com restrições de estabilidade — Análise do modelo TBPP-BUD e da metaheurística GRASP-VNS"*
(UERN, Ciência da Computação).

O pacote contém:
- o modelo exato (MILP, resolvido com o HiGHS);
- as metaheurísticas GRASP, VNS e GRASP-VNS;
- as linhas de base (sem compartilhamento e FFD temporal);
- o gerador de instâncias sintéticas;
- a calibração de parâmetros;
- o estudo de ablação;
- os scripts que geram as tabelas e figuras do Capítulo 6.

A organização segue o Apêndice B do texto.

```
config/        experimento.json (delineamento e parâmetros); parametros_calibrados.json (gerado)
src/tbppbud/   implementação
  instancia.py        instâncias e gerador sintético
  solucao.py          estrutura de solução + verificador independente de viabilidade
  construtivo.py      sem compartilhamento (C_ref), FFD temporal, construção GRASP
  busca.py            vizinhanças Swap, Shift, Merge, Consolidar, Resize; VND; shaking
  metaheuristicas.py  GRASP, VNS, GRASP-VNS
  milp.py             modelo MILP (Seções 5.2–5.6) no HiGHS
scripts/       gerar_instancias, executar_experimentos, calibrar, exemplo_seis_pacientes,
               registrar_ambiente
analysis/      analisar_resultados.py (tabelas LaTeX/CSV, figuras, testes de Wilcoxon)
instances/     teste/ (90 instâncias) e calibracao/ (18), geradas pelo script
results/       saídas brutas por instância e semente, e results/analise/
tests/         testes de correção (inclui comparação com força bruta)
```

## Instalação

Requer Python 3.10 ou superior (o texto usa 3.12).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q          # deve terminar com "3 passed"
```

## Passo a passo da reprodução

```bash
python scripts/registrar_ambiente.py        # 1. grava environment.txt
python scripts/gerar_instancias.py          # 2. 90 instâncias de teste + 18 de calibração
python scripts/exemplo_seis_pacientes.py    # 3. exemplo da Seção 6.1 (BUD 6, 2, 1,5 e 1 h)
python scripts/calibrar.py                  # 4. calibração -> config/parametros_calibrados.json
python scripts/executar_experimentos.py --so-milp --processos 4   # 5a. MILP (pode ser paralelo)
python scripts/executar_experimentos.py --sem-milp                # 5b. heurísticas (sequencial)
python scripts/executar_experimentos.py --ablacao                 # 6. ablação (opcional)
python analysis/analisar_resultados.py      # 7. tabelas e figuras em results/analise/
```

Para um **teste rápido**, que leva poucos minutos e não serve para o texto:

```bash
python scripts/executar_experimentos.py --tempo-heur 5 --tempo-milp 20 --sementes 1 2 --max-instancias 6
python analysis/analisar_resultados.py
```

A execução é **retomável**: se for interrompida, rode o mesmo comando de novo e o que já foi feito é pulado.

### Tempo estimado da execução completa

Os tempos valem para a configuração padrão: 10 sementes, 60 s por heurística e MILP com 3.600 s.

- **MILP:** as instâncias pequenas resolvem em segundos. Médias e grandes tendem a bater o limite de
  3.600 s, o que dá cerca de 60 h no total se rodar em sequência. Rodar com `--processos 4` divide esse tempo por 4.
- **Heurísticas:** são 3 métodos × 10 sementes por instância, com até 60 s cada. Isso dá cerca de 30 min
  por instância grande e algumas horas no total.

Para medir tempo de forma justa, rode as heurísticas com `--processos 1`, ou deixe um núcleo
físico livre para cada processo, e com o computador sem outras cargas.

Se o prazo apertar, reduza `milp.tempo_limite_s` (por exemplo, para 600) ou o número de sementes em
`config/experimento.json`, e **informe o valor usado no texto**.

## Correspondência com o texto e decisões de implementação

As escolhas abaixo detalham ou corrigem pontos que o texto deixava em aberto. Elas precisam
ser descritas no TCC (Capítulos 4 e 5).

| Tema | Implementação |
|---|---|
| Instâncias (4.4) | n uniforme na faixa da classe; horários em slots de 15 min num expediente de 10 h; dose = 50 mg/m² × superfície corporal, com SC ~ N(1,8; 0,2) truncada em [1,3; 2,4]; frascos de 10, 25, 50, 100, 200 e 500 mg com custo de R$ 50/mg (o de 100 mg custa R$ 5.000, como no exemplo). 10 instâncias por classe × BUD. |
| Conjunto de calibração | 2 instâncias por classe × BUD, com sementes diferentes das de teste. |
| Abertura do frasco τ | Como as doses são pontuais, um grupo é viável se e só se max tᵢ − min tᵢ ≤ Δ. Adota-se τ = min tᵢ. |
| Cenário de referência C_ref (4.5) | Sem compartilhamento: cada paciente abre o frasco mais barato que comporta sua dose. |
| MILP (5.2–5.6) | HiGHS. M = T_max. Cópias por tipo limitadas a min(#doses que cabem, ⌊UB/c_t⌋), com UB = FFD. Quebra de simetria z_k ≥ z_{k+1}. Warm start com o FFD. Com BUD ≥ horizonte (24 h), as restrições temporais são omitidas por serem redundantes. |
| Limite inferior (gap) | Ótimo, se provado. Caso contrário, max(limite dual do HiGHS, LB volumétrico), arredondado para cima ao múltiplo do MDC dos custos. |
| Construção GRASP (5.8) | Ordem FFD (dose decrescente, depois horário). A RCL é de **candidatos de alocação** (frascos abertos viáveis e abertura de cada tipo compatível). Função gulosa "descrita": 0 para frasco aberto e c_t para frasco novo. Existe a variante "residual". |
| Vizinhanças (5.9) | Swap, Shift e Merge como no texto, mais duas vizinhanças necessárias quando há frascos de tamanhos diferentes: **Consolidar** (junta vários frascos num frasco novo de tipo maior) e **Resize** (troca um frasco pelo tipo mais barato que comporta a carga). |
| Critério de aceitação | Lexicográfico: menor custo e, em empate, maior concentração Σ(carga/V_max)². Sem esse critério, o Swap nunca melhora a avaliação. Desligue com `criterio_secundario=false`. |
| VND | Primeira melhora em ordem aleatória (`estrategia="first"`) ou melhor melhora (`"best"`). Ordem padrão: merge, consolidar, shift, resize, swap. |
| VNS | VNS básico: o shaking N_k realoca k pacientes, k = 1…k_max (k_max = "intensidade de shaking"). Aceita só se melhorar ("move-or-not"). Para após `limite_estagnacao` iterações sem melhora. |
| GRASP isolado | Construção + VND, sem shaking. |
| VNS isolado | FFD temporal + VNS, reiniciado até esgotar o orçamento. |
| Orçamento igual | GRASP e VNS isolados recebem o mesmo tempo de parede que o GRASP-VNS usou naquela instância e semente. |
| Ablação | Variantes sem Swap, sem Shift, sem Merge e sem Consolidar, além da variante "descrito_texto" (só Swap, Shift e Merge). |

Durante o desenvolvimento, um teste com n = 20 mostrou o motivo das vizinhanças extras: o ótimo
usa frascos de 500 mg, que juntam 5 ou 6 doses. Swap, Shift e Merge sozinhos não chegam a essas
soluções, porque só movem doses entre frascos que já existem. A variante "descrito_texto" da
ablação mede esse efeito.

## Saídas principais (`results/analise/`)

- **`tab_desempenho_classe.tex`:** gap (média, DP, mínimo, mediana, máximo) e tempos por classe. Substitui a tabela da Seção 6.2.
- **`tab_classe_bud.tex`:** os mesmos indicadores, mais economia e utilização, por classe e BUD.
- **`tab_economia_bud.tex`:** economia por BUD (Seção 6.3).
- **`tab_comparacao_metodos.tex`:** GRASP-VNS × GRASP × VNS × FFD, com vitórias/empates/derrotas e p-valor de Wilcoxon.
- **`tab_ablacao.tex`:** contribuição das vizinhanças (Seção 6.4).
- **`tab_por_instancia.tex`:** resultados por instância, para um apêndice.
- **Figuras:** `fig_gap_tempo_classe.pdf`, `fig_economia_bud.pdf` e `fig_comparacao_metodos.pdf`.
- **`resumo.txt`:** visão geral em texto.

As tabelas `.tex` usam `booktabs` e o comando `\fonte{}` já definido no `main.tex` do TCC.
Para usá-las, basta `\input{tab_desempenho_classe.tex}`.
# TBPP-BUD — Compartilhamento de frascos de quimioterápicos com restrição de BUD

Código, instâncias e resultados do Trabalho de Conclusão de Curso
*"Otimização do compartilhamento de frascos de quimioterápicos com restrições de estabilidade:
análise do modelo TBPP-BUD e da metaheurística GRASP-VNS"*
(Robert Danilo Santos da Silva — Ciência da Computação, UERN, 2026; orientação: Prof. Dr. Dario José Aloise).

Este repositório contém a versão exata usada nos experimentos da monografia (release `v1.0-tcc`),
incluindo os resultados brutos de todas as execuções.

## Conteúdo

- **Modelo exato:** MILP do TBPP-BUD, resolvido com o HiGHS.
- **Metaheurística:** GRASP-VNS com cinco vizinhanças (Swap, Shift, Merge, Consolidar e Resize).
- **Referências:** cenário sem compartilhamento e FFD temporal.
- **Variantes implementadas, mas não usadas na execução reportada:** GRASP isolado, VNS isolado e estudo de ablação.
- **Ferramentas:** gerador de instâncias sintéticas, calibração de parâmetros, verificador independente de viabilidade e scripts de análise.

```
config/        experimento.json (delineamento) e parametros_calibrados.json (resultado da calibração)
src/tbppbud/   implementação
  instancia.py        instâncias e gerador sintético
  solucao.py          estrutura de solução e verificador de viabilidade
  construtivo.py      sem compartilhamento, FFD temporal e construção GRASP
  busca.py            vizinhanças, VND e shaking
  metaheuristicas.py  GRASP, VNS e GRASP-VNS
  milp.py             modelo MILP (HiGHS)
scripts/       geração de instâncias, calibração, execução dos experimentos, exemplo de seis pacientes
analysis/      tabelas e figuras do Capítulo 6
instances/     90 instâncias de teste e 18 de calibração (JSON)
results/       resultados por instância e semente, soluções, configuração usada e análise
tests/         testes de correção (inclui comparação com enumeração completa)
*.log          registros da execução oficial
```

## Configuração usada nos experimentos da monografia

| Item | Valor |
|---|---|
| Instâncias | 90 de teste (3 classes × 3 janelas BUD × 10) e 18 de calibração, com sementes distintas |
| Métodos avaliados | sem compartilhamento, FFD temporal, MILP e GRASP-VNS |
| GRASP-VNS | 10 sementes por instância, até 60 s por execução |
| MILP | HiGHS 1.16.0, limite de 1.800 s, 1 thread, solução inicial do FFD |
| Calibração | 3 valores para cada um de 4 parâmetros, 1 passada, 3 sementes; valores finais em `config/parametros_calibrados.json` (α = 0,5; 500 iterações; estagnação 35; k_max = 3) |
| Paralelismo | GRASP-VNS em 10 processos de uma thread; MILP em 1 processo por limitação de RAM; fases em sequência |
| Ambiente | Acer Nitro 5, Intel Core i5-13420H (8 núcleos, 12 lógicos), 8 GB DDR5, Windows 11 Home, Python 3.11.0rc2 |

Por limitação de tempo, as comparações com GRASP e VNS isolados e a ablação não fizeram parte
da execução reportada. Elas podem ser executadas com o código deste repositório (ver abaixo).

## Principais resultados

| Classe | Ótimos provados pelo MILP | Gap médio do GRASP-VNS | Gap médio do FFD |
|---|---|---|---|
| Pequena (10–30 pacientes) | 30/30 | 0,00% | 2,78% |
| Média (31–100) | 17/30 | 0,62% | 8,95% |
| Grande (101–200) | 0/30 | 0,80% (contra limite inferior) | 10,79% |

Há solução ótima conhecida em 62 das 90 instâncias. A discussão completa, incluindo o efeito do BUD
e a dependência da economia em relação ao catálogo de frascos, está no Capítulo 6 da monografia.
Os números são gerados por `analysis/analisar_resultados.py` a partir de `results/`.

## Instalação

Requer Python 3.10 ou superior.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows (Git Bash): source .venv/Scripts/activate
pip install -r requirements.txt
export PYTHONUTF8=1
python -m pytest -q                # deve terminar com "3 passed"
```

## Reprodução

```bash
python scripts/registrar_ambiente.py       # grava environment.txt
python scripts/gerar_instancias.py         # 90 instâncias de teste e 18 de calibração
python scripts/exemplo_seis_pacientes.py   # exemplo de seis pacientes (BUD de 6, 2, 1,5 e 1 h)
bash rodar_tudo.sh                         # calibração, MILP, GRASP-VNS e análise
```

As instâncias são geradas de forma determinística a partir das sementes de `config/experimento.json`;
os arquivos em `instances/` são os mesmos usados na monografia.

A execução completa levou cerca de 28 horas na máquina descrita acima, a maior parte no MILP.
Ela é retomável: se for interrompida, basta rodar o mesmo comando de novo, e o que já foi feito é pulado.
Para apenas recalcular tabelas e figuras a partir dos resultados existentes:

```bash
python analysis/analisar_resultados.py     # saída em results/analise/
```

### Dicas para Windows (Git Bash)

- Mantenha o computador na tomada, com a suspensão desativada, e não feche a janela do Git Bash durante a execução.
- Para interromper, use `taskkill //F //IM python.exe` em outro terminal; o Ctrl+C nem sempre chega ao Python quando a saída passa pelo `tee`.
- Não execute duas cópias ao mesmo tempo: os processos disputariam CPU e os tempos medidos ficariam distorcidos.

## Experimentos complementares (não incluídos na monografia)

Em `config/experimento.json`:

- **GRASP e VNS isolados:** defina `"metodos": ["GRASP-VNS", "GRASP", "VNS"]` e rode
  `python scripts/executar_experimentos.py --sem-milp`. As execuções do GRASP-VNS já existentes são reaproveitadas,
  e os dois métodos recebem o mesmo tempo que o GRASP-VNS usou em cada instância e semente.
- **Ablação das vizinhanças:** defina `"ablacao": {"executar": true, ...}` e rode
  `python scripts/executar_experimentos.py --ablacao`.

Depois, rode `python analysis/analisar_resultados.py` para incluir as novas comparações e o teste de Wilcoxon.

## Decisões de implementação

| Tema | Implementação |
|---|---|
| Instâncias | n uniforme na faixa da classe; horários em intervalos de 15 min num expediente de 10 h; dose = 50 mg/m² × superfície corporal, com SC ~ N(1,8; 0,2) truncada em [1,3; 2,4]; frascos de 10 a 500 mg a R$ 50/mg |
| Abertura do frasco | um grupo é viável se e só se max tᵢ − min tᵢ ≤ Δ; adota-se τ = min tᵢ |
| Referência da economia | sem compartilhamento: cada paciente abre o frasco mais barato que comporta sua dose |
| MILP | M = T_max; cópias por tipo limitadas a min(#doses que cabem, ⌊UB/c_t⌋), com UB = FFD; quebra de simetria z_k ≥ z_{k+1}; restrições temporais omitidas quando Δ ≥ horizonte |
| Limite inferior (gap) | ótimo, se provado; senão, max(limite dual do HiGHS, limite volumétrico), arredondado ao múltiplo do MDC dos custos |
| Construção GRASP | ordem por dose decrescente; RCL de candidatos de alocação (frascos abertos viáveis e abertura de cada tipo compatível) |
| Vizinhanças | Swap, Shift e Merge, mais Consolidar (junta vários frascos num frasco novo de tipo maior) e Resize (troca para o tipo mais barato que comporta a carga) |
| Critério de aceitação | lexicográfico: menor custo; em empate, maior concentração Σ(carga/V_max)² |
| VND | primeira melhora, em ordem aleatória; ordem Merge, Consolidar, Shift, Resize, Swap |
| VNS | shaking N_k realoca k pacientes (k = 1…k_max); aceita só se melhorar; para após o limite de estagnação |

## Licença

Distribuído sob a licença MIT (arquivo `LICENSE`).

## Como citar

SILVA, R. D. S. da. *Otimização do compartilhamento de frascos de quimioterápicos com restrições
de estabilidade: análise do modelo TBPP-BUD e da metaheurística GRASP-VNS*. Trabalho de Conclusão
de Curso (Bacharelado em Ciência da Computação) — Universidade do Estado do Rio Grande do Norte, Mossoró, 2026.