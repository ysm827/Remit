"""取消和超时只回收当前操作创建的进程树。"""

import os
import subprocess
import time

import psutil

from app.services.async_io import check_cancelled


def run_owned(command, **kwargs):
    """轮询本次子进程；超时和取消只回收它及观察到的后代。"""
    check_cancelled()
    timeout = kwargs.pop("timeout", None)
    check = kwargs.pop("check", False)
    if kwargs.pop("capture_output", False):
        kwargs["stdout"] = kwargs["stderr"] = subprocess.PIPE
    kwargs.setdefault(
        "creationflags", subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    )
    started = time.monotonic()
    process = subprocess.Popen(command, **kwargs)
    try:
        owner = psutil.Process(process.pid)
    except psutil.NoSuchProcess:
        owner = None
    children: dict[int, psutil.Process] = {}
    try:
        while True:
            try:
                if owner is not None:
                    children.update(
                        (child.pid, child) for child in owner.children(recursive=True)
                    )
            except psutil.NoSuchProcess:
                pass
            check_cancelled()
            remaining = (
                None if timeout is None else timeout - (time.monotonic() - started)
            )
            if remaining is not None and remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                stdout, stderr = process.communicate(
                    timeout=min(0.1, remaining) if remaining is not None else 0.1
                )
                break
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        # psutil Process checks creation time before killing, protecting PID reuse.
        owned = [*children.values(), *([owner] if owner is not None else [])]
        for child in owned:
            try:
                child.kill()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(owned, timeout=3)
        if alive:
            raise RuntimeError("子进程尚未退出，不能确认停止完成")
        process.communicate(timeout=3)
        raise
    result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    if check:
        result.check_returncode()
    check_cancelled()
    return result
