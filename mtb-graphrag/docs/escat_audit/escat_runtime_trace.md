# Trace ESCAT verso V3

## Percorso legacy calcolato

    Evidence.evidence_level
      -> query CYPHER_VARIANT_POINT / CYPHER_VARIANT_MP /
         CYPHER_VARIANT_BIOMARKER
      -> record con evidence_level e PMID
      -> backend/pipeline/agents/variant_interpreter.py
      -> MTBState.escat_tier
      -> agentic runtime
      -> API e frontend legacy

Le query leggono Evidence.evidence_level, significance, disease e PMID. Il
variant_interpreter costruisce un prompt che chiede un tier ESCAT globale e
usa un fallback basato su evidence_level e confronto testuale del tumore.
Questo è un calcolo runtime, non la propagazione di un'annotazione ESCAT del
grafo. Non sono stati eseguiti questi percorsi durante l'audit.

## Percorso V3 qualificato

    Evidence
      -> v2_adapter
      -> EvidenceStatement.evidence_level
      -> GraphEvidenceRecord / shadow claim
      -> qualified_claim_repository/1.4
      -> API V3

Nel v2_adapter:

- valori A/B/C/D vengono marcati come system civic;
- valori LEVEL_* vengono marcati come system oncokb;
- original_value viene conservato nell'EvidenceStatement;
- normalized_tier resta null;
- system=escat non viene assegnato.

I GraphEvidenceRecord attivi contengono biomarker_context,
disease_context, original_intervention_associations e raw lineage, ma non un
campo ESCAT. Le righe delle qualified claim attive non contengono
evidence_level né alcun campo ESCAT.

## Primo punto di perdita

Per ESCAT il primo punto di perdita non è materializzazione: il campo ESCAT
non entra mai dal grafo, perché non esiste nel record Evidence. Il campo
generico evidence_level viene invece preservato dall'adapter V2 come oggetto
CIViC/OncoKB, ma non è presente nelle claim materializzate. La perdita del
generic evidence_level avviene nella proiezione dallo statement/parent alle
qualified claim; non deve essere descritta come perdita di ESCAT.

## Rinomina e ambiguità

Il nome escat_tier compare in MTBState, negli output legacy e nelle API
legacy. È un campo derivato. Non è una rinomina automatica di
Evidence.evidence_level: il codice può interpellare un LLM e può applicare
fallback euristici. Questa semantica non è claim-level provenance e non è
propagata alla V3.
