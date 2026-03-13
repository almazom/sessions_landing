# Session Detail Next Step

## Зачем Нужен Этот План

Мы уже пришли к важной идее:

- JSON-файл сессии - это источник правды
- временное окно сессии - это координатная рамка
- detail page - это место, где мы собираем максимум полезной информации вокруг этого окна

Этот файл фиксирует следующий практический шаг.

## Следующий Главный Шаг

Следующий сильный шаг:

- превратить detail page из набора блоков в evidence-centered session dossier

Коротко:

- меньше "просто карточек"
- больше "слоёв подтверждения одной истории"

## Что Уже Есть

У нас уже есть:

- route на отдельную страницу сессии
- message anchors
- session timeline
- tool list
- files modified
- git commits in session window

Это уже хороший фундамент.

## Что Хотим Дальше

Нужно усилить три направления:

1. связность сигналов
2. будущие action placeholders
3. новые смысловые слои

## Направление 1. Evidence Matrix

Идея:

- показать рядом несколько источников правды
- дать глазу быстро сравнить их

Минимальный набор колонок:

- user direction
- commits
- files
- timeline

Пример:

```text
[ User Direction ]   [ Commit Narrative ]
починить detail      Add session detail route
добавить anchors     Add message anchors block
проверить timeline   Improve published checks

[ Files ]
frontend/components/SessionDetailClient.tsx
frontend/e2e/published-url.spec.ts
backend/api/session_artifacts.py
```

Зачем:

- пользователь видит не только "что говорил"
- но и "что реально дошло до репозитория"

## Направление 2. Topic Threads

Сейчас у нас главный смысловой слой - intent evolution.

Следующий слой:

- topic threads

Что это:

- не направление пользователя
- а темы, которые реально шли через сессию

Пример:

```text
Topics
- routing
- session evidence
- git commits
- published checks
- auth gate reuse
```

Зачем:

- это улучшит навигацию
- это даст базу для будущих тематических лендингов

## Направление 3. Ask This Session

Нужно заранее закладывать block для вопросов к сессии.

Даже если сначала это будет placeholder.

Будущий UX:

```text
[ Ask This Session ]
Вопрос: "какая была главная цель этой сессии?"
Harness: Gemini
Mode: headless
[ Ask ]
```

Важная мысль:

- мы не меняем JSON
- мы строим query layer поверх artifact

## Направление 4. Continue / Resume

Нужно отдельно думать о блоке продолжения работы.

Будущий UX:

```text
[ Continue Session ]
Harness: Codex
Target: existing session
Mode: tmux wrapper
Prompt: "продолжи работу над session detail page"
[ Continue ]
```

Это особенно важно, если detail page станет operational hub, а не только архивом.

## Практический Следующий Implementation Step

Самый логичный следующий implementation step:

- добавить на detail page `future actions` section с двумя placeholder-картами:
  - `Ask this session`
  - `Continue / Resume session`

Почему это лучший следующий шаг:

- он не ломает текущую модель
- он уже готовит страницу к будущей интерактивности
- он показывает направление roadmap прямо в UI
- он усиливает идею "session page = место действия"

## После Этого Шага

После placeholder actions логично идти так:

1. добавить `topic threads`
2. добавить `evidence matrix`
3. связать commits с files modified
4. сделать первый реальный headless question flow

## Визуальная Идея Следующей Версии

```text
[ Hero ]
[ Message Anchors ]
[ Intent Direction ]   [ Git Commits ]
[ Files ]              [ Tools ]
[ Session Timeline ]
[ Topic Threads ]      [ Future Actions ]
```

Где `Future Actions` сначала выглядит так:

```text
Future Actions
- Ask this session
- Continue in Codex
- Resume in Claude Code
- Start derived session
```

## Product Rule For This Plan

Каждое новое обогащение detail page должно отвечать хотя бы на один из вопросов:

- это лучше объясняет, что происходило?
- это добавляет новый независимый слой правды?
- это помогает продолжить работу из этой сессии?
- это делает страницу более удобной для человеческого глаза?

Если ответ везде "нет", блок не нужен.
