"""Audit read-only del repository shadow 1.3 prima di una promozione prototipale.

Il pacchetto non promuove nulla e non scrive fuori dalla propria directory di
output. Ogni modulo deriva le proprie conclusioni **dai file emessi dalla 1.3**,
non dal manifest della 1.3: un manifest che si autodichiara coerente non e' una
verifica, e la sola forma utile di audit e' quella che potrebbe contraddirlo.
"""

from __future__ import annotations

__all__ = [
    "findings",
    "gate_audit",
    "identity_audit",
    "inventory",
    "lineage_audit",
    "novelty",
    "plan_audit",
    "promotion",
    "provenance_audit",
    "scope",
]
