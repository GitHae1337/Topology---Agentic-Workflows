import { useState } from 'react';
import { useSessionStore } from '../../store';

// Floating panel for the researcher (not the participant). On every new trial
// the researcher fills in (participant_id, task_id) and clicks Start Trial,
// which mints a fresh session and resets the canvas to a clean state.
//
// Renders as an inline TopBar item. The expanded panel uses absolute
// positioning so it overlays the canvas without disturbing TopBar layout.
export const ResearcherPanel = () => {
  const [open, setOpen] = useState(false);
  const [participantId, setParticipantId] = useState(
    () => localStorage.getItem('mas_participant_id') || ''
  );
  const [taskId, setTaskId] = useState('');
  const startTrial = useSessionStore((s) => s.startTrial);
  const currentSessionId = useSessionStore((s) => s.sessionId);

  const handleStart = async () => {
    const p = participantId.trim();
    const t = taskId.trim();
    if (!p || !t) {
      console.warn('[ResearcherPanel] participantId/taskId required');
      return;
    }
    await startTrial(p, t);
    console.log('[ResearcherPanel] trial started');
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="px-3 py-1.5 bg-[#262626] hover:bg-[#333] border border-[#404040] rounded-lg text-[#a3a3a3] hover:text-white text-sm cursor-pointer transition-colors"
        title="Researcher Mode"
      >
        Researcher
      </button>

      {open && (
        <div className="absolute top-full right-0 mt-2 bg-[#1f1f1f] border border-[#404040] rounded-lg shadow-xl p-3 w-72 text-sm z-50">
          <div className="flex justify-between items-center mb-2">
            <span className="font-semibold text-white">Researcher Mode</span>
            <button
              onClick={() => setOpen(false)}
              className="text-[#888] hover:text-white"
              title="Close"
            >
              X
            </button>
          </div>

          <label className="block mb-2">
            <span className="text-xs text-[#a3a3a3]">participant_id</span>
            <input
              type="text"
              value={participantId}
              onChange={(e) => setParticipantId(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#404040] rounded px-2 py-1 mt-0.5 text-white"
              placeholder="P01"
            />
          </label>

          <label className="block mb-2">
            <span className="text-xs text-[#a3a3a3]">task_id</span>
            <input
              type="text"
              value={taskId}
              onChange={(e) => setTaskId(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#404040] rounded px-2 py-1 mt-0.5 text-white"
              placeholder="travelplanner-0"
            />
          </label>

          <button
            onClick={handleStart}
            className="w-full bg-[#404040] hover:bg-[#525252] text-white rounded py-1.5 text-xs font-medium border border-[#525252]"
          >
            Start Trial (resets canvas)
          </button>

          {currentSessionId && (
            <div className="mt-2 text-[10px] text-[#666] break-all">
              session: {currentSessionId}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
