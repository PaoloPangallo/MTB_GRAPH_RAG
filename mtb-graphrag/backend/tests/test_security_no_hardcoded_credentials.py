"""Impedisce la reintroduzione di credenziali scritte nel codice.

Il repository conteneva la password Neo4j come valore di default di `os.getenv` in
quattordici script. Un default del genere e' peggio di una variabile mancante: il
codice funziona, quindi nessuno si accorge che il segreto e' versionato.

Questi test scansionano i file **tracciati da git** e falliscono se il pattern
ricompare. Girano offline e non richiedono ne' Neo4j ne' modelli.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest import TestCase

REPO_ROOT = Path(__file__).resolve().parents[3]

# Variabili il cui valore e' un segreto: non possono avere un default non vuoto.
SECRET_ENV_VARS = (
    "NEO4J_PASSWORD",
    "OLLAMA_API_KEY",
    "ONCOKB_TOKEN",
    "NCBI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)

_SECRET_NAMES = "|".join(SECRET_ENV_VARS)

# os.getenv("SEGRETO", "qualcosa") oppure os.environ.get("SEGRETO", "qualcosa")
_FALLBACK = re.compile(
    rf"""(?:getenv|environ\.get)\(\s*["'](?:{_SECRET_NAMES})["']\s*,\s*["'][^"']+["']"""
)

# Assegnazione diretta di una credenziale a un letterale non vuoto.
_DIRECT_ASSIGNMENT = re.compile(
    rf"""^\s*_?(?:{_SECRET_NAMES}|password|PASSWORD)\s*=\s*["'][^"'{{}}$]{{4,}}["']\s*$""",
    re.MULTILINE,
)

# URI con userinfo incorporato: bolt://utente:password@host
_URI_WITH_USERINFO = re.compile(r"""(?:bolt|neo4j|https?)\+?s?://[^\s"'/]+:[^\s"'/@]+@""")

# File in cui un URI con userinfo e' una fixture di test legittima.
_URI_FIXTURE_ALLOWLIST = {
    "mtb-graphrag/backend/tests/test_pilot_gold_audit.py",
    "mtb-graphrag/backend/tests/test_security_no_hardcoded_credentials.py",
    "mtb-graphrag/benchmarks/mtb_evidence/pilot/audit_lib/serialize.py",
}


def _tracked_files(*patterns: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", *patterns],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8", errors="replace")


class NoHardcodedCredentialsTest(TestCase):
    def test_no_secret_env_var_has_a_non_empty_default(self):
        offenders = []
        for relative in _tracked_files("*.py"):
            if _FALLBACK.search(_read(relative)):
                offenders.append(relative)
        self.assertEqual(
            offenders,
            [],
            "Una variabile segreta ha un valore di default nel codice. Usa "
            "utility.credentials.require_env, che fallisce con un messaggio leggibile.",
        )

    def test_no_direct_credential_assignment(self):
        offenders = []
        for relative in _tracked_files("*.py"):
            for match in _DIRECT_ASSIGNMENT.finditer(_read(relative)):
                # Un valore vuoto o un placeholder non e' un segreto.
                literal = match.group(0).split("=", 1)[1].strip().strip("\"'")
                if literal and not literal.upper().startswith(("REDACTED", "CHANGEME", "XXX")):
                    offenders.append(f"{relative}: {match.group(0).strip()[:40]}")
        self.assertEqual(offenders, [], "Credenziale assegnata a un letterale.")

    def test_no_uri_with_embedded_userinfo(self):
        offenders = []
        for relative in _tracked_files("*.py", "*.md", "*.json", "*.cypher", "*.env*"):
            if relative in _URI_FIXTURE_ALLOWLIST:
                continue
            if _URI_WITH_USERINFO.search(_read(relative)):
                offenders.append(relative)
        self.assertEqual(offenders, [], "URI con credenziali incorporate.")


class EnvFileHygieneTest(TestCase):
    def test_no_real_env_file_is_tracked(self):
        tracked = _tracked_files("*.env", ".env", "**/.env")
        self.assertEqual(tracked, [], "Un file .env reale risulta tracciato da git.")

    def test_env_example_has_no_secret_values(self):
        example = REPO_ROOT / "mtb-graphrag" / ".env.example"
        self.assertTrue(example.is_file(), ".env.example mancante")
        for line in example.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, _, value = stripped.partition("=")
            if name.strip() in SECRET_ENV_VARS:
                self.assertEqual(
                    value.strip(),
                    "",
                    f"{name.strip()} in .env.example deve restare vuoto",
                )

    def test_gitignore_covers_env_files(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".env", gitignore)


class CredentialHelperTest(TestCase):
    def test_require_env_fails_readably_when_missing(self):
        import os
        import sys

        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from utility.credentials import MissingCredentialError, require_env

        name = "MTB_TEST_ABSENT_CREDENTIAL"
        os.environ.pop(name, None)
        with self.assertRaises(MissingCredentialError) as ctx:
            require_env(name)
        message = str(ctx.exception)
        self.assertIn(name, message)
        self.assertIn("non e' definita", message)
        self.assertIn("default", message)

    def test_require_env_returns_the_environment_value(self):
        import os
        import sys

        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from utility.credentials import require_env

        name = "MTB_TEST_PRESENT_CREDENTIAL"
        os.environ[name] = "valore-di-prova"
        try:
            self.assertEqual(require_env(name), "valore-di-prova")
        finally:
            os.environ.pop(name, None)

    def test_error_message_never_contains_a_value(self):
        import os
        import sys

        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from utility.credentials import MissingCredentialError, require_env

        name = "MTB_TEST_EMPTY_CREDENTIAL"
        os.environ[name] = "   "
        try:
            with self.assertRaises(MissingCredentialError) as ctx:
                require_env(name)
            self.assertNotIn("   ", str(ctx.exception).replace("\n", ""))
        finally:
            os.environ.pop(name, None)
