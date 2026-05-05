import { useEffect, useState } from 'react';
import { useSessionStore, useCanvasStore } from '../../store';
import {
  benchmarksApi,
  ConstraintResult,
  ConstraintStatus,
  EvaluationResult,
} from '../../api/benchmarks';

// Floating panel that auto-grades the latest agent reply against the
// 13 TravelPlanner constraints (8 commonsense + 5 hard) for the active
// task. Reference-only — the participant decides when to stop.
//
// Trigger: every time `currentChat.messages` gains a new assistant message
// (and a task is set), we POST that message's content to the evaluator.

const COMMONSENSE_KEYS = [
  'is_reasonable_visiting_city',
  'is_valid_restaurants',
  'is_valid_attractions',
  'is_valid_accommodation',
  'is_valid_transportation',
  'is_valid_information_in_current_city',
  'is_valid_information_in_sandbox',
  'is_not_absent',
] as const;

const HARD_KEYS = [
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

function ConstraintRow({
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
  const messages = useCanvasStore((s) => s.currentChat.messages);

  const [result, setResult] = useState<EvaluationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [evaluatedMessageId, setEvaluatedMessageId] = useState<string | null>(null);

  // Find the latest assistant message in the current chat.
  const latestAssistant = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === 'assistant') return m;
    }
    return null;
  })();

  const triggerKey = latestAssistant ? latestAssistant.id : null;

  // Reset evaluation state whenever the active task changes (new trial).
  // Without this, switching trials shows the previous trial's pass/fail
  // until a new evaluation completes.
  useEffect(() => {
    setResult(null);
    setError(null);
    setEvaluatedMessageId(null);
    setLoading(false);
  }, [taskId]);

  useEffect(() => {
    if (!taskId || !latestAssistant) {
      return;
    }
    if (evaluatedMessageId === triggerKey) {
      return; // already evaluated this message
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    console.log(
      '[EvaluationPanel] auto-evaluate task=',
      taskId,
      'msg=',
      latestAssistant.id,
    );
    benchmarksApi
      .evaluateTravelPlanner(taskId, latestAssistant.content)
      .then((r) => {
        if (cancelled) return;
        setResult(r);
        setEvaluatedMessageId(latestAssistant.id);
        setLoading(false);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        console.error('[EvaluationPanel] evaluate failed:', e);
        setError(e.message);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [taskId, triggerKey, latestAssistant, evaluatedMessageId]);

  const handleManualReeval = () => {
    if (!taskId || !latestAssistant) return;
    setEvaluatedMessageId(null); // force re-trigger via useEffect
  };

  const summaryLine = (() => {
    if (!result) return null;
    return `전달=${result.delivered ? 'yes' : 'no'} · 통과 ${result.passed_count}/${result.evaluated_count} · 전체통과=${result.all_passed ? 'yes' : 'no'}`;
  })();

  const buttonLabel = (() => {
    if (!taskId) return '평가';
    if (loading) return '평가 중...';
    if (!result) return '평가 (대기)';
    return `평가 ${result.passed_count}/${result.evaluated_count}${result.all_passed ? ' ✓' : ''}`;
  })();

  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className="px-3 py-1.5 bg-[#262626] hover:bg-[#333] border border-[#404040] rounded-lg text-[#a3a3a3] hover:text-white text-sm cursor-pointer transition-colors"
        title="최신 응답에 대한 제약 사항 평가"
      >
        {buttonLabel}
      </button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-2 bg-[#1f1f1f] border border-[#404040] rounded-lg shadow-xl p-3 w-[420px] max-h-[80vh] overflow-y-auto text-sm z-50">
          <div className="flex justify-between items-center mb-2">
            <span className="font-semibold text-white">제약 사항 평가</span>
            <div className="flex gap-1.5 items-center">
              <button
                onClick={handleManualReeval}
                disabled={!taskId || !latestAssistant}
                className="text-[#888] hover:text-white text-xs disabled:opacity-30 disabled:cursor-not-allowed"
                title="최신 응답으로 다시 평가"
              >
                재평가
              </button>
              <button
                onClick={onToggle}
                className="text-[#888] hover:text-white"
                title="닫기"
              >
                X
              </button>
            </div>
          </div>

          {!taskId && (
            <div className="text-[#888] text-xs">
              활성 과제가 없습니다. 처음 화면에서 task_id를 입력하세요.
            </div>
          )}

          {taskId && !latestAssistant && (
            <div className="text-[#888] text-xs">
              먼저 워크플로우를 실행하세요. 마지막 응답을 평가합니다.
            </div>
          )}

          {loading && <div className="text-[#888] text-xs">평가 중...</div>}

          {error && (
            <div className="text-[#dc2626] text-xs break-all">
              평가 실패: {error}
            </div>
          )}

          {result && (
            <div className="space-y-2">
              <div className="text-[10px] text-[#a3a3a3] font-mono break-all">
                {summaryLine}
              </div>

              {/* 두 단계 구조:
                  1단계 — 기본 검증 (commonsense 8개) — 항상 표시.
                  2단계 — 추가 제약 (hard 5개) — 1단계 핵심 통과(gate) 시에만
                          개별 평가. 미통과 시 5개 row 대신 한 줄 안내. */}
              {(() => {
                const csCount = COMMONSENSE_KEYS.reduce(
                  (acc, k) => acc + (result.constraints.commonsense[k]?.status === 'pass' ? 1 : 0),
                  0,
                );

                const GATE_FAIL_REASONS = new Set([
                  '공통상식 검증 실패로 하드 제약 미평가',
                  '계획 미생성',
                ]);
                const hardEntries = HARD_KEYS.map((k) => result.constraints.hard[k]);
                const isHardGateFail = hardEntries.every(
                  (e) => e?.status === 'skipped' && GATE_FAIL_REASONS.has(e?.reason ?? ''),
                );
                const hardEvaluated = hardEntries.filter((e) => e?.status !== 'skipped').length;
                const hardPassed = hardEntries.filter((e) => e?.status === 'pass').length;

                return (
                  <div className="bg-[#0a0a0a] border border-[#333] rounded p-2 space-y-3">
                    {/* 1단계 */}
                    <div>
                      <div className="text-[11px] font-semibold text-[#a3a3a3] mb-1.5">
                        1단계: 기본 검증 ({csCount}/8)
                      </div>
                      <div className="space-y-0.5">
                        {COMMONSENSE_KEYS.map((k) => (
                          <ConstraintRow
                            key={k}
                            name={k}
                            result={result.constraints.commonsense[k]}
                          />
                        ))}
                      </div>
                    </div>

                    {/* 2단계 */}
                    <div>
                      <div className="text-[11px] font-semibold text-[#a3a3a3] mb-1.5">
                        2단계: 추가 제약
                        {!isHardGateFail && ` (${hardPassed}/${hardEvaluated})`}
                      </div>
                      {isHardGateFail ? (
                        <div className="text-[11px] text-[#888] bg-[#171717] border border-[#262626] rounded px-2 py-1.5 leading-snug">
                          기본 검증 통과 시에만 추가 제약(예산 / 숙소 규약 / 음식 / 객실 / 교통수단)을 평가합니다 — 현재는 기본 검증 미통과로 생략됨.
                        </div>
                      ) : (
                        <div className="space-y-0.5">
                          {HARD_KEYS.map((k) => (
                            <ConstraintRow
                              key={k}
                              name={k}
                              result={result.constraints.hard[k]}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
