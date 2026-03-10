'use client';

type Props = {
  agent: string;
  className?: string;
};

const agentEmoji: Record<string, string> = {
  codex: '🤖',
  kimi: '🟠',
  gemini: '🔵',
  qwen: '🟣',
  claude: '🩷',
  pi: '🩵',
};

export default function AgentIcon({ agent, className = 'h-4 w-4' }: Props) {
  if (agent === 'codex') {
    return (
      <img
        src="/agent-logos/codex.jpg"
        alt="Codex logo"
        className={`${className} rounded-md object-cover`}
      />
    );
  }

  if (agent === 'qwen') {
    return (
      <img
        src="/agent-logos/qwen.png"
        alt="Qwen logo"
        className={`${className} rounded-md object-cover`}
      />
    );
  }

  if (agent === 'claude') {
    return (
      <img
        src="/agent-logos/claude.jpg"
        alt="Claude logo"
        className={`${className} rounded-md object-cover`}
      />
    );
  }

  if (agent === 'pi') {
    return (
      <img
        src="/agent-logos/pi.svg"
        alt="Pi logo"
        className={`${className} rounded-md object-cover`}
      />
    );
  }

  if (agent === 'gemini') {
    return (
      <img
        src="/agent-logos/gemini.webp"
        alt="Gemini logo"
        className={`${className} rounded-md object-cover`}
      />
    );
  }

  return (
    <span aria-hidden="true" className={`inline-flex items-center justify-center ${className}`}>
      {agentEmoji[agent] || '⚪'}
    </span>
  );
}
