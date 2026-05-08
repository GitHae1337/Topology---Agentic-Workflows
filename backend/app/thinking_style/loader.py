"""Loader for `backend/data/thinking_styles/prompts.json`.

The participant-curated JSON groups queries by task and by thinking style.
Validates the structure with Pydantic and flattens it into (task_id, style_id,
query) records the matrix runner consumes.

Design choices kept extensible across phases (current phase mirrors the 5 PDF
topologies, but a future phase may swap in a totally different thinking-style
taxonomy):
- ThinkingStyle is pure metadata (id + description). No flag like
  `use_original` is baked into the style definition.
- `tasks[].queries` may omit a style id, or set its value to an empty string.
  In either case, the loader fills that (task, style) cell with the task's
  original TravelPlanner query — same fallback rule for any style, any phase.
"""
import json
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, Field, model_validator

from ..benchmarks.travelplanner.dataset import TravelPlannerProblem


DEFAULT_PROMPTS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "thinking_styles" / "prompts.json"
)


class ThinkingStyle(BaseModel):
    id: str = Field(..., description="short identifier used as JSON key, csv column, jsonl field")
    description: str = Field(default="", description="one-line definition of the style")


class TaskPrompts(BaseModel):
    task_id: str
    queries: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "map style_id -> query text. A style may be omitted or set to '' — "
            "in that case the loader substitutes the task's original query."
        ),
    )


class PromptsFile(BaseModel):
    thinking_styles: List[ThinkingStyle]
    tasks: List[TaskPrompts]

    @model_validator(mode="after")
    def _check_structure(self) -> "PromptsFile":
        style_ids = {s.id for s in self.thinking_styles}
        if len(style_ids) != len(self.thinking_styles):
            raise ValueError("duplicate style id in thinking_styles")
        if not style_ids:
            raise ValueError("thinking_styles is empty")

        task_ids = [t.task_id for t in self.tasks]
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("duplicate task_id in tasks")

        for t in self.tasks:
            extra = set(t.queries.keys()) - style_ids
            if extra:
                raise ValueError(
                    f"task {t.task_id} has queries for unknown style ids: {sorted(extra)}"
                )
        return self


class PromptRecord(BaseModel):
    """One (task, style, query) triple — the unit the matrix runner consumes."""
    task_id: str
    style_id: str
    query: str
    used_original: bool = Field(default=False, description="true when query was filled from task.query")


def load_prompts(path: Path = DEFAULT_PROMPTS_PATH) -> PromptsFile:
    """Read + validate prompts.json. Raises pydantic ValidationError if malformed."""
    print(f"[thinking_style.loader] reading {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    pf = PromptsFile.model_validate(raw)
    print(
        f"[thinking_style.loader] {len(pf.thinking_styles)} styles, "
        f"{len(pf.tasks)} tasks → up to {len(pf.thinking_styles) * len(pf.tasks)} (task,style) records"
    )
    return pf


def flatten(
    prompts_file: PromptsFile,
    problems: List[TravelPlannerProblem],
) -> List[PromptRecord]:
    """Expand the nested file into a flat list of PromptRecord.

    For each (task, style) pair: if the style key is missing OR the query is
    empty/whitespace, the record's query is filled with the task's original
    TravelPlanner query and used_original=True. Otherwise the curated query
    is used as-is.
    """
    problem_by_id = {p.task_id: p for p in problems}
    out: List[PromptRecord] = []
    fallback_count = 0
    for task in prompts_file.tasks:
        problem = problem_by_id.get(task.task_id)
        if not problem:
            print(
                f"[thinking_style.loader] WARNING: task {task.task_id} not in dataset — "
                f"skipping all its (style) cells"
            )
            continue
        for style in prompts_file.thinking_styles:
            curated = task.queries.get(style.id, "")
            if curated and curated.strip():
                out.append(PromptRecord(
                    task_id=task.task_id,
                    style_id=style.id,
                    query=curated,
                    used_original=False,
                ))
            else:
                out.append(PromptRecord(
                    task_id=task.task_id,
                    style_id=style.id,
                    query=problem.query,
                    used_original=True,
                ))
                fallback_count += 1
    out.sort(key=lambda r: (r.task_id, r.style_id))
    if fallback_count:
        print(
            f"[thinking_style.loader] {fallback_count} (task, style) cells used "
            f"original task.query as fallback"
        )
    return out
