"""`artifact_hash_policy/2.0` e l'erratum che registra cosa non torna.

Il difetto che questi test impediscono e' rimasto invisibile per otto fasi. Gli
audit congelavano l'integrita' di un sorgente con lo sha256 dei suoi byte, e
verificavano quell'hash contro il file sul disco. Nessuno verificava che il file
sul disco fosse anche cio' che git consegna: su Windows la forma CRLF sul disco e
la forma LF nel blob sono due sequenze diverse, git le considera equivalenti, e
l'hash congelato descriveva la prima mentre il repository conservava la seconda.

I controlli qui guardano i byte che un checkout pulito scriverebbe — blob piu' la
conversione dichiarata in `.gitattributes` — e mai l'albero di lavoro: e'
esattamente la differenza fra i due che il difetto sfruttava.
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

from backend.pipeline.evidence.integrity import hash_policy as POLICY

REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_ROOT = REPO_ROOT.parent

ERRATUM_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "mtb_evidence"
    / "v3"
    / "hermetic_reproducibility_closure"
    / "artifact_hash_erratum.json"
)

_HEX64 = re.compile(r"\b[0-9a-f]{64}\b")
_GIT_TIMEOUT_SECONDS = 120


class PolicyTests(unittest.TestCase):
    """La normalizzazione e' dichiarata, e rifiuta cio' che non sa trattare."""

    def test_crlf_becomes_lf(self) -> None:
        self.assertEqual(POLICY.canonical_lf_bytes(b"a\r\nb\r\n"), b"a\nb\n")

    def test_lf_is_already_canonical(self) -> None:
        self.assertEqual(POLICY.canonical_lf_bytes(b"a\nb\n"), b"a\nb\n")

    def test_a_lone_carriage_return_is_refused(self) -> None:
        """Il rifiuto e' la promessa, non un dettaglio implementativo.

        Convertire anche il CR isolato darebbe la stessa impronta a due file
        diversi, cioe' toglierebbe a un'impronta l'unica cosa che deve fare.
        """
        with self.assertRaises(POLICY.LoneCarriageReturnError):
            POLICY.canonical_lf_bytes(b"a\rb")

    def test_a_lone_carriage_return_among_valid_line_endings_is_refused(self) -> None:
        with self.assertRaises(POLICY.LoneCarriageReturnError):
            POLICY.canonical_lf_bytes(b"a\r\nb\rc\r\n")

    def test_the_two_forms_of_the_same_text_share_one_canonical_hash(self) -> None:
        self.assertEqual(
            POLICY.canonical_lf_sha256(b"a\r\nb\r\n"),
            POLICY.canonical_lf_sha256(b"a\nb\n"),
        )

    def test_the_raw_hash_keeps_them_apart(self) -> None:
        self.assertNotEqual(
            POLICY.raw_sha256(b"a\r\nb\r\n"), POLICY.raw_sha256(b"a\nb\n")
        )

    def test_a_record_without_its_policy_version_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            POLICY.HashRecord.from_mapping(
                {
                    "canonical_lf_sha256": "a" * 64,
                    "historical_raw_sha256": "b" * 64,
                    "reason_code": POLICY.REASON_LEGACY_LINE_ENDING,
                }
            )

    def test_a_complete_record_round_trips(self) -> None:
        record = POLICY.HashRecord(
            historical_raw_sha256="b" * 64, canonical_lf_sha256="a" * 64
        )
        self.assertEqual(
            POLICY.HashRecord.from_mapping(record.as_dict()), record
        )
        self.assertTrue(record.diverges)


class ErratumCase(unittest.TestCase):
    """Base: l'erratum letto una volta, e i byte che un checkout scriverebbe."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.erratum = json.loads(ERRATUM_PATH.read_text(encoding="utf-8"))

    def _git(self, *args: str) -> bytes:
        result = subprocess.run(
            ["git", *args],
            cwd=GIT_ROOT,
            capture_output=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            self.skipTest("git non utilizzabile in questo checkout")
        return result.stdout

    def _checkout_bytes(self, relative: str) -> bytes:
        """I byte che un checkout pulito scriverebbe su disco.

        Non i byte del blob: fra il blob e il disco c'e' la conversione di fine
        riga dichiarata in `.gitattributes`, ed e' proprio quella conversione che
        l'impronta deve sopravvivere. Confrontare il blob nudo misurerebbe
        qualcosa che nessuno scrive mai.
        """
        path = f"mtb-graphrag/{relative}"
        blob = self._git("show", f"HEAD:{path}")
        attrs = self._git("check-attr", "text", "eol", "--", path).decode()
        declared = {
            line.rsplit(": ", 2)[-2]: line.rsplit(": ", 1)[-1].strip()
            for line in attrs.splitlines()
            if line.count(": ") >= 2
        }
        if declared.get("text") in ("unset", "false"):
            return blob
        if declared.get("eol") == "crlf":
            return blob.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        return blob


class ErratumShapeTests(ErratumCase):
    """L'erratum dichiara sotto quale politica e' stato scritto."""

    def test_it_declares_the_policy_and_the_normalization(self) -> None:
        self.assertEqual(
            self.erratum["hash_policy_version"], POLICY.POLICY_VERSION
        )
        self.assertEqual(self.erratum["normalization"], POLICY.NORMALIZATION)
        self.assertEqual(self.erratum["schema_version"], "artifact_hash_erratum/1.0")

    def test_every_source_carries_a_complete_record(self) -> None:
        for source, payload in self.erratum["sources"].items():
            with self.subTest(source=source):
                record = POLICY.HashRecord.from_mapping(payload)
                self.assertEqual(record.reason_code, POLICY.REASON_LEGACY_LINE_ENDING)
                self.assertEqual(record.hash_policy_version, POLICY.POLICY_VERSION)
                self.assertEqual(record.normalization, POLICY.NORMALIZATION)
                self.assertTrue(
                    record.diverges,
                    f"{source} non diverge: se l'impronta storica coincide con "
                    f"quella canonica, la voce non appartiene a un erratum",
                )

    def test_the_declared_counts_match_the_declared_content(self) -> None:
        counts = self.erratum["counts"]
        self.assertEqual(counts["sources"], len(self.erratum["sources"]))
        self.assertEqual(counts["artifacts"], len(self.erratum["artifacts"]))
        self.assertEqual(
            counts["references"],
            sum(
                len(payload["recorded_by"])
                for payload in self.erratum["sources"].values()
            ),
        )

    def test_the_artifact_list_is_exactly_what_the_sources_name(self) -> None:
        named = {
            artifact
            for payload in self.erratum["sources"].values()
            for artifact in payload["recorded_by"]
        }
        self.assertEqual(named, set(self.erratum["artifacts"]))


class ErratumIsTrueTests(ErratumCase):
    """Le due impronte dichiarate sono entrambe verificabili, oggi."""

    def test_every_source_is_tracked(self) -> None:
        for source in self.erratum["sources"]:
            with self.subTest(source=source):
                self.assertTrue((REPO_ROOT / source).is_file())

    def test_the_canonical_hash_is_what_a_clean_checkout_writes(self) -> None:
        """Il lato «presente» dell'erratum.

        Se questo fallisce, la forma canonica dichiarata non e' quella che il
        repository consegna, e l'erratum descrive una macchina invece del
        repository — lo stesso difetto, di nuovo.
        """
        for source, payload in self.erratum["sources"].items():
            with self.subTest(source=source):
                self.assertEqual(
                    POLICY.canonical_lf_sha256(self._checkout_bytes(source)),
                    payload["canonical_lf_sha256"],
                )

    def test_the_historical_hash_is_still_written_in_every_artifact(self) -> None:
        """Il lato «passato»: prova che nessun artefatto storico e' stato riscritto.

        E' il controllo che rende l'erratum una registrazione invece di una
        correzione. Se un artefatto smettesse di portare l'impronta storica,
        qualcuno lo avrebbe rigenerato, ed e' precisamente cio' che questa fase
        si e' impegnata a non fare.
        """
        for source, payload in self.erratum["sources"].items():
            historical = payload["historical_raw_sha256"]
            for artifact in payload["recorded_by"]:
                with self.subTest(source=source, artifact=artifact):
                    declared = (REPO_ROOT / artifact).read_text(encoding="utf-8")
                    self.assertIn(
                        historical,
                        set(_HEX64.findall(declared)),
                        f"{artifact} non registra piu' l'impronta storica di "
                        f"{source}: l'artefatto e' stato riscritto",
                    )

    def test_the_historical_blob_still_reproduces_the_historical_hash(self) -> None:
        """L'impronta storica e' ancora rifacibile, non solo ricordata."""
        for source, payload in self.erratum["sources"].items():
            with self.subTest(source=source):
                blob = self._git("cat-file", "blob", payload["historical_blob"])
                form = payload["historical_form"]
                if form == "crlf":
                    measured = POLICY.raw_sha256(
                        POLICY.canonical_lf_bytes(blob).replace(b"\n", b"\r\n")
                    )
                else:
                    measured = POLICY.raw_sha256(blob)
                self.assertEqual(measured, payload["historical_raw_sha256"])

    def test_no_canonical_hash_is_already_written_in_its_artifacts(self) -> None:
        """Se una coppia si chiudesse, la voce andrebbe tolta, non lasciata qui.

        Un erratum che nessuno rivede diventa un elenco di cose vere una volta
        sola. Questo fallisce quando il disallineamento e' stato chiuso davvero,
        e chiede di registrarlo invece di lasciarlo scritto come aperto.
        """
        for source, payload in self.erratum["sources"].items():
            canonical = payload["canonical_lf_sha256"]
            for artifact in payload["recorded_by"]:
                with self.subTest(source=source, artifact=artifact):
                    declared = (REPO_ROOT / artifact).read_text(encoding="utf-8")
                    self.assertNotIn(
                        canonical,
                        set(_HEX64.findall(declared)),
                        f"{artifact} ora registra anche l'impronta canonica di "
                        f"{source}: il disallineamento e' chiuso, togli la voce "
                        f"dall'erratum",
                    )


class ErratumIsCompleteTests(ErratumCase):
    """L'erratum e' cio' che il repository contiene, non cio' che ricordiamo."""

    def test_it_matches_what_a_fresh_scan_discovers(self) -> None:
        """La completezza e' la proprieta' che una lista scritta a mano non ha.

        Le due costanti che questo erratum sostituisce coprivano 10 referenze su
        26 e omettevano due sorgenti interi, e nessuno se n'era accorto perche'
        nessun controllo confrontava la lista con il repository. Qui la lista
        viene rifatta da zero e confrontata: se qualcuno congela una nuova
        impronta non riproducibile, o ne chiude una, il test lo dice.
        """
        try:
            from benchmarks.mtb_evidence.evaluation.scripts import (
                build_artifact_hash_erratum as BUILDER,
            )
        except ImportError as error:  # pragma: no cover
            self.skipTest(f"generatore non importabile: {error}")

        try:
            discovered = BUILDER.discover()
        except subprocess.SubprocessError as error:
            self.skipTest(f"git non utilizzabile in questo checkout: {error}")

        self.assertEqual(discovered["counts"], self.erratum["counts"])
        self.assertEqual(
            sorted(discovered["sources"]), sorted(self.erratum["sources"])
        )
        self.assertEqual(discovered["artifacts"], self.erratum["artifacts"])
        for source, payload in discovered["sources"].items():
            with self.subTest(source=source):
                self.assertEqual(payload, self.erratum["sources"][source])


class NoLoneCarriageReturnTests(ErratumCase):
    """Nessun sorgente operativo porta piu' un CR aggiunto per far tornare un hash."""

    def test_the_operational_sources_are_canonical(self) -> None:
        for source in self.erratum["sources"]:
            if not source.startswith("backend/"):
                continue
            with self.subTest(source=source):
                blob = self._git("show", f"HEAD:mtb-graphrag/{source}")
                # Non solleva: se sollevasse, un CR isolato sarebbe tornato.
                self.assertEqual(POLICY.canonical_lf_bytes(blob), blob)


class GeneratorProvenanceErratumTests(unittest.TestCase):
    """L'erratum di provenance e' distinto, e resta vero.

    Separato da `artifact_hash_erratum` perche' registra un fatto diverso: la'
    il file e' lo stesso e cambia la forma dei byte, qui il file e' proprio un
    altro e nessuna normalizzazione lo riporta indietro. Due cose che si
    chiudono in modi diversi non stanno bene sotto lo stesso nome.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from benchmarks.mtb_evidence.evaluation import (
            generator_provenance as PROVENANCE,
        )

        cls.provenance = PROVENANCE
        cls.erratum = PROVENANCE.erratum()

    def test_it_declares_its_own_schema(self) -> None:
        self.assertEqual(
            self.erratum["schema_version"], "generator_provenance_erratum/1.0"
        )
        # E' un file distinto da `artifact_hash_erratum.json`, non lo stesso
        # sotto altro nome: i due registrano fatti che si chiudono in modi
        # diversi.
        self.assertNotEqual(self.provenance.ERRATUM_PATH, ERRATUM_PATH)

    def test_every_entry_carries_the_declared_fields(self) -> None:
        required = {
            "artifact_generation_version",
            "current_generator_compatibility",
            "current_generator_sha256",
            "historical_artifact_path",
            "historical_generator_path",
            "historical_generator_sha256",
            "historical_reproducibility_status",
            "reason_code",
        }
        for entry in self.erratum["entries"]:
            with self.subTest(artifact=entry["historical_artifact_path"]):
                self.assertEqual(required - set(entry), set())
                self.assertIsNotNone(entry["artifact_generation_version"])

    def test_every_diverging_entry_carries_the_declared_reason_code(self) -> None:
        for entry in self.erratum["entries"]:
            if entry["historical_generator_sha256"] == entry["current_generator_sha256"]:
                continue
            with self.subTest(artifact=entry["historical_artifact_path"]):
                self.assertEqual(
                    entry["reason_code"],
                    "GENERATOR_SOURCE_EVOLVED_AFTER_FROZEN_ARTIFACT",
                )

    def test_the_current_hash_is_the_generator_as_it_is_now(self) -> None:
        """Se il generatore cambia ancora, l'erratum lo deve dire."""
        for entry in self.erratum["entries"]:
            with self.subTest(generator=entry["historical_generator_path"]):
                self.assertEqual(
                    entry["current_generator_sha256"],
                    self.provenance.current_generator_sha256(entry),
                )

    def test_the_historical_artifact_still_declares_the_historical_hash(self) -> None:
        """Prova che nessun manifest storico e' stato riscritto per chiudere il caso."""
        for entry in self.erratum["entries"]:
            with self.subTest(artifact=entry["historical_artifact_path"]):
                self.provenance.check_historical_integrity(
                    entry["historical_artifact_path"]
                )

    def test_a_declared_exception_covers_a_real_divergence(self) -> None:
        """Una deroga su un campo che coincide sarebbe una riga morta."""
        for entry in self.erratum["entries"]:
            with self.subTest(artifact=entry["historical_artifact_path"]):
                if entry["non_reproducible_fields"]:
                    self.assertNotEqual(
                        entry["historical_generator_sha256"],
                        entry["current_generator_sha256"],
                    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
