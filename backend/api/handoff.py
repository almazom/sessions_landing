"""Handoff system for transferring work between agents."""

from datetime import datetime
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class HandoffContext:
    """Контекст для передачи между агентами."""
    project_path: str
    previous_agent: str
    original_task: str
    completed_steps: List[str]
    next_steps: List[str]
    notes: str = ""
    created_at: str = ""


def create_handoff_file(
    project_path: str,
    previous_agent: str,
    original_task: str,
    completed_steps: List[str],
    next_steps: List[str],
    notes: str = "",
) -> Path:
    """
    Создать файл .agent_handoff.md в корне проекта.
    
    Возвращает путь к созданному файлу.
    """
    handoff_path = Path(project_path) / ".agent_handoff.md"
    
    now = datetime.now().isoformat()
    
    content = f"""# Agent Handoff

> Автоматически создано {now}

## 📋 Контекст передачи

| Поле | Значение |
|------|----------|
| **Предыдущий агент** | {previous_agent} |
| **Проект** | `{project_path}` |
| **Время** | {now} |

## 🎯 Исходная задача

{original_task}

## ✅ Выполненные шаги

{chr(10).join(f"- [x] {step}" for step in completed_steps) if completed_steps else "_Нет выполненных шагов_"}

## 🔜 Следующие шаги

{chr(10).join(f"- [ ] {step}" for step in next_steps) if next_steps else "_Нет запланированных шагов_"}

## 📝 Заметки

{notes if notes else "_Нет дополнительных заметок_"}

## 🔄 Продолжить в другом агенте

Выберите агент для продолжения работы:

- [Codex](/handoff/codex) - OpenAI Codex CLI
- [Kimi](/handoff/kimi) - Moonshot Kimi
- [Gemini](/handoff/gemini) - Google Gemini
- [Qwen](/handoff/qwen) - Alibaba Qwen
- [Claude](/handoff/claude) - Anthropic Claude
- [Pi](/handoff/pi) - Pi Agent

---

_Файл создан автоматически Agent Nexus_
"""
    
    handoff_path.write_text(content, encoding='utf-8')
    print(f"📝 Handoff файл создан: {handoff_path}")
    
    return handoff_path


def parse_handoff_file(handoff_path: Path) -> Optional[HandoffContext]:
    """
    Парсить существующий handoff файл.
    
    Возвращает HandoffContext или None если файл не существует.
    """
    if not handoff_path.exists():
        return None
    
    content = handoff_path.read_text(encoding='utf-8')
    
    # Простой парсинг markdown
    lines = content.split('\n')
    
    previous_agent = ""
    original_task = ""
    completed_steps = []
    next_steps = []
    notes = ""
    
    current_section = ""
    
    for line in lines:
        line = line.strip()
        
        if line.startswith("| **Предыдущий агент**"):
            previous_agent = line.split("|")[2].strip()
        elif line.startswith("## 🎯 Исходная задача"):
            current_section = "task"
        elif line.startswith("## ✅ Выполненные шаги"):
            current_section = "completed"
        elif line.startswith("## 🔜 Следующие шаги"):
            current_section = "next"
        elif line.startswith("## 📝 Заметки"):
            current_section = "notes"
        elif line.startswith("##"):
            current_section = ""
        elif line.startswith("- [x]"):
            completed_steps.append(line[5:].strip())
        elif line.startswith("- [ ]"):
            next_steps.append(line[5:].strip())
        elif line and current_section == "task" and not line.startswith("_"):
            original_task += line + " "
        elif line and current_section == "notes" and not line.startswith("_"):
            notes += line + " "
    
    return HandoffContext(
        project_path=str(handoff_path.parent),
        previous_agent=previous_agent,
        original_task=original_task.strip(),
        completed_steps=completed_steps,
        next_steps=next_steps,
        notes=notes.strip(),
        created_at=datetime.now().isoformat(),
    )


# Agent launch commands
AGENT_COMMANDS = {
    "codex": "codex --project {path}",
    "kimi": "kimi {path}",
    "gemini": "gemini {path}",
    "qwen": "qwen {path}",
    "claude": "claude {path}",
    "pi": "pi {path}",
}


def get_handoff_command(agent: str, project_path: str) -> str:
    """Получить команду для запуска агента."""
    template = AGENT_COMMANDS.get(agent, "{agent} {path}")
    return template.format(agent=agent, path=project_path)
