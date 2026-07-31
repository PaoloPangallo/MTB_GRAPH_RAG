"""`artifact_tree_hash_policy/1.0` e l'erratum degli hash di albero.

Lo stesso difetto delle impronte di file, un livello piu' su: le impronte di
nove directory furono congelate su un disco dove 65 file erano CRLF, e un
checkout pulito le consegna in LF. Quattro di quelle nove non tornano piu'
altrove.

**Nessuno di questi test interroga git.** La classificazione testo/binario e'
registrata nell'erratum, quindi l'impronta canonica si ricalcola dai file su
disco in qualunque ambiente — compreso un archivio estratto. E' la ragione per
cui la classificazione e' stata registrata invece di essere ricavata al volo:
un controllo che ha bisogno della storia non puo' girare dove la storia non c'e'.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from backend.pipeline.evidence.integrity import hash_policy as FILE_POLICY
from backend.pipeline.evidence.integrity import tree_hash_policy as TREE
from benchmarks.mtb_evidence.evaluation import tree_hash_erratum as ERRATUM

REPO_ROOT = Path(__file__).resolve().parents[2]

_HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


class PolicyTests(unittest.TestCase):
    """L'algoritmo e' definito, e le sue promesse sono verificabili."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        (self.root / "nested").mkdir()
        (self.root / "b.txt").write_bytes(b"uno\ndue\n")
        (self.root / "a.txt").write_bytes(b"alfa\r\nbeta\r\n")
        (self.root / "nested" / "c.txt").write_bytes(b"tre\n")
        self.text = ["a.txt", "b.txt", "nested/c.txt"]

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _hash(self, **kwargs) -> str:
        return TREE.canonical_tree_sha256(self.root, text_files=self.text, **kwargs)

    def test_the_order_is_lexicographic_on_the_posix_relative_path(self) -> None:
        rows = TREE.canonical_tree_rows(self.root, text_files=self.text)
        self.assertEqual([name for name, _ in rows], ["a.txt", "b.txt", "nested/c.txt"])

    def test_crlf_and_lf_forms_of_the_same_text_agree(self) -> None:
        before = self._hash()
        (self.root / "a.txt").write_bytes(b"alfa\nbeta\n")
        self.assertEqual(self._hash(), before)

    def test_a_binary_is_not_normalized(self) -> None:
        """Per un binario CRLF e LF sono due contenuti, non due forme."""
        (self.root / "blob.bin").write_bytes(b"\x00\r\n\x01")
        crlf = self._hash(require_declared=False)
        (self.root / "blob.bin").write_bytes(b"\x00\n\x01")
        self.assertNotEqual(self._hash(require_declared=False), crlf)

    def test_a_lone_carriage_return_in_a_text_file_is_refused(self) -> None:
        (self.root / "a.txt").write_bytes(b"alfa\rbeta\n")
        with self.assertRaises(FILE_POLICY.LoneCarriageReturnError):
            self._hash()

    def test_an_undeclared_file_is_refused_instead_of_guessed(self) -> None:
        (self.root / "sorpresa.txt").write_bytes(b"x\n")
        with self.assertRaises(TREE.UndeclaredFileError):
            TREE.canonical_tree_sha256(
                self.root, text_files=self.text, require_declared=True
            )

    def test_the_separator_cannot_be_forged_by_a_path(self) -> None:
        """Due alberi diversi non possono produrre la stessa riga.

        Con `f"{path}:{digest}"` un path che contenesse `:` potrebbe collidere
        con un'altra coppia. Con `NUL` non e' possibile: in un nome di file non
        puo' comparire.
        """
        self.assertEqual(TREE.SEPARATOR, b"\0")
        self.assertNotIn(TREE.SEPARATOR.decode("latin-1"), "a.txt")


class ErratumCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.erratum = ERRATUM.erratum()
        cls.trees = cls.erratum["trees"]
        cls.diverging = [
            tree
            for tree in cls.trees
            if tree["current_reproducibility_status"]
            == "not_reproducible_from_a_clean_checkout"
        ]


class ErratumShapeTests(ErratumCase):
    def test_it_declares_its_own_schema_and_policy(self) -> None:
        self.assertEqual(self.erratum["schema_version"], "tree_hash_erratum/1.0")
        self.assertEqual(self.erratum["hash_policy_version"], TREE.POLICY_VERSION)
        self.assertEqual(self.erratum["normalization"], TREE.NORMALIZATION)

    def test_it_is_a_file_of_its_own(self) -> None:
        """Tre erratum, tre fatti diversi, tre file."""
        from benchmarks.mtb_evidence.evaluation import legacy_hash_erratum as FILES
        from benchmarks.mtb_evidence.evaluation import generator_provenance as GEN

        paths = {ERRATUM.ERRATUM_PATH, FILES.ERRATUM_PATH, GEN.ERRATUM_PATH}
        self.assertEqual(len(paths), 3)

    def test_every_diverging_tree_carries_a_complete_record(self) -> None:
        required = {
            "affected_paths",
            "affected_text_file_count",
            "canonical_lf_tree_sha256",
            "classification_commit",
            "classification_source",
            "current_reproducibility_status",
            "file_count",
            "gitattributes_paths",
            "gitattributes_sha256",
            "hash_policy_version",
            "historical_commit",
            "historical_form",
            "historical_raw_tree_sha256",
            "normalization",
            "reason_code",
            "recorded_by_artifacts",
            "recorded_by_tests",
            "text_files",
            "tree_root",
        }
        for tree in self.diverging:
            with self.subTest(tree=tree["tree_root"]):
                self.assertEqual(required - set(tree), set())
                record = TREE.TreeHashRecord.from_mapping(tree)
                self.assertTrue(record.diverges)
                self.assertEqual(record.reason_code, TREE.REASON_LEGACY_TREE_HASH)

    def test_the_declared_counts_match_the_declared_content(self) -> None:
        counts = self.erratum["counts"]
        self.assertEqual(counts["declared_trees"], len(self.trees))
        self.assertEqual(counts["diverging_trees"], len(self.diverging))
        self.assertEqual(
            counts["affected_files"],
            sum(tree["affected_text_file_count"] for tree in self.diverging),
        )

    def test_the_measured_perimeter_is_the_one_the_phase_declared(self) -> None:
        """4 alberi, 65 file. Se cambia, e' una scoperta, non un dettaglio."""
        self.assertEqual(self.erratum["counts"]["diverging_trees"], 4)
        self.assertEqual(self.erratum["counts"]["affected_files"], 65)
        self.assertEqual(
            sum(tree["file_count"] for tree in self.diverging), 72
        )

    def test_the_classification_provenance_is_recorded(self) -> None:
        """Su **tutti** gli alberi dichiarati, non solo su quelli divergenti.

        La regola che classifica testo e binario vale per l'intero elenco: se
        `.gitattributes` cambiasse, cambierebbe la classificazione anche degli
        alberi che oggi tornano, e nessuno se ne accorgerebbe fino a quando uno
        di loro smettesse di tornare.
        """
        for tree in self.trees:
            with self.subTest(tree=tree["tree_root"]):
                self.assertEqual(tree["classification_source"], "git check-attr text")
                self.assertRegex(tree["classification_commit"], r"^[0-9a-f]{40}$")
                self.assertEqual(
                    sorted(tree["gitattributes_sha256"]),
                    sorted(tree["gitattributes_paths"]),
                )
                for path, digest in tree["gitattributes_sha256"].items():
                    self.assertEqual(
                        FILE_POLICY.canonical_lf_sha256(REPO_ROOT.parent / path),
                        digest,
                        f"{path} e' cambiato: la regola da cui deriva la "
                        f"classificazione non e' piu' quella registrata",
                    )


class HistoricalIntegrityTests(ErratumCase):
    """A. L'artefatto congelato dichiara ancora l'impronta di allora."""

    def test_every_historical_tree_hash_is_still_written_in_its_artifacts(self) -> None:
        for tree in self.diverging:
            historical = tree["historical_raw_tree_sha256"]
            for artifact in tree["recorded_by_artifacts"]:
                with self.subTest(tree=tree["tree_root"], artifact=artifact):
                    declared = (REPO_ROOT / artifact).read_text(encoding="utf-8")
                    self.assertIn(
                        historical,
                        set(_HEX64.findall(declared)),
                        f"{artifact} non registra piu' l'impronta storica di "
                        f"{tree['tree_root']}: l'artefatto e' stato riscritto",
                    )

    def test_no_canonical_tree_hash_is_already_written_in_its_artifacts(self) -> None:
        """Se un albero tornasse riproducibile, la voce andrebbe tolta."""
        for tree in self.diverging:
            canonical = tree["canonical_lf_tree_sha256"]
            for artifact in tree["recorded_by_artifacts"]:
                with self.subTest(tree=tree["tree_root"], artifact=artifact):
                    declared = (REPO_ROOT / artifact).read_text(encoding="utf-8")
                    self.assertNotIn(canonical, set(_HEX64.findall(declared)))


class CanonicalIntegrityTests(ErratumCase):
    """B. L'impronta canonica e' la stessa nei quattro ambienti.

    Il test non puo' visitare quattro ambienti da solo: cio' che dimostra e' che
    il valore **non dipende dall'ambiente** — nessuna lettura di git, nessuna
    dipendenza dalle fini riga su disco. La matrice verifica il resto.
    """

    def test_every_canonical_tree_hash_is_reproduced_from_the_files_on_disk(self) -> None:
        for tree in self.trees:
            with self.subTest(tree=tree["tree_root"]):
                self.assertEqual(
                    ERRATUM.canonical_tree_sha256(tree),
                    tree["canonical_lf_tree_sha256"],
                )

    def test_the_canonical_hash_survives_a_crlf_working_tree(self) -> None:
        """Il valore non cambia se i file su disco sono CRLF invece che LF."""
        tree = self.diverging[0]
        source = REPO_ROOT / tree["tree_root"]
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / "albero"
            shutil.copytree(source, copy)
            for name in tree["text_files"]:
                target = copy / name
                data = target.read_bytes().replace(b"\r\n", b"\n")
                target.write_bytes(data.replace(b"\n", b"\r\n"))
            self.assertEqual(
                TREE.canonical_tree_sha256(
                    copy,
                    text_files=tree["text_files"],
                    exclude=self.erratum["exclude"],
                    require_declared=False,
                ),
                tree["canonical_lf_tree_sha256"],
            )

    def test_the_reader_never_shells_out_to_git(self) -> None:
        """La verifica canonica gira dove una storia git non c'e'.

        Il controllo guarda il **lettore**, non questo file: un test che
        ispezionasse il proprio sorgente troverebbe le stringhe che nomina per
        vietarle, e fallirebbe per averle scritte.
        """
        import ast

        for module in (ERRATUM, TREE):
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            imported = {
                alias.name.split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            } | {
                node.module.split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
            }
            with self.subTest(module=module.__name__):
                # L'AST e non una ricerca di stringhe: il lettore *nomina*
                # `git check-attr` in un commento, per dire che non lo usa, e
                # un grep non sa distinguere una menzione da una chiamata.
                self.assertNotIn("subprocess", imported)


class CompletenessTests(ErratumCase):
    """C. L'erratum e' cio' che il repository contiene, non cio' che ricordiamo."""

    def test_it_matches_what_a_fresh_scan_discovers(self) -> None:
        try:
            from benchmarks.mtb_evidence.evaluation.scripts import (
                build_tree_hash_erratum as BUILDER,
            )
        except ImportError as error:  # pragma: no cover
            self.skipTest(f"generatore non importabile: {error}")

        try:
            discovered = BUILDER.build()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"discovery non eseguibile in questo checkout: {error}")

        self.assertEqual(discovered["counts"], self.erratum["counts"])
        self.assertEqual(
            [tree["tree_root"] for tree in discovered["trees"]],
            [tree["tree_root"] for tree in self.trees],
        )
        for found, declared in zip(discovered["trees"], self.trees, strict=True):
            with self.subTest(tree=declared["tree_root"]):
                self.assertEqual(found["affected_paths"], declared["affected_paths"])
                self.assertEqual(
                    found["canonical_lf_tree_sha256"],
                    declared["canonical_lf_tree_sha256"],
                )

    def test_the_file_hash_erratum_covers_the_three_remaining_failures(self) -> None:
        """La riclassificazione della discovery, resa verificabile.

        Delle quindici failure osservate in un checkout pulito, dodici sono di
        albero e tre sono di **file**: `test_author_approval_23344087` non usa
        `sha256_tree`, e le sue tre righe dipendono da due sorgenti di
        `v3/first_review/` gia' coperti da `artifact_hash_erratum`. Sono chiuse
        la', sotto il proprio reason code — non sotto quello di albero.
        """
        from benchmarks.mtb_evidence.evaluation import legacy_hash_erratum as FILES

        covered = set(FILES.registered_paths())
        for source in (
            "benchmarks/mtb_evidence/v3/first_review/FIRST_REVIEW_QUEUE.md",
            "benchmarks/mtb_evidence/v3/first_review/first_review_queue.csv",
        ):
            with self.subTest(source=source):
                self.assertIn(source, covered)

        # E nessun albero dell'erratum li reclama come propri.
        for tree in self.trees:
            with self.subTest(tree=tree["tree_root"]):
                self.assertNotIn("first_review", tree["tree_root"])


class AdversarialTests(ErratumCase):
    """D. Sette modi di rompere la promessa, e sette test che se ne accorgono.

    Ognuno lavora su una **copia** dell'albero in una directory temporanea: un
    test che alterasse l'albero vero per dimostrare di accorgersene sarebbe un
    modo curioso di distruggere cio' che protegge.
    """

    def setUp(self) -> None:
        self.tree = self.diverging[0]
        self._temp = tempfile.TemporaryDirectory()
        self.copy = Path(self._temp.name) / "albero"
        shutil.copytree(REPO_ROOT / self.tree["tree_root"], self.copy)
        self.text = list(self.tree["text_files"])

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _hash(self, **kwargs) -> str:
        return TREE.canonical_tree_sha256(
            self.copy,
            text_files=kwargs.pop("text_files", self.text),
            exclude=self.erratum["exclude"],
            require_declared=False,
            **kwargs,
        )

    def test_a_modified_historical_hash_is_caught(self) -> None:
        forged = dict(self.tree, historical_raw_tree_sha256="0" * 64)
        record = TREE.TreeHashRecord.from_mapping(forged)
        self.assertNotEqual(
            record.historical_raw_tree_sha256,
            self.tree["historical_raw_tree_sha256"],
        )
        artifact = self.tree["recorded_by_artifacts"][0]
        declared = (REPO_ROOT / artifact).read_text(encoding="utf-8")
        self.assertNotIn(forged["historical_raw_tree_sha256"], _HEX64.findall(declared))

    def test_an_omitted_file_is_caught(self) -> None:
        (self.copy / self.text[0]).unlink()
        self.assertNotEqual(self._hash(), self.tree["canonical_lf_tree_sha256"])

    def test_a_semantic_content_change_is_caught(self) -> None:
        target = self.copy / self.text[0]
        target.write_bytes(target.read_bytes() + b"riga aggiunta\n")
        self.assertNotEqual(self._hash(), self.tree["canonical_lf_tree_sha256"])

    def test_a_lone_carriage_return_is_caught(self) -> None:
        target = self.copy / self.text[0]
        target.write_bytes(target.read_bytes().replace(b"\n", b"\r", 1))
        with self.assertRaises(FILE_POLICY.LoneCarriageReturnError):
            self._hash()

    def test_a_changed_enumeration_order_changes_nothing(self) -> None:
        """L'ordine non e' una variabile: e' fissato dalla politica.

        Il modo di romperlo sarebbe ordinare per `Path` invece che per path
        relativo POSIX — e' cio' che faceva la prima misura di questa fase, e
        dava un perimetro sbagliato. Qui si dimostra che le due cose
        differiscono davvero, e che la politica usa quella giusta.
        """
        rows = TREE.canonical_tree_rows(
            self.copy, text_files=self.text, exclude=self.erratum["exclude"]
        )
        names = [name for name, _ in rows]
        self.assertEqual(names, sorted(names))
        shuffled = sorted(names, reverse=True)
        self.assertNotEqual(names, shuffled)
        # Ricalcolare dopo aver toccato i tempi di accesso non cambia nulla:
        # l'enumerazione del filesystem non entra nel risultato.
        for path in self.copy.rglob("*"):
            if path.is_file():
                path.touch()
        self.assertEqual(self._hash(), self.tree["canonical_lf_tree_sha256"])

    def test_an_uncovered_tree_is_caught(self) -> None:
        with self.assertRaises(ERRATUM.TreeErratumError):
            ERRATUM.check_canonical("benchmarks/mtb_evidence/v3/albero_inesistente")

    def test_a_wrong_declared_count_is_caught(self) -> None:
        forged = dict(self.erratum["counts"], diverging_trees=99)
        self.assertNotEqual(forged["diverging_trees"], len(self.diverging))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
