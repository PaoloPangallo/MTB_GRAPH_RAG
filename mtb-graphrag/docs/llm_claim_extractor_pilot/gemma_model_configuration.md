# Configurazione modello Gemma

Tag richiesto (`gemma4-31b:cloud`) non trovato (`ollama show` -> "model not
found"). Tag usato al suo posto: `gemma4:cloud`, confermato disponibile via
`ollama show gemma4:cloud` -> architettura `gemma4`, 32682372656 parametri
(~31-32B, coerente con il nome richiesto), context length 262144, embedding
length 5376, quantizzazione BF16, capabilities: completion, thinking, tools,
vision.

Endpoint: `ollama_python_chat` (stesso endpoint usato per MiniMax, libreria
`ollama` PyPI, non `langchain-ollama`). Nessuna credenziale o API key
registrata.

Configurazione chiamata, identica a MiniMax: `temperature=0`, `top_p=1.0`,
`seed=run_index`, `num_predict=4096`, `think=False`. Transport
`llm-claim-proposal-transport/1.2`, prompt `llm-claim-extractor-prompt/1.3`,
schema `llm-claim-proposal/1.0`, validator
`deterministic-llm-proposal-validator/1.1` — tutti invariati rispetto a
MiniMax.

Tool calling: supportato, usato correttamente su tutte e 3 le chiamate
(`tool_call_count=1`, nome tool corretto `submit_flat_claim_proposal`).

Think: supportato e onorato su tutte e 3 le chiamate
(`thinking_disable_honored=true`, `thinking_length=0`) — a differenza di
MiniMax, che ha ignorato `think=False` su tutte e 3 le chiamate
(`thinking_disable_honored=false`, `thinking_length` fino a 13042 caratteri).

Context window disponibile: 262144 token (MiniMax non lo dichiara in questo
pilot).
