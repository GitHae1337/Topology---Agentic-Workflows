"""Per-benchmark answer extraction + scoring.

Each model output is expected to end with '#### X' where X is:
    - GSM8K:    integer (or decimal) — extract digits
    - AQuA:     letter A..E
    - MMLU-Pro: letter A..J

FORMAT_HINTS is appended to the user input before sending to the topology
to coax the final-answer line.
"""
import re
from typing import Callable, Optional


def extract_gsm8k(output: str) -> Optional[str]:
    """Extract the integer/decimal after '#### ' marker."""
    m = re.search(r"####\s*(-?\d+(?:\.\d+)?)", output)
    return m.group(1).strip() if m else None


def _extract_letter(output: str, max_letter: str) -> Optional[str]:
    """Extract a single letter A..max_letter after '#### ' marker."""
    pattern = rf"####\s*([A-{max_letter}])\b"
    m = re.search(pattern, output, re.IGNORECASE)
    return m.group(1).upper() if m else None


def extract_aqua(output: str) -> Optional[str]:
    return _extract_letter(output, "E")


def extract_mmlu_pro(output: str) -> Optional[str]:
    return _extract_letter(output, "J")


EXTRACTORS: dict[str, Callable[[str], Optional[str]]] = {
    "gsm8k": extract_gsm8k,
    "aqua": extract_aqua,
    "mmlu_pro": extract_mmlu_pro,
}


FORMAT_HINTS: dict[str, str] = {
    "gsm8k": (
        "Think step by step, then end your answer with a line of the exact form "
        "'#### N' where N is the final integer."
    ),
    "aqua": (
        "Reason step by step, then end your answer with a line of the exact form "
        "'#### X' where X is one of A, B, C, D, E."
    ),
    "mmlu_pro": (
        "Reason step by step, then end your answer with a line of the exact form "
        "'#### X' where X is a single letter from A to J."
    ),
}


def score(extracted: Optional[str], expected: str) -> bool:
    """Strict equality after upper-casing and trimming."""
    if extracted is None:
        return False
    return extracted.strip().upper() == expected.strip().upper()
