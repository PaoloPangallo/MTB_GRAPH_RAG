"""La rigenerazione degli artefatti di comparison, contro il gold.

Rigenerare questo artefatto richiede il bundle gold: il manifest incorpora il
checksum dell'albero del bundle (`bundle_present`, `sha256`), e senza l'ingresso
la rigenerazione produce `bundle_present: false`. Non e' un difetto del builder,
e' un confronto che senza il bundle non ha soggetto.

Stava in `backend/tests/test_multi_intervention_review_comparison.py`, dove si dichiarava saltato quando il bundle
mancava. Uno skip in una suite che si dice indipendente dagli ingressi esterni
e' una dipendenza scritta in piccolo: qui la dipendenza e' la collocazione.
"""

from __future__ import annotations

import unittest

from backend.tests import test_multi_intervention_review_comparison as CORE


class RebuildTests(unittest.TestCase):
    """Cio' che il repository contiene e' cio' che il builder produce."""

    def test_rebuilding_reproduces_the_committed_artifacts(self) -> None:
        for name, content in CORE.build(swap=False).items():
            with self.subTest(artifact=name):
                self.assertEqual(
                    content, (CORE.COMPARISON / name).read_text(encoding="utf-8")
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
