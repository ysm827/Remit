"""目录附件进入远程计算环境时保留路径，并增量同步后续附件。"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.tools.e2b_interpreter import E2BCodeInterpreter


def test_folder_inputs_are_uploaded_with_parents_without_replacing_existing(tmp_path):
    (tmp_path / "data/train").mkdir(parents=True)
    (tmp_path / "data/train/a.csv").write_text("x\n1")
    (tmp_path / ".remit-inputs.json").write_text(json.dumps(["data/train/a.csv"]))
    interpreter = E2BCodeInterpreter("folder-test", str(tmp_path), None)
    files = SimpleNamespace(write=AsyncMock(), make_dir=AsyncMock())
    interpreter.sbx = SimpleNamespace(files=files)

    async def run():
        await interpreter._upload_all_files()
        (tmp_path / "data/train/b.custom").write_bytes(b"new")
        (tmp_path / ".remit-inputs.json").write_text(
            json.dumps(["data/train/a.csv", "data/train/b.custom"])
        )
        await interpreter._upload_all_files()
        await interpreter._upload_all_files()

    asyncio.run(run())
    assert len(files.write.await_args_list) == 2
    assert files.write.await_args_list[0].args[0].endswith("/data/train/a.csv")
    assert files.write.await_args_list[1].args[0].endswith("/data/train/b.custom")
    assert all(
        call.args[0].endswith("/data/train") for call in files.make_dir.await_args_list
    )
