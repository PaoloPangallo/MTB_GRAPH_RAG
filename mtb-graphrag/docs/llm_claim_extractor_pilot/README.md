# LLM Claim Extractor pilot

Il protocollo constrained è pronto sul campione congelato: 40 candidate e 25
EvidenceBundle. La run reale richiesta su glm-5.2:cloud è stata verificata ma
bloccata prima del pilot.

Ollama 0.18.3 riconosce il modello, mentre la chiamata restituisce 403
Forbidden perché è richiesto un abbonamento Cloud. Non sono stati usati
modelli alternativi, provider mock o output storici come risultati reali.

La parte C resta quindi non eseguita; A e B restano baseline congelate.
