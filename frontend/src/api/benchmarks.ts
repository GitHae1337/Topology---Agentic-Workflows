// Benchmark API client. Mirrors backend/app/api/benchmarks.py endpoints.
// Used by TaskPanel (task fetch) and EvaluationView (POST evaluate).

const API_BASE = '/api/benchmarks';

export interface TravelPlannerReferenceItem {
  Description: string;
  Content: string;
  // Backend best-effort parse of Content (pd.read_fwf). null when parsing
  // failed — frontend falls back to rendering Content as <pre>.
  Records: Array<Record<string, string | number>> | null;
}

export interface TravelPlannerLocalConstraint {
  'house rule': string | null;
  cuisine: string | null;
  'room type': string | null;
  transportation: string | null;
}

export interface TravelPlannerProblem {
  task_id: string;
  org: string;
  dest: string;
  days: number;
  visiting_city_number: number;
  date: string;
  people_number: number;
  budget: number | null;
  level: string;
  query: string;
  local_constraint: TravelPlannerLocalConstraint;
  reference_information: TravelPlannerReferenceItem[];
  // 'KRW' when Korean override applied (budget is in won), else 'USD'.
  currency: 'USD' | 'KRW';
}

// Lightweight item for the ResearcherLanding dropdown — backend lists all
// Korean-translated tasks via GET /travelplanner/translations.
export interface TravelPlannerTranslationItem {
  task_id: string;
  level: string;
  days: number;
  org: string;
  dest: string;
}

export type ConstraintStatus = 'pass' | 'fail' | 'skipped';

export interface ConstraintResult {
  status: ConstraintStatus;
  reason?: string;
}

export interface EvaluationResult {
  delivered: boolean;
  all_passed: boolean;
  passed_count: number;
  evaluated_count: number;
  constraints: {
    commonsense: Record<string, ConstraintResult>;
    hard: Record<string, ConstraintResult>;
  };
  parsed_plan: Array<Record<string, unknown>> | null;
}

export const benchmarksApi = {
  async listTravelPlannerTranslations(): Promise<TravelPlannerTranslationItem[]> {
    console.log('[benchmarksApi] GET translations');
    const resp = await fetch(`${API_BASE}/travelplanner/translations`);
    if (!resp.ok) {
      throw new Error(`listTravelPlannerTranslations failed: ${resp.status}`);
    }
    return resp.json();
  },

  async getTravelPlannerProblem(taskId: string): Promise<TravelPlannerProblem> {
    console.log('[benchmarksApi] GET problem:', taskId);
    const resp = await fetch(`${API_BASE}/travelplanner/problems/${encodeURIComponent(taskId)}`);
    if (!resp.ok) {
      throw new Error(`getTravelPlannerProblem ${taskId} failed: ${resp.status}`);
    }
    return resp.json();
  },

  async evaluateTravelPlanner(taskId: string, output: string): Promise<EvaluationResult> {
    console.log('[benchmarksApi] POST evaluate:', taskId, 'output_chars=', output.length);
    const resp = await fetch(`${API_BASE}/travelplanner/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, output }),
    });
    if (!resp.ok) {
      throw new Error(`evaluateTravelPlanner ${taskId} failed: ${resp.status}`);
    }
    return resp.json();
  },
};
