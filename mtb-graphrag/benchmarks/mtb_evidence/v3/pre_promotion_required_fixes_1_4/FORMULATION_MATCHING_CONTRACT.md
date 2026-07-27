# Contratto di matching fra active moiety, sale e formulazione

Contratto: `intervention_formulation_contract/1.0`  
Registro: `verified_formulation_registry/1.0`  
Voci verificate: **1**

## Il problema

La 1.3 decide le relazioni di forma con una tupla di cinque suffissi.
Chi finisce dentro la tupla diventa `normalized_atomic_intervention`,
cioe' primario e con punteggio strutturale; chi resta fuori diventa
`incompatible`, cioe' respinto come un farmaco senza alcuna relazione.

| Coppia | Esito nella 1.3 | Fonte |
|---|---|---|
| `infigratinib hydrochloride` → `infigratinib` | primary | nessuna |
| `infigratinib phosphate` → `infigratinib` | rejected | `EV-BGJ398-06` |
| `alectinib` → `alectinib hydrochloride` | primary | nessuna |
| `neratinib` → `neratinib maleate` | rejected | nessuna |

L'unica coppia per cui una fonte autorevole esiste e' quella che la
tabella respinge. Le altre tre non hanno nessuna fonte: la differenza fra
loro e' soltanto quale suffisso qualcuno ha scritto nella tupla.

## Le relazioni

| Relazione | Bucket | Primary | Warning | Audit | Score strutturale |
|---|---|---|---|---|---|
| `exact_intervention_form` | `primary_ranked_results` | **true** | false | false | **true** |
| `normalized_exact_intervention_form` | `primary_ranked_results` | **true** | false | false | **true** |
| `verified_same_active_moiety_different_form` | `retained_with_warning` | false | **true** | false | false |
| `verified_salt_of_active_moiety` | `retained_with_warning` | false | **true** | false | false |
| `verified_formulation_variant` | `retained_with_warning` | false | **true** | false | false |
| `unresolved_formulation_relation` | `audit_only_results` | false | false | **true** | false |
| `different_intervention_form` | `retained_with_warning` | false | **true** | false | false |
| `incompatible_active_moiety` | `rejected_by_native_constraints` | false | false | false | false |

## La regola strict

> Primary exact soltanto quando la active moiety coincide e la forma canonica coincide, oppure quando un alias exact gia' verificato esiste per la stessa forma.

Non diventano mai exact:

- active moiety contro sale
- sale contro active moiety
- due sali differenti
- due formulazioni differenti

Sottostringa puo' produrre exact: false  
Rimozione del suffisso puo' produrre exact: false  
Distanza di edit puo' produrre exact: false

I token di forma restano utili e cambiano ruolo. Dicono *che* due
stringhe potrebbero parlare di forme diverse, ed e' quel sospetto — non
una conclusione — che manda la coppia al registro. Se il registro tace,
la relazione resta irrisolta.

## Il registro

| Forma | Moiety | Relazione | Fonte | Identificatori |
|---|---|---|---|---|
| `infigratinib phosphate` | `infigratinib` | `verified_salt_of_active_moiety` | DGIdb su NCIt e RxNorm (EV-BGJ398-06) | `ncit:C175088` contro `rxcui:2550729` |

Il registro contiene una sola voce, e questo e' il fatto rilevante: la
tabella dei suffissi ne trattava cinque come note. Una voce senza fonte
non e' una relazione debole, e' una relazione che nessuno ha verificato,
e il tipo `FormulationEntry` non permette di crearla.

## Le due forme di infigratinib, decise separatamente

### `infigratinib phosphate`

- moiety: `infigratinib`
- tipo di forma: `salt`
- origine della regola precedente: assenza di 'phosphate' dalla tupla SALT_FORM_SUFFIXES del contratto claim-type-retrieval-contract/1.0
- fonte autorevole: DGIdb su NCIt e RxNorm, evidence EV-BGJ398-06
- relazione: `verified`
- prima: `incompatible` → `rejected_by_native_constraints`
- adesso: `verified_salt_of_active_moiety` → `retained_with_warning`
- decisa per presenza nel grafo: false
- fusa con la moiety: false

E' l'unica coppia di forme del repository per cui esiste una fonte autorevole, e la regola in vigore la respinge come farmaco estraneo. Il sale ha concept id proprio (ncit:C175088), distinto dalla moiety (rxcui:2550729): la relazione esiste, ed e' una relazione di diversita'.

### `infigratinib hydrochloride`

- moiety: `infigratinib`
- tipo di forma: `salt`
- origine della regola precedente: presenza di 'hydrochloride' nella tupla SALT_FORM_SUFFIXES del contratto claim-type-retrieval-contract/1.0
- fonte autorevole: **nessuna**
- relazione: `unresolved`
- prima: `normalized_atomic_intervention` → `primary_ranked_results`
- adesso: `unresolved_formulation_relation` → `audit_only_results`
- decisa per presenza nel grafo: false
- fusa con la moiety: false

Nessuna fonte lega questa forma alla moiety, e nessun record del grafo la contiene. Diventava primaria per il solo fatto che il suo suffisso era stato scritto in una tupla. Senza prove la relazione resta irrisolta: non fusa e non respinta, ma visibile in audit.

Le due forme ricevono esiti diversi perche' le prove disponibili sono
diverse, non per simmetria e non perche' una delle due sia nel grafo.
Nessuna delle due e' exact, e nessuna delle due e' fusa con la moiety.

## Le forme nel repository

Claim con forma o codice: **18**  
Claim in forma salina: **13**  
Forme invisibili alla tabella dei suffissi: **1**

| Claim | Letterale | Token | Oggi | Domani | Impatto |
|---|---|---|---|---|---|
| `CLM-0e59264facd7…` | `alectinib hydrochloride` | `hydrochloride` | `normalized_atomic_intervention` | `unresolved_formulation_relation` | leaves_primary_bucket |
| `CLM-0f234bc9c538…` | `alectinib hydrochloride` | `hydrochloride` | `normalized_atomic_intervention` | `unresolved_formulation_relation` | leaves_primary_bucket |
| `CLM-43229efd0cd8…` | `pazopanib hydrochloride` | `hydrochloride` | `normalized_atomic_intervention` | `unresolved_formulation_relation` | leaves_primary_bucket |
| `CLM-45252d017284…` | `pd173074` | — | `exact_atomic_intervention` | `exact_intervention_form` | unchanged |
| `CLM-464501e94094…` | `alectinib hydrochloride` | `hydrochloride` | `normalized_atomic_intervention` | `unresolved_formulation_relation` | leaves_primary_bucket |
| `CLM-5071bb2d8657…` | `BGJ398` | — | `exact_atomic_intervention` | `exact_intervention_form` | unchanged |
| `CLM-5071bb2d8657…` | `PD173074` | — | `exact_atomic_intervention` | `exact_intervention_form` | unchanged |
| `CLM-68b84650d65a…` | `pazopanib hydrochloride` | `hydrochloride` | `normalized_atomic_intervention` | `unresolved_formulation_relation` | leaves_primary_bucket |
| `CLM-6b6cb6d60b7c…` | `neratinib maleate` | `maleate` | `incompatible` | `unresolved_formulation_relation` | becomes_visible_instead_of_rejected |
| `CLM-75b47fea10f5…` | `alectinib hydrochloride` | `hydrochloride` | `normalized_atomic_intervention` | `unresolved_formulation_relation` | leaves_primary_bucket |
| `CLM-8a0fde4cfe05…` | `alectinib hydrochloride` | `hydrochloride` | `normalized_atomic_intervention` | `unresolved_formulation_relation` | leaves_primary_bucket |
| `CLM-90e863f00f13…` | `BGJ398` | — | `exact_atomic_intervention` | `exact_intervention_form` | unchanged |
| `CLM-90e863f00f13…` | `PD173074` | — | `exact_atomic_intervention` | `exact_intervention_form` | unchanged |
| `CLM-a7de634d04f6…` | `alectinib hydrochloride` | `hydrochloride` | `normalized_atomic_intervention` | `unresolved_formulation_relation` | leaves_primary_bucket |
| `CLM-af5265811e7a…` | `alectinib hydrochloride` | `hydrochloride` | `normalized_atomic_intervention` | `unresolved_formulation_relation` | leaves_primary_bucket |
| `CLM-bd4e24be0a47…` | `alectinib hydrochloride` | `hydrochloride` | `normalized_atomic_intervention` | `unresolved_formulation_relation` | leaves_primary_bucket |
| `CLM-cf53824b662b…` | `alectinib hydrochloride` | `hydrochloride` | `normalized_atomic_intervention` | `unresolved_formulation_relation` | leaves_primary_bucket |
| `CLM-d3951a629938…` | `alectinib hydrochloride` | `hydrochloride` | `normalized_atomic_intervention` | `unresolved_formulation_relation` | leaves_primary_bucket |

**12 claim** smettono di essere raggiunti nel bucket primario
da una query sulla moiety nuda e diventano audit-only. Va detto senza
attenuarlo: e' una perdita di copertura. Ma nessuna fonte lega quelle
forme alla propria moiety, e la copertura che si perde e' quella che la
tabella dei suffissi produceva senza averne il titolo. La voce resta
aperta come informational per una revisione terminologica esterna.

Nella direzione opposta, `neratinib maleate` smette di essere respinto
come farmaco estraneo e diventa visibile in audit: `maleate` non era
nella tupla, e la sua moiety veniva trattata come un'altra molecola.

## Simulazione

| Caso | Query | Claim | Relazione | Atteso |
|---|---|---|---|---|
| `case-and-space-variation-stays-primary` | `  INFIGRATINIB  ` | `infigratinib` | `normalized_exact_intervention_form` | **true** |
| `exact-form-stays-primary` | `infigratinib` | `infigratinib` | `exact_intervention_form` | **true** |
| `moiety-against-salt-in-repository` | `alectinib` | `alectinib hydrochloride` | `unresolved_formulation_relation` | **true** |
| `salt-form-exact-query-still-primary` | `alectinib hydrochloride` | `alectinib hydrochloride` | `exact_intervention_form` | **true** |
| `substring-is-not-a-form-token` | `phosphatermine` | `infigratinib` | `incompatible_active_moiety` | **true** |
| `two-different-salts-not-fused` | `infigratinib phosphate` | `infigratinib hydrochloride` | `unresolved_formulation_relation` | **true** |
| `unknown-salt-is-unresolved` | `alectinib besylate` | `alectinib hydrochloride` | `unresolved_formulation_relation` | **true** |
| `unregistered-salt-is-unresolved` | `infigratinib hydrochloride` | `infigratinib` | `unresolved_formulation_relation` | **true** |
| `unregistered-suffix-no-longer-invisible` | `neratinib` | `neratinib maleate` | `unresolved_formulation_relation` | **true** |
| `unrelated-drug-stays-rejected` | `erlotinib` | `infigratinib` | `incompatible_active_moiety` | **true** |
| `verified-salt-is-warning-not-primary` | `infigratinib phosphate` | `infigratinib` | `verified_salt_of_active_moiety` | **true** |
| `verified-salt-symmetric` | `infigratinib` | `infigratinib phosphate` | `verified_salt_of_active_moiety` | **true** |

## Il gate

Gate: `qualified_claim_structural_gate/1.1`  
Contratto di uscita: `qualified_claim_retrieval_result/1.3`

La relazione di forma entra nella congiunzione **dopo** l'identita'
dell'intervento e **prima** di direzione e punteggio. L'ordine non e'
estetico: l'identita' risponde a "e' lo stesso farmaco?", la forma a
"e' la stessa forma di quel farmaco?", e la seconda domanda ha senso solo
dopo la prima.

Un mismatch di forma non e' compensabile da disease exact, biomarcatore
exact, provenance, qualita' della fonte o punteggio elevato.

