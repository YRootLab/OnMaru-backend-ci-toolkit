from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass, field

from pipeline_toolkit.security import redact

@dataclass(frozen=True)
class Command:
    executable: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)

@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 1
    retry_exit_codes: tuple[int, ...] = ()

@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str
    exit_code: int | None
    reason: str
    attempts: int
    duration_seconds: float

class CommandRunner:
    def __init__(self, allowed_executables: set[str] | None = None, secrets: tuple[str, ...] = ()):
        self.allowed = allowed_executables
        self.secrets = secrets

    def run(self, command: Command, timeout: float = 300, retry: RetryPolicy = RetryPolicy()) -> CommandResult:
        if not command.executable or (self.allowed is not None and command.executable not in self.allowed):
            raise PermissionError(f"executable is not allowed: {command.executable}")
        argv = (command.executable, *command.args)
        started = time.monotonic()
        last: CommandResult | None = None
        for attempt in range(1, max(1, retry.attempts) + 1):
            env = os.environ.copy(); env.update(command.env)
            try:
                proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                        env=env, start_new_session=True)
                try:
                    out, err = proc.communicate(timeout=timeout)
                    reason = "success" if proc.returncode == 0 else "non_zero_exit"
                    last = CommandResult(argv, redact(out, self.secrets), redact(err, self.secrets), proc.returncode, reason, attempt, time.monotonic()-started)
                except subprocess.TimeoutExpired as exc:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try: out, err = proc.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL); out, err = proc.communicate()
                    last = CommandResult(argv, redact(exc.stdout or out or "", self.secrets), redact(exc.stderr or err or "", self.secrets), proc.returncode, "timeout", attempt, time.monotonic()-started)
            except OSError as exc:
                last = CommandResult(argv, "", redact(str(exc), self.secrets), None, "execution_error", attempt, time.monotonic()-started)
            if last.reason == "success" or last.exit_code not in retry.retry_exit_codes: break
        assert last is not None
        return last
