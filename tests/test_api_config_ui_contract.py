"""API 配置界面的发行契约。"""

from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ApiConfigUiContractTests(unittest.TestCase):
    def test_openalex_is_optional_when_saving_model_credentials(self) -> None:
        dialog = (
            PROJECT_ROOT
            / "frontend"
            / "src"
            / "pages"
            / "chat"
            / "components"
            / "ApiDialog.vue"
        ).read_text(encoding="utf-8")

        self.assertIn('if (!email) return { valid: true', dialog)
        self.assertIn("!openalexEmail.value.trim() ||", dialog)

    def test_save_is_not_silently_skipped_after_validation(self) -> None:
        dialog = (
            PROJECT_ROOT
            / "frontend"
            / "src"
            / "pages"
            / "chat"
            / "components"
            / "ApiDialog.vue"
        ).read_text(encoding="utf-8")

        self.assertNotIn("if (!allValid.value) {\n\t\treturn;", dialog)
        self.assertIn("await loadEffectiveConfig()", dialog)


if __name__ == "__main__":
    unittest.main()
