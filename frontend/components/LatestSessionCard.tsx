'use client';

import { LatestSessionSummary } from '@/lib/api';
import RichSessionCard from '@/components/RichSessionCard';

interface Props {
  session: LatestSessionSummary;
  scannedProviders: number;
  scannedFiles: number;
  timezone: string;
  errors?: string[];
}

export default function LatestSessionCard({ session, scannedProviders, scannedFiles, timezone, errors = [] }: Props) {
  return (
    <RichSessionCard
      session={session}
      dataTestId="latest-session-card"
      eyebrow="🔥 Latest Session"
      title="Самая свежая живая сессия"
      description={`Один глобальный latest среди ${scannedProviders} провайдеров. Проверено ${scannedFiles} файлов. Таймзона: ${timezone}.`}
      topBadgeText="latest :: one global session"
      errors={errors}
      actionHref={session.route?.href}
      actionLabel="Открыть страницу сессии"
    />
  );
}
