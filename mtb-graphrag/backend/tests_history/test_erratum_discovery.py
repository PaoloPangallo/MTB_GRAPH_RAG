"""I tre erratum coincidono con cio' che una scansione da zero scopre.

La completezza e' la proprieta' che un elenco scritto a mano non ha, e questa
fase l'ha vista fallire due volte: le costanti `FROZEN` e
`KNOWN_UNREPRODUCIBLE` coprivano dieci referenze su ventisei, e la prima misura
degli alberi ne dava nove invece di quattro.

La discovery indicizza l'object database — quindi ha bisogno della storia. Nella
suite core resta il controllo che l'erratum sia *internamente* coerente e che le
sue impronte canoniche siano riprodotte dai file; qui si controlla la cosa che
solo la storia consente: che l'elenco non sia rimasto indietro rispetto al
repository.
"""

from __future__ import annotations

import unittest


class ArtifactHashErratumTests(unittest.TestCase):
    def test_it_matches_what_a_fresh_scan_discovers(self) -> None:
        import json

        from benchmarks.mtb_evidence.evaluation.scripts import (
            build_artifact_hash_erratum as BUILDER,
        )

        declared = json.loads(
            BUILDER.ERRATUM_PATH.read_text(encoding="utf-8")
        )
        discovered = BUILDER.discover()

        self.assertEqual(discovered["counts"], declared["counts"])
        self.assertEqual(sorted(discovered["sources"]), sorted(declared["sources"]))
        self.assertEqual(discovered["artifacts"], declared["artifacts"])
        for source, payload in discovered["sources"].items():
            with self.subTest(source=source):
                self.assertEqual(payload, declared["sources"][source])


class TreeHashErratumTests(unittest.TestCase):
    def test_it_matches_what_a_fresh_scan_discovers(self) -> None:
        from benchmarks.mtb_evidence.evaluation import tree_hash_erratum as ERRATUM
        from benchmarks.mtb_evidence.evaluation.scripts import (
            build_tree_hash_erratum as BUILDER,
        )

        declared = ERRATUM.erratum()
        discovered = BUILDER.build()

        self.assertEqual(discovered["counts"], declared["counts"])
        self.assertEqual(
            [tree["tree_root"] for tree in discovered["trees"]],
            [tree["tree_root"] for tree in declared["trees"]],
        )
        for found, expected in zip(
            discovered["trees"], declared["trees"], strict=True
        ):
            with self.subTest(tree=expected["tree_root"]):
                self.assertEqual(found["affected_paths"], expected["affected_paths"])
                self.assertEqual(found["text_files"], expected["text_files"])
                self.assertEqual(
                    found["canonical_lf_tree_sha256"],
                    expected["canonical_lf_tree_sha256"],
                )
                self.assertEqual(
                    found["historical_raw_tree_sha256"],
                    expected["historical_raw_tree_sha256"],
                )


class GeneratorProvenanceErratumTests(unittest.TestCase):
    def test_it_matches_what_a_fresh_scan_discovers(self) -> None:
        from benchmarks.mtb_evidence.evaluation import generator_provenance as ERRATUM
        from benchmarks.mtb_evidence.evaluation.scripts import (
            build_generator_provenance_erratum as BUILDER,
        )

        declared = ERRATUM.erratum()
        discovered = BUILDER.build()
        self.assertEqual(discovered["counts"], declared["counts"])
        self.assertEqual(discovered["entries"], declared["entries"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
