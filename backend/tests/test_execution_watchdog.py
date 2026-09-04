"""代码执行复杂度、超时和事件循环存活性回归测试。"""

from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.execution_guard import assess_code_execution
from app.tools.local_interpreter import LocalCodeInterpreter
from app.tools.notebook_serializer import NotebookSerializer


class ExecutionComplexityGuardTests(unittest.TestCase):
    def test_rejects_metaheuristic_with_quadratic_check_in_inner_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            solver = Path(tmp) / "solver.m"
            solver.write_text(
                """
seeds=1:10; n=300; levels=35; moves_per_temp=15;
for seed=seeds
  for level=1:levels
    for move=1:round(moves_per_temp*n)
      [layout, score] = btSA_step(layout);
      score = indVerify(layout, n);
    end
  end
end
function score=indVerify(layout,n)
score=0;
for i=1:n-1
  for j=i+1:n
    score=score+overlaps(layout,i,j);
  end
end
end
""".strip(),
                encoding="utf-8",
            )

            assessment = assess_code_execution(
                "run('solver.m');", language="matlab", work_dir=tmp
            )

        self.assertFalse(assessment.allowed)
        self.assertIn("复杂度", assessment.reason)
        self.assertIn("solver.m", assessment.reason)

    def test_allows_small_bounded_vectorized_code(self) -> None:
        assessment = assess_code_execution(
            "x = 1:100; y = x.^2; disp(mean(y));",
            language="matlab",
            work_dir=".",
        )

        self.assertTrue(assessment.allowed, assessment.reason)


class LocalExecutionWatchdogTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_does_not_block_event_loop_and_recovers_kernel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            interpreter = LocalCodeInterpreter(
                task_id="python-timeout-test",
                work_dir=tmp,
                notebook_serializer=NotebookSerializer(work_dir=tmp),
                timeout=0.05,
            )
            interpreter.kc = MagicMock()
            interpreter.km = MagicMock()
            interpreter._run_raw = MagicMock(
                side_effect=lambda code: (time.sleep(0.2) or [])
            )
            interpreter._recover_kernel_after_timeout = AsyncMock()
            interpreter._push_to_websocket = AsyncMock()
            ready = asyncio.Event()
            heartbeat_delay: list[float] = []

            async def event_loop_probe() -> None:
                started = time.perf_counter()
                ready.set()
                await asyncio.sleep(0.01)
                heartbeat_delay.append(time.perf_counter() - started)

            with (
                patch(
                    "app.tools.local_interpreter.redis_manager.publish_message",
                    new=AsyncMock(),
                ),
                patch(
                    "app.tools.local_interpreter.settings."
                    "CODE_EXECUTION_HEARTBEAT_SECONDS",
                    0.01,
                    create=True,
                ),
            ):
                probe = asyncio.create_task(event_loop_probe())
                await ready.wait()
                output, failed, error = await interpreter.execute_code(
                    "value = 1"
                )
                await probe

            self.assertTrue(failed)
            self.assertIn("执行超过", output)
            self.assertEqual(error, output)
            self.assertLess(heartbeat_delay[0], 0.08)
            interpreter._recover_kernel_after_timeout.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
