# Filone: La frontiera dell'automazione nel Molecular Tumor Board

Pacchetto autonomo che documenta l'analisi su *quanta parte della
preparazione di un Molecular Tumor Board (MTB) sia realisticamente
automatizzabile e quale resti nel dominio del giudizio multidisciplinare*.

Il contenuto deriva dai quattro esperimenti della tesi (accuratezza
multi-hop, generalizzabilità tra reader, robustezza alla riformulazione,
sicurezza/astensione) e li sintetizza in una mappa a dieci stadi con una
"frontiera dell'automazione" tra lo stadio 5 e lo stadio 6.

## Contenuto del pacchetto

| File | Descrizione |
|------|-------------|
| `capitolo_frontiera_automazione.tex` | Capitolo LaTeX autonomo (preambolo completo, compilabile con `tectonic`). |
| `capitolo_frontiera_automazione.pdf` | Capitolo compilato (4 pagine). |
| `fig9_automation_frontier.png` | Figura: mappa dei 10 stadi con le tre zone e la frontiera. |
| `frontiera_automazione_stadi.csv` | Dati dei 10 stadi (stadio, descrizione, natura, automatizzabilità, evidenza sperimentale). |
| `04_frontiera_automazione.py` | Script standalone che rigenera la figura dal CSV (dipendenze: pandas, matplotlib). |

## Riproduzione

```bash
# 1. Rigenerare la figura dal CSV
python 04_frontiera_automazione.py        # -> fig9_automation_frontier.png @300dpi

# 2. Compilare il capitolo (richiede la figura nella stessa cartella)
tectonic capitolo_frontiera_automazione.tex   # -> capitolo_frontiera_automazione.pdf
```

## Tesi centrale

L'automazione non sposta il confine macchina/clinico lungo il workflow MTB:
lo rende **esplicito e sicuro**. Il recupero fattuale (stadi 1--3) è
automatizzabile con F1 ~0,99 fino a 5 hop, bridge-recall 100%, in modo
indipendente dal reader e con astensione deterministica sui casi senza
risposta. Il giudizio multidisciplinare (stadi 6--10) resta umano. Gli stadi
4--5 sono assistivi. Il valore del sistema non è rispondere *di più*, ma
sapere *dove smettere di rispondere*.
