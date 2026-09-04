"""探索实验运行时间硬门禁回归测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.core.pilot import PilotValidationError, validate_pilot_results
from app.schemas.A2A import PilotPlan


class PilotRuntimeBudgetTests(unittest.TestCase):
    def test_over_budget_candidate_is_not_accepted_as_success(self) -> None:
        plan = PilotPlan.model_validate(
            {
                "questions": {
                    "ques1": {
                        "candidates": [
                            {
                                "name": "baseline",
                                "role": "baseline",
                                "approach": "快速贪心基线方法",
                            },
                            {
                                "name": "slow-search",
                                "role": "candidate",
                                "approach": "复杂元启发式搜索",
                            },
                        ],
                        "sampling_rule": "固定抽取前 100 行",
                        "primary_metric": "rmse",
                        "time_budget_minutes": 1,
                    }
                }
            }
        )
        payload = {
            "questions": {
                "ques1": {
                    "sample_description": "100 rows",
                    "candidates": [
                        {
                            "name": "baseline",
                            "metric_name": "rmse",
                            "metric_value": 1.0,
                            "runtime_seconds": 61,
                            "ran_ok": True,
                        },
                        {
                            "name": "slow-search",
                            "metric_name": "rmse",
                            "metric_value": 0.9,
                            "runtime_seconds": 120,
                            "ran_ok": True,
                        },
                    ],
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pilot_results.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            with self.assertRaisesRegex(PilotValidationError, "没有任何真实跑通"):
                validate_pilot_results(tmp, plan)


if __name__ == "__main__":
    unittest.main()
