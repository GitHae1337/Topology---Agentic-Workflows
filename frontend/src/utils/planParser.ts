// Frontend port of backend/app/benchmarks/travelplanner/parser.py.
// Extracts a list-of-dicts plan from an LLM's natural-language reply so the
// chat UI can render a Korean-localized plan card instead of the raw output.
//
// Strategies, in order:
//   1. Fenced code block ```python ... ``` or ```json ... ```
//   2. Bare list-of-dicts span starting with '[{' and ending with '}]'
// Returns null if no parseable plan list is recoverable.

export interface PlanDay {
  days: number;
  current_city: string;
  transportation?: string;
  breakfast?: string;
  lunch?: string;
  dinner?: string;
  attraction?: string;
  accommodation?: string;
  // LLM-written 2-3 sentence Korean narrative for the day. Optional —
  // backend prompt requests it; graceful when absent.
  description?: string;
  [key: string]: unknown;
}

const FENCE_RE = /```(?:python|json)?\s*\n?([\s\S]*?)```/gi;
const BARE_LIST_RE = /\[\s*\{[\s\S]*\}\s*\]/;

function isListOfDicts(value: unknown): value is PlanDay[] {
  if (!Array.isArray(value)) return false;
  return value.every((item) => typeof item === 'object' && item !== null && !Array.isArray(item));
}

function tryParse(span: string): PlanDay[] | null {
  // JSON.parse is strict — Python repr (single quotes, None) won't work.
  // Coerce common Python-isms before parsing.
  const cleaned = span
    .trim()
    .replace(/\bNone\b/g, 'null')
    .replace(/\bTrue\b/g, 'true')
    .replace(/\bFalse\b/g, 'false');

  let parsed: unknown = null;
  try {
    parsed = JSON.parse(cleaned);
  } catch {
    // Try with single quotes → double quotes (lossy heuristic but catches
    // most LLM output that uses single quotes inside a Python list literal).
    try {
      const requoted = cleaned.replace(/'/g, '"');
      parsed = JSON.parse(requoted);
    } catch {
      return null;
    }
  }
  return isListOfDicts(parsed) ? parsed : null;
}

export function parsePlan(text: string): PlanDay[] | null {
  if (!text) return null;

  // 1. Fenced code blocks — pick the LAST one (final answer convention)
  const fences: string[] = [];
  let match: RegExpExecArray | null;
  FENCE_RE.lastIndex = 0;
  while ((match = FENCE_RE.exec(text)) !== null) {
    fences.push(match[1]);
  }
  if (fences.length > 0) {
    const plan = tryParse(fences[fences.length - 1]);
    if (plan) return plan;
  }

  // 2. Bare list-of-dicts span
  const bare = text.match(BARE_LIST_RE);
  if (bare) {
    const plan = tryParse(bare[0]);
    if (plan) return plan;
  }

  return null;
}
