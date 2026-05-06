// Client for /api/logs/evaluation — Stage 1 self-assessment guide logging.
// Two streams in one endpoint:
//   A. automaticEvaluation populated, guideAction null
//   B. guideAction populated, automaticEvaluation null

const API_BASE = '/api/logs';

interface BasePayload {
  sessionId: string;
  participantId: string;
  taskId: string;
  iterationIndex: number;
}

export interface AutomaticEvalLog extends BasePayload {
  automaticEvaluation: unknown;
}

export interface GuideActionLog extends BasePayload {
  guideAction: {
    type: 'expand' | 'collapse';
    dimensionId: string;
  };
}

export type EvaluationLog = AutomaticEvalLog | GuideActionLog;

export const logsApi = {
  async logEvaluation(payload: EvaluationLog): Promise<void> {
    const body = {
      timestamp: new Date().toISOString(),
      ...payload,
    };
    console.log('[logsApi] POST /evaluation:', body);
    const resp = await fetch(`${API_BASE}/evaluation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      console.error('[logsApi] evaluation log failed:', resp.status);
    }
  },
};
