# Limitations

- Four queries are insufficient for inference; no significance test is run.
- The gold is provisional and lacks statement IDs and graded relevance.
- nDCG is therefore not computed.
- Historical V2 serialized order has no score comparable to V3.
- Historical V2 and V3 use different representations and candidate contracts.
- V3 native matching loses historical FGFR2 and EGFR coverage in this snapshot.
- Only one gold-claim projection receives a qualifier contribution.
- All qualification is `prototype_only`; no unit is `final`.
- Second review is absent, so linking and propagation are not final.
- Runtime is not comparable with the older agentic pipeline.
- Metrics do not measure clinical applicability, treatment recommendation
  quality, safety, physician agreement, or clinical utility.
