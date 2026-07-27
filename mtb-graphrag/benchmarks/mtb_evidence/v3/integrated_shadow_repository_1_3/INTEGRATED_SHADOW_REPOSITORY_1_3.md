# Integrated shadow repository 1.3

Repository: `qualified_claim_repository/1.3`
Stato: `shadow_not_promoted`
Motivazione del bump: verified intervention terminology update plus directional disease policy integration

La 1.3 fa due cose che le versioni precedenti avevano preparato e non potevano
fare: applica il mapping terminologico che la review ha verificato, e fa
derivare l'eleggibilità dalla congiunzione dei gate invece che da un gate alla
volta.

## Terminologia

`BGJ398` → `infigratinib`, decisione
`TP-BGJ398-INFIGRATINIB`, scope globale, verificata.

Il mapping cambia una rappresentazione canonica, non una proposizione. I due
gruppi coinvolti restano aggregate non separabili, `permits_member_specific_claims`
resta falso, e nessun claim atomico nasce dai membri. Cambia però l'identità,
perché la rappresentazione canonica è uno dei campi dell'hash: i due claim
vecchi sono ritirati con lineage reversibile e ne nascono due nuovi.

| gruppo | claim ritirato | claim attivo |
|---|---|---|
| `evidence:1851` | `CLM-a7c903cf8d423f015e29` | `CLM-90e863f00f134fc3cd3d` |
| `evidence:1853` | `CLM-aae818bbc8ec735a255d` | `CLM-5071bb2d8657ac0fbed0` |

Il letterale della fonte non è stato toccato. `BGJ398` è ciò
che il testo del 2013 dice, e un'identificazione pubblicata dopo non riscrive un
documento: il claim porta entrambe le rappresentazioni in campi distinti, ed è
raggiungibile con entrambi i nomi senza che nessuno dei due lo promuova.

`AUY922` / luminespib resta irrisolto. Nessun alias exact,
nessuna materializzazione, nessun claim ID modificato. Il registro elenca la
coppia aperta con lo stesso rilievo di quella chiusa: una coda che sembra vuota
non viene più guardata.

Collisioni: 0. Deduplicazioni: 0.

## Conteggi

| oggetto | valore |
|---|---:|
| parent | 147 |
| claim attivi | 148 |
| terapeutici | 146 |
| diagnostici | 2 |
| prognostici | 0 |
| atomic | 140 |
| aggregate | 3 |
| regimen | 3 |
| unsupported association | 6 |
| unresolved association | 6 |
| parent senza claim | 3 |
| aggregate ritirati | 2 |
| aggregate sostitutivi | 2 |
| diagnostici ritirati, solo lineage | 2 |

I claim ritirati non entrano nei 148 attivi. I due
diagnostici ritirati dalle versioni precedenti restano leggibili soltanto nel
lineage storico.

## Perimetro

Corpus, adapter, repository, retriever, scoring e QualifiedEvidenceView
operative restano invariati, e la parità è misurata sugli hash prima e dopo più
una query operativa rieseguita. I repository shadow 1.0, 1.1 e 1.2 restano
leggibili e invariati con i propri manifest. I piani di link e view hanno
`executed = false`. Il gold non è stato letto.
