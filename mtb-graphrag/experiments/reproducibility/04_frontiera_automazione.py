#!/usr/bin/env python3
"""
04_frontiera_automazione.py
---------------------------
Genera la Figura 'frontiera dell'automazione MTB' a partire dal CSV
`frontiera_automazione_stadi.csv`.

La figura mappa i 10 stadi della preparazione di un Molecular Tumor Board
in tre zone (automatizzabile / parziale / giudizio umano) e traccia la
"frontiera dell'automazione" tra lo stadio 5 e lo stadio 6.

Uso:
    python 04_frontiera_automazione.py
Output:
    fig9_automation_frontier.png  (300 dpi)

Dipendenze: pandas, matplotlib.
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

CSV = "frontiera_automazione_stadi.csv"
OUT = "fig9_automation_frontier.png"

# etichette brevi (2 righe) per il box di ogni stadio, allineate al CSV
SHORT = {
 1: "Annotazione varianti\n(gene · tipo · HGVS/dbSNP)",
 2: "Assemblaggio catene evidenza\nvariante→gene→farmaco→trial→cdx",
 3: "Companion diagnostics\ne approvazioni FDA",
 4: "Pre-screening eleggibilità trial\n(criteri strutturati)",
 5: "Armonizzazione livelli evidenza\n(CIViC A–E vs OncoKB LEVEL_x)",
 6: "Ponderazione evidenze\ndeboli o contrastanti",
 7: "Integrazione contesto-paziente\n(comorbidità · linee · PS · organi)",
 8: "Priorità tra alterazioni\nmultiple azionabili",
 9: "Off-label / uso compassionevole\netica · accesso · costi",
 10:"Raccomandazione terapeutica\nfinale e accountability",
}
# nota empirica breve a destra (solo dove c'è)
EV = {
 1: "look-up strutturato",
 2: "GraphRAG F1 ≈ 0.99 (hop 2–5)\nbridge-recall 100% · reader-indip.",
 3: "template cdx · F1 ≈ 1.0",
 4: "assistivo · criteri espliciti",
 5: "richiede convenzioni · scale miste",
}
CATMAP = {"automatizzabile":"auto","parziale":"part","giudizio_umano":"judge"}
col  = {'auto':'#1f5fa8', 'part':'#c99a12', 'judge':'#8a8f96'}
face = {'auto':'#dbe6f2', 'part':'#f4ead0', 'judge':'#e9ebed'}


def main():
    df = pd.read_csv(CSV).sort_values("stadio")
    stages = [(int(r.stadio), SHORT[int(r.stadio)], CATMAP[r.automatizzabilita],
               EV.get(int(r.stadio), "")) for r in df.itertuples()]
    n = len(stages); top = n
    box_x, box_w, ev_x = 0.06, 0.50, 0.60

    fig, ax = plt.subplots(figsize=(10.5, 7.4))
    for i, (num, label, cat, ev) in enumerate(stages):
        y = top - i - 1
        yfrac = (y + 0.5) / top
        bb = FancyBboxPatch((box_x, (y + 0.14) / top), box_w, (1.0 - 0.28) / top,
                            boxstyle="round,pad=0.004,rounding_size=0.015",
                            transform=ax.transAxes, mutation_aspect=1)
        bb.set_facecolor(face[cat]); bb.set_edgecolor(col[cat]); bb.set_linewidth(1.4)
        ax.add_patch(bb)
        ax.text(box_x + 0.032, yfrac, str(num), transform=ax.transAxes, ha='center',
                va='center', fontsize=10, fontweight='bold', color=col[cat])
        ax.text(box_x + 0.070, yfrac, label, transform=ax.transAxes, ha='left',
                va='center', fontsize=7.2, color='#1a1a1a')
        if ev:
            ax.text(ev_x, yfrac, ev, transform=ax.transAxes, ha='left', va='center',
                    fontsize=6.6, color=col[cat], style='italic')

    # frontiera tra stadio 5 e 6
    yf = (top - 5) / top
    ax.plot([0.02, 0.98], [yf, yf], transform=ax.transAxes, color='#b5121b',
            lw=1.8, ls=(0, (6, 3)), zorder=5)
    ax.text(0.98, yf + 0.010, "frontiera dell'automazione", transform=ax.transAxes,
            ha='right', va='bottom', fontsize=7.6, color='#b5121b', fontweight='bold')

    def zone(y0, y1, color, txt):
        ax.annotate('', xy=(0.006, y1), xytext=(0.006, y0), xycoords='axes fraction',
                    arrowprops=dict(arrowstyle='-', color=color, lw=2.6))
        ax.text(-0.05, (y0 + y1) / 2, txt, transform=ax.transAxes, rotation=90,
                va='center', ha='center', fontsize=7.0, color=color, fontweight='bold')
    zone((top - 3) / top + 0.002, 1.0, col['auto'], "AUTOMATIZZABILE\n(validato)")
    zone((top - 5) / top + 0.002, (top - 3) / top - 0.002, col['part'], "PARZIALE\n(assistivo)")
    zone(0.0, (top - 5) / top - 0.002, col['judge'], "GIUDIZIO\nMULTIDISCIPLINARE")

    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    ax.set_title("La frontiera dell'automazione nella preparazione del Molecular Tumor Board\n"
                 "il retrieval automatizza l'assemblaggio fattuale; il giudizio clinico resta umano",
                 fontsize=9.5, loc='left', pad=12)
    handles = [mpatches.Patch(facecolor=face['auto'], edgecolor=col['auto'], label='Automatizzabile — dimostrato in tesi'),
               mpatches.Patch(facecolor=face['part'], edgecolor=col['part'], label='Parzialmente automatizzabile / assistivo'),
               mpatches.Patch(facecolor=face['judge'], edgecolor=col['judge'], label='Intrinsecamente giudizio umano')]
    ax.legend(handles=handles, frameon=False, fontsize=7.4, loc='center',
              bbox_to_anchor=(0.78, 0.22), ncol=1, handlelength=1.4)

    fig.savefig(OUT, dpi=300, bbox_inches='tight')
    print("saved", OUT)


if __name__ == "__main__":
    main()
