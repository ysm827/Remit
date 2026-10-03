"""Pilot isolation, durable recovery, and input invalidation without real model calls."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.pilot import (
    PilotValidationError,
    pilot_input_context,
    pilot_input_fingerprint,
    validate_pilot_results,
)
from app.core.workflow import RemitWorkFlow
from app.schemas.A2A import ModelerToCoder, PilotPlan


def make_plan():
    return PilotPlan.model_validate(
        {
            "questions": {
                key: {
                    "candidates": [
                        {
                            "name": "baseline",
                            "role": "baseline",
                            "approach": "使用简单可行的基线方案",
                        },
                        {"name": "alternative", "approach": "使用相同样本比较另一方案"},
                    ],
                    "sampling_rule": "固定抽取相同的两个地点",
                    "primary_metric": "cost",
                }
                for key in ("ques1", "ques2")
            }
        }
    )


def output(key):
    return {
        "questions": {
            key: {
                "sample_description": "the same two sites",
                "candidates": [
                    {
                        "name": name,
                        "metric_name": "cost",
                        "metric_value": 2.0,
                        "runtime_seconds": 1,
                        "ran_ok": True,
                    }
                    for name in ("baseline", "alternative")
                ],
            }
        }
    }


class PilotQuestionRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_later_failure_preserves_first_question_and_resume_skips_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cleaned").mkdir()
            data = root / "cleaned" / "sites.csv"
            data.write_text("site,height\nS001,10\n", encoding="utf-8")
            wf = RemitWorkFlow()
            wf.work_dir = tmp
            wf.task_id = "test"
            wf.questions = {"ques1": "FIRST_QUESTION", "ques2": "SECOND_QUESTION"}
            wf.checkpoint = MagicMock()
            wf._check_cancelled = AsyncMock()
            strategies = ModelerToCoder(
                questions_solution={
                    "ques1": "FIRST_APPROVED",
                    "ques2": "SECOND_APPROVED",
                }
            )
            state, calls = {}, []
            fail_second = True

            async def run(**kwargs):
                key = kwargs["subtask_title"].split(":")[1]
                calls.append(key)
                self.assertEqual(
                    kwargs["required_files"], (f"pilot_{key}_results.json",)
                )
                self.assertLessEqual(kwargs["max_code_executions"], 6)
                self.assertIn("site", kwargs["prompt"])
                if key == "ques1":
                    self.assertIn("FIRST_APPROVED", kwargs["prompt"])
                    self.assertNotIn("SECOND_APPROVED", kwargs["prompt"])
                if key == "ques2" and fail_second:
                    return
                (root / kwargs["required_files"][0]).write_text(
                    json.dumps(output(key)), encoding="utf-8"
                )

            coder = SimpleNamespace(run=AsyncMock(side_effect=run))
            with patch("app.core.workflow.publish_activity", new_callable=AsyncMock):
                with self.assertRaises(PilotValidationError):
                    await wf._run_pilot_questions(state, coder, strategies, make_plan())
                self.assertEqual(calls, ["ques1", "ques2", "ques2"])
                self.assertTrue((root / "pilot_ques1_results.json").exists())
                self.assertFalse((root / "pilot_results.json").exists())
                # Simulate checkpoint serialization and another process after recovery.
                state = json.loads(json.dumps(state))
                fail_second = False
                calls.clear()
                result = await wf._run_pilot_questions(
                    state, coder, strategies, make_plan()
                )
                self.assertEqual(calls, ["ques2"])
                self.assertEqual(set(result["questions"]), {"ques1", "ques2"})
                self.assertEqual(validate_pilot_results(root, make_plan()), result)
                # An edited result cannot reuse the cached validation.
                (root / "pilot_ques1_results.json").write_text("{}", encoding="utf-8")
                calls.clear()
                await wf._run_pilot_questions(state, coder, strategies, make_plan())
                self.assertEqual(calls, ["ques1"])
                # Changed scientific input invalidates both questions, even if new metrics coincide.
                data.write_text("site,height\nS001,20\n", encoding="utf-8")
                calls.clear()
                await wf._run_pilot_questions(state, coder, strategies, make_plan())
                self.assertEqual(calls, ["ques1", "ques2"])

    def test_fingerprint_tracks_original_attachments_and_confines_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "original.csv"
            data.write_text("x\n1\n")
            manifest = root / ".remit-inputs.json"
            manifest.write_text('["original.csv"]')
            before = pilot_input_fingerprint(root, {"strategy": "approved"})
            data.write_text("x\n2\n")
            self.assertNotEqual(
                before, pilot_input_fingerprint(root, {"strategy": "approved"})
            )
            manifest.write_text('["../outside.csv"]')
            with self.assertRaises(PilotValidationError):
                pilot_input_fingerprint(root, {})

    def test_missing_candidate_cannot_be_used_to_finalize_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = output("ques1")
            data["questions"]["ques1"]["candidates"].pop()
            (root / "pilot_results.json").write_text(json.dumps(data))
            plan = make_plan()
            plan.questions.pop("ques2")
            with self.assertRaisesRegex(PilotValidationError, "缺少候选记录"):
                validate_pilot_results(root, plan)
            self.assertIn("真实表结构", pilot_input_context(root))
