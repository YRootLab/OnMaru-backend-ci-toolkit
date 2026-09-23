import sys
from pipeline_toolkit.runners import Command, CommandRunner, RetryPolicy

def test_timeout_terminates_process_group_and_preserves_partial_streams():
    code = "import time; print('before', flush=True); time.sleep(10)"
    result = CommandRunner({sys.executable}).run(Command(sys.executable, ("-c", code)), timeout=0.05)
    assert result.reason == "timeout"
    assert "before" in result.stdout

def test_retry_history_distinguishes_retryable_attempts_from_final_success():
    result = CommandRunner({sys.executable}).run(
        Command(sys.executable, ("-c", "import sys; sys.exit(42)")),
        retry=RetryPolicy(attempts=2, retry_exit_codes=(42,)),
    )
    assert result.reason == "non_zero_exit"
    assert result.attempts == 2
    assert result.attempt_reasons == ("non_zero_exit", "non_zero_exit")

def test_signal_termination_has_distinct_reason():
    code = "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"
    result = CommandRunner({sys.executable}).run(Command(sys.executable, ("-c", code)))
    assert result.reason == "signal:SIGTERM"
