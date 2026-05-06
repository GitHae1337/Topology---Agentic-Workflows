import { useEffect, useState } from 'react';
import { useSessionStore } from '../../store';
import { benchmarksApi, TravelPlannerProblem, TravelPlannerReferenceItem } from '../../api/benchmarks';

// Korean column-name → display label. Keys are lowercase so English-task
// columns (PascalCase like 'Name', 'Phone') don't accidentally get translated.
const COLUMN_LABELS: Record<string, string> = {
  name: '이름',
  city: '도시',
  cuisine: '메뉴',
  price_per_person: '1인 가격(원)',
  price_per_night: '1박 가격(원)',
  room_type: '객실 유형',
  house_rules: '숙소 규약',
  max_occupancy: '최대 인원',
  minimum_nights: '최소 숙박일',
  rating: '평점',
  address: '주소',
  category: '카테고리',
  type: '유형',
  carrier: '운영사',
  number: '편명/호선',
  from: '출발지',
  to: '도착지',
  departure_time: '출발 시각',
  arrival_time: '도착 시각',
  duration_hours: '소요 시간',
};

// Reference Content. Backend tries to parse the pandas to_string() snapshot
// into structured records (item.Records). When parsing succeeds we render a
// real HTML table for readability; otherwise we fall back to the raw <pre>.
const ReferenceContent = ({ item }: { item: TravelPlannerReferenceItem }) => {
  if (item.Records && item.Records.length > 0) {
    // (1) Hardcoded irrelevant columns. Patterns are case-insensitive regex —
    //     match either exact (lat/long/city) or prefix/substring (unnamed,
    //     average, aggregate) so column-name variants are all caught.
    const HIDDEN_PATTERNS = [
      /^latitude$/i,
      /^longitude$/i,
      // 'city' is intentionally NOT hidden here. Single-city tasks have
      // a uniform city column which the uniform-filter below removes
      // automatically; multi-city (5/7-day) tasks vary, and the user
      // wants to see which option is in which city.
      /^unnamed/i,
      /average/i,
      /aggregate/i,
    ];
    const isHidden = (col: string) =>
      HIDDEN_PATTERNS.some((p) => p.test(col));

    // (2) Uniform-value columns are redundant (every row identical → no signal).
    //     Only apply when there's more than 1 row, otherwise everything gets
    //     stripped trivially.
    const records = item.Records;
    const isUniform = (col: string) => {
      if (records.length <= 1) return false;
      const first = String(records[0][col]);
      return records.every((row) => String(row[col]) === first);
    };

    const columns = Object.keys(records[0]).filter(
      (col) => !isHidden(col) && !isUniform(col)
    );

    if (columns.length === 0) {
      return (
        <div className="px-2 py-2 text-xs text-[#666] border-t border-[#333]">
          표시할 컬럼이 없습니다.
        </div>
      );
    }

    return (
      <div className="border-t border-[#333] max-h-72 overflow-auto">
        <table className="w-full text-xs text-white">
          <thead className="bg-[#171717] sticky top-0">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-2 py-1.5 text-left font-semibold text-[#a3a3a3] whitespace-nowrap"
                >
                  {COLUMN_LABELS[col] ?? col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.map((row, i) => (
              <tr key={i} className={i % 2 === 0 ? 'bg-[#0a0a0a]' : 'bg-[#111]'}>
                {columns.map((col) => (
                  <td key={col} className="px-2 py-1 align-top whitespace-nowrap">
                    {row[col] === '' || row[col] == null ? '—' : String(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  // Parsing failed — fall back to raw text but keep the larger font.
  return (
    <pre className="px-2 py-2 text-xs text-white font-mono whitespace-pre border-t border-[#333] max-h-72 overflow-auto leading-snug">
      {item.Content.trim()}
    </pre>
  );
};

// Floating panel that displays the active TravelPlanner task. Mirrors the
// landing-page form fields and auto-fetches whenever sessionStore.taskId
// changes (e.g. after the researcher hits Start on the landing screen).
interface TaskPanelProps {
  isOpen: boolean;
  onToggle: () => void;
}

export const TaskPanel = ({ isOpen, onToggle }: TaskPanelProps) => {
  const taskId = useSessionStore((s) => s.taskId);

  const [problem, setProblem] = useState<TravelPlannerProblem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [refExpanded, setRefExpanded] = useState<Record<number, boolean>>({});

  useEffect(() => {
    if (!taskId) {
      setProblem(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setProblem(null);

    console.log('[TaskPanel] fetching task:', taskId);
    benchmarksApi
      .getTravelPlannerProblem(taskId)
      .then((p) => {
        if (cancelled) return;
        setProblem(p);
        setLoading(false);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        console.error('[TaskPanel] fetch failed:', e);
        setError(e.message);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [taskId]);

  const buttonLabel = taskId ? `과제: ${taskId}` : '과제';

  // Reformat the upstream `date` string ("['2022-03-13', '2022-03-14', '2022-03-15']")
  // as a clean range "2022-03-13 ~ 2022-03-15".
  const formatDateRange = (raw: string): string => {
    const matches = raw.match(/\d{4}-\d{2}-\d{2}/g);
    if (!matches || matches.length === 0) return raw;
    if (matches.length === 1) return matches[0];
    return `${matches[0]} ~ ${matches[matches.length - 1]}`;
  };

  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className="px-3 py-1.5 bg-[#262626] hover:bg-[#333] border border-[#404040] rounded-lg text-[#a3a3a3] hover:text-white text-sm cursor-pointer transition-colors"
        title="현재 과제"
      >
        {buttonLabel}
      </button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-2 bg-[#1f1f1f] border border-[#404040] rounded-lg shadow-xl p-3 w-[480px] max-h-[80vh] overflow-y-auto text-sm z-50">
          <div className="flex justify-between items-center mb-2">
            <span className="font-semibold text-white">현재 과제</span>
            <button
              onClick={onToggle}
              className="text-[#888] hover:text-white"
              title="닫기"
            >
              X
            </button>
          </div>

          {!taskId && (
            <div className="text-[#888] text-xs">
              활성 과제가 없습니다. 처음 화면에서 task_id를 입력하고 Start를 눌러주세요.
            </div>
          )}

          {taskId && loading && (
            <div className="text-[#888] text-xs">{taskId} 불러오는 중...</div>
          )}

          {taskId && error && (
            <div className="text-[#dc2626] text-xs break-all">
              {taskId} 불러오기 실패: {error}
            </div>
          )}

          {problem && (
            <div className="space-y-3">
              {/* Meta — level 제거, 한국어 라벨, 날짜 범위 포맷 */}
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <div>
                  <span className="text-[#888]">일수:</span>{' '}
                  <span className="text-white">{problem.days}</span>
                </div>
                <div>
                  <span className="text-[#888]">예산:</span>{' '}
                  <span className="text-white">
                    {problem.budget == null
                      ? '—'
                      : problem.currency === 'KRW'
                        ? `${problem.budget.toLocaleString('ko-KR')}원`
                        : `$${problem.budget.toLocaleString('en-US')}`}
                  </span>
                </div>
                <div>
                  <span className="text-[#888]">인원수:</span>{' '}
                  <span className="text-white">{problem.people_number}</span>
                </div>
                <div className="col-span-2">
                  <span className="text-[#888]">출발지 → 도착지:</span>{' '}
                  <span className="text-white">
                    {problem.org} → {problem.dest}
                  </span>
                </div>
                <div className="col-span-2">
                  <span className="text-[#888]">날짜:</span>{' '}
                  <span className="text-white">{formatDateRange(problem.date)}</span>
                </div>
              </div>

              {/* Query */}
              <div>
                <div className="text-xs font-semibold text-[#a3a3a3] mb-1">요청</div>
                <div className="text-xs text-white whitespace-pre-wrap bg-[#0a0a0a] border border-[#333] rounded p-2">
                  {problem.query}
                </div>
              </div>

              {/* Local constraint */}
              <div>
                <div className="text-xs font-semibold text-[#a3a3a3] mb-1">
                  제약 사항 (음식 종류 등)
                </div>
                <div className="text-xs bg-[#0a0a0a] border border-[#333] rounded p-2 space-y-0.5">
                  {Object.entries(problem.local_constraint).map(([k, v]) => (
                    <div key={k}>
                      <span className="text-[#888]">{k}:</span>{' '}
                      <span className={v == null ? 'text-[#666]' : 'text-white'}>
                        {v == null ? '—' : String(v)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Reference info (collapsible per item) */}
              <div>
                <div className="text-xs font-semibold text-[#a3a3a3] mb-1">
                  참고 자료 ({problem.reference_information.length} 섹션)
                </div>
                <div className="text-[10px] text-[#666] mb-1">
                  계획 작성에 쓸 후보 목록 — 모두 만족할 필요는 없음.
                </div>
                <div className="space-y-1">
                  {problem.reference_information.map((ref, i) => (
                    <div
                      key={i}
                      className="bg-[#0a0a0a] border border-[#333] rounded text-xs"
                    >
                      <button
                        onClick={() =>
                          setRefExpanded((s) => ({ ...s, [i]: !s[i] }))
                        }
                        className="w-full text-left px-2 py-1 hover:bg-[#171717] flex justify-between text-[#a3a3a3]"
                      >
                        <span>{ref.Description}</span>
                        <span className="text-[#666]">
                          {refExpanded[i] ? '−' : '+'}
                        </span>
                      </button>
                      {refExpanded[i] && (
                        <ReferenceContent item={ref} />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
