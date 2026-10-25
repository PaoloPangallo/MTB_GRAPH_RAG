"""La rigenerazione degli artefatti dei fix 1.4, contro il gold.

Rigenerare questo artefatto richiede il bundle gold: il manifest incorpora il
checksum dell'albero del bundle (`bundle_present`, `sha256`), e senza l'ingresso
la rigenerazione produce `bundle_present: false`. Non e' un difetto del builder,
e' un confronto che senza il bundle non ha soggetto.

Stava in `backend/tests/test_pre_promotion_required_fixes_1_4.py`, dove si dichiarava saltato quando il bundle
mancava. Uno skip in una suite che si dice indipendente dagli ingressi esterni
e' una dipendenza scritta in piccolo: qui la dipendenza e' la collocazione.
"""

from __future__ import annotations

import unittest

from backend.tests import test_pre_promotion_required_fixes_1_4 as CORE


class RebuildTests(unittest.TestCase):
    """Cio' che il repository contiene e' cio' che il builder produce."""

    def test_rebuilding_reproduces_the_committed_artifacts(self) -> None:
        for name, text in CORE.build().items():
            with self.subTest(artifact=name):
                self.assertEqual(
                    (CORE.OUTPUT / name).read_text(encoding="utf-8"), text
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
