from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import time
from pathlib import Path

from .contract import ExperimentError, MAX_BYTES, REPOSITORY, load_json_bytes, require


class BoundedProcess:
    """Fixed argv, bounded stdout+stderr, a deadline, and no automatic retries."""

    def run(self, argv, *, cwd=None, stdin=b"", timeout=30.0, max_bytes=MAX_BYTES) -> bytes:
        require(argv[0] in ("git", "gh"), "unsupported_executable")
        require(0 < timeout <= 3600 and len(stdin) <= 4096, "invalid_limits")
        process = None
        selector = selectors.DefaultSelector()
        output = bytearray()
        total = 0
        deadline = time.monotonic() + timeout
        try:
            process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            process.stdin.write(stdin)
            process.stdin.close()
            selector.register(process.stdout, selectors.EVENT_READ, True)
            selector.register(process.stderr, selectors.EVENT_READ, False)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                require(remaining > 0, "command_timeout")
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    require(total <= max_bytes, "command_output_limit")
                    if key.data:
                        output.extend(chunk)
            require(process.wait(timeout=max(0.001, deadline - time.monotonic())) == 0, "command_failed")
            return bytes(output)
        except subprocess.TimeoutExpired as exc:
            raise ExperimentError("command_timeout") from exc
        except OSError as exc:
            raise ExperimentError("command_unavailable") from exc
        finally:
            selector.close()
            if process is not None:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait()
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()


class GitHub:
    """Inject a process boundary for offline fixtures; restrict the API host."""

    def __init__(self, process=None):
        self.process = process or BoundedProcess()
        self.deadline = None

    def _timeout(self):
        timeout = 30.0 if self.deadline is None else min(30.0, self.deadline - time.monotonic())
        require(timeout > 0, "wait_timeout")
        return timeout

    def authenticate(self):
        self.process.run(["gh", "auth", "status", "--hostname", "github.com"], timeout=self._timeout())
        actor = self.api("user")
        require(isinstance(actor.get("login"), str) and bool(actor["login"]), "unauthenticated")
        repository = self.api("repos/" + REPOSITORY)
        require(repository.get("full_name") == REPOSITORY and repository.get("fork") is False, "untrusted_repository")
        return actor["login"]

    def raw(self, endpoint, *, payload=None):
        argv = ["gh", "api", endpoint, "--hostname", "github.com", "--method", "GET" if payload is None else "POST", "-H", "X-GitHub-Api-Version: 2026-03-10"]
        raw = b""
        if payload is not None:
            argv.extend(["--input", "-"])
            raw = json.dumps(payload, sort_keys=True).encode()
        return self.process.run(argv, stdin=raw, timeout=self._timeout())

    def api(self, endpoint, *, payload=None):
        return load_json_bytes(self.raw(endpoint, payload=payload))

    def git(self, root: Path, *args):
        try:
            return self.process.run(["git", "-C", str(root), *args], timeout=self._timeout()).decode("utf-8").strip()
        except UnicodeError as exc:
            raise ExperimentError("invalid_git_output") from exc
