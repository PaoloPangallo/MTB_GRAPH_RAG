"""Cio' che git conserva coincide con cio' che il checkout scrive.

E' la domanda da cui e' nata l'intera fase: gli audit misuravano il file sul
disco e nessuno verificava che quel file fosse anche cio' che git conserva. Su
Windows la forma CRLF sul disco e la forma LF nel blob sono due sequenze
diverse, git le considera equivalenti, e l'impronta congelata descriveva la
prima mentre il repository conservava la seconda.

Rispondere richiede **entrambi** i termini: il blob e il disco. Senza storia c'e'
solo il secondo, e il confronto perde il soggetto — per questo questi controlli
stanno qui e non nella suite core, che ne conserva la meta' misurabile ovunque
(l'impronta canonica ricalcolata dai file).
"""

from __future__ import annotations

import json
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

_GIT_TIMEOUT_SECONDS = 120


class FrozenBlobCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.erratum = json.loads(ERRATUM_PATH.read_text(encoding="utf-8"))

    def _git(self, *args: str) -> bytes:
        return subprocess.run(
            ["git", *args],
            cwd=GIT_ROOT,
            capture_output=True,
            check=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        ).stdout

    def _checkout_bytes(self, relative: str) -> bytes:
        """I byte che un checkout pulito scriverebbe su disco.

        Non i byte del blob: fra il blob e il disco c'e' la conversione di fine
        riga dichiarata in `.gitattributes`, ed e' proprio quella conversione
        che l'impronta deve sopravvivere. Confrontare il blob nudo misurerebbe
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


class CheckoutMatchesTheBlobTests(FrozenBlobCase):
    def test_the_canonical_hash_is_what_a_clean_checkout_writes(self) -> None:
        """Il lato che solo la storia puo' verificare.

        La suite core controlla che l'impronta canonica sia riprodotta dai file
        su disco — vero in ogni ambiente. Qui si controlla la cosa in piu': che
        quei byte siano anche cio' che git consegnerebbe. E' la differenza fra i
        due che il difetto originale sfruttava.
        """
        for source, payload in self.erratum["sources"].items():
            with self.subTest(source=source):
                self.assertEqual(
                    POLICY.canonical_lf_sha256(self._checkout_bytes(source)),
                    payload["canonical_lf_sha256"],
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

    def test_the_committed_operational_sources_are_canonical(self) -> None:
        """Nessun sorgente operativo porta un CR *nel blob*.

        Sul disco un file puo' essere CRLF senza che nulla sia stato manomesso:
        dipende dal checkout. Nel blob no — e' li' che il commit `29bda1d` aveva
        messo il `\\r` aggiunto per far tornare un hash, ed e' li' che va
        verificato che non ci sia tornato.
        """
        for source in self.erratum["sources"]:
            if not source.startswith("backend/"):
                continue
            with self.subTest(source=source):
                blob = self._git("show", f"HEAD:mtb-graphrag/{source}")
                self.assertEqual(POLICY.canonical_lf_bytes(blob), blob)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
