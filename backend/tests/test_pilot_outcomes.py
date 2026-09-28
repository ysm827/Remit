import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.project_audit import evaluated_node_status, pilot_evidence_notice
from app.core.pilot import PilotValidationError
from app.core.workflow import RemitWorkFlow
from app.schemas.A2A import ModelerToCoder
from app.services.writing_workspace import sync_results


class PilotOutcomeTests(unittest.IsolatedAsyncioTestCase):
    async def test_technical_error_does_not_complete_or_skip_pilot(self):
        await self.check_failure(ConnectionError("gateway unavailable"), technical=True)

    async def test_invalid_comparison_is_explicitly_skipped(self):
        await self.check_failure(PilotValidationError("no valid candidates"), technical=False)

    async def check_failure(self, error, *, technical):
        with tempfile.TemporaryDirectory() as tmp:
            wf = RemitWorkFlow()
            wf.work_dir = tmp
            wf.task_id = "test"
            wf.questions = {"ques1":"question"}
            wf.code_interpreter = SimpleNamespace(language="matlab")
            wf.checkpoint = MagicMock()
            wf.checkpoint.consume_revision_feedback.return_value = None
            wf._start_node = AsyncMock()
            wf._complete_node = AsyncMock()
            wf._check_cancelled = AsyncMock()
            modeler = SimpleNamespace(design_pilot_plan=AsyncMock(side_effect=error))
            coder = SimpleNamespace(append_chat_history=AsyncMock())
            state = {}
            with patch("app.core.workflow.redis_manager.publish_message", new_callable=AsyncMock), patch("app.core.workflow.publish_activity", new_callable=AsyncMock):
                if technical:
                    with self.assertRaises(ConnectionError):
                        await wf._pilot_node(state, modeler, coder, ModelerToCoder(questions_solution={"ques1":"strategy"}))
                    wf._complete_node.assert_not_awaited()
                    self.assertNotIn("pilot_skipped", state)
                    self.assertEqual(state["node_outcomes"]["pilot"]["status"], "failed")
                else:
                    await wf._pilot_node(state, modeler, coder, ModelerToCoder(questions_solution={"ques1":"strategy"}))
                    wf._complete_node.assert_awaited_once()
                    self.assertEqual(evaluated_node_status(state, "pilot"), "skipped")

    def test_old_skipped_checkpoint_and_writing_snapshot_keep_limitations(self):
        state = {"pilot_skipped":"no usable comparison", "completed_nodes":["pilot"]}
        self.assertEqual(evaluated_node_status(state, "pilot"), "skipped")
        self.assertIn("不得声称", pilot_evidence_notice(state))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            info = sync_results(root, state)
            snapshot = root / "paper" / ".inputs" / info["revision"] / "evidence.json"
            evidence = json.loads(snapshot.read_text(encoding="utf-8"))
            self.assertEqual(evidence["pilot_skipped"], state["pilot_skipped"])
            self.assertIn("不得声称", evidence["evidence_notice"])

    def test_records_without_decision_are_not_passed(self):
        self.assertEqual(evaluated_node_status({"pilot_results":{"questions":{}}}, "pilot"), "warning")
