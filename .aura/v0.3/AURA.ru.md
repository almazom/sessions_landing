# СИСТЕМНЫЙ ПРОТОКОЛ AURA v0.3 — Agent Nexus

> **Версия:** 0.3
> **Дата:** 2026-03-12
> **Проект:** Agent Nexus
> **Статус:** Active

---

РОЛЬ: Строить эту систему как markdown-центричную, contract-first, изолированную CLI-архитектуру.

ЦЕЛЬ: Превращать provider session files в понятные и переиспользуемые артефакты через маленькие инструменты с явными контрактами.

## 1. ВЕРСИОНИРУЕМАЯ СТРУКТУРА AURA

Этот проект использует версионируемую структуру `.aura/`, вдохновлённую паттерном CineTaste v5.

```text
.aura/
├── latest -> v0.3
├── v0.1/
│   └── AURA.md
├── v0.2/
│   └── AURA.md
├── v0.3/
│   └── AURA.md
├── templates/
│   ├── KANBAN.template.json
│   ├── CONTRACT.template.json
│   └── MANIFEST.template.json
└── kanban/
    ├── KANBAN-2026-03-10-bootstrap.json
    └── latest -> KANBAN-2026-03-10-bootstrap.json
```

Стабильные точки входа:

- `AURA.md` -> `.aura/latest/AURA.md`
- `.aura/latest/AURA.md` -> текущая активная версия Aura

Правило:

- когда Aura меняется существенно, создавай новую версию в `.aura/vX.Y/`, а не переписывай паттерн молча
- держи `AURA.md` как стабильный путь, который указывает на активную версию

## 2. ПОРЯДОК ИСТОЧНИКОВ

Читай и используй слои проекта в таком порядке:

1. `PROFILE.md` — зачем существует проект
2. `AURA.md` — как систему нужно строить
3. `PROTOCOL.json` — топология и реестр контрактов
4. `.MEMORY/` — короткий operational context
5. `contracts/*.schema.json` — строгие границы данных
6. `tools/*/MANIFEST.json` — исполняемые CLI-интерфейсы

## 3. БАЗОВЫЙ СТИЛЬ

В этом репозитории нужно предпочитать:

- markdown-centric planning and documentation
- contract-first design
- isolated CLI tools в `tools/`
- explicit provider fallback chains
- small, testable, inspectable artifacts

Избегать:

- скрытой runtime-связки
- недокументированного магического поведения
- импортов `backend/` или `frontend/` внутри isolated tools
- смешивания stdout diagnostics и JSON payloads
- широких инструментов с несколькими ответственностями

## 4. ПРАВИЛО ISOLATED CLI

Новые переиспользуемые операции по умолчанию должны становиться isolated CLI.

Каждый CLI в `tools/` должен:

- иметь одну ответственность
- объявлять входной и выходной контракты
- иметь ясную wrapper-команду
- запускаться без web app
- читать из файлов и флагов, а не из app internals
- писать JSON в stdout или в явно указанный output file
- писать diagnostics в stderr

Если используется provider chain, preflight и fallback-поведение должны быть явно описаны в файлах, manifests, docs и state cache.

## 5. CONTRACT-FIRST ПОРЯДОК СБОРКИ

Строй в таком порядке:

1. определить границу задачи в markdown
2. определить контракт в `contracts/`
3. зарегистрировать его в `PROTOCOL.json`
4. создать `tools/<tool-name>/MANIFEST.json`
5. добавить исполняемый wrapper
6. реализовать `main.py`
7. добавить examples и smoke tests
8. только потом подключать это к app-level surfaces, если нужно

## 6. MARKDOWN-CENTERED ДИСЦИПЛИНА

Markdown — это часть операционной системы репозитория.

Используй markdown-файлы, чтобы разделять уровни ответственности:

- `PROFILE.md` отвечает на вопрос why
- `docs/product/HIGH_LEVEL_EXPECTATIONS.md` задаёт product-level expectations и целевое состояние UX
- `AURA.md` задаёт стиль и метод
- `AGENTS.md` говорит агентам, как работать в этом репозитории
- `.MEMORY/` хранит короткие reusable operational notes
- `README.md` объясняет setup и usage

## 7. ПРЕДПОЧТИТЕЛЬНОЕ НАПРАВЛЕНИЕ СИСТЕМЫ

Предпочтительное направление — библиотека isolated tools поверх provider session files, например:

- collect
- normalize
- filter
- compute activity
- cognize
- cardify
- publish selected fragments

Web application может потреблять эти инструменты, но не должна быть местом, где рождается их core logic.

## 8. ПЛАНКА КАЧЕСТВА

Каждый новый CLI должен быть:

- простым для запуска по документированному примеру команды
- простым для проверки на реальном локальном файле
- простым для замены без поломки контрактов
- простым для инспекции через manifest и schema

## 9. СТИЛЬ ЗАВЕРШЕНИЯ IMPLEMENTATION SESSION

Предпочтительный стиль репозитория после каждой implementation session:

- запускать skill `code-simplifier` по коду и docs, которые были затронуты в этой сессии
- держать simplification pass без изменения поведения
- после simplification и verification запускать workflow `auto-commit` для изменений этой сессии
- не оставлять изменения implementation session незафиксированными, если они уже в shippable state
- держать commits атомарными
- не захватывать в commit нерелевантные грязные изменения из worktree

Интерпретация:

- simplification идёт перед commit
- verification идёт перед commit
- auto-commit должен чисто упаковывать результат сессии
- если в worktree уже есть нерелевантные правки, нужно изолировать изменения текущей сессии, а не коммитить всё вместе

## 10. АВТОНОМНАЯ FEEDBACK-DRIVEN ИТЕРАЦИЯ ПОЛНЫМ ЦИКЛОМ

Предпочтительный стиль работы для существенных implementation-задач:

- сначала восстанавливать expectation из самых сильных доступных источников
- восстанавливать user intent из текущего пользовательского запроса и ближайшего task context
- выводить SDD-like requirements, заполняя gaps между expectation, user intent и текущей реализацией
- думать в терминах полного end-to-end iteration loop, а не одноразового patch

Порядок восстановления expectation:

1. пользовательский запрос
2. `PROFILE.md`
3. `docs/product/HIGH_LEVEL_EXPECTATIONS.md`
4. релевантные roadmap docs
5. текущий код и tests

Автономный цикл:

1. сформулировать вероятный human workflow для задачи как короткий список шагов
2. рассматривать этот список как operational script, который человек запустил бы в другом терминале
3. выполнять эти шаги через терминал и встроенные инструменты по одному, когда это безопасно
4. собирать feedback из build output, tests, linters, API responses, browser checks, screenshots и runtime logs
5. сравнивать этот feedback с user intent и ожидаемым product behavior
6. выявлять оставшиеся gaps
7. итерироваться снова без ожидания пользователя, если следующий шаг ясен и безопасен

Правило измерения:

- использовать собранный feedback как слой измерения между expected result, intended result и actual result
- продолжать итерации, пока результат не будет примерно на `95%+` согласован с user intent и product expectation, либо пока не появится реальный blocker
- если цикл нельзя безопасно продолжать, явно показывать blocker, а не делать вид, что задача завершена

Правило коммуникации:

- информировать пользователя только о major steps
- предпочитать краткие milestone-обновления постоянному шуму
- когда удалённое уведомление полезно, `t2me` доступен как global CLI для доставки в Telegram
- использовать `t2me` для major-step notifications, screenshots или proof artifacts, если это улучшает workflow

Граница безопасности:

- этот цикл нужен для безопасной, evidence-driven итерации, а не для слепой автономии
- нельзя выдумывать недостающие требования, если существует более сильный user или repo context
- нельзя запускать destructive или high-risk действия только ради поддержания цикла
- если безопасное продолжение блокируется credentials, approvals, external side effects или неоднозначным product choice, нужно остановиться и явно показать decision point

## 11. ИСТОРИЯ ВЕРСИЙ

| Версия | Дата | Изменения |
|---------|------|---------|
| v0.3 | 2026-03-12 | Добавлены правила autonomous feedback-driven full-circle iteration и preference для уведомлений через `t2me` |
| v0.2 | 2026-03-12 | Добавлены правила post-implementation simplification и auto-commit |
| v0.1 | 2026-03-10 | Добавлены versioned Aura layout, templates и stable symlink entrypoint |
