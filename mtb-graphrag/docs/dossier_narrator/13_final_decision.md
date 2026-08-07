# 13 — Decisione pre-freeze

# `READY_FOR_FREEZE`

L'ultimo tratto dell'architettura è implementato, verificato e non ha riaperto
alcun blocker.

## §41 — I criteri

| Criterio | Richiesto | Misurato |
|---|:-:|:-:|
| `new_p0` | 0 | **0** ✅ |
| `blocking_p1` | 0 | **0** ✅ |
| `canonical_dossier_preexists_narrator` | true | **true** ✅ |
| `narrator_can_change_canonical_status` | false | **false** ✅ |
| `narrator_can_change_support_mask` | false | **false** ✅ |
| `narrator_can_change_gate` | false | **false** ✅ |
| `narrative_verifier_uses_llm` | false | **false** ✅ |
| `unauthorized_entities_presented` | 0 | **0** ✅ |
| `status_escalations_presented` | 0 | **0** ✅ |
| `polarity_inversions_presented` | 0 | **0** ✅ |
| `unauthorized_quotes_presented` | 0 | **0** ✅ |
| `unauthorized_recommendations_presented` | 0 | **0** ✅ |
| `failed_narratives_presented` | 0 | **0** ✅ |
| `rq3_prompt_only_restrictions` | 0 | **0** ✅ |
| `rq3_uncontrolled_boundaries` | 0 | **0** ✅ |
| `frontend_build_passed` | true | **true** ✅ |
| `backend_tests_passed` | true | **true** ✅ |
| `evaluation_tests_passed` | true | **true** ✅ |

Diciotto su diciotto.

## §36 — Nessuna condizione di hard stop

Nessuna decision logic spostata nell'LLM; il Narrator riceve solo dati canonici;
non può modificare status, support mask o gate; il frontend non inferisce
validazione; nessuna narrativa fallita è mostrata; nessuna quote rigettata è
narrata come supporto; `Does Not Support` non può diventare positivo; il verifier
non usa un LLM e non giudica correttezza clinica; nessun secondo passaggio LLM;
GCA runtime invariato; OncoKB non chiamato; artifact storici invariati; nessun P0
riaperto; nessun nuovo P0.

## §42 — Le quindici domande

**1. Il dossier canonico è costruito prima di ogni chiamata al Narrator?**
Sì. Verificato per ordine degli stage, per sequenza dichiarata, per ordine degli
eventi nel ledger, e anche quando la narrazione non è disponibile.

**2. Gemma può modificare status, gate, support mask o provenance?**
No. Lo schema non ha campi che vi mappino, il trasporto rifiuta le chiavi extra,
e il dossier canonico è byte-identico con un narratore ostile.

**3. Il Narrator riceve esclusivamente informazioni già ammesse nel dossier?**
Sì. `build_narrator_input` legge solo il dossier canonico. Tre test verificano
per assenza che quote rigettate, `excluded_papers` e internals del validatore
non compaiano nella projection.

**4. Una candidate esclusa può comparire nella narrativa?**
No. Non entra nella projection, e un `candidate_id` sconosciuto produce
`NARRATIVE_UNKNOWN_CANDIDATE_ID`.

**5. Una quote rigettata può comparire come prova?**
No, su due strati: non raggiunge il modello, e se comparisse produrrebbe
`NARRATIVE_REJECTED_QUOTE_PROMOTED`.

**6. Una source `Does Not Support` può essere raccontata come supporto?**
No. `NARRATIVE_POLARITY_INVERSION` sulle affermazioni positive,
`NARRATIVE_NEGATION_LOST` se la negazione è semplicemente taciuta.

**7. Una candidate `AMBIGUOUS` può essere descritta come supportata?**
No. `NARRATIVE_STATUS_ESCALATION`. Il controllo è asimmetrico: una `DIRECT` può
esserlo.

**8. Il Narrator può introdurre farmaci, biomarcatori o fonti assenti?**
No. Entity closure su identificatori, simboli maiuscoli e radici INN — queste
ultime intercettano un farmaco inventato anche in minuscolo.

**9. Può produrre raccomandazioni terapeutiche non presenti nel dossier?**
No. Il dossier non contiene alcuna recommendation, quindi ogni formulazione
prescrittiva è non autorizzata. 24 pattern, italiano e inglese.

**10. Il Narrative Verifier è completamente deterministico e senza LLM?**
Sì. Un test verifica staticamente che il modulo non importi `requests`,
`transport`, `llm_config`, `ollama` né `call_narrator`. Stessa coppia di input →
stessa impronta.

**11. Se il verifier fallisce, il sistema mostra solo il dossier strutturato?**
Sì. `presentation_mode = STRUCTURED_DOSSIER_FALLBACK`, `narrative = null`
nell'API, e la UI mostra i reason code.

**12. L'integrazione ha riaperto un blocker chiuso?**
No. ISS-001…ISS-006 riverificati; sweep ISS-002 su 46 864 candidate: 1 936
negative, 0 promosse, 0 nel bucket primario.

**13. RQ3 rimane sostenibile dopo il terzo uso dell'LLM?**
Sì, e rafforzata: 7 `IMPOSSIBLE_BY_CONSTRUCTION`, 4 `VALIDATED_DOWNSTREAM`, 0
`PROMPT_ONLY_RESTRICTION`, 0 `UNCONTROLLED`.

**14. La narrativa è una presentation view e non una nuova fonte di decisione?**
Sì. È una foglia: il suo output non rientra nella catena che produce lo stato
canonico.

**15. Dopo questa fase il repository è pronto per il freeze?**
Sì.

## Una nota su come è andata

Due difetti sono emersi **dai test**, non dalla lettura del codice:

- il primo evento `STRUCTURED_FALLBACK_USED` non portava `stage_id` e rompeva
  l'invariante del ledger. L'ha trovato un test di integrità **preesistente**,
  scritto per proteggere il ledger e non per questa fase;
- il lexicon non normalizzava Unicode: in italiano la lettera accentata può
  arrivare in due forme, e senza NFC un modello ne avrebbe aggirato la policy
  scrivendo una frase indistinguibile a occhio nudo.

E la prima run LIVE del benchmark ha prodotto 3 FAIL che si sono rivelati **falsi
positivi del verifier**, non infedeltà del modello. Correggerli era necessario
quanto correggere un difetto opposto: un verifier troppo stretto spinge verso il
fallback permanente, cioè verso il non mostrare mai nulla.

## Verdetto

```
READY_FOR_FREEZE
```
