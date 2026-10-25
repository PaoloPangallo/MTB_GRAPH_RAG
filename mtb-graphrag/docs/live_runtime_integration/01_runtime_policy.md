# Runtime policy

LIVE and REPLAY are intentionally distinct:

- LIVE: GCA provenance -> authorized cache -> official API on miss -> canonical parser -> frozen deterministic selector -> Gemma V2 -> validator.
- REPLAY: recorded parser/document/bundle artifacts -> frozen `source_unit_ids` -> replay providers; no network and no live selector.

A LIVE miss never silently falls back to a recorded bundle.
