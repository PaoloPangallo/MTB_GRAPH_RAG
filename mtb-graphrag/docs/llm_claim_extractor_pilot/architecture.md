# Architettura

candidate + EvidenceBundle congelato + massimo quattro SourceUnit
→ provider constrained
→ proposta JSON
→ LlmClaimProposalValidator
→ ClaimSupportVerifier e policy bundle esistenti
→ support status finale non assegnato dall'LLM.

La parte C è additiva e offline. Non rigenera bundle, non cambia il retriever,
non legge il repository 1.4 e non produce gate, score o bucket. Il campione è
25 bundle derivati da 40 candidate.
