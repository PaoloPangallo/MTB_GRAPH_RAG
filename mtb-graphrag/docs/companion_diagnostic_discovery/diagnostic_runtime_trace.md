# Traccia diagnostica fino al corpus V3

## Percorso osservato

    Drug - HAS_COMPANION_DIAGNOSTIC -> CompanionDiagnostic
      -> query/traversal legacy
      -> record di subgrafo o target result
      -> eventuale chunk RAG / visualizzazione

Questo percorso non prosegue nel materializzatore di qualified claims V3:

    Evidence -> v2_adapter -> EvidenceStatement -> shadow claim builder
            -> corpus materialization -> qualified_claim_repository/1.4

L'adapter V2 legge i campi di Evidence: direzione, tipo, significance,
citation_id e statement. Non legge device_name, platform_type, specimen_types
o associated_drug come campi di claim.

## File e funzioni

| fase | file/funzione | input | output/effetto | filtro o limite |
|---|---|---|---|---|
| query target | backend/pipeline/cypher.py, CYPHER_TARGET_POINT, _MP, _BIOMARKER | Drug e profilo | campi opzionali companion_diagnostic, cd_platform | match opzionale centrato sul Drug |
| subgrafo | backend/api/subgraph.py, CYPHER_SUBGRAPH_POINT, _MP | Drug e profilo | nodo CDx e arco HAS_COMPANION_DIAGNOSTIC | uso per subgrafo/visualizzazione |
| builder/agent | backend/pipeline/agents/target_identifier.py | target results | raggruppamento per farmaco | non crea claim CDx |
| RAG esplorativo | backend/evaluation/ablation_rag.py, CYPHER_CDX | Drug | chunk testuale | percorso ablation, non V3 |
| adattamento V2 | backend/pipeline/evidence/v2_adapter.py | Evidence | EvidenceStatement | nessun campo CDx |
| claim shadow | backend/pipeline/evidence/shadow/claims.py, non_therapeutic_claims.py | Evidence/audit | claim terapeutiche o diagnostic | DiagnosticClaim non è CompanionDiagnosticClaim |
| materializzazione | backend/pipeline/evidence/corpus/materialization.py | claim già costruite | JSONL di dominio | nessun join col grafo CDx |

## Primo punto di perdita

Il primo punto osservabile in cui il dato CDx non viene propagato nel percorso
V3 è l'adapter v2_adapter.py: il contratto di input è il record Evidence,
mentre i campi CDx appartengono a nodi separati collegati a Drug. Anche prima,
la query CDx non entra nel flusso evidence-to-claim. Il materializzatore riceve
quindi claim già prive di questi campi.

## Perché esistono solo due claim diagnostiche

La migrazione non terapeutica considera tre record espliciti:
evidence:347, evidence:1846, evidence:1847. Solo 1846 e 1847 hanno verdetto
diagnostic_claim_supported; il primo resta unresolved perché la direzione del
record non coincide con la fonte e la terapia nominata nella fonte non è
presente in modo claim-safe nel record. Le due claim attive derivano quindi da
Evidence auditato, non dai 166 nodi CDx.

## Confronto col dominio terapeutico

Il dominio terapeutico ha un percorso Evidence -> EvidenceStatement ->
intervention claim, con parent e source unit già parte del contratto. Il
dominio CDx dispone invece di un percorso di query/subgrafo e di campi
descrittivi sul device, ma non di un record evidence-to-claim con source unit,
locator, categoria diagnostica e relazione clinica esplicita.
