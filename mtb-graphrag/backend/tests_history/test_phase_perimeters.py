"""Ogni fase ha scritto soltanto dentro il proprio perimetro.

Nove fasi, nove intervalli chiusi di commit. La misura e'
`git diff START..END`: senza storia non e' ricalcolabile, ed e' la ragione per
cui questi test stanno qui e non nella suite core.

Il perimetro si misura su un **intervallo chiuso**, mai contro HEAD. Un
`git diff START` aperto crescerebbe con la fase successiva e fallirebbe per la
ragione sbagliata — la proprieta' da verificare e' storica e chiusa, e va
misurata come tale.

Le costanti restano nei moduli core che le dichiarano: qui si importano, non si
ricopiano. Due copie dello stesso SHA divergono, e la seconda non verificherebbe
piu' la fase che dice di verificare.
"""

from __future__ import annotations

import importlib
import unittest

from backend.tests.phase_scope import PhaseScope

# I moduli core che dichiarano un perimetro di fase. L'elenco e' esplicito
# perche' aggiungere una fase senza dichiararne il perimetro sia una decisione
# visibile e non una dimenticanza.
PHASE_MODULES = (
    "backend.tests.test_diagnostic_disease_scope_narrowing_shadow",
    "backend.tests.test_disease_hierarchy_policy",
    "backend.tests.test_integrated_shadow_repository_1_3",
    "backend.tests.test_pre_promotion_audit_1_3",
    "backend.tests.test_pre_promotion_required_fixes_1_4",
    "backend.tests.test_prototype_corpus_promotion_1_4",
    "backend.tests.test_v3_conjunctive_query_closure",
    "backend.tests.test_v3_retriever_binding",
    "backend.tests.test_v3_retriever_regression_closure",
)

REQUIRED = ("REPO_ROOT", "START_SHA", "PHASE_END_SHA", "ALLOWED_WRITE_PREFIXES")


class PhasePerimeterTests(unittest.TestCase):
    """Il perimetro di ogni fase, misurato sull'intervallo che la chiude."""

    def test_every_declared_phase_exposes_its_perimeter(self) -> None:
        for name in PHASE_MODULES:
            module = importlib.import_module(name)
            for attribute in REQUIRED:
                with self.subTest(module=name, attribute=attribute):
                    self.assertTrue(
                        hasattr(module, attribute),
                        f"{name} non dichiara {attribute}: il perimetro non e' "
                        f"misurabile, e un perimetro non misurabile non e' un "
                        f"perimetro",
                    )

    def test_every_phase_wrote_only_inside_its_own_perimeter(self) -> None:
        for name in PHASE_MODULES:
            module = importlib.import_module(name)
            end = getattr(module, "PHASE_END_SHA", "")
            with self.subTest(phase=name):
                self.assertTrue(
                    end,
                    f"{name} non dichiara l'estremo di chiusura: una fase "
                    f"aperta non ha un perimetro da verificare",
                )
                scope = PhaseScope(
                    module.REPO_ROOT.parent,
                    module.START_SHA,
                    end,
                    module.ALLOWED_WRITE_PREFIXES,
                )
                self.assertEqual(scope.violations(scope.changed_paths()), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
