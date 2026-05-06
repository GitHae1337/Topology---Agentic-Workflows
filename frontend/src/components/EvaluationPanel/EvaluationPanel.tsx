import { useEffect, useState } from 'react';
import { useSessionStore, useCanvasStore } from '../../store';
import {
  benchmarksApi,
  ConstraintResult,
  ConstraintStatus,
} from '../../api/benchmarks';
import { logsApi } from '../../api/logs';
import guideConfig from './guideConfig.json';

// Stage 1 — Self-Assessment Guide.
//
// The participant sees a non-scoring guide (5 dimensions + 기타). Automatic
// evaluation still runs in the background per assistant message but is
// hidden from the UI; both the eval result and every dimension expand/
// collapse action are POSTed to /api/logs/evaluation as a hidden trial log
// for post-hoc research analysis.
//
// Helpers below (CONSTRAINT_LABELS, translateReason, ConstraintRow,
// COMMONSENSE_KEYS, HARD_KEYS, etc.) are intentionally kept-but-unused so
// Stage 2 can revive them if a different UI is needed. Do not delete.

export const COMMONSENSE_KEYS = [
  'is_reasonable_visiting_city',
  'is_valid_restaurants',
  'is_valid_attractions',
  'is_valid_accommodation',
  'is_valid_transportation',
  'is_valid_information_in_current_city',
  'is_valid_information_in_sandbox',
  'is_not_absent',
] as const;

export const HARD_KEYS = [
  'valid_cost',
  'valid_room_rule',
  'valid_cuisine',
  'valid_room_type',
  'valid_transportation',
] as const;

const CONSTRAINT_LABELS: Record<string, string> = {
  is_reasonable_visiting_city: '합리적 도시 경로',
  is_valid_restaurants: '식당 다양성',
  is_valid_attractions: '관광지 다양성',
  is_valid_accommodation: '최소 숙박일',
  is_valid_transportation: '교통수단 불일치',
  is_valid_information_in_current_city: '현재 도시 정보 일치',
  is_valid_information_in_sandbox: '데이터 일치',
  is_not_absent: '정보 누락 없음',
  valid_cost: '예산 충족',
  valid_room_rule: '숙소 규약 충족',
  valid_cuisine: '음식 종류 충족',
  valid_room_type: '객실 유형 충족',
  valid_transportation: '교통수단 충족',
};

const STATUS_ICON: Record<ConstraintStatus, string> = {
  pass: '✓',
  fail: '✗',
  skipped: '–',
};

// Translate vendored evaluator's English reason messages to Korean.
// Patterns are checked in order — first match wins. Captures handle day
// numbers / cities / meal types so dynamic parts stay correct.
const MEAL_KO: Record<string, string> = {
  breakfast: '아침',
  lunch: '점심',
  dinner: '저녁',
};
const CATEGORY_KO: Record<string, string> = {
  breakfast: '아침',
  lunch: '점심',
  dinner: '저녁',
  attraction: '관광지',
  accommodation: '숙소',
  transportation: '교통편',
  restaurant: '식당',
};

const REASON_PATTERNS: Array<[RegExp, (m: RegExpMatchArray) => string]> = [
  [/^The trip should be a closed circle\.?$/, () => '여행은 출발지로 돌아오는 순환 경로여야 합니다.'],
  [/^The restaurant in day (\d+) (\w+) is repeated\.?$/, (m) => `${m[1]}일차 ${MEAL_KO[m[2]] ?? m[2]} 식당이 중복되었습니다.`],
  [/^The (\w+) in day (\d+) is repeated\.?$/, (m) => `${m[2]}일차 ${CATEGORY_KO[m[1]] ?? m[1]}이(가) 중복되었습니다.`],
  [/^The (\w+) in day (\d+) is invalid in the sandbox\.?$/, (m) => `${m[2]}일차 ${CATEGORY_KO[m[1]] ?? m[1]} 항목이 참고 자료에 없습니다.`],
  [/^The transportation in day (\d+) is invalid city choice\.?$/, (m) => `${m[1]}일차 교통편 도시 선택이 잘못되었습니다.`],
  [/^Invalid City Number\.?$/, () => '방문 도시 수가 잘못되었습니다.'],
  [/^The first day's city should be (.+?)\.?$/, (m) => `1일차 도시는 ${m[1]}이어야 합니다.`],
  [/^The city sequence is invalid\.?$/, () => '도시 방문 순서가 잘못되었습니다.'],
  [/^(.+?) is not a valid city\.?$/, (m) => `${m[1]}는 유효한 도시가 아닙니다.`],
  [/^(.+?) is not in (.+?)\.?$/, (m) => `${m[1]}는 ${m[2]} 안에 없습니다.`],
  [/^No transportation in day (\d+) is not allowed\.?$/, (m) => `${m[1]}일차 교통편 누락 (필수)`],
  [/^No attaction in day (\d+) is not allowed\.?$/, (m) => `${m[1]}일차 관광지 누락 (필수)`],
  [/^No accommodation in day (\d+) is not allowed\.?$/, (m) => `${m[1]}일차 숙소 누락 (필수)`],
  [/^No meal in day (\d+) is not allowed\.?$/, (m) => `${m[1]}일차 식사 누락 (필수)`],
  [/^No (\w+) Info\.?$/, (m) => `${CATEGORY_KO[m[1].toLowerCase()] ?? m[1]} 정보 누락`],
  [/^The absent information is more than 50%\.?$/, () => '정보 누락이 50% 초과'],
];

function translateReason(reason: string | undefined): string | undefined {
  if (!reason) return reason;
  for (const [re, fn] of REASON_PATTERNS) {
    const m = reason.match(re);
    if (m) return fn(m);
  }
  return reason;  // unmatched → keep original
}

const STATUS_COLOR: Record<ConstraintStatus, string> = {
  pass: 'text-green-400',
  fail: 'text-red-400',
  skipped: 'text-[#666]',
};

export function ConstraintRow({
  name,
  result,
}: {
  name: string;
  result: ConstraintResult | undefined;
}) {
  const status: ConstraintStatus = result?.status ?? 'skipped';
  const reason = result?.reason;
  return (
    <div className="flex items-start gap-2 text-xs py-0.5">
      <span className={`w-4 ${STATUS_COLOR[status]} font-mono`}>
        {STATUS_ICON[status]}
      </span>
      <div className="flex-1">
        <div className="text-white">{CONSTRAINT_LABELS[name] ?? name}</div>
        {reason && (
          <div className="text-[#888] text-[10px] mt-0.5 break-words">
            {translateReason(reason)}
          </div>
        )}
      </div>
    </div>
  );
}

interface EvaluationPanelProps {
  isOpen: boolean;
  onToggle: () => void;
}

export const EvaluationPanel = ({ isOpen, onToggle }: EvaluationPanelProps) => {
  const taskId = useSessionStore((s) => s.taskId);
  const participantId = useSessionStore((s) => s.participantId);
  const sessionId = useSessionStore((s) => s.sessionId);
  const messages = useCanvasStore((s) => s.currentChat.messages);

  // iterationIndex starts at 0 and increments to 1 on the first auto-eval
  // of the trial, 2 on the second, etc. Resets when taskId changes.
  const [iterationIndex, setIterationIndex] = useState(0);
  const [evaluatedMessageId, setEvaluatedMessageId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  // Find the latest assistant message in the current chat.
  const latestAssistant = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === 'assistant') return m;
    }
    return null;
  })();
  const triggerKey = latestAssistant ? latestAssistant.id : null;

  // Reset on new trial (taskId change).
  useEffect(() => {
    setIterationIndex(0);
    setEvaluatedMessageId(null);
    setExpanded(new Set());
  }, [taskId]);

  // Stream A — hidden automatic evaluation. Fetch but never render.
  // The result is POSTed to /api/logs/evaluation tagged with the current
  // iterationIndex so the researcher can correlate auto-eval with
  // self-judgment post-hoc.
  useEffect(() => {
    if (!taskId || !latestAssistant) return;
    if (evaluatedMessageId === triggerKey) return;

    let cancelled = false;
    const nextIter = iterationIndex + 1;

    console.log(
      '[EvaluationPanel] Stream A auto-eval task=', taskId,
      'msg=', latestAssistant.id, 'iter=', nextIter,
    );
    benchmarksApi
      .evaluateTravelPlanner(taskId, latestAssistant.content)
      .then((r) => {
        if (cancelled) return;
        setEvaluatedMessageId(latestAssistant.id);
        setIterationIndex(nextIter);
        if (sessionId && participantId) {
          logsApi.logEvaluation({
            sessionId,
            participantId,
            taskId,
            iterationIndex: nextIter,
            automaticEvaluation: r,
          });
        }
      })
      .catch((e: Error) => {
        if (cancelled) return;
        console.error('[EvaluationPanel] auto-eval failed:', e);
      });

    return () => { cancelled = true; };
  }, [taskId, triggerKey, latestAssistant, evaluatedMessageId, iterationIndex, sessionId, participantId]);

  // Stream B — guide expand/collapse interaction log.
  const toggleDimension = (dimensionId: string) => {
    const next = new Set(expanded);
    let actionType: 'expand' | 'collapse';
    if (next.has(dimensionId)) {
      next.delete(dimensionId);
      actionType = 'collapse';
    } else {
      next.add(dimensionId);
      actionType = 'expand';
    }
    setExpanded(next);

    if (sessionId && participantId && taskId) {
      logsApi.logEvaluation({
        sessionId,
        participantId,
        taskId,
        iterationIndex,
        guideAction: { type: actionType, dimensionId },
      });
    }
  };

  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className="px-3 py-1.5 bg-[#262626] hover:bg-[#333] border border-[#404040] rounded-lg text-[#a3a3a3] hover:text-white text-sm cursor-pointer transition-colors"
        title="자기 점검 가이드"
      >
        평가
      </button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-2 bg-[#1f1f1f] border border-[#404040] rounded-lg shadow-xl p-3 w-[420px] max-h-[80vh] overflow-y-auto text-sm z-50">
          <div className="flex justify-between items-center mb-2">
            <span className="font-semibold text-white">자기 점검 가이드</span>
            <button
              onClick={onToggle}
              className="text-[#888] hover:text-white"
              title="닫기"
            >
              X
            </button>
          </div>

          <div className="text-[11px] text-[#a3a3a3] mb-3 leading-snug">
            {guideConfig.header}
          </div>

          <div className="space-y-1">
            {guideConfig.dimensions.map((dim) => {
              const isExpanded = expanded.has(dim.id);
              return (
                <div key={dim.id} className="bg-[#0a0a0a] border border-[#333] rounded">
                  <button
                    onClick={() => toggleDimension(dim.id)}
                    className="w-full flex items-center justify-between px-2.5 py-2 text-left hover:bg-[#171717] transition-colors"
                  >
                    <span className="text-white text-xs font-medium">
                      {dim.label}
                    </span>
                    <span className="text-[#666] text-xs">
                      {isExpanded ? '▾' : '▸'}
                    </span>
                  </button>
                  {isExpanded && (
                    <ul className="px-4 py-2 space-y-1.5 border-t border-[#262626] list-disc list-outside marker:text-[#666]">
                      {dim.subQuestions.map((q) => (
                        <li
                          key={q.id}
                          className="text-[11px] text-[#d4d4d4] leading-snug pl-1"
                        >
                          {q.text}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
