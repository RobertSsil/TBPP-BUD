# Exemplo de seis pacientes


## BUD = 6 h

| Método | Frascos | Custo (R$) | Sobra (mg) | Utilização (%) | Agrupamento |
|---|---|---|---|---|---|
| Sem compartilhamento | 6 | 30.000,00 | 345 | 42.5 | {P1} {P2} {P3} {P4} {P5} {P6} |
| FFD temporal | 3 | 15.000,00 | 45 | 85.0 | {P1,P5} {P2,P6} {P3,P4} |
| GRASP | 3 | 15.000,00 | 45 | 85.0 | {P1,P5} {P2,P6} {P3,P4} |
| VNS | 3 | 15.000,00 | 45 | 85.0 | {P1,P5} {P2,P6} {P3,P4} |
| GRASP-VNS | 3 | 15.000,00 | 45 | 85.0 | {P1,P5} {P2,P6} {P3,P4} |
| MILP (ótimo) | 3 | 15.000,00 | 45 | 85.0 | {P1} {P2,P5,P6} {P3,P4} |

Janelas da solução do MILP: {P2,P5,P6} 10h00–16h00; {P1} 8h30–14h30; {P3,P4} 11h30–17h30

## BUD = 2 h

| Método | Frascos | Custo (R$) | Sobra (mg) | Utilização (%) | Agrupamento |
|---|---|---|---|---|---|
| Sem compartilhamento | 6 | 30.000,00 | 345 | 42.5 | {P1} {P2} {P3} {P4} {P5} {P6} |
| FFD temporal | 3 | 15.000,00 | 45 | 85.0 | {P1,P2} {P3,P4} {P5,P6} |
| GRASP | 3 | 15.000,00 | 45 | 85.0 | {P1,P2} {P3,P4} {P5,P6} |
| VNS | 3 | 15.000,00 | 45 | 85.0 | {P1,P2} {P3,P4} {P5,P6} |
| GRASP-VNS | 3 | 15.000,00 | 45 | 85.0 | {P1,P2} {P3,P4} {P5,P6} |
| MILP (ótimo) | 3 | 15.000,00 | 45 | 85.0 | {P1,P2} {P3,P4} {P5,P6} |

Janelas da solução do MILP: {P3,P4} 11h30–13h30; {P5,P6} 14h30–16h30; {P1,P2} 8h30–10h30

## BUD = 1.5 h

| Método | Frascos | Custo (R$) | Sobra (mg) | Utilização (%) | Agrupamento |
|---|---|---|---|---|---|
| Sem compartilhamento | 6 | 30.000,00 | 345 | 42.5 | {P1} {P2} {P3} {P4} {P5} {P6} |
| FFD temporal | 3 | 15.000,00 | 45 | 85.0 | {P1,P2} {P3,P4} {P5,P6} |
| GRASP | 3 | 15.000,00 | 45 | 85.0 | {P1,P2} {P3,P4} {P5,P6} |
| VNS | 3 | 15.000,00 | 45 | 85.0 | {P1,P2} {P3,P4} {P5,P6} |
| GRASP-VNS | 3 | 15.000,00 | 45 | 85.0 | {P1,P2} {P3,P4} {P5,P6} |
| MILP (ótimo) | 3 | 15.000,00 | 45 | 85.0 | {P1,P2} {P3,P4} {P5,P6} |

Janelas da solução do MILP: {P3,P4} 11h30–13h00; {P5,P6} 14h30–16h00; {P1,P2} 8h30–10h00

## BUD = 1 h

| Método | Frascos | Custo (R$) | Sobra (mg) | Utilização (%) | Agrupamento |
|---|---|---|---|---|---|
| Sem compartilhamento | 6 | 30.000,00 | 345 | 42.5 | {P1} {P2} {P3} {P4} {P5} {P6} |
| FFD temporal | 5 | 25.000,00 | 245 | 51.0 | {P1} {P2} {P3} {P4} {P5,P6} |
| GRASP | 5 | 25.000,00 | 245 | 51.0 | {P1} {P2} {P3} {P4} {P5,P6} |
| VNS | 5 | 25.000,00 | 245 | 51.0 | {P1} {P2} {P3} {P4} {P5,P6} |
| GRASP-VNS | 5 | 25.000,00 | 245 | 51.0 | {P1} {P2} {P3} {P4} {P5,P6} |
| MILP (ótimo) | 5 | 25.000,00 | 245 | 51.0 | {P1} {P2} {P3} {P4} {P5,P6} |

Janelas da solução do MILP: {P2} 10h00–11h00; {P4} 13h00–14h00; {P5,P6} 14h30–15h30; {P3} 11h30–12h30; {P1} 8h30–9h30
