# Gemma end-to-end

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatto: `gemma_comparison.json`.

## 1. Il confronto

Stesso bundle, stessa candidate, due insiemi di unità: quelle del bundle
congelato e quelle scelte dal selector. Stessi enricher e validatore reali.
Interessa la differenza, non il valore assoluto.

Campione stratificato per dimensione documento, fino a tre bundle per fascia:
**8 bundle**, 16 chiamate al modello.

## 2. Risultati

| Metrica | bundle gold | **selector** |
|---|---:|---:|
| QUOTE rate | 0.750 | **0.750** |
| ABSTAIN rate | 0.250 | **0.250** |
| quote validate | 0.750 | **0.750** |
| quote errate | 0.000 | **0.000** |
| SourceUnit non autorizzate | 0.000 | **0.000** |
| caratteri medi di prompt | 2499 | 2602 |
| token medi in ingresso | 1576 | 1668 |

**Accordo sulla decisione: 8 su 8.** Dove il gold produceva QUOTE il selector
produce QUOTE; dove produceva ABSTAIN produce ABSTAIN. Sovrapposizione media con
il gold: 2.6 unità su 4.

Il costo aggiuntivo è del 6% di token. Nessuna quote errata, nessuna SourceUnit
citata fuori da quelle offerte.

## 3. Le astensioni

Due casi su otto astengono con entrambi gli insiemi. Il più istruttivo è
`EB-003e4bcab4a57d2a1c80cb5c` — ABL1 V299L su `PMC248481`:

- il bundle congelato registra `core_support_mask.biomarker: UNSUPPORTED`;
- il selector porta in cima tutte e tre le unità gold;
- il modello astiene, motivando che il documento non menziona la variante.

Il selector ha fatto il proprio lavoro — ha trovato i passaggi giusti — e il
modello ha fatto il proprio: ha rifiutato di attribuire agli autori
un'affermazione che non hanno fatto. **Un'astensione corretta non è un
fallimento del selector** (§23), ed è il caso in cui la distinzione fra i due
ruoli si vede meglio.

## 4. Finestra di contesto (§26)

Tre casi, aggiungendo l'unità precedente e successiva a ciascuna selezionata:

| Bundle | unità | caratteri | decisione | validata |
|---|---|---|---|---|
| `EB-003e4bcab...` | 3 → 7 | 1681 → 2177 | ABSTAIN (invariata) | no |
| `EB-479f55c21...` | 4 → 10 | 3545 → 4634 | QUOTE (invariata) | sì |
| `EB-4ee2d856d...` | 4 → 12 | 3518 → 4779 | ABSTAIN (invariata) | no |

Costo: **+32.5%** di testo. Beneficio misurato: **nessuno** — nessuna decisione
cambia, nessuna validazione migliora.

Su tre casi non si conclude granché, ma la direzione è chiara e il costo è
certo. `NEIGHBOR_WINDOW` **non** viene proposto come comportamento canonico.

## 5. Cosa questo non dice

Otto bundle sono pochi. Il campione è stratificato e dichiarato, non
rappresentativo. E i due insiemi di unità si sovrappongono in media per 2.6
elementi su 4: il confronto misura una differenza parziale, non due condizioni
indipendenti.
