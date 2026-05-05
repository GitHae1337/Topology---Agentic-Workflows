// Edit-log API client. Mirrors backend/app/api/edit_log.py endpoints.
// Used by sessionStore (session lifecycle) and canvasStore (per-action edit logging).

const API_BASE = '/api/edit-log';

export interface SessionStartPayload {
  sessionId: string;
  participantId: string | null;
  taskId?: string | null;
  startedAt: string;
  userAgent?: string;
}

export interface EditLogAppendPayload {
  sessionId: string;
  timestamp: string;
  action: string;
  payload: Record<string, unknown>;
  undoStackDepth: number;
}

export interface EventPayload {
  sessionId: string;
  timestamp: string;
  eventType: string;
  payload?: Record<string, unknown>;
}

// Send-and-forget POST. We log on failure but never throw, since edit-log
// failure must not break the user's authoring flow.
const postJson = async (path: string, body: unknown): Promise<void> => {
  console.log(`[editLogApi] POST ${path}`);
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    console.error(`[editLogApi] ${path} failed with status ${response.status}`);
  }
};

export const editLogApi = {
  // Called once when a participant session begins.
  sessionStart: (payload: SessionStartPayload) => postJson('/session-start', payload),

  // Called for every structural canvas mutation.
  appendEdit: (payload: EditLogAppendPayload) => postJson('/append', payload),

  // Called for non-edit timing events (first_canvas_click, undo, redo, session_end).
  appendEvent: (payload: EventPayload) => postJson('/event', payload),
};
