import { PlanDay } from '../../utils/planParser';

// Renders a parsed TravelPlanner plan as a series of Korean day cards.
// Used inside ChatPanel to replace LLM raw output (English natural language
// + code-fenced dict) with a consistent localized view.

interface PlanCardProps {
  plan: PlanDay[];
}

const DASH_VALUES = new Set(['-', '–', '—', '']);

function isEmpty(v: unknown): boolean {
  if (v == null) return true;
  if (typeof v !== 'string') return false;
  return DASH_VALUES.has(v.trim());
}

function Row({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div className="flex gap-2 text-xs">
      <span className="w-5 text-center shrink-0">{icon}</span>
      <span className="w-9 text-[#a3a3a3] shrink-0">{label}</span>
      <span className="text-white break-words">{value}</span>
    </div>
  );
}

// Meals row — header + one indented line per meal slot. Skips empty/dash.
function MealsBlock({ day }: { day: PlanDay }) {
  const slots: Array<[string, unknown]> = [
    ['아침', day.breakfast],
    ['점심', day.lunch],
    ['저녁', day.dinner],
  ];
  const present = slots.filter(([, v]) => !isEmpty(v));
  if (present.length === 0) {
    return <Row icon="🍽️" label="식사" value="—" />;
  }
  return (
    <div className="flex gap-2 text-xs">
      <span className="w-5 text-center shrink-0">🍽️</span>
      <span className="w-9 text-[#a3a3a3] shrink-0">식사</span>
      <div className="flex-1 space-y-0.5 text-white">
        {present.map(([label, value]) => (
          <div key={label} className="break-words">
            <span className="text-[#a3a3a3] mr-1.5">{label}</span>
            {String(value)}
          </div>
        ))}
      </div>
    </div>
  );
}

export const PlanCard = ({ plan }: PlanCardProps) => {
  if (!plan || plan.length === 0) return null;

  return (
    <div className="space-y-2">
      {plan.map((day, idx) => (
        <div
          key={idx}
          className="bg-[#171717] border border-[#333] rounded-lg p-2.5 space-y-1"
        >
          <div className="text-xs font-semibold text-white mb-1.5">
            📅 {day.days}일차 · {day.current_city}
          </div>
          {!isEmpty(day.description) && (
            <div className="text-[12px] text-[#d4d4d4] leading-relaxed pb-2 mb-1.5 border-b border-[#262626]">
              {String(day.description)}
            </div>
          )}
          {!isEmpty(day.transportation) && (
            <Row icon="🚆" label="교통" value={String(day.transportation)} />
          )}
          {!isEmpty(day.attraction) && (
            <Row icon="🏛️" label="관광" value={String(day.attraction)} />
          )}
          <MealsBlock day={day} />
          {!isEmpty(day.accommodation) && (
            <Row icon="🛏️" label="숙소" value={String(day.accommodation)} />
          )}
        </div>
      ))}
    </div>
  );
};
