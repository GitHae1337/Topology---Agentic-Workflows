"""Dispatch between prompt variants via env var PROMPT_VARIANT.

Default: v1 (= prompts_paper_style.py)
Set PROMPT_VARIANT=v2 to use prompts_paper_style_v2.py.

All importers — executors (centralized.py / hierarchical.py / mesh.py) and
the topology preset module (topologies.py) — should import from THIS module
instead of from prompts_paper_style.* directly, so the variant choice is
picked up at process start.

Adding a new variant (v3, v4, ...):
  1) create prompts_paper_style_v<N>.py (import * from a parent variant + override)
  2) add an `elif _VARIANT == "vN":` branch below
"""
import os

_VARIANT = os.environ.get("PROMPT_VARIANT", "v1")
ACTIVE_VARIANT = _VARIANT  # exposed for logging / inspection

if _VARIANT == "v2":
    from .prompts_paper_style_v2 import *  # noqa: F401, F403
else:
    from .prompts_paper_style import *  # noqa: F401, F403
