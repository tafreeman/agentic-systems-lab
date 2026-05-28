import { Activity, CheckCircle2, XCircle, Timer } from "lucide-react";
import DurationDisplay from "../common/DurationDisplay";
import type { RunsSummary } from "../../api/types";

interface Props {
  summary: RunsSummary | undefined;
  isLoading: boolean;
}

export default function RunSummaryCards({ summary, isLoading }: Props) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card animate-pulse h-24" />
        ))}
      </div>
    );
  }

  const cards = [
    {
      label: "Total Runs",
      value: summary?.total_runs ?? 0,
      icon: Activity,
      color: "text-accent-blue",
    },
    {
      label: "Successful",
      value: summary?.success ?? 0,
      icon: CheckCircle2,
      color: "text-green-400",
    },
    {
      label: "Failed",
      value: summary?.failed ?? 0,
      icon: XCircle,
      color: "text-red-400",
    },
    {
      label: "Avg Duration",
      value: summary?.avg_duration_ms,
      icon: Timer,
      color: "text-amber-400",
      isDuration: true,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {cards.map((card) => (
        <div key={card.label} className="card">
          <div className="flex items-center gap-2">
            <card.icon className={`h-4 w-4 ${card.color}`} />
            <span className="text-xs text-gray-500">{card.label}</span>
          </div>
          <div className="mt-2 text-2xl font-semibold">
            {card.isDuration ? (
              <DurationDisplay ms={card.value as number | null} />
            ) : (
              card.value
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
