'use client';

import { Session } from '@/lib/api';
import AgentIcon from '@/components/AgentIcon';

interface Props {
  session: Session;
}

// Цвета агентов
const agentColors: Record<string, string> = {
  codex: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  kimi: 'bg-amber-100 text-amber-700 border-amber-200',
  gemini: 'bg-blue-100 text-blue-700 border-blue-200',
  qwen: 'bg-violet-100 text-violet-700 border-violet-200',
  claude: 'bg-pink-100 text-pink-700 border-pink-200',
  pi: 'bg-cyan-100 text-cyan-700 border-cyan-200',
};

// Иконки статусов
const statusIcons: Record<string, string> = {
  active: '🟢',
  completed: '✅',
  error: '❌',
  paused: '⏸️',
  unknown: '⚪',
};

export default function SessionCard({ session }: Props) {
  const agentColor = agentColors[session.agent_type] || 'bg-gray-100 text-gray-700';
  const statusIcon = statusIcons[session.status] || '⚪';
  const directionText = session.user_intent || session.first_user_message || session.last_user_message || 'Направление пока не извлечено.';

  // Форматирование токенов
  const formatTokens = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
  };

  return (
    <div
      data-testid="session-card"
      data-agent-type={session.agent_type}
      data-session-status={session.status}
      className="rounded-[24px] border border-[#d7e0ea] bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span data-testid="session-agent-name" className={`rounded-full border px-3 py-1 text-xs font-semibold ${agentColor}`}>
            <span className="mr-2 inline-flex align-middle">
              <AgentIcon agent={session.agent_type} className="h-4 w-4" />
            </span>
            {session.agent_name}
          </span>
          <span className="rounded-full border border-nexus-200 bg-nexus-50 px-3 py-1 text-xs font-medium text-nexus-600">
            {statusIcon} {session.status}
          </span>
          <span className="rounded-full border border-nexus-200 bg-nexus-50 px-3 py-1 font-mono text-[11px] text-nexus-500">
            💬 {session.user_message_count ?? 0}
          </span>
        </div>

        <span className="text-xs text-nexus-400">
          {session.timestamp_start
            ? new Date(session.timestamp_start).toLocaleString('ru-RU', {
                day: 'numeric',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
              })
            : '—'}
        </span>
      </div>

      <div className="mb-3 grid gap-3">
        <div className="rounded-2xl border border-nexus-200 bg-[#f8fbff] p-3">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-nexus-500">
            📄 Файл сессии
          </div>
          <div className="font-mono text-[13px] leading-6 text-nexus-800 whitespace-pre-wrap break-all">
            {session.source_file || '—'}
          </div>
        </div>

        <div className="rounded-2xl border border-nexus-200 bg-nexus-50 p-3">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-nexus-500">
            📁 Рабочая директория
          </div>
          <div className="font-mono text-[13px] leading-6 text-nexus-700 whitespace-pre-wrap break-all">
            {session.cwd || '—'}
          </div>
        </div>
      </div>

      <div className="mb-3 rounded-2xl border border-[#d7e0ea] bg-[#fffaf0] p-3">
        <div className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-[0.22em] text-nexus-500">
          🧭 Направление
        </div>
        <div className="text-sm leading-7 text-nexus-800 whitespace-pre-wrap break-words">
          {directionText}
        </div>
      </div>

      {(session.first_user_message || session.last_user_message) && (
        <div className="mb-3 grid gap-3">
          <div className="rounded-2xl border border-nexus-200 bg-[#fbfdff] p-3">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-nexus-500">
              1️⃣ Первое сообщение пользователя
            </div>
            <div className="text-sm leading-7 text-nexus-700 whitespace-pre-wrap break-words">
              {session.first_user_message || '—'}
            </div>
          </div>

          <div className="rounded-2xl border border-nexus-200 bg-[#fbfdff] p-3">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-nexus-500">
              2️⃣ Последнее сообщение пользователя
            </div>
            <div className="text-sm leading-7 text-nexus-700 whitespace-pre-wrap break-words">
              {session.last_user_message || '—'}
            </div>
          </div>
        </div>
      )}

      {session.tool_calls.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {session.tool_calls.slice(0, 6).map((tool, i) => (
            <span
              key={i}
              className="rounded-full border border-nexus-200 bg-nexus-50 px-2.5 py-1 text-xs text-nexus-600"
            >
              {tool}
            </span>
          ))}
          {session.tool_calls.length > 6 && (
            <span className="rounded-full border border-nexus-200 bg-white px-2.5 py-1 text-xs text-nexus-400">
              +{session.tool_calls.length - 6}
            </span>
          )}
        </div>
      )}

      <div className="grid gap-2 border-t border-nexus-100 pt-3 text-xs text-nexus-500 sm:grid-cols-3">
        <div className="rounded-xl border border-nexus-100 bg-nexus-50 px-3 py-2">
          🔤 Токены: {formatTokens(session.token_usage?.total_tokens || 0)}
        </div>
        <div className="rounded-xl border border-nexus-100 bg-nexus-50 px-3 py-2">
          🛠 Инструменты: {session.tool_calls.length}
        </div>
        <div className="rounded-xl border border-nexus-100 bg-nexus-50 px-3 py-2">
          💬 Сообщения: {session.user_message_count ?? 0}
        </div>
      </div>

      {session.error_message && (
        <div className="mt-3 rounded-2xl border border-red-200 bg-red-50 p-3 text-xs leading-6 text-red-600 whitespace-pre-wrap break-words">
          ⚠️ {session.error_message}
        </div>
      )}
    </div>
  );
}
