import { create } from 'zustand';
import { editLogApi } from '../api/editLog';
import { useCanvasStore } from './canvasStore';

// Persisted session keys. We deliberately keep both the id and startedAt in
// localStorage so a page reload mid-study resumes the same session record on
// the server side rather than creating a new one.
const STORAGE_KEY_SESSION_ID = 'mas_session_id';
const STORAGE_KEY_STARTED_AT = 'mas_session_started_at';
const STORAGE_KEY_PARTICIPANT_ID = 'mas_participant_id';
const STORAGE_KEY_TASK_ID = 'mas_task_id';

interface SessionState {
  sessionId: string | null;
  participantId: string | null;
  taskId: string | null;
  startedAt: string | null;
  firstClickAt: string | null;
  hasFiredSessionStart: boolean;

  initSession: () => Promise<void>;
  startTrial: (participantId: string, taskId: string) => Promise<void>;
  setParticipantId: (id: string) => void;
  markFirstClick: () => void;
  reset: () => void;
}

const readStorage = (key: string): string | null => {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(key);
};

const writeStorage = (key: string, value: string | null): void => {
  if (typeof window === 'undefined') return;
  if (value === null) {
    window.localStorage.removeItem(key);
  } else {
    window.localStorage.setItem(key, value);
  }
};

export const useSessionStore = create<SessionState>((set, get) => ({
  sessionId: null,
  participantId: null,
  taskId: null,
  startedAt: null,
  firstClickAt: null,
  hasFiredSessionStart: false,

  // Called once at app mount. Restores or creates a session, then fires
  // /session-start on the backend the first time only.
  initSession: async () => {
    const state = get();
    if (state.hasFiredSessionStart) {
      console.log('[sessionStore] initSession skipped: already fired');
      return;
    }

    let sessionId = readStorage(STORAGE_KEY_SESSION_ID);
    let startedAt = readStorage(STORAGE_KEY_STARTED_AT);
    const participantId = readStorage(STORAGE_KEY_PARTICIPANT_ID);
    const taskId = readStorage(STORAGE_KEY_TASK_ID);

    const isNewSession = !sessionId || !startedAt;
    if (isNewSession) {
      sessionId = crypto.randomUUID();
      startedAt = new Date().toISOString();
      writeStorage(STORAGE_KEY_SESSION_ID, sessionId);
      writeStorage(STORAGE_KEY_STARTED_AT, startedAt);
      console.log(`[sessionStore] new session created: ${sessionId}`);
    } else {
      console.log(`[sessionStore] session restored: ${sessionId}`);
    }

    set({
      sessionId,
      startedAt,
      participantId,
      taskId,
      hasFiredSessionStart: true,
    });

    await editLogApi.sessionStart({
      sessionId: sessionId!,
      participantId,
      startedAt: startedAt!,
      userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
    });
  },

  // Researcher-initiated trial start. A "trial" = one (participant, task)
  // instance — the researcher panel calls this each time the participant
  // moves on to a new (task, topology) attempt. We mint a fresh sessionId,
  // wipe the canvas to a clean slate, and write trial metadata to the
  // backend so master-table builders can join everything later.
  startTrial: async (participantId: string, taskId: string) => {
    const sessionId = crypto.randomUUID();
    const startedAt = new Date().toISOString();

    writeStorage(STORAGE_KEY_SESSION_ID, sessionId);
    writeStorage(STORAGE_KEY_STARTED_AT, startedAt);
    writeStorage(STORAGE_KEY_PARTICIPANT_ID, participantId);
    writeStorage(STORAGE_KEY_TASK_ID, taskId);

    set({
      sessionId,
      startedAt,
      participantId,
      taskId,
      firstClickAt: null,
      hasFiredSessionStart: true,
    });

    useCanvasStore.getState().resetForNewTrial();

    await editLogApi.sessionStart({
      sessionId,
      participantId,
      taskId,
      startedAt,
      userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
    });

    console.log(`[sessionStore] startTrial: P=${participantId}, task=${taskId}, session=${sessionId}`);
  },

  setParticipantId: (id: string) => {
    writeStorage(STORAGE_KEY_PARTICIPANT_ID, id);
    set({ participantId: id });
    console.log(`[sessionStore] participantId set: ${id}`);
  },

  // First canvas interaction. Idempotent: only the first call counts.
  markFirstClick: () => {
    const state = get();
    if (state.firstClickAt) return;
    const now = new Date().toISOString();
    set({ firstClickAt: now });
    console.log(`[sessionStore] firstClickAt: ${now}`);

    if (state.sessionId) {
      editLogApi.appendEvent({
        sessionId: state.sessionId,
        timestamp: now,
        eventType: 'first_canvas_click',
        payload: {},
      });
    }
  },

  // Manual reset (used if the researcher wants a fresh session for a new
  // participant on the same machine without clearing localStorage by hand).
  reset: () => {
    writeStorage(STORAGE_KEY_SESSION_ID, null);
    writeStorage(STORAGE_KEY_STARTED_AT, null);
    writeStorage(STORAGE_KEY_PARTICIPANT_ID, null);
    writeStorage(STORAGE_KEY_TASK_ID, null);
    set({
      sessionId: null,
      participantId: null,
      taskId: null,
      startedAt: null,
      firstClickAt: null,
      hasFiredSessionStart: false,
    });
    console.log('[sessionStore] reset');
  },
}));
