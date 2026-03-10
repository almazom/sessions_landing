'use client';

import { Metrics } from '@/lib/api';
import AgentIcon from '@/components/AgentIcon';

interface Props {
  metrics: Metrics;
}

// Форматирование токенов
const formatTokens = (n: number) => {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
};

export default function MetricsPanel({ metrics }: Props) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
      {/* Total Sessions */}
      <div data-testid="metric-total-sessions-card" className="bg-white rounded-xl border border-nexus-200 p-4">
        <div data-testid="metric-total-sessions-value" className="text-2xl font-bold text-nexus-800">
          {metrics.total_sessions}
        </div>
        <div className="text-sm text-nexus-500">Сессий</div>
      </div>

      {/* Total Tokens */}
      <div data-testid="metric-total-tokens-card" className="bg-white rounded-xl border border-nexus-200 p-4">
        <div data-testid="metric-total-tokens-value" className="text-2xl font-bold text-nexus-800">
          {formatTokens(metrics.total_tokens)}
        </div>
        <div className="text-sm text-nexus-500">Токенов</div>
      </div>

      {/* Active */}
      <div data-testid="metric-active-card" className="bg-white rounded-xl border border-nexus-200 p-4">
        <div data-testid="metric-active-value" className="text-2xl font-bold text-emerald-600">
          {metrics.by_status.active || 0}
        </div>
        <div className="text-sm text-nexus-500">Активных</div>
      </div>

      {/* Errors */}
      <div data-testid="metric-errors-card" className="bg-white rounded-xl border border-nexus-200 p-4">
        <div data-testid="metric-errors-value" className="text-2xl font-bold text-red-500">
          {metrics.by_status.error || 0}
        </div>
        <div className="text-sm text-nexus-500">Ошибок</div>
      </div>

      {/* Agents breakdown */}
      <div data-testid="metric-agents-breakdown" className="col-span-2 md:col-span-4 bg-white rounded-xl border border-nexus-200 p-4">
        <div className="text-sm text-nexus-500 mb-2">По агентам</div>
        <div className="flex flex-wrap gap-3">
          {Object.entries(metrics.by_agent).map(([agent, count]) => (
            <div key={agent} data-testid={`metric-agent-${agent}`} className="flex items-center gap-1">
              <AgentIcon agent={agent} className="h-4 w-4" />
              <span className="text-sm font-medium">{agent}</span>
              <span className="text-sm text-nexus-400">({count})</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
