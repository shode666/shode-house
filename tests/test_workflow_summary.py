"""Keep the public workflow summary aligned with the canonical drift rules."""

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
WORKFLOW = ROOT / "skills/discipline/shode-house-workflow/SKILL.md"


class WorkflowSummaryTest(unittest.TestCase):
    @staticmethod
    def assert_m4_routes(row):
        lowered = row.lower()
        assert "defect" in lowered and "affected" in lowered and "iter" in lowered
        assert "scope change" in lowered and "acceptance" in lowered
        assert "question/status" in lowered and "evidence" in lowered
        for blanket in ("feedback ใด ๆ", "all feedback", "every comment", "all comments"):
            assert blanket not in lowered

    def test_m4_only_invalidates_claims_affected_by_a_defect(self):
        readme = README.read_text()
        workflow = WORKFLOW.read_text()

        self.assertIn("M4 — User feedback invalidates the affected claim", workflow)
        for route in (
            "defect → record finding, reopen affected criterion/phase",
            "scope change → record revised acceptance",
            "question/status → answer from evidence",
        ):
            self.assertIn(route, workflow)

        m4 = next(line for line in readme.splitlines() if line.startswith("| M4 |"))
        self.assert_m4_routes(m4)

    def test_m4_route_mutations_are_rejected(self):
        valid = next(line for line in README.read_text().splitlines() if line.startswith("| M4 |"))
        mutations = (
            valid.replace("defect = reopen affected criterion/phase + iter++; ", ""),
            valid.replace("scope change → revise acceptance; ", ""),
            valid.replace("question/status → answer from evidence", ""),
            valid + " all feedback reopens everything",
        )
        for mutation in mutations:
            with self.assertRaises(AssertionError):
                self.assert_m4_routes(mutation)


if __name__ == "__main__":
    unittest.main()
