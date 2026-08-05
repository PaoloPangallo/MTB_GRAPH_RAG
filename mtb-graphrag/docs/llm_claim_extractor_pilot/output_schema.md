# Output schema llm-claim-proposal/1.0

La proposta contiene proposal_id, identità candidate/bundle/document, quattro
campi (disease, biomarker, intervention, direction) con valore normalizzato,
source unit, quote esatta e explicitness, oltre a relation type, claim text,
negation, contradiction, uncertainties e astensione.

proposal_id è derivato deterministicamente da candidate, bundle,
configurazione modello, indice di run e hash della risposta grezza. Il JSON è
strict: chiavi estranee, tipi errati e enum non ammessi sono rifiutati.
