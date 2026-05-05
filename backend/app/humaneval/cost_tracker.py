from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UsageBucket:
    """Accumulator for token usage entries during a single benchmark trial."""
    entries: list[dict] = field(default_factory=list)

    def add(self, usage: dict) -> None:
        self.entries.append(dict(usage))

    @property
    def total_input_tokens(self) -> int:
        return sum(int(e.get("input_tokens", e.get("prompt_tokens", 0))) for e in self.entries)

    @property
    def total_output_tokens(self) -> int:
        return sum(int(e.get("output_tokens", e.get("completion_tokens", 0))) for e in self.entries)

    @property
    def total_tokens(self) -> int:
        return sum(int(e.get("total_tokens", 0)) for e in self.entries)

    @property
    def call_count(self) -> int:
        return len(self.entries)


_current_bucket: ContextVar[Optional[UsageBucket]] = ContextVar(
    "humaneval_usage_bucket", default=None
)


def start_collection() -> UsageBucket:
    """Begin capturing usage entries for the current async context."""
    bucket = UsageBucket()
    _current_bucket.set(bucket)
    print(f"[cost_tracker] started new collection bucket")
    return bucket


def record_usage(usage: Optional[dict]) -> None:
    """Append an entry to the active bucket, if any. No-op when inactive."""
    if not usage:
        return
    bucket = _current_bucket.get()
    if bucket is None:
        return
    bucket.add(usage)


def stop_collection() -> Optional[UsageBucket]:
    """Detach and return the current bucket. Subsequent record_usage is no-op."""
    bucket = _current_bucket.get()
    _current_bucket.set(None)
    if bucket is not None:
        print(f"[cost_tracker] stopped: {bucket.call_count} calls, {bucket.total_tokens} tokens")
    return bucket
