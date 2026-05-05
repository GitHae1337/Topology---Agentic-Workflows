import { useEffect, useState } from 'react';
import { useSessionStore } from '../../store';
import { benchmarksApi, TravelPlannerTranslationItem } from '../../api/benchmarks';

// Full-page landing screen the researcher fills in BEFORE handing the
// computer to the participant. Contains the same form ResearcherPanel had
// (participant_id + task_id), but no longer floats over a canvas — the
// canvas only appears after Start is pressed.
//
// On Start: mints a fresh trial session and notifies the parent so the app
// can switch to canvas mode.
const LEVEL_ORDER: Record<string, number> = { easy: 0, medium: 1, hard: 2 };

export const ResearcherLanding = ({ onStart }: { onStart: () => void }) => {
  const [participantId, setParticipantId] = useState(
    () => localStorage.getItem('mas_participant_id') || ''
  );
  const [taskId, setTaskId] = useState(
    () => localStorage.getItem('mas_task_id') || ''
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [tasks, setTasks] = useState<TravelPlannerTranslationItem[]>([]);
  const [loadingTasks, setLoadingTasks] = useState(true);
  const [tasksError, setTasksError] = useState<string | null>(null);

  const startTrial = useSessionStore((s) => s.startTrial);

  useEffect(() => {
    let cancelled = false;
    console.log('[ResearcherLanding] fetching translation list');
    benchmarksApi
      .listTravelPlannerTranslations()
      .then((items) => {
        if (cancelled) return;
        const sorted = [...items].sort((a, b) => {
          const ld = (LEVEL_ORDER[a.level] ?? 99) - (LEVEL_ORDER[b.level] ?? 99);
          if (ld !== 0) return ld;
          if (a.days !== b.days) return a.days - b.days;
          return a.task_id.localeCompare(b.task_id);
        });
        setTasks(sorted);
        setLoadingTasks(false);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        console.error('[ResearcherLanding] task list fetch failed:', e);
        setTasksError(e.message);
        setLoadingTasks(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleStart = async () => {
    const p = participantId.trim();
    const t = taskId.trim();
    if (!p || !t) {
      setError('participant_id와 task_id 둘 다 입력해주세요.');
      return;
    }

    setSubmitting(true);
    setError(null);
    console.log('[ResearcherLanding] start trial', p, t);
    await startTrial(p, t);
    setSubmitting(false);
    onStart();
  };

  return (
    <div className="min-h-screen w-screen flex items-center justify-center bg-[#0a0a0a] text-white">
      <div className="w-[420px] bg-[#171717] border border-[#262626] rounded-xl shadow-2xl p-6">
        <h1 className="text-lg font-semibold mb-1">Researcher Setup</h1>
        <p className="text-xs text-[#888] mb-5">
          참가자 정보 + task_id를 입력한 뒤 Start를 누르세요. 캔버스로 넘어가면
          이 화면은 사라집니다.
        </p>

        <label className="block mb-3">
          <span className="text-xs text-[#a3a3a3]">participant_id</span>
          <input
            type="text"
            value={participantId}
            onChange={(e) => setParticipantId(e.target.value)}
            className="w-full bg-[#0a0a0a] border border-[#404040] rounded px-2 py-1.5 mt-1 text-white text-sm"
            placeholder="P01"
            autoFocus
          />
        </label>

        <label className="block mb-4">
          <span className="text-xs text-[#a3a3a3]">task_id</span>
          {loadingTasks ? (
            <div className="text-[#888] text-xs mt-1">task 목록 불러오는 중...</div>
          ) : tasksError ? (
            <div className="text-[#dc2626] text-xs mt-1 break-all">
              task 목록 불러오기 실패: {tasksError}
            </div>
          ) : (
            <select
              value={taskId}
              onChange={(e) => setTaskId(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#404040] rounded px-2 py-1.5 mt-1 text-white text-sm cursor-pointer"
            >
              <option value="">— task 선택 —</option>
              {tasks.map((t) => (
                <option key={t.task_id} value={t.task_id}>
                  {t.task_id} ({t.level}, {t.days}-day) — {t.org} → {t.dest}
                </option>
              ))}
            </select>
          )}
        </label>

        {error && (
          <div className="text-[#dc2626] text-xs mb-3">{error}</div>
        )}

        <button
          onClick={handleStart}
          disabled={submitting}
          className="w-full bg-[#404040] hover:bg-[#525252] disabled:bg-[#262626] disabled:text-[#666] text-white rounded py-2 text-sm font-medium border border-[#525252]"
        >
          {submitting ? '시작 중...' : 'Start (캔버스로 이동)'}
        </button>
      </div>
    </div>
  );
};
