'use client';

import { useEffect, useState } from 'react';

import { LatestSessionSummary } from '@/lib/api';
import AgentIcon from '@/components/AgentIcon';

interface Props {
  session: LatestSessionSummary;
  scannedProviders: number;
  scannedFiles: number;
  timezone: string;
  errors?: string[];
}

const providerLabels: Record<string, string> = {
  codex: 'Codex',
  kimi: 'Kimi',
  gemini: 'Gemini',
  qwen: 'Qwen',
  claude: 'Claude',
  pi: 'Pi',
};

const providerColors: Record<string, string> = {
  codex: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  kimi: 'bg-amber-100 text-amber-800 border-amber-200',
  gemini: 'bg-blue-100 text-blue-800 border-blue-200',
  qwen: 'bg-violet-100 text-violet-800 border-violet-200',
  claude: 'bg-pink-100 text-pink-800 border-pink-200',
  pi: 'bg-cyan-100 text-cyan-800 border-cyan-200',
};

const activityColors: Record<string, string> = {
  live: 'bg-red-100 text-red-700 border-red-200',
  active: 'bg-amber-100 text-amber-700 border-amber-200',
  idle: 'bg-slate-100 text-slate-700 border-slate-200',
};

function detailRow(label: string, value: string, emoji: string) {
  return (
    <div className="rounded-2xl border border-[#d7e0ea] bg-[#f8fbff] p-4">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-nexus-500">
        {emoji} {label}
      </div>
      <div className="font-mono text-[13px] leading-6 text-nexus-800 whitespace-pre-wrap break-all">
        {value || '—'}
      </div>
    </div>
  );
}

function stepWord(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return 'шаг';
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return 'шага';
  }
  return 'шагов';
}

export default function LatestSessionCard({ session, scannedProviders, scannedFiles, timezone, errors = [] }: Props) {
  const [showAllIntentSteps, setShowAllIntentSteps] = useState(false);
  const providerLabel = providerLabels[session.provider] || session.provider;
  const providerColor = providerColors[session.provider] || 'bg-white text-nexus-700 border-nexus-200';
  const activityColor = activityColors[session.activity_state] || 'bg-white text-nexus-700 border-nexus-200';
  const intentSteps = session.intent_evolution || [];
  const visibleIntentSteps = showAllIntentSteps ? intentSteps : intentSteps.slice(0, 2);
  const hiddenIntentCount = Math.max(0, intentSteps.length - visibleIntentSteps.length);

  useEffect(() => {
    setShowAllIntentSteps(false);
  }, [session.path]);

  return (
    <section
      data-testid="latest-session-card"
      className="mb-8 overflow-hidden rounded-[30px] border border-[#d7e0ea] bg-white shadow-[0_18px_60px_rgba(15,23,42,0.08)]"
    >
      <div className="border-b border-[#d7e0ea] bg-[linear-gradient(135deg,#fff6dc_0%,#ffffff_48%,#edf6ff_100%)] px-6 py-6">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <span className={`inline-flex items-center rounded-full border px-3 py-1 text-sm font-semibold ${providerColor}`}>
            <AgentIcon agent={session.provider} className="mr-2 h-4 w-4" />
            {providerLabel}
          </span>
          <span className={`inline-flex items-center rounded-full border px-3 py-1 text-sm font-medium ${activityColor}`}>
            🧭 {session.activity_state}
          </span>
          <span className="inline-flex items-center rounded-full border border-nexus-200 bg-white px-3 py-1 text-sm font-medium text-nexus-600">
            ⏱ {session.age_human}
          </span>
          <span className="inline-flex items-center rounded-full border border-[#d7e0ea] bg-white px-3 py-1 font-mono text-xs text-nexus-500">
            latest :: one global session
          </span>
        </div>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-nexus-500">
              🔥 Latest Session
            </div>
            <h2 className="mt-2 text-3xl font-bold text-nexus-900">
              Самая свежая живая сессия
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-nexus-600">
              Один глобальный latest среди {scannedProviders} провайдеров. Проверено {scannedFiles} файлов.
              Таймзона: {timezone}.
            </p>
          </div>

          <div className="rounded-[26px] border border-[#d7e0ea] bg-white/90 p-4">
            <div className="mb-3 font-mono text-[11px] uppercase tracking-[0.24em] text-nexus-500">
              session snapshot
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-nexus-200 bg-nexus-50 p-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-nexus-500">🕒 Изменено</div>
                <div className="mt-1 text-sm font-semibold text-nexus-800">{session.modified_human}</div>
                <div className="mt-1 text-xs text-nexus-500">{session.modified_at_local}</div>
              </div>
              {session.duration_human && (
                <div className="rounded-xl border border-nexus-200 bg-nexus-50 p-3">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-nexus-500">⏳ Длительность</div>
                  <div data-testid="latest-duration-value" className="mt-1 text-sm font-semibold text-nexus-800">
                    {session.duration_human}
                  </div>
                  <div className="mt-1 text-xs text-nexus-500">
                    {session.started_at_local ? `начата ${session.started_at_local}` : '—'}
                  </div>
                </div>
              )}
              <div className="rounded-xl border border-nexus-200 bg-nexus-50 p-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-nexus-500">🧾 Records</div>
                <div className="mt-1 text-sm font-semibold text-nexus-800">{session.record_count}</div>
                <div className="mt-1 text-xs text-nexus-500">Parse errors: {session.parse_errors}</div>
              </div>
              <div className="rounded-xl border border-nexus-200 bg-nexus-50 p-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-nexus-500">💬 Сообщения</div>
                <div className="mt-1 text-sm font-semibold text-nexus-800">{session.user_message_count}</div>
                <div className="mt-1 text-xs text-nexus-500">Provider: {providerLabel}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 bg-[#f7fafc] px-6 py-6">
        <div className="grid gap-4">
          {detailRow('Путь к файлу', session.path, '📁')}
        </div>
      </div>

      {intentSteps.length > 0 && (
        <div className="border-t border-[#d7e0ea] bg-[#f7fafc] px-6 py-6">
          <div
            data-testid="latest-intent-evolution"
            className="rounded-[24px] border border-[#d7e0ea] bg-white p-4"
          >
            <div className="mb-3 font-mono text-[11px] font-semibold uppercase tracking-[0.24em] text-nexus-500">
              🧭 Вектор намерений
            </div>
            <div className="grid gap-2">
              {visibleIntentSteps.map((step, index) => {
                const stepNumber = index + 1;
                return (
                  <div
                    key={`${stepNumber}-${step}`}
                    data-testid={`latest-intent-step-${index}`}
                    className="rounded-2xl border border-nexus-200 bg-[#fbfdff] px-4 py-3 text-sm leading-7 text-nexus-800 whitespace-pre-wrap break-words"
                  >
                    {stepNumber}. {step}
                  </div>
                );
              })}
            </div>
            {intentSteps.length > 2 && (
              <button
                type="button"
                data-testid="latest-intent-toggle"
                onClick={() => setShowAllIntentSteps((current) => !current)}
                className="mt-3 inline-flex items-center rounded-full border border-nexus-200 bg-nexus-50 px-3 py-1 text-sm font-medium text-nexus-700 transition-colors hover:bg-white"
              >
                {showAllIntentSteps ? 'свернуть' : `ещё ${hiddenIntentCount} ${stepWord(hiddenIntentCount)}`}
              </button>
            )}
          </div>
        </div>
      )}

      <div className="grid gap-4 border-t border-[#d7e0ea] bg-white px-6 py-6 lg:grid-cols-2">
        <div className="rounded-[24px] border border-[#d7e0ea] bg-[#fbfdff] p-4">
          <div className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-[0.24em] text-nexus-500">
            1️⃣ Первое сообщение
          </div>
          <div className="rounded-2xl border border-nexus-200 bg-white p-4 text-sm leading-7 text-nexus-800 whitespace-pre-wrap break-words">
            {session.first_user_message || '—'}
          </div>
        </div>

        <div className="rounded-[24px] border border-[#d7e0ea] bg-[#fbfdff] p-4">
          <div className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-[0.24em] text-nexus-500">
            2️⃣ Последнее сообщение
          </div>
          <div className="rounded-2xl border border-nexus-200 bg-white p-4 text-sm leading-7 text-nexus-800 whitespace-pre-wrap break-words">
            {session.last_user_message || '—'}
          </div>
        </div>
      </div>

      {errors.length > 0 && (
        <div className="border-t border-amber-200 bg-amber-50 px-6 py-4 text-sm leading-6 text-amber-800">
          ⚠️ {errors.join(' ')}
        </div>
      )}
    </section>
  );
}
