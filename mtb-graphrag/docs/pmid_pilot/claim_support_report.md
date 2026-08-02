# Claim-document support report

## Metodo

Per ogni riga sono stati confrontati soltanto i campi strutturati della claim
con il testo dell'abstract locale. Il matching deterministico ha usato:

- identificatore normalizzato `PMID`;
- presenza letterale o normalizzata di biomarker, malattia e intervento;
- direzione esplicita (`response`, `sensitivity`, `resistance`, `suppressed`,
  `progression`);
- tipo di evidenza esplicito nel testo o nel record strutturato;
- contesto/popolazione dichiarati nel testo.

Un termine più ampio è stato classificato `COMPATIBLE`, non `EXACT`. Un
intervento diverso, un codice di sviluppo non collegato localmente al nome
canonico o un risultato non separabile dal sottogruppo è stato classificato
`PARTIAL`. L'assenza nell'abstract non è stata trasformata in contraddizione.

## Esiti per claim

Il dettaglio macchina è in `claim_document_alignment.csv`; i passaggi che
seguono sono le citazioni esatte conservate per l'audit.

### Supporto diretto

- `CLM-0e59264facd7b2df0e67` — PMID 25393796: l'abstract nomina EML4-ALK,
  alectinib, I1171S e resistenza acquisita nello stesso caso.
- `CLM-8941c177da91f66ff93a` — PMID 24122810: identifica FGFR2-BICC1 e FGFR2
  fusions nel sottotipo intraepatico; il claim è diagnostico/classificatorio,
  non di utilità clinica.
- `CLM-5ce49705979f72f174e9` — PMID 37879444: EGFR exon 19/L858R, NSCLC,
  braccio amivantamab-carboplatino-pemetrexed e PFS superiore sono nello stesso
  abstract.
- `CLM-4a89bb28592af7ebaccf` — PMID 38942080: amivantamab-lazertinib,
  osimertinib, EGFR-mutant NSCLC e confronto di PFS sono espliciti.
- `CLM-1d3ba8b6ae49232969c7` — PMID 30420614, Gruppo B: il testo candidato
  supporta FGFR2 fusion, iCCA, derazantinib e attività antitumorale, ma il
  collegamento rimane `parent_candidate`.

### Supporto parziale

- `CLM-091cf6602db85e2a2d41`: ponatinib è associato a stable disease dopo
  pazopanib; questo non equivale automaticamente a una risposta/sensibilità
  non qualificata.
- `CLM-5ce532268b4aa1661311`: C1156Y e resistenza a crizotinib sono espliciti,
  ma EML4 non è esplicito nell'abstract locale.
- `CLM-4ffe85304f3ef5533b58`: EGFR-TKI, NSCLC e L858R sono presenti, ma
  L858R è aggregato con le delezioni dell'esone 19 nell'analisi.
- `CLM-90e863f00f134fc3cd3d` e `CLM-5071bb2d8657ac0fbed0`: FGFR2 partner,
  cellule NIH3T3 e soppressione della trasformazione sono presenti; BGJ398 è
  il letterale dell'abstract, mentre il claim usa `infigratinib`.
- `CLM-1fc4af943701d57d45ad` e `CLM-89ea67ee7946d9ccd552`: gefitinib,
  erlotinib e L858R compaiono in una popolazione mista con exon-19 deletion,
  senza effetto isolato per L858R.
- `CLM-a7e1c40b794d2c4d4ca8`: AHCYL1 è identificato, ma prevalenza e
  conclusione sono per FGFR2 fusions complessive.
- `CLM-0269a5c7db107cd8a893`, Gruppo B: T790M e l'attività di AZD9291 sono
  espliciti, ma il nome canonico `osimertinib` non compare nel testo locale e
  l'evidenza mescola modelli preclinici e due pazienti.
- `CLM-1e4f404ac84ee591fbda`, Gruppo B: BGJ398 e FGFR2 fusions sono espliciti,
  ma `infigratinib`, partner e scope iCCA non sono claim-specifici nel testo.

### Ambiguità

`CLM-0f234bc9c53847910521` ha un passaggio candidato forte in PMID 24736079:

> In a second case, we identified a secondary acquired ALK G1202R, which also
> confers resistance to alectinib (CH5424802/RO5424802), a second-generation
> ALK inhibitor.

Il parent, tuttavia, contiene sei PMID (`24736079`, `27130468`, `27432227`,
`29373100`, `29376144`, `29650534`) e nessun mapping source-unit claim-specifico.
Per questo il risultato è `AMBIGUOUS`, non `CLAIM_VERIFIED_LOCATOR`.

### Context only, contraddizioni, nessun supporto e testo non disponibile

Nel campione selezionato:

- `CONTEXT_ONLY`: 0;
- `CONTRADICTED`: 0;
- `NO_SUPPORT_FOUND`: 0;
- `TEXT_UNAVAILABLE`: 0.

Tutti i 16 casi hanno un abstract locale; questo non implica che ogni campo
della claim sia supportato. L'assenza di questi stati è una proprietà del
campione, non una conclusione sull'intero repository.

## Confronto A/B

| misura | Gruppo A (12) | Gruppo B (4) |
|---|---:|---:|
| testo locale disponibile | 12/12 = 100% | 4/4 = 100% |
| `DIRECT_SUPPORT` | 4/12 = 33,3% | 1/4 = 25,0% |
| `PARTIAL_SUPPORT` | 8/12 = 66,7% | 2/4 = 50,0% |
| `CONTEXT_ONLY` | 0/12 = 0% | 0/4 = 0% |
| `AMBIGUOUS` | 0/12 = 0% | 1/4 = 25,0% |
| `CONTRADICTED` | 0/12 = 0% | 0/4 = 0% |
| `NO_SUPPORT_FOUND` | 0/12 = 0% | 0/4 = 0% |
| `TEXT_UNAVAILABLE` | 0/12 = 0% | 0/4 = 0% |

Il confronto mostra che il PMID parent-level può essere utile per ritrovare un
passaggio candidato: nel Gruppo B il testo ha prodotto un supporto diretto e
due parziali. Non può però sostituire il mapping claim -> source unit: il caso
ALK multi-PMID resta ambiguo anche con un passaggio candidato molto forte.

## Limiti

Gli abstract locali non garantiscono full-text availability, non separano
sempre i sottogruppi biomarker-specifici e non risolvono automaticamente la
canonicalizzazione dei codici di sviluppo (`BGJ398`, `AZD9291`). I DOI non sono
disponibili nei record locali dei 16 casi. Nessun locator artificiale è stato
creato: per il testo cache è stato usato `locator_type=ABSTRACT`.
