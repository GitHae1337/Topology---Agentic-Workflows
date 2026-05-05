import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SandboxResult:
    """Outcome of running a candidate solution against HumanEval test code."""
    passed: bool
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    error_message: str


DEFAULT_TIMEOUT_SEC = 10
DEFAULT_MEMORY_BYTES = 256 * 1024 * 1024  # currently unused on macOS; reserved for future portable use


_CHILD_PROGRAM_TEMPLATE = textwrap.dedent("""\
    import resource, signal, sys

    # CPU-time cap + wall-clock alarm for hard termination inside the child.
    # NOTE: RLIMIT_AS (address space) is intentionally NOT applied here; on macOS
    # the default hard limit is below typical Python runtime needs and setting it
    # raises ValueError. The parent timeout + RLIMIT_CPU + signal.alarm together
    # already prevent runaway processes for the HumanEval workload.
    resource.setrlimit(resource.RLIMIT_CPU, ({cpu_sec}, {cpu_sec}))
    signal.alarm({cpu_sec})

    # --- begin candidate program ---
    {candidate_block}
    # --- end candidate program ---

    # --- begin HumanEval test ---
    {test_block}
    # --- end HumanEval test ---

    check({entry_point})
    print("__SANDBOX_PASS__")
""")


def run_humaneval_sandbox(
    candidate_code: str,
    test_code: str,
    entry_point: str,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    memory_bytes: int = DEFAULT_MEMORY_BYTES,
) -> SandboxResult:
    """
    Execute candidate code + HumanEval test in an isolated subprocess.

    Pass condition: child prints "__SANDBOX_PASS__" and exits with returncode 0.
    """
    program = _CHILD_PROGRAM_TEMPLATE.format(
        cpu_sec=timeout_sec,
        mem_bytes=memory_bytes,
        candidate_block=candidate_code,
        test_block=test_code,
        entry_point=entry_point,
    )

    print(f"[sandbox] starting subprocess for entry_point={entry_point}, timeout={timeout_sec}s")

    proc = subprocess.Popen(
        [sys.executable, "-I", "-c", program],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(Path.cwd()),
    )

    # try/except is normally banned by project convention; the single allowed
    # exception is subprocess.TimeoutExpired (granted 2026-04-27) so we can record
    # a timeout outcome instead of letting it escape into the runner loop.
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout_sec + 1)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        timed_out = True
        print(f"[sandbox] TIMEOUT after {timeout_sec}s for entry_point={entry_point}")

    returncode = proc.returncode

    # Treat child-internal SIGALRM (-14) and SIGXCPU (-24) as timeouts as well.
    # These fire when signal.alarm() / RLIMIT_CPU inside the child kills it before
    # the parent's communicate() timeout triggers.
    if returncode in (-14, -24):
        timed_out = True

    passed = (not timed_out) and returncode == 0 and "__SANDBOX_PASS__" in stdout

    if passed:
        error_message = ""
    elif timed_out:
        error_message = f"timeout after {timeout_sec}s (returncode={returncode})"
    elif returncode != 0:
        error_message = (stderr or "").strip().splitlines()[-1][:500] if stderr else f"exit {returncode}"
    else:
        error_message = "no pass marker emitted"

    print(f"[sandbox] result: passed={passed}, timed_out={timed_out}, returncode={returncode}")

    return SandboxResult(
        passed=passed,
        stdout=stdout or "",
        stderr=stderr or "",
        returncode=returncode,
        timed_out=timed_out,
        error_message=error_message,
    )
