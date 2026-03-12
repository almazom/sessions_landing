'use client';

import { FormEvent, MutableRefObject } from 'react';

interface Props {
  passwordRequired: boolean;
  telegramEnabled: boolean;
  telegramConfigured: boolean;
  telegramMode: string | null;
  authSubmitting: boolean;
  authError: string | null;
  password: string;
  telegramWidgetRef: MutableRefObject<HTMLDivElement | null>;
  onPasswordChange: (value: string) => void;
  onPasswordSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onTelegramLogin: () => void;
}

export default function AuthPanel({
  passwordRequired,
  telegramEnabled,
  telegramConfigured,
  telegramMode,
  authSubmitting,
  authError,
  password,
  telegramWidgetRef,
  onPasswordChange,
  onPasswordSubmit,
  onTelegramLogin,
}: Props) {
  return (
    <section className="grid min-h-[calc(100vh-12rem)] place-items-start pt-8 md:pt-14">
      <div className="w-full max-w-4xl rounded-[32px] border border-[#d7e0ea] bg-white shadow-[0_24px_70px_rgba(15,23,42,0.08)]">
        <div className="grid gap-0 lg:grid-cols-[minmax(0,0.95fr)_minmax(320px,0.85fr)]">
          <div className="border-b border-[#d7e0ea] bg-[linear-gradient(135deg,#fff6dc_0%,#ffffff_55%,#eef6ff_100%)] p-8 lg:border-b-0 lg:border-r">
            <div className="font-mono text-[11px] uppercase tracking-[0.26em] text-nexus-500">
              private access
            </div>
            <h2 className="mt-3 text-3xl font-bold text-nexus-900">Доступ защищён</h2>
            <p className="mt-3 max-w-xl text-sm leading-7 text-nexus-600">
              Это приватный рабочий dashboard. Войдите, чтобы открыть latest session,
              карточки сессий, метрики и live-обновления.
            </p>

            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-white/80 bg-white/80 p-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-nexus-500">🔒 Режим</div>
                <div className="mt-2 text-sm font-semibold text-nexus-800">Private only</div>
              </div>
              <div className="rounded-2xl border border-white/80 bg-white/80 p-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-nexus-500">🗂 Доступ</div>
                <div className="mt-2 text-sm font-semibold text-nexus-800">Latest + sessions</div>
              </div>
              <div className="rounded-2xl border border-white/80 bg-white/80 p-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-nexus-500">📡 Live</div>
                <div className="mt-2 text-sm font-semibold text-nexus-800">WebSocket ready</div>
              </div>
            </div>
          </div>

          <div className="p-8">
            <div data-testid="login-form" className="mx-auto max-w-md space-y-5">
              <div>
                <div className="font-mono text-[11px] uppercase tracking-[0.24em] text-nexus-500">
                  sign in
                </div>
                <h3 className="mt-3 text-2xl font-bold text-nexus-900">Открыть приватную панель</h3>
                <p className="mt-2 text-sm leading-6 text-nexus-600">
                  Используйте пароль или Telegram, если он включён на сервере.
                </p>
              </div>

              {telegramEnabled && telegramConfigured && (
                <>
                  <button
                    type="button"
                    data-testid="telegram-login-button"
                    onClick={onTelegramLogin}
                    disabled={authSubmitting}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-[#d7e0ea] bg-white px-4 py-3 text-sm font-medium text-nexus-700 transition-colors hover:bg-nexus-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <span aria-hidden="true">✈️</span>
                    <span>Log in with Telegram</span>
                  </button>

                  {telegramMode === 'widget' && (
                    <div
                      ref={telegramWidgetRef}
                      className="flex justify-center rounded-2xl border border-dashed border-nexus-200 bg-nexus-50 px-4 py-5"
                    />
                  )}
                </>
              )}

              {passwordRequired && (
                <>
                  {telegramEnabled && (
                    <div className="flex items-center gap-3 text-xs uppercase tracking-[0.2em] text-nexus-400">
                      <span className="h-px flex-1 bg-nexus-200" />
                      <span>or use password</span>
                      <span className="h-px flex-1 bg-nexus-200" />
                    </div>
                  )}

                  <form onSubmit={onPasswordSubmit} className="space-y-4">
                    <label className="block">
                      <span className="mb-2 block text-sm font-medium text-nexus-700">Пароль</span>
                      <input
                        data-testid="auth-password-input"
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(event) => onPasswordChange(event.target.value)}
                        className="w-full rounded-2xl border border-nexus-200 px-4 py-3 outline-none focus:border-nexus-400"
                        placeholder="Введите пароль"
                      />
                    </label>

                    <button
                      data-testid="login-button"
                      type="submit"
                      disabled={authSubmitting || password.length === 0}
                      className="w-full rounded-2xl bg-nexus-800 px-4 py-3 text-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {authSubmitting ? 'Вход...' : 'Войти'}
                    </button>
                  </form>
                </>
              )}

              {authError && (
                <p data-testid="auth-error" className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                  {authError}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
