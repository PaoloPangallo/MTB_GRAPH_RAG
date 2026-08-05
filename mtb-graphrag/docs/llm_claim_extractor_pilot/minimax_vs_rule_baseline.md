# MiniMax contro baseline B

La baseline ? usata come confronto tecnico, non come verit? clinica. Sono confrontati solo maschere, SourceUnit, cue e provenance gi? congelati.

## EB-b4c48ba003913f278ff182a6

- Baseline status: `DIRECT`
- Baseline core support mask: `{"biomarker": "SUPPORTED", "direction": "SUPPORTED", "disease": "SUPPORTED", "intervention": "SUPPORTED"}`
- Baseline SourceUnit: `SU-12a97ff4a9065ff0947b17c7, SU-6e4d5a52c9be05f545487ad0, SU-4c4ce81824f39e09575501ab, SU-df35f0a7e69e4930f88bdf5d`
- Baseline relation cues: `[]`
- Baseline field provenance: `{"biomarker": ["SU-4c4ce81824f39e09575501ab", "SU-6e4d5a52c9be05f545487ad0"], "direction": ["SU-4c4ce81824f39e09575501ab", "SU-6e4d5a52c9be05f545487ad0", "SU-df35f0a7e69e4930f88bdf5d"], "disease": ["SU-12a97ff4a9065ff0947b17c7", "SU-4c4ce81824f39e09575501ab", "SU-df35f0a7e69e4930f88bdf5d"], "intervention": ["SU-12a97ff4a9065ff0947b17c7", "SU-4c4ce81824f39e09575501ab", "SU-6e4d5a52c9be05f545487ad0"]}`
- MiniMax transport: `TOOL_CALL_VALID`; validator: `REJECTED_UNGROUNDED`
- Differenza: il modello non ha prodotto un insieme di campi/quote sufficientemente valido per modificare la maschera baseline.

## EB-2ae853e8abf1195cc4c84846

- Baseline status: `PARTIAL`
- Baseline core support mask: `{"biomarker": "SUPPORTED", "direction": "UNSUPPORTED", "disease": "UNSUPPORTED", "intervention": "NOT_APPLICABLE"}`
- Baseline SourceUnit: `SU-85b873d9e71a5bfd4adba10e, SU-9b966cc43a666add1d24c54f, SU-2f2b8a24fa60fde080f2d79c, SU-ca497cbc7c667f126f922e8c`
- Baseline relation cues: `[]`
- Baseline field provenance: `{"biomarker": ["SU-2f2b8a24fa60fde080f2d79c", "SU-85b873d9e71a5bfd4adba10e", "SU-9b966cc43a666add1d24c54f", "SU-ca497cbc7c667f126f922e8c"], "direction": [], "disease": [], "intervention": []}`
- MiniMax transport: `TOOL_CALL_VALID`; validator: `REJECTED_UNGROUNDED`
- Differenza: il modello non ha prodotto un insieme di campi/quote sufficientemente valido per modificare la maschera baseline.

## EB-6a291f12975b20b79e1c3dd7

- Baseline status: `CONTRADICTED`
- Baseline core support mask: `{"biomarker": "AMBIGUOUS", "direction": "AMBIGUOUS", "disease": "AMBIGUOUS", "intervention": "AMBIGUOUS"}`
- Baseline SourceUnit: `SU-3b689cb9cc6e59eab7b1d43e, SU-0fa3d66ee8b75632a00465b7, SU-999ca2e7f57dce9cf915928d, SU-fc4994778b8b27071aec221e`
- Baseline relation cues: `[]`
- Baseline field provenance: `{"biomarker": ["SU-fc4994778b8b27071aec221e"], "direction": ["SU-3b689cb9cc6e59eab7b1d43e", "SU-999ca2e7f57dce9cf915928d"], "disease": [], "intervention": []}`
- MiniMax transport: `TOOL_CALL_VALID`; validator: `REJECTED_DIRECTION`
- Differenza: il modello non ha prodotto un insieme di campi/quote sufficientemente valido per modificare la maschera baseline.
