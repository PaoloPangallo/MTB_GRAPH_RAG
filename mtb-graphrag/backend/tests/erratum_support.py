"""Verificare un'impronta congelata senza far finta che sia riproducibile.

Dodici artefatti di otto fasi chiuse registrano l'impronta di otto sorgenti
misurati nella forma CRLF di una macchina Windows. Un checkout pulito consegna
LF, quindi il confronto diretto fra il file e l'impronta congelata fallisce, e
fallisce dicendo la verita': quell'impronta non descrive questi byte.

Il modo sbagliato di chiudere il caso e' rendere il confronto piu' debole —
confrontare ignorando le fini riga, o normalizzare in silenzio. Diventerebbe un
controllo che passa sempre, e la prossima volta che un sorgente cambia davvero
nessuno se ne accorge.

Il modo giusto e' dire esattamente cosa si sta verificando: **il file e' ancora
quello che l'artefatto congelato descriveva**, e ci sono due modi di esserlo.

    1. l'impronta canonica del file coincide con quella dichiarata — il caso
       normale, nessuna mediazione;
    2. l'erratum registra la divergenza per quel path, l'impronta dichiarata e'
       quella storica che l'erratum riporta, **e** il file ha ancora la forma
       canonica che l'erratum gli attribuisce.

Il terzo congiunto del secondo caso e' cio' che tiene in piedi il controllo: se
il sorgente cambia, la sua forma canonica non e' piu' quella registrata e
l'asserzione fallisce, erratum o no.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.pipeline.evidence.integrity import hash_policy as POLICY
from benchmarks.mtb_evidence.evaluation import legacy_hash_erratum as ERRATUM

REPO_ROOT = Path(__file__).resolve().parents[2]


def assert_frozen_digest(
    case: unittest.TestCase,
    path: Path | str,
    declared: str,
    *,
    context: str = "",
) -> None:
    """Il file e' ancora quello che l'impronta congelata descriveva."""
    path = Path(path)
    where = f" ({context})" if context else ""
    canonical = POLICY.canonical_lf_sha256(path)
    if canonical == declared:
        return

    relative = path.resolve().relative_to(REPO_ROOT).as_posix()
    entry = ERRATUM.erratum()["sources"].get(relative)
    case.assertIsNotNone(
        entry,
        f"{relative}{where} non coincide con l'impronta congelata {declared} e "
        f"non e' registrato nell'erratum: il sorgente e' cambiato, oppure "
        f"l'erratum e' incompleto",
    )
    assert entry is not None  # per i type checker: assertIsNotNone non restringe
    case.assertEqual(
        declared,
        entry["historical_raw_sha256"],
        f"{relative}{where} porta un'impronta congelata che l'erratum non "
        f"conosce: registrata {declared}, storica dichiarata "
        f"{entry['historical_raw_sha256']}",
    )
    case.assertEqual(
        canonical,
        entry["canonical_lf_sha256"],
        f"{relative}{where} non ha piu' la forma canonica che l'erratum gli "
        f"attribuisce: il file e' cambiato e l'impronta storica non lo descrive "
        f"piu'",
    )


__all__ = ["assert_frozen_digest"]
