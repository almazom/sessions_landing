import SessionDetailClient from '@/components/SessionDetailClient';

interface Props {
  params: {
    harness: string;
    id: string;
  };
}

export default function SessionDetailPage({ params }: Props) {
  return <SessionDetailClient harness={params.harness} artifactId={params.id} />;
}
