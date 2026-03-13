# Agent Nexus 🤖

**Real-time AI Coding Agent Monitoring Dashboard**

Мониторинг всех AI агентов в одном месте: Codex, Kimi, Gemini, Qwen, Claude, Pi

## 🚀 Быстрый старт

```bash
# Backend
cd backend
pip install -r requirements.txt
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend
npm install
npm run dev
```

Открыть локально: http://localhost:3000

Если фронтенд открыт напрямую на `:3000`, добавьте `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Для опубликованного доступа через Caddy используйте:

```text
http://107.174.231.22:8888
```

В этом сценарии `NEXT_PUBLIC_API_URL` не нужен: фронтенд должен использовать текущий origin.

Быстрый запуск опубликованного стека:

```bash
./scripts/start_published.sh
```

Полное восстановление published-стека с доказательством через headless Playwright,
скриншотами и повторными confidence-прогонами:

```bash
make published-restore
```

Все project-level shell scripts теперь лежат в `scripts/`.

По умолчанию `scripts/start_published.sh` после старта гоняет Playwright-проверку по
реальному published URL. Отключается через `NEXUS_PLAYWRIGHT_CHECK_ENABLED=0`.
Если на хосте ещё нет Chromium, скрипт попытается один раз установить его
автоматически через `npx playwright install chromium`. Отдельно можно запустить:

```bash
cd frontend
npm run playwright:install
```

Основные порты, URL и лимиты теперь лежат в корневом `.env`.
Shell-скрипты читают их через `config/runtime.sh`, backend через `backend/api/settings.py`,
frontend через `frontend/lib/runtime-config.ts`.

Для Nginx deploy-шаблонов есть рендер:

```bash
./deploy/render_nginx_conf.sh ./deploy/nginx-nexus.conf /tmp/nginx-nexus.conf
./deploy/render_nginx_conf.sh ./deploy/nginx.conf /tmp/nginx.conf
```

Отдельный внешний browser-check:

```bash
./deploy/check_published_url.sh
./deploy/check_published_url.sh http://107.174.231.22:8888
```

Если нужен автоподъём после ребута и минутный watchdog:

```bash
./scripts/install_published_watchdog.sh
```

## 📚 Документация

- [docs/README.md](docs/README.md) -> карта документации
- [docs/product/HIGH_LEVEL_EXPECTATIONS.md](docs/product/HIGH_LEVEL_EXPECTATIONS.md) -> верхнеуровневые продуктовые ожидания
- [PROFILE.md](PROFILE.md) -> зачем существует проект
- [AURA.md](AURA.md) -> как проект должен строиться
- [PROTOCOL.json](PROTOCOL.json) -> какие контракты и инструменты уже существуют

## Debug Logging

Backend now emits structured JSON logs to stdout for:
- request start and completion with `request_id`
- auth success and denial reasons
- session scans and scan summaries
- WebSocket connect, disconnect, and message flow

Browser-side debug events are mirrored into:

```js
window.__AGENT_NEXUS_DEBUG__
```

That buffer keeps recent API and WebSocket events, including the same request IDs that the backend returns in `X-Request-ID`. For live debugging:

```bash
tail -f /tmp/nexus-backend.log
tail -f /tmp/nexus-frontend.log
```

GitHub Actions:
- workflow `.github/workflows/published-url-check.yml`
- запускается вручную, по расписанию каждые 30 минут и может вызываться из будущего deploy workflow через `workflow_call`
- URL берёт из `vars.NEXUS_PUBLIC_URL`, либо использует дефолт `http://107.174.231.22:8888`

## 📊 Возможности

- **6 агентов**: Codex, Kimi, Gemini, Qwen, Claude, Pi
- **Real-time**: WebSocket обновления
- **Метрики**: Токены, статусы, распределение
- **Поиск**: FTS5 полнотекстовый поиск
- **Безопасность**: 
  - Парольная аутентификация
  - IP whitelist
  - Rate limiting
  - Secret masking (28 паттернов)
- **Handoff**: Передача задач между агентами

## 📁 Структура

```
agents_sessions_dashboard/
├── backend/
│   ├── api/           # FastAPI endpoints
│   │   ├── main.py    # App + middleware
│   │   ├── routes/    # Sessions, Auth, WebSocket
│   │   ├── database.py # SQLite + FTS5
│   │   └── handoff.py  # Agent handoff
│   ├── parsers/       # 6 agent parsers
│   ├── summarizer/    # Compression + masking
│   └── watcher/       # File watcher
├── frontend/          # Next.js 14
│   ├── app/           # Pages
│   ├── components/    # UI components
│   ├── hooks/         # useWebSocket
│   └── lib/           # API client
└── deploy/            # Systemd + Nginx
```

## 🔧 Конфигурация

```bash
# Environment variables
NEXUS_PASSWORD=secret          # Пароль для входа
NEXUS_IP_WHITELIST=10.0.0.0/8  # Разрешённые IP
RATE_LIMIT_REQUESTS=100        # Лимит запросов
TELEGRAM_CLIENT_ID=1234567890  # Client ID из BotFather Web Login
TELEGRAM_CLIENT_SECRET=...     # Client Secret из BotFather Web Login
TELEGRAM_ALLOWED_USER_IDS=...  # Предпочтительный allow-list
TELEGRAM_ALLOWED_USERNAMES=... # Временный allow-list по username
```

Для Telegram Login добавьте публичный origin и callback URL в BotFather Web Login Allowed URLs:

```text
http://107.174.231.22:8888
http://107.174.231.22:8888/api/auth/telegram/callback
```

## 📡 API

| Endpoint | Description |
|----------|-------------|
| `GET /api/sessions` | Список сессий |
| `GET /api/sessions/{id}` | Детали сессии |
| `GET /api/metrics` | Метрики |
| `POST /api/sessions/scan` | Пересканировать |
| `WS /ws` | Real-time обновления |
| `POST /api/auth/login` | Вход |
| `POST /api/auth/telegram/login` | Вход через Telegram |
| `GET /health` | Health check |

## 🎨 Цвета агентов

| Agent | Color |
|-------|-------|
| Codex | 🟢 Зелёный |
| Kimi | 🟠 Оранжевый |
| Gemini | 🔵 Синий |
| Qwen | 🟣 Фиолетовый |
| Claude | 🩷 Розовый |
| Pi | 🩵 Бирюзовый |

## 📦 Deploy

```bash
# Systemd
sudo cp deploy/nexus.service /etc/systemd/system/
sudo systemctl enable --now nexus

# Nginx
./deploy/render_nginx_conf.sh ./deploy/nginx.conf /tmp/nexus.nginx.conf
sudo cp /tmp/nexus.nginx.conf /etc/nginx/sites-available/nexus
sudo ln -s /etc/nginx/sites-available/nexus /etc/nginx/sites-enabled/
sudo nginx -s reload
```

## 📝 License

MIT
