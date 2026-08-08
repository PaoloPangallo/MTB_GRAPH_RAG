# Zero-direct cases

There are 11 cases with no directly relevant unit. The frozen selector always returns top-5 units by design; it has no `NO_RELEVANT_SOURCE_UNIT` output. Therefore true-negative is not claimed. All 11 select at least one unit; 1 includes partial material, 6 include context-only material, and 6 include not-relevant material (categories overlap). The potential false-direct-signal rate is 11/11 under the conservative operational definition, but this is not a support decision: Gemma and the validator remain responsible for QUOTE/ABSTAIN.
