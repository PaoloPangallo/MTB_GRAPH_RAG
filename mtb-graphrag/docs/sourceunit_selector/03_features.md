# Feature e normalizzazione

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

## 1. Normalizzazione (§4)

| Passo | Regola |
|---|---|
| Unicode | NFC |
| Maiuscole | `casefold()` |
| Punteggiatura | sostituita da spazio (conservati `>` e `<` per le notazioni HGVS) |
| Spazi | collassati |
| Geni | solo alfanumerico: `ABL1` → `abl1` |
| Alterazioni | prefisso HGVS rimosso: `p.V299L` → `v299l` |
| Farmaci | testo normalizzato, confronto per token interi |

**Nessuna espansione semantica.** `EGFR mutation` non diventa `EGFR L858R`: un
test lo verifica esplicitamente, perché quella trasformazione inventerebbe
un'evidenza che il documento non contiene.

Un bug trovato dai test: `normalize_text` rimuove la punteggiatura, quindi
togliere il prefisso HGVS *dopo* produceva `pv299l` — un'alterazione inesistente
che non avrebbe mai combaciato. Il prefisso va tolto **prima**.

`rs` non è nell'elenco dei prefissi: in `rs12345` fa parte dell'identificatore
dbSNP, e rimuoverlo lascerebbe un numero senza significato.

## 2. Le feature (§5)

| Feature | Origine nella GCA | Peso |
|---|---|---:|
| `F_alteration` | `biomarkers[]` con `type != Gene` | **3.0** |
| `F_gene` | `biomarkers[]` con `type == Gene` | 2.0 |
| `F_intervention` | `interventions[].label` | 2.0 |
| `F_disease` | `disease[].label` | 0.5 |
| lessicale | BM25 su tutti i termini sopra | 1.0 |

L'ordine riflette il potere discriminante: un'alterazione puntuale identifica
un'affermazione; una malattia, in un articolo di oncologia, compare quasi
ovunque e discrimina poco.

`graph_relation` è nell'ingresso ma **non genera termini di query**: usarla
significherebbe cercare sinonimi della relazione («resistance», «sensitivity»)
che il documento potrebbe non contenere, cioè fare espansione semantica dalla
porta di servizio.

## 3. Matching per token interi

```python
tokens = set(tokenize(unit_text))
normalized_units = {normalize_gene(t) for t in tokens} | {normalize_alteration(t) for t in tokens}
alterations = tuple(a for a in selection.alterations
                    if normalize_alteration(a) in normalized_units)
```

Il confronto non è per sottostringa. Cercare `V299L` dentro il testo troverebbe
anche `V299LX`, e un match di comodo su un'alterazione è precisamente l'errore
che rende inutile un grounding documentale.

**Il gene non implica la variante** (§16). Un'unità che dice «ABL1 kinase domain
mutations were analysed» ottiene `matched_gene = ("ABL1",)` e
`matched_alteration = ()`. Un test lo verifica.

## 4. Prior strutturale sul tipo di unità (§6)

Ricavato dalla **forma** delle unità, non dal loro tasso di gold. Tarare il
prior sui 25 bundle di valutazione vorrebbe dire misurare quanto bene si
riproduce il gold usando il gold.

Il criterio è l'auto-contenimento: quanto un'unità regge da sola come citazione
verificabile.

| Prior | Tipi | Argomento |
|---:|---|---|
| 1.00 | `ABSTRACT`, `BRIEF_SUMMARY`, `DETAILED_DESCRIPTION` | narrazione completa |
| 0.95 | `FULLTEXT_PARAGRAPH` | argomenta e contestualizza |
| 0.85 | `ABSTRACT_SENTENCE` | densa, ma frammento |
| 0.80 | `TITLE`, `TRIAL_TITLE` | enunciano la tesi, non l'argomentano |
| 0.70 | `INTERVENTION` | etichetta strutturata |
| 0.60 | `CONDITION`, `FULLTEXT_SENTENCE` | precise ma fuori contesto |
| 0.50 | `TABLE_CELL`, `TABLE_CAPTION`, `FIGURE_CAPTION` | frammenti tabellari |
| 0.20 | `FULLTEXT_SECTION` | sono intestazioni: «Introduction», «Results» |

I tassi di gold osservati corroborano l'ordine — `ABSTRACT` 100%,
`FULLTEXT_SECTION` 0% — ma non sono stati usati per fissarlo.

Le tabelle **non** sono escluse a priori (§18): un biomarcatore può comparire
solo lì, e un test verifica che una `TABLE_CELL` pertinente venga selezionata.

## 5. Guardia sul contesto (§19)

```python
context = min(1.0, len(text) / MIN_CONTEXT_CHARS)   # MIN_CONTEXT_CHARS = 80
bonus = (pesi delle feature) * context
```

Un'unità `TABLE_CELL` contenente solo `V299L` ottiene il bonus dell'alterazione
smorzato a `5/80`. «V299L» da sola è un'occorrenza, non un'affermazione
d'autore, e una citazione senza contesto non è verificabile.

Lo smorzamento è proporzionale, non un azzeramento: se nient'altro nel documento
è pertinente, quell'unità resta selezionabile.

## 6. Score

```
score(unit) = (BM25(query, unit) + bonus_feature * context) * section_prior
```

Ogni componente è registrato separatamente in `RankedSourceUnit`, così la somma
è ricostruibile a mano.
