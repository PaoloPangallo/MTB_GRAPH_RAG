# Infrastruttura LLM esistente

L'audit ha trovato:

- backend/pipeline/llm/__init__.py, con costruzione lazy di ChatOllama;
- ollama_adapter.py, resolver e registry di modelli;
- configurazione e capability in model_resolver.py, model_registry.py,
  model_capabilities.py, credentials.py;
- backend/config/requirements.txt con langchain-ollama;
- manifest storici in benchmarks/mtb_evidence/model_selection/results/v1/.

Il nuovo adapter riusa backend.pipeline.llm.build_llm tramite
OllamaClaimExtractorProvider. Le variabili d'ambiente sono lette senza
registrarne i valori. Nel contesto corrente non risultano configurati endpoint
utilizzabili, modello attivo o credenziali operative: MODEL_NOT_CONFIGURED.

I manifest storici non sono stati trattati come configurazione attiva. Il
provider mock serve solo ai test del contratto.
