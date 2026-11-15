"""Keep the design critique contextual and its user-flow guidance aligned with Playwright."""
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CARD = ROOT / "references/design-intel/references/interface-quality.md"
CATALOGUE = ROOT / "references/runbooks/design-catalogue.md"


class DesignInterfaceQualityTest(unittest.TestCase):
    def test_card_is_routed_from_design_catalogue(self):
        self.assertTrue(CARD.is_file())
        self.assertIn(str(CARD.relative_to(ROOT)), CATALOGUE.read_text())

    def test_anti_slop_is_contextual_not_a_style_ban(self):
        text = " ".join(CARD.read_text().split())
        self.assertIn("not a style recipe", text)
        self.assertIn("not a defect by itself", text)
        for signal in ("product's task", "hierarchy", "accessibility", "intentional design choice"):
            self.assertIn(signal, text)

    def test_playwright_guidance_favors_user_behavior(self):
        text = CARD.read_text()
        for signal in ("user-visible behavior", "role/name or label", "web-first assertions", "isolated state"):
            self.assertIn(signal, text)
        self.assertLess(text.index("role/name or label"), text.index("data-testid"))


if __name__ == "__main__":
    unittest.main()
