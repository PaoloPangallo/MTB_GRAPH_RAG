"""Nessuna fase ha toccato cio' che dichiarava congelato.

Otto fasi dichiarano un elenco di path congelati e verificano che
`git diff START..END` non li contenga. E' la stessa misura del perimetro vista
dall'altro lato: il perimetro dice *dove si poteva scrivere*, questo dice *dove
non si e' scritto*.

Anche qui il primo termine e' una revisione, e senza storia non esiste. Stavano
in otto `setUpClass` che si dichiaravano saltate appena mancava `.git`, portando
con se' ventinove test.

Le costanti restano nei moduli core che le dichiarano. Due nomi convivono da
prima di questa fase — `FROZEN_PATHS` e `FROZEN_OPERATIONAL_PATHS` — e non
vengono uniformati qui: rinominare una costante in otto moduli per far tornare
un elenco e' il genere di modifica che sembra pulizia e non lo e'.
"""

from __future__ import annotations

import importlib
import unittest

from backend.tests.phase_scope import PhaseScope

FROZEN_NAMES = ("FROZEN_PATHS", "FROZEN_OPERATIONAL_PATHS")

PHASE_MODULES = (
    "backend.tests.test_claim_type_retrieval_contract",
    "backend.tests.test_multi_intervention_adjudication",
    "backend.tests.test_multi_intervention_review_comparison",
    "backend.tests.test_multi_intervention_second_review",
    "backend.tests.test_non_therapeutic_claim_contract",
    "backend.tests.test_non_therapeutic_shadow_update",
    "backend.tests.test_non_therapeutic_source_closure",
    "backend.tests.test_typed_claim_shadow_migration",
)


def _frozen(module: object) -> tuple[str, ...]:
    for name in FROZEN_NAMES:
        if hasattr(module, name):
            return tuple(getattr(module, name))
    raise AttributeError(
        f"{module!r} non dichiara nessuno fra {FROZEN_NAMES}: senza un elenco "
        f"di path congelati non c'e' niente da verificare"
    )


class UntouchedArtifactTests(unittest.TestCase):
    def test_every_phase_declares_what_it_froze(self) -> None:
        for name in PHASE_MODULES:
            module = importlib.import_module(name)
            with self.subTest(module=name):
                self.assertTrue(_frozen(module))

    def test_no_phase_touched_what_it_declared_frozen(self) -> None:
        for name in PHASE_MODULES:
            module = importlib.import_module(name)
            scope = PhaseScope(
                module.REPO_ROOT.parent,
                module.START_SHA,
                module.PHASE_END_SHA,
                getattr(module, "ALLOWED_WRITE_PREFIXES", ()),
            )
            changed = scope.changed_paths()
            for path in _frozen(module):
                with self.subTest(module=name, path=path):
                    self.assertNotIn(path, changed)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
