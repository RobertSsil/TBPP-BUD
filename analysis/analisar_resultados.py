"""Análise dos resultados: tabelas (CSV + LaTeX booktabs), figuras e testes pareados.

Referência de qualidade por instância (Seção 2.6):
  * se o MILP provou otimalidade: Z_L = ótimo (tipo "ótimo");
  * caso contrário: Z_L = max(limite dual do HiGHS, LB volumétrico), arredondado para cima
    ao múltiplo do MDC dos custos dos frascos (todo custo viável é múltiplo dele) (tipo "LI").
  gap(%) = 100 (Z_H - Z_L) / Z_L.
Também se reporta o desvio em relação à melhor solução conhecida (BKS = menor custo
obtido por qualquer método, inclusive o incumbente do MILP).

Economia (Seção 4.5): E(%) = 100 (C_ref - C) / C_ref, com C_ref = cenário sem
compartilhamento (cada paciente abre o frasco mais barato que comporta sua dose).

Uso:  python analysis/analisar_resultados.py
Saída: results/analise/  (tabelas .csv e .tex, figuras .pdf/.png, resumo.txt)
"""
from __future__ import annotations

import json
import math
import sys
from functools import reduce
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
RES = RAIZ / "results"
OUT = RES / "analise"
ORDEM_CLASSES = ["pequena", "media", "grande"]
NOME_CLASSE = {"pequena": "Pequena", "media": "Média", "grande": "Grande"}
METODOS = ["GRASP-VNS", "GRASP", "VNS"]


def ler(tipo: str) -> pd.DataFrame:
    arqs = sorted((RES / tipo).glob("*.csv"))
    if not arqs:
        return pd.DataFrame()
    return pd.concat([pd.read_csv(a) for a in arqs], ignore_index=True)


def mdc_custos() -> dict:
    out = {}
    for p in (RAIZ / "instances" / "teste").rglob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        cs = [int(round(t["custo"] * 100)) for t in d["tipos"]]
        out[d["nome"]] = reduce(math.gcd, cs) / 100.0
    return out


def fmt(x, nd=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "--"
    return f"{x:.{nd}f}".replace(".", ",")


def tabela_longa(df: pd.DataFrame, caminho: Path, legenda: str, rotulo: str, alinh: str) -> None:
    """Tabela que quebra entre páginas (longtable), para o apêndice por instância."""
    esc = lambda s: str(s).replace("%", r"\%").replace("_", r"\_").replace("&", r"\&")
    cab = " & ".join(rf"\textbf{{{esc(c)}}}" for c in df.columns) + r" \\"
    l = [r"\begingroup\scriptsize\setlength{\tabcolsep}{3pt}",
         rf"\begin{{longtable}}{{@{{}}{alinh}@{{}}}}",
         rf"\caption{{{legenda}}}\label{{{rotulo}}}\\", r"\toprule", cab, r"\midrule\endfirsthead",
         rf"\multicolumn{{{df.shape[1]}}}{{l}}{{\textit{{(continuação)}}}}\\", r"\toprule", cab, r"\midrule\endhead",
         r"\bottomrule", rf"\multicolumn{{{df.shape[1]}}}{{c}}{{Fonte: elaboração própria.}}\\", r"\endlastfoot"]
    for _, row in df.iterrows():
        l.append(" & ".join(esc(v) for v in row.values) + r" \\")
    l += [r"\end{longtable}", r"\endgroup"]
    caminho.write_text("\n".join(l) + "\n", encoding="utf-8")


def tabela_latex(df: pd.DataFrame, caminho: Path, legenda: str, rotulo: str,
                 alinh: str | None = None, nota: str = "Fonte: elaboração própria.") -> None:
    alinh = alinh or ("l" + "r" * (df.shape[1] - 1))
    esc = lambda s: str(s).replace("%", r"\%").replace("_", r"\_").replace("&", r"\&")
    largo = df.shape[1] >= 8  # tabelas largas são reduzidas à largura do texto
    l = [r"\begin{table}[H]", r"\centering", rf"\caption{{{legenda}}}\label{{{rotulo}}}",
         r"\small"] + ([r"\resizebox{\textwidth}{!}{%"] if largo else []) + [
         rf"\begin{{tabular}}{{@{{}}{alinh}@{{}}}}", r"\toprule",
         " & ".join(rf"\textbf{{{esc(c)}}}" for c in df.columns) + r" \\", r"\midrule"]
    for _, row in df.iterrows():
        l.append(" & ".join(esc(v) for v in row.values) + r" \\")
    l += [r"\bottomrule", r"\end{tabular}"] + (["}"] if largo else []) + [rf"\fonte{{{nota[7:] if nota.startswith('Fonte: ') else nota}}}",
          r"\end{table}"]
    caminho.write_text("\n".join(l) + "\n", encoding="utf-8")


def wilcoxon(a, b):
    try:
        from scipy.stats import wilcoxon as w
        d = np.array(a) - np.array(b)
        if np.allclose(d, 0):
            return 1.0
        return float(w(a, b, zero_method="zsplit").pvalue)
    except Exception:
        return float("nan")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ex, ref, milp, abl = ler("execucoes"), ler("referencias"), ler("milp"), ler("ablacao")
    if ex.empty or ref.empty:
        sys.exit("sem resultados em results/ — rode scripts/executar_experimentos.py")
    mdc = mdc_custos()

    # ------------------------------------------------ referência Z_L por instância
    ref = ref.set_index("instancia")
    if not milp.empty:
        milp = milp.drop_duplicates("instancia", keep="last").set_index("instancia")
    linhas = []
    for nome, r in ref.iterrows():
        g = mdc.get(nome, 0.0)
        lb = r["lb_volumetrico"]
        tipo, zl, m_custo, m_tempo, m_status = "LI", lb, np.nan, np.nan, "não executado"
        if not milp.empty and nome in milp.index:
            m = milp.loc[nome]
            m_custo, m_tempo, m_status = m["custo"], m["tempo_s"], m["status"]
            if int(m["otimo"]) == 1:
                tipo, zl = "ótimo", float(m["custo"])
            elif pd.notna(m["limite_inferior"]):
                zl = max(zl, float(m["limite_inferior"]))
        if tipo == "LI" and g > 0:
            zl = math.ceil(zl / g - 1e-9) * g
        linhas.append(dict(instancia=nome, Z_L=zl, tipo_ref=tipo, milp_custo=m_custo,
                           milp_tempo_s=m_tempo, milp_status=m_status))
    zref = pd.DataFrame(linhas).set_index("instancia")
    ref = ref.join(zref)

    ex = ex.join(ref[["Z_L", "tipo_ref", "custo_sem_compart", "custo_ffd", "milp_custo"]], on="instancia")
    bks = pd.concat([ex.groupby("instancia")["custo"].min(), ref["milp_custo"], ref["custo_ffd"]], axis=1).min(axis=1)
    ex["BKS"] = ex["instancia"].map(bks)
    ex["gap"] = 100 * (ex["custo"] - ex["Z_L"]) / ex["Z_L"]
    ex["dev_bks"] = 100 * (ex["custo"] - ex["BKS"]) / ex["BKS"]
    ex["economia"] = 100 * (ex["custo_sem_compart"] - ex["custo"]) / ex["custo_sem_compart"]
    ex["economia_vs_ffd"] = 100 * (ex["custo_ffd"] - ex["custo"]) / ex["custo_ffd"]
    ex.to_csv(OUT / "execucoes_com_metricas.csv", index=False)
    ref["gap_ffd"] = 100 * (ref["custo_ffd"] - ref["Z_L"]) / ref["Z_L"]
    ref["gap_milp"] = 100 * (ref["milp_custo"] - ref["Z_L"]) / ref["Z_L"]

    gv = ex[ex["metodo"] == "GRASP-VNS"]
    resumo = []

    # ------------------------------------------------ T1: desempenho por classe
    t1 = []
    for c in ORDEM_CLASSES:
        d = gv[gv["classe"] == c]
        if d.empty:
            continue
        rc = ref[ref["classe"] == c]
        t1.append({
            "Classe": NOME_CLASSE[c],
            "Inst.": rc.shape[0],
            "Ótimos MILP": int((rc["tipo_ref"] == "ótimo").sum()),
            "Gap médio (%)": fmt(d["gap"].mean()),
            "DP": fmt(d["gap"].std()),
            "Mín.": fmt(d["gap"].min()),
            "Mediana": fmt(d["gap"].median()),
            "Máx.": fmt(d["gap"].max()),
            "Tempo médio (s)": fmt(d["tempo_s"].mean(), 1),
            "Tempo máx. (s)": fmt(d["tempo_s"].max(), 1),
            "Tempo MILP médio (s)": fmt(rc["milp_tempo_s"].mean(), 0),
        })
    t1 = pd.DataFrame(t1)
    t1.to_csv(OUT / "tab_desempenho_classe.csv", index=False)
    tabela_latex(t1, OUT / "tab_desempenho_classe.tex",
                 "Desempenho do GRASP-VNS por classe de instância (todas as execuções).",
                 "tab:desempenho_classe", "l" + "r" * (t1.shape[1] - 1))

    # ------------------------------------------------ T2: classe x BUD
    t2 = []
    for c in ORDEM_CLASSES:
        for b in sorted(gv["bud_h"].unique()):
            d = gv[(gv["classe"] == c) & (gv["bud_h"] == b)]
            if d.empty:
                continue
            rc = ref[(ref["classe"] == c) & (ref["bud_h"] == b)]
            t2.append({"Classe": NOME_CLASSE[c], "BUD (h)": f"{b:g}",
                       "Referência": f"{int((rc['tipo_ref']=='ótimo').sum())} ót. / {int((rc['tipo_ref']=='LI').sum())} LI",
                       "Gap médio (%)": fmt(d["gap"].mean()), "DP gap": fmt(d["gap"].std()),
                       "Economia média (%)": fmt(d["economia"].mean()),
                       "Economia mín.–máx. (%)": f"{fmt(d['economia'].min())}–{fmt(d['economia'].max())}",
                       "Utilização (%)": fmt(d["utilizacao"].mean(), 1),
                       "Tempo médio (s)": fmt(d["tempo_s"].mean(), 1)})
    t2 = pd.DataFrame(t2)
    t2.to_csv(OUT / "tab_classe_bud.csv", index=False)
    tabela_latex(t2, OUT / "tab_classe_bud.tex",
                 "Resultados do GRASP-VNS por classe e janela BUD.", "tab:classe_bud",
                 "llrrrrrrr")

    # ------------------------------------------------ T3: economia por BUD
    t3 = []
    for b in sorted(gv["bud_h"].unique()):
        d = gv[gv["bud_h"] == b]
        rb = ref[ref["bud_h"] == b]
        t3.append({"BUD (h)": f"{b:g}",
                   "Economia média (%)": fmt(d["economia"].mean()),
                   "DP": fmt(d["economia"].std()),
                   "Mín. (%)": fmt(d["economia"].min()), "Máx. (%)": fmt(d["economia"].max()),
                   "Economia do FFD (%)": fmt((100 * (rb["custo_sem_compart"] - rb["custo_ffd"]) / rb["custo_sem_compart"]).mean()),
                   "Sobra média (mg)": fmt(d["sobra_mg"].mean(), 0)})
    t3 = pd.DataFrame(t3)
    t3.to_csv(OUT / "tab_economia_bud.csv", index=False)
    tabela_latex(t3, OUT / "tab_economia_bud.tex",
                 "Economia em relação ao cenário sem compartilhamento, por janela BUD.", "tab:economia_bud")

    # ------------------------------------------------ T4: comparação de métodos
    t4 = []
    por_inst = ex.groupby(["instancia", "classe", "metodo"])["custo"].mean().unstack("metodo")
    for c in ORDEM_CLASSES:
        sub = ex[ex["classe"] == c]
        if sub.empty:
            continue
        pi = por_inst.xs(c, level="classe")
        rc = ref[ref["classe"] == c]
        linha = {"Classe": NOME_CLASSE[c], "FFD gap (%)": fmt(rc["gap_ffd"].mean())}
        for mt in METODOS:
            d = sub[sub["metodo"] == mt]
            if d.empty:
                continue
            linha[f"{mt} gap (%)"] = f"{fmt(d['gap'].mean())} ± {fmt(d['gap'].std())}"
        for mt in ("GRASP", "VNS"):
            if mt in pi and "GRASP-VNS" in pi:
                a_, b_ = pi["GRASP-VNS"].values, pi[mt].values
                v = int((a_ < b_ - 1e-6).sum()); e = int((abs(a_ - b_) <= 1e-6).sum()); dd = int((a_ > b_ + 1e-6).sum())
                linha[f"V/E/D vs {mt}"] = f"{v}/{e}/{dd}"
                linha[f"p (Wilcoxon) vs {mt}"] = fmt(wilcoxon(a_, b_), 3)
        t4.append(linha)
    t4 = pd.DataFrame(t4)
    t4.to_csv(OUT / "tab_comparacao_metodos.csv", index=False)
    tabela_latex(t4, OUT / "tab_comparacao_metodos.tex",
                 "Comparação entre FFD temporal, GRASP, VNS e GRASP-VNS sob o mesmo orçamento de tempo. "
                 "V/E/D: instâncias em que o GRASP-VNS vence/empata/perde (custo médio nas sementes).",
                 "tab:comparacao_metodos")

    # ------------------------------------------------ T5: por instância (apêndice)
    agg = gv.groupby("instancia").agg(gv_medio=("custo", "mean"), gv_melhor=("custo", "min"),
                                     gv_dp=("custo", "std"), gv_tempo=("tempo_s", "mean"),
                                     gap_medio=("gap", "mean"))
    t5 = ref.join(agg).reset_index()
    t5["ordem"] = t5["classe"].map({c: i for i, c in enumerate(ORDEM_CLASSES)})
    t5 = t5.sort_values(["ordem", "bud_h", "n"])
    t5_out = pd.DataFrame({
        "Instância": t5["instancia"], "n": t5["n"], "BUD (h)": t5["bud_h"].map(lambda b: f"{b:g}"),
        "C_ref": t5["custo_sem_compart"].map(lambda x: fmt(x / 1000, 0)),
        "FFD": t5["custo_ffd"].map(lambda x: fmt(x / 1000, 0)),
        "MILP": t5["milp_custo"].map(lambda x: fmt(x / 1000, 0) if pd.notna(x) else "--"),
        "Z_L": t5["Z_L"].map(lambda x: fmt(x / 1000, 0)), "Ref.": t5["tipo_ref"],
        "GV médio": t5["gv_medio"].map(lambda x: fmt(x / 1000, 1)),
        "GV melhor": t5["gv_melhor"].map(lambda x: fmt(x / 1000, 0)),
        "Gap (%)": t5["gap_medio"].map(fmt), "Tempo (s)": t5["gv_tempo"].map(lambda x: fmt(x, 1))})
    t5_out.to_csv(OUT / "tab_por_instancia.csv", index=False)
    t5_out["Instância"] = t5_out["Instância"].str.replace("_", "-")
    tabela_longa(t5_out, OUT / "tab_por_instancia.tex",
                 "Resultados por instância (custos em R\\$ mil; GV = GRASP-VNS, média das sementes).",
                 "tab:por_instancia", "lrrrrrrlrrrr")

    # ------------------------------------------------ ablação
    if not abl.empty:
        abl = abl.join(ref[["Z_L", "classe"]].rename(columns={"classe": "classe_r"}), on="instancia")
        abl["gap"] = 100 * (abl["custo"] - abl["Z_L"]) / abl["Z_L"]
        ta = abl.groupby(["metodo"]).agg(gap_medio=("gap", "mean"), gap_dp=("gap", "std"),
                                        tempo_medio=("tempo_s", "mean")).reset_index()
        ta.columns = ["Variante", "Gap médio (%)", "DP", "Tempo médio (s)"]
        for col in ta.columns[1:]:
            ta[col] = ta[col].map(fmt)
        ta.to_csv(OUT / "tab_ablacao.csv", index=False)
        tabela_latex(ta, OUT / "tab_ablacao.tex", "Estudo de ablação das vizinhanças do GRASP-VNS.",
                     "tab:ablacao")

    # ------------------------------------------------ tabela de calibração
    calib = RAIZ / "config" / "parametros_calibrados.json"
    cfg_exp = json.loads((RAIZ / "config" / "experimento.json").read_text(encoding="utf-8"))
    pexp = cfg_exp["heuristicas"]["parametros"]
    faixas = {"alfa": ("Parâmetro guloso $\\alpha$", "0,1; 0,2; 0,3; 0,5; 0,7"),
              "iteracoes_grasp": ("Iterações GRASP", "50; 100; 200; 350; 500"),
              "limite_estagnacao": ("Limite de estagnação VNS", "5; 10; 20; 35; 50"),
              "intensidade_shaking": ("Intensidade máxima de \\textit{shaking} ($k_{\\max}$)", "1; 2; 3; 4; 5")}
    pcal = json.loads(calib.read_text(encoding="utf-8"))["parametros"] if calib.exists() else {}
    tc = pd.DataFrame([{"Parâmetro": nome, "Valores testados": fx,
                        "Valor final": str(pcal.get(k, pexp[k])).replace(".", ",")}
                       for k, (nome, fx) in faixas.items()])
    tc.to_csv(OUT / "tab_calibracao.csv", index=False)
    l = [r"\begin{table}[H]", r"\centering",
         r"\caption{Valores testados e valores finais dos parâmetros do GRASP-VNS após a calibração.}\label{tab:calib}",
         r"\small", r"\begin{tabular}{@{}llc@{}}", r"\toprule",
         r"\textbf{Parâmetro} & \textbf{Valores testados} & \textbf{Valor final} \\", r"\midrule"]
    l += [f"{r['Parâmetro']} & {r['Valores testados']} & {r['Valor final']} \\\\" for _, r in tc.iterrows()]
    l += [r"\bottomrule", r"\end{tabular}", r"\fonte{elaboração própria.}", r"\end{table}"]
    (OUT / "tab_calibracao.tex").write_text("\n".join(l) + "\n", encoding="utf-8")

    # ------------------------------------------------ macros numéricas para o texto
    def mac(nome, valor):
        return f"\\renewcommand{{\\{nome}}}{{{valor}}}"
    M = []
    M.append(mac("NumInstancias", ref.shape[0]))
    M.append(mac("NumSementes", int(gv.groupby("instancia")["semente"].nunique().max())))
    M.append(mac("NumExecucoes", ex.shape[0]))
    M.append(mac("NumOtimos", int((ref["tipo_ref"] == "ótimo").sum())))
    if not milp.empty:
        M.append(mac("TempoLimiteMILP", f"{int(milp['tempo_limite_s'].max()):,}".replace(",", ".")))
    usada = RES / "config_usada.json"
    t_heur = pexp["tempo_limite_s"]
    if usada.exists():
        t_heur = json.loads(usada.read_text(encoding="utf-8"))["config"]["heuristicas"]["parametros"]["tempo_limite_s"]
    M.append(mac("TempoLimiteHeur", f"{t_heur:g}"))
    sufixo = {"pequena": "Pequena", "media": "Media", "grande": "Grande"}
    for c in ORDEM_CLASSES:
        d = gv[gv["classe"] == c]; rc = ref[ref["classe"] == c]
        if d.empty:
            continue
        S = sufixo[c]
        M += [mac(f"Gap{S}", fmt(d["gap"].mean())), mac(f"GapMax{S}", fmt(d["gap"].max())),
              mac(f"Tempo{S}", fmt(d["tempo_s"].mean(), 1)), mac(f"TempoMax{S}", fmt(d["tempo_s"].max(), 1)),
              mac(f"Otimos{S}", int((rc["tipo_ref"] == "ótimo").sum())),
              mac(f"GapFFD{S}", fmt(rc["gap_ffd"].mean())),
              mac(f"TempoMILP{S}", fmt(rc["milp_tempo_s"].mean(), 0))]
        for mt, nm in (("GRASP", "Grasp"), ("VNS", "Vns")):
            dm = ex[(ex["classe"] == c) & (ex["metodo"] == mt)]
            if not dm.empty:
                M.append(mac(f"Gap{nm}{S}", fmt(dm["gap"].mean())))
    nome_bud = {2: "Dois", 6: "Seis", 24: "VinteQuatro"}
    for b in sorted(gv["bud_h"].unique()):
        d = gv[gv["bud_h"] == b]
        if int(b) in nome_bud:
            B = nome_bud[int(b)]
            M += [mac(f"Econ{B}", fmt(d["economia"].mean())), mac(f"EconMin{B}", fmt(d["economia"].min())),
                  mac(f"EconMax{B}", fmt(d["economia"].max()))]
    if not abl.empty:
        g = abl.groupby("metodo")["gap"].mean()
        for var, nm in (("completo", "AblCompleto"), ("descrito_texto", "AblDescrito"),
                        ("sem_consolidar", "AblSemConsolidar"), ("sem_swap", "AblSemSwap"),
                        ("sem_shift", "AblSemShift"), ("sem_merge", "AblSemMerge")):
            if var in g:
                M.append(mac(nm, fmt(g[var])))
    (OUT / "numeros.tex").write_text("% gerado por analysis/analisar_resultados.py\n" + "\n".join(M) + "\n",
                                     encoding="utf-8")

    # ------------------------------------------------ figuras
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
        cls = [c for c in ORDEM_CLASSES if c in set(gv["classe"])]

        fig, ax = plt.subplots(1, 2, figsize=(9, 3.6))
        ax[0].boxplot([gv[gv["classe"] == c]["gap"] for c in cls], tick_labels=[NOME_CLASSE[c] for c in cls])
        ax[0].set_ylabel("Gap (%)"); ax[0].set_title("Gap do GRASP-VNS vs. referência")
        ax[1].boxplot([gv[gv["classe"] == c]["tempo_s"] for c in cls], tick_labels=[NOME_CLASSE[c] for c in cls])
        ax[1].set_yscale("log"); ax[1].set_ylabel("Tempo (s, log)"); ax[1].set_title("Tempo do GRASP-VNS")
        fig.tight_layout(); fig.savefig(OUT / "fig_gap_tempo_classe.pdf"); fig.savefig(OUT / "fig_gap_tempo_classe.png", dpi=200)
        plt.close(fig)

        buds = sorted(gv["bud_h"].unique())
        fig, ax = plt.subplots(figsize=(6, 3.6))
        ax.boxplot([gv[gv["bud_h"] == b]["economia"] for b in buds], tick_labels=[f"{b:g} h" for b in buds])
        ax.set_xlabel("Janela BUD"); ax.set_ylabel("Economia vs. sem compartilhamento (%)")
        fig.tight_layout(); fig.savefig(OUT / "fig_economia_bud.pdf"); fig.savefig(OUT / "fig_economia_bud.png", dpi=200)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(7, 3.6))
        largura = 0.25
        for j, mt in enumerate(METODOS):
            vals = [ex[(ex["classe"] == c) & (ex["metodo"] == mt)]["gap"].mean() for c in cls]
            ax.bar(np.arange(len(cls)) + (j - 1) * largura, vals, largura, label=mt)
        ax.bar(np.arange(len(cls)) + 2 * largura, [ref[ref["classe"] == c]["gap_ffd"].mean() for c in cls],
               largura, label="FFD temporal", color="lightgray")
        ax.set_xticks(np.arange(len(cls)) + largura / 2, [NOME_CLASSE[c] for c in cls])
        ax.set_ylabel("Gap médio (%)"); ax.legend(frameon=False, fontsize=8)
        fig.tight_layout(); fig.savefig(OUT / "fig_comparacao_metodos.pdf"); fig.savefig(OUT / "fig_comparacao_metodos.png", dpi=200)
        plt.close(fig)
    except Exception as e:  # figuras são opcionais
        print("aviso: figuras não geradas:", e)

    # ------------------------------------------------ resumo
    resumo.append(f"Instâncias analisadas: {ref.shape[0]}; execuções: {ex.shape[0]}")
    resumo.append(f"Sementes por instância: {gv.groupby('instancia')['semente'].nunique().max()}")
    resumo.append("Ótimos provados pelo MILP: " + str(int((ref['tipo_ref'] == 'ótimo').sum())))
    for nome, t in [("Desempenho por classe", t1), ("Classe x BUD", t2), ("Economia por BUD", t3),
                    ("Comparação de métodos", t4)]:
        resumo.append(f"\n== {nome} ==\n" + t.to_string(index=False))
    (OUT / "resumo.txt").write_text("\n".join(resumo) + "\n", encoding="utf-8")
    print("\n".join(resumo))
    print(f"\nTabelas e figuras em {OUT}")


if __name__ == "__main__":
    main()
