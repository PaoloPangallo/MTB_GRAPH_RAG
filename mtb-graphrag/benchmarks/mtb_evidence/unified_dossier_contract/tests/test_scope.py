from __future__ import annotations

from pathlib import Path
import unittest


class UnifiedDossierScopeTests(unittest.TestCase):
    def test_shadow_package_has_no_production_surface_imports(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
        self.assertNotIn("backend.api", text)
        self.assertNotIn("frontend", text.casefold())
        self.assertNotIn("gold_g", text)

    def test_only_local_qualified_repository_is_read_and_no_production_surface_is_referenced(self) -> None:
        preview = (Path(__file__).resolve().parents[1] / "preview.py").read_text(encoding="utf-8")
        self.assertIn("qualified_claim_repository_1_4", preview)
        self.assertNotIn("production_endpoint", preview)
        self.assertNotIn("frontend", preview.casefold())
        self.assertNotIn("gold_g", preview)

    def test_required_core_keys_are_not_recomputed_by_field_names(self) -> None:
        contract = (Path(__file__).resolve().parents[1] / "contract.py")
        text = contract.read_text(encoding="utf-8") if contract.exists() else ""
        self.assertNotIn("bucket =", text)
        self.assertNotIn("score =", text)
        self.assertNotIn("gate_trace =", text)


if __name__ == "__main__":
    unittest.main()
