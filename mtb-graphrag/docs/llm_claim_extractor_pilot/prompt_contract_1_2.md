# Prompt contract 1.2

Il prompt richiede una sola chiamata a `submit_flat_claim_proposal`, nessun testo e nessun oggetto annidato. Gli ID e le quote devono essere array reali; i campi assenti usano value, ID e quote vuoti con `explicitness=ABSENT`. Il modello deve usare solo le SourceUnit, citare sottostringhe letterali, preservare negazione e contraddizione e astenersi quando necessario.

`think=false` viene richiesto, ma il thinking ? registrato separatamente e non entra negli argomenti o nella validazione.
