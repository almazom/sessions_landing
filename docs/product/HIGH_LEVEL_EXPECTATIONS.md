# High Level Expectations

## Роль Этого Файла

Этот файл отвечает на вопрос:

- каким должен быть хороший продуктовый результат
- как должна ощущаться система для пользователя
- что мы считаем сильной, полезной, живой страницей сессии

Использовать его нужно так:

- `PROFILE.md` -> зачем существует проект
- `docs/product/HIGH_LEVEL_EXPECTATIONS.md` -> каким должен быть хороший результат
- `AURA.md` -> как это строить инженерно

## Главная Идея Продукта

Agent Nexus должен превращать разрозненные AI session files в одну понятную рабочую среду для одного пользователя.

Главная цель:

- быстро понять, что происходило
- быстро найти нужную сессию
- быстро увидеть, во что разговор превратился на практике
- быстро открыть более глубокий слой и продолжить работу

## JSON Как Источник Правды

JSON или JSONL файл харнесса является основным источником правды о сессии.

Нужно мыслить так:

- один файл = одна сессия
- у сессии есть временной промежуток
- у сессии есть начало
- у сессии есть конец
- у сессии есть внутренняя хронология
- всё дальнейшее обогащение привязывается к этому окну времени

Это значит:

- мы не подменяем JSON внешними догадками
- мы расширяем понимание сессии вокруг JSON
- все дополнительные сигналы должны быть привязаны к этой сессии и её времени

## Landing Page Expectation

Главная страница должна быть рабочей панелью, а не декоративной витриной.

Ожидаемое поведение:

- по умолчанию показывать все сессии за сегодня
- latest session всегда держать наверху
- latest session можно показывать шире и богаче
- остальные сессии должны быстро сканироваться глазами
- каждая карточка сессии должна быть ссылкой в глубину

Короткая идея:

- landing = карта дня
- detail page = досье одной сессии

## Session Detail Expectation

Страница сессии должна ощущаться как живое досье по одному JSON-артефакту.

Это не короткая карточка.
Это отдельная страница, где можно позволить себе глубину.

Обязательные слои:

- identity
- time window
- narrative
- evidence
- future actions

## Identity Layer Expectation

На detail page должно быть понятно:

- какой это harness
- какой это session id
- где лежит исходный файл
- какой route открывает эту сессию
- какой cwd или project root относится к этой сессии

Пользователь не должен терять точную идентичность артефакта.

## Time Window Expectation

Время сессии - это один из самых важных координатных слоёв.

Нужно явно показывать:

- когда сессия началась
- когда закончилась
- длительность
- что попало внутрь этого окна

Именно на это окно потом можно навешивать:

- commits
- file changes
- timeline events
- future topic extraction
- future question answering

## Evidence Layers Expectation

Одна сессия не должна объясняться только одним типом сигнала.

Нужны несколько слоёв правды:

- пользовательские сообщения
- intent evolution
- timeline событий
- изменённые файлы
- git commits
- позже topic extraction
- позже action extraction
- позже question-answer layer поверх файла

Сильная detail page - это страница, где несколько независимых источников подтверждают одну историю.

## Evidence Priority Rule

Не все слои правды равны.

Нужен явный порядок доверия:

1. исходный session JSON или JSONL
2. timeline, который прямо извлечён из session artifact
3. локальные repository signals внутри окна времени
4. derived layers

Где:

- `derived layers` = intent extraction, topic extraction, summaries, question-answer outputs

Правило:

- derived layer не должен спорить с source artifact как будто он главнее
- если есть конфликт, source artifact важнее
- если есть конфликт между user intent и commits, это не ошибка автоматически
- это может значить, что пользователь хотел одно, а реализовано было другое

То есть система должна уметь показывать расхождение, а не скрывать его.

## Intent Layer Expectation

Intent extraction сейчас в первую очередь опирается на пользовательские сообщения.

Это хорошо, потому что показывает:

- куда пользователь вёл систему
- как менялось направление
- какие были повороты

Но intent layer - это только один слой.
Он отвечает скорее за направление пользователя, чем за фактическую реализацию.

## Git Commits As Evidence

Git commits являются отдельным источником правды.

Они особенно важны, если проект движется к дисциплине авто-коммитов по логическим блокам.

Тогда коммит показывает:

- что дошло до репозитория
- какой логический блок был завершён
- как система формулировала результат в виде commit title

Нужно считать commit titles полезным смысловым слоем, а не просто техническим логом.

Хорошая detail page должна уметь показать:

- commits внутри окна сессии
- commit titles
- commit order
- связь commit titles с narrative сессии

## Topic Extraction Expectation

В будущем мы должны уметь извлекать не только user intent, но и темы.

Разница такая:

- intent = куда пользователь вёл работу
- topic = какие смысловые блоки реально обсуждались

Пример:

- intent: "починить detail page"
- topics:
  - routing
  - session timeline
  - git commits
  - published verification

Это даст более богатые будущие лендинги и визуализации.

## Session As Action Surface

В будущем страница сессии должна быть не только для чтения, но и для действия.

Нужно закладывать ожидание, что сессия может быть:

- архивной
- восстанавливаемой
- живой

И что из UI можно будет:

- задать вопрос по этой сессии
- продолжить эту сессию
- открыть новую сессию на основе этой
- отправить headless prompt в существующую сессию

Важно:

- это не должно менять исходный JSON-файл
- это должен быть отдельный operational layer поверх исходного artifact

## Session State Model

У detail page должна быть понятная модель состояния сессии.

Минимальные состояния:

- `archived`
- `restorable`
- `live`
- `queryable`

Смысл такой:

- `archived` -> только чтение, исторический artifact
- `restorable` -> можно поднять или продолжить через harness workflow
- `live` -> сессия ещё активна или очень недавно активна
- `queryable` -> к сессии можно задавать вопросы через отдельный query layer

Важно:

- одна и та же сессия может иметь несколько признаков
- например: `archived + queryable`
- или `live + queryable + restorable`

UI должен со временем научиться показывать это явно.

## Headless Query Expectation

У системы должна появиться возможность задавать вопросы к сессии без ручного вмешательства в JSON-файл.

Пример будущего поведения:

- выбрать harness
- указать session artifact
- отправить вопрос в headless режиме
- получить ответ на упрощённом русском языке

Источники для такого ответа могут быть разные:

- сам JSON-файл
- timeline
- commits
- files modified
- intent layer
- later: topic layer

## Action Safety Rules

Action blocks не должны обещать больше, чем система реально умеет безопасно делать.

Нужны режимы безопасности:

- `read-only`
- `ask-only`
- `resume-allowed`

Правило работы:

- `read-only` -> можно только смотреть evidence
- `ask-only` -> можно задавать вопросы к artifact без изменения source file
- `resume-allowed` -> можно запускать продолжение сессии через отдельный operational flow

Важно:

- resume не должен запускаться скрыто
- destructive actions не должны быть default path
- если система не уверена, интерфейс должен деградировать в `read-only` или `ask-only`

## UI Placeholder Expectation

Даже если некоторые функции ещё не готовы, интерфейс уже может готовить под них место.

Хорошие будущие placeholder-блоки:

- `Ask this session`
- `Continue session`
- `Resume in harness`
- `Topic threads`
- `Evidence matrix`
- `Commit narrative`

Плейсхолдер должен не шуметь, а заранее готовить архитектуру страницы.

## Phase Map Expectation

В документе и в продукте должно быть видно, что уже есть, что идёт следующим шагом, а что относится к будущему.

Хорошая схема фаз:

- `now`
- `next`
- `later`

Сейчас (`now`) уже разумно считать базой:

- session identity
- time window
- message anchors
- timeline
- tools
- files
- git commits

Следующий шаг (`next`):

- future actions section
- topic threads
- evidence matrix

Позже (`later`):

- real headless question flow
- real resume flow
- deeper cross-session visualizations
- topic-driven landing pages

Это нужно, чтобы не смешивать текущую реализацию и дальний roadmap.

## Visual Expectation

Страница должна быть удобна для человеческого глаза.

Нужно стремиться к такому ритму:

- сверху identity и summary
- ниже message anchors
- ниже evidence blocks
- ниже timeline
- ниже future action area

Страница должна читаться сверху вниз как история.

## Quality Bar For Detail Page

Detail page считается достаточно зрелой, если она отвечает минимум на четыре вопроса:

- что это за сессия
- что пользователь хотел
- что реально происходило по времени
- что дошло до репозитория или файловой системы

Минимальный хороший состав страницы:

- identity block
- time window block
- message anchors
- timeline
- хотя бы один operational evidence block

Где `operational evidence block` может быть:

- files modified
- git commits
- tools used

Сильная detail page - это не страница, где много блоков.
Это страница, где блоки вместе собирают одну понятную историю.

## Visual Example

Пример желаемого строя страницы:

```text
[ Hero / Identity ]
[ Message Anchors ]
[ Intent Direction ]   [ Git Commits ]
[ Files ]              [ Tools ]
[ Session Timeline ]
[ Topic Threads ]      [ Ask This Session ]
```

Другой вариант, более narrative:

```text
1. Что это за сессия
2. С чего всё началось
3. Как менялось направление
4. Что реально делали
5. Что закоммитили
6. Что можно спросить или продолжить дальше
```

## Routing Expectation

Каждая сессия должна открываться по стабильному route.

Ожидаемая форма:

- `/sessions/<harness>/<id>`

Этого должно хватать, чтобы переоткрыть нужный artifact, если известны harness и id.

## Repository Evidence Rule

Для чтения локального состояния репозитория:

- по умолчанию использовать `git`
- `gh` использовать для GitHub-специфичных операций
- нельзя делать базовую session evidence зависимой от GitHub

Примеры:

- `git log` -> локальные коммиты
- `git show` -> детали коммита
- `gh` -> pull request, Actions, repo metadata, GitHub surfaces

## Engineering Expectation

Инженерно система должна оставаться:

- явной
- проверяемой
- расширяемой
- устойчивой к missing data

Высокоуровневые ожидания:

- contracts важнее shape drift
- source artifact важнее догадок
- graceful fallback обязателен
- stable URLs обязательны
- tests обязательны для новых visible behaviors
- published verification обязательна для больших UI изменений

## Non-Goals

Проект не пытается быть:

- общей командной аналитикой
- публичным SaaS
- копией чата
- красивой витриной без operational value

Это приватная система одного пользователя для работы поверх многих AI harnesses и provider formats.
