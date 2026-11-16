#!/usr/bin/env bash
# Protocolo acelerado: calibração reduzida -> MILP -> GRASP-VNS -> ablação opcional -> análise.
# Uso (Git Bash, com o .venv ativado):   bash rodar_tudo.sh [processos]
# Padrão: paralelismo.processos em config/experimento.json (configurado como 10).
# Pode ser interrompido e rodado de novo: o que já foi feito é pulado.
set -o pipefail
export PYTHONUTF8=1
P=${1:-$(python -c 'import json; print(json.load(open("config/experimento.json", encoding="utf-8"))["paralelismo"]["processos"])')}
inicio=$(date +%s)
etapa () { echo; echo "=== $1 — $(date '+%d/%m %H:%M') (decorrido: $(( ($(date +%s)-inicio)/60 )) min) ==="; }

if [ ! -f config/parametros_calibrados.json ]; then
  etapa "1/5 CALIBRAÇÃO"
  rm -f results/calibracao.csv
  python -u scripts/calibrar.py --processos "$P" 2>&1 | tee calibracao.log || exit 1
else
  etapa "1/5 CALIBRAÇÃO já feita (config/parametros_calibrados.json) — pulando"
fi
etapa "2/5 MILP"
python -u scripts/executar_experimentos.py --so-milp  --processos "$P" 2>&1 | tee -a milp.log        || exit 1
etapa "3/5 HEURÍSTICAS"
python -u scripts/executar_experimentos.py --sem-milp --processos "$P" 2>&1 | tee -a heuristicas.log || exit 1
if python -c 'import json,sys; sys.exit(0 if json.load(open("config/experimento.json", encoding="utf-8"))["ablacao"]["executar"] else 1)'; then
  etapa "4/5 ABLAÇÃO"
  python -u scripts/executar_experimentos.py --ablacao --processos "$P" 2>&1 | tee -a ablacao.log || exit 1
else
  etapa "4/5 ABLAÇÃO desativada pela configuração — pulando"
fi
etapa "5/5 ANÁLISE"
python analysis/analisar_resultados.py 2>&1 | tee analise.log || exit 1
etapa "=== TUDO CONCLUÍDO ==="
