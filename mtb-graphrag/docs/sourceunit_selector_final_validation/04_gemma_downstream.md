# Gemma downstream

Provider: Ollama Cloud / Paper Context Enricher V2. The key was loaded from the original `.env` into process memory only; it was not printed or persisted. All 20 independent pairs were executed under two conditions, GOLD and SELECTOR, with K=5 and the unchanged V2 prompt/transport/validator.

Both conditions: 20/20 transport success, 4 QUOTE, 16 ABSTAIN, 4 validated quotes, 0 rejected quotes. Validated quote rate is 0.2000 in both conditions; abstain rate is 0.8000 in both. Positive cases have 3/9 validated quotes; zero-direct cases have 1/11. There were zero wrong-document, wrong-source-unit, or wrongly accepted quote outcomes. Six positive-case abstentions are classified as QUESTIONABLE_ABSTAIN; ten zero-direct abstentions as CORRECT_ABSTAIN.
