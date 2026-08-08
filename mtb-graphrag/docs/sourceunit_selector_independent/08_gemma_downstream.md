# Gemma downstream

The independent Gemma comparison was requested for 20 pairs and K=3/5/10, but it was not executed because the configured provider is `https://ollama.com` and the required `OLLAMA_API_KEY` or `RESEARCH_PIPELINE_LLM_API_KEY` was absent. The live stage correctly returned `LiveStageFailed` and did not fabricate output.

Therefore QUOTE, ABSTAIN, validated-quote, rejected-quote and wrong-quote rates are null, not zero. Retrieval metrics remain valid and independent of this unavailable downstream stage. The previous pilot evidence that Gemma can abstain remains historical pilot evidence and is not silently reused as independent evidence.
