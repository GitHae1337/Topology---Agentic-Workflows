import json
from pathlib import Path
from typing import Iterator
from pydantic import BaseModel


DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "HumanEval.jsonl"


class HumanEvalProblem(BaseModel):
    """Single HumanEval problem record."""
    task_id: str
    prompt: str
    canonical_solution: str
    test: str
    entry_point: str


def load_problems(path: Path = DATA_PATH) -> list[HumanEvalProblem]:
    """Load all HumanEval problems from JSONL file into memory."""
    if not path.exists():
        raise FileNotFoundError(
            f"HumanEval dataset not found at {path}. "
            f"See backend/data/README.md for download instructions."
        )

    problems: list[HumanEvalProblem] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            problems.append(HumanEvalProblem(**json.loads(line)))

    return problems


def iter_problems(path: Path = DATA_PATH) -> Iterator[HumanEvalProblem]:
    """Stream HumanEval problems one by one."""
    if not path.exists():
        raise FileNotFoundError(
            f"HumanEval dataset not found at {path}. "
            f"See backend/data/README.md for download instructions."
        )

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield HumanEvalProblem(**json.loads(line))
