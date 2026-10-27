# Task Manager — контроль задач по открытию магазинов

Telegram-бот и Telegram Mini App. Руководители назначают задачи по открытию магазинов, сотрудники видят свои задачи, меняют статусы и пишут комментарии с фото. Приложение открывается прямо внутри Telegram, пользователь определяется автоматически.

## Быстрый старт

### 1. Создать бота в Telegram

1. Найдите в Telegram `@BotFather` → отправьте `/newbot`
2. Придумайте имя и username (должен заканчиваться на `bot`)
3. Сохраните токен вида `1234567890:AA...`
4. Узнайте свой Telegram ID: напишите `@userinfobot`

### 2. Настроить окружение

```bash
cp .env.example .env
# BOT_TOKEN=ваш_токен
# ADMIN_TG_IDS=ваш_telegram_id      (через запятую, если руководителей несколько)
# WEBHOOK_URL=https://ваш-домен/webhook
```

### 3. Запустить

```bash
docker-compose up -d
```

## Mini App

Mini App работает только по **HTTPS**. Когда задан `WEBHOOK_URL` с `https://`, сервер при старте сам:

- регистрирует webhook;
- ставит кнопку **«Задачи»** слева от поля ввода в чате с ботом — она открывает приложение у всех пользователей.

Кнопки «📂 Открыть» в уведомлениях открывают нужную задачу сразу внутри Telegram.

**Авторизация.** Telegram передаёт приложению `initData`, подписанные токеном бота. Сервер проверяет подпись (заголовок `X-Telegram-Init-Data`) и по ней определяет пользователя. ID вручную вводить не нужно, подделать чужой нельзя. Новые пользователи регистрируются автоматически при первом входе или при `/start`. Пользователи из `ADMIN_TG_IDS` сразу становятся руководителями.

Необязательно: в `@BotFather` → `/newapp` можно зарегистрировать приложение с коротким именем. Тогда появится ссылка вида `t.me/ваш_бот/app`.

### Проверка в обычном браузере

Вне Telegram подписи нет. Для отладки запустите сервер с `DEBUG=true` и откройте `http://localhost:8000/?debug_tg_user_id=123456789`. **В production `DEBUG` должен быть `false`.**

---

## Локальная разработка без Docker

```bash
cd backend
pip install -r requirements.txt
BOT_TOKEN=ваш_токен DEBUG=true uvicorn app.main:app --reload --port 8000
```

Без `WEBHOOK_URL` бот работает через long polling. Mini App-кнопки в этом режиме заменяются обычными ссылками: Telegram не открывает Mini App по http. Документация API: http://localhost:8000/docs

---

## Магазины и задачи

Создать магазин:

```bash
curl -X POST https://ваш-домен/api/stores/ \
  -H 'Content-Type: application/json' \
  -d '{"name": "Магазин ул. Ленина 1", "address": "г. Москва, ул. Ленина, д. 1", "planned_open_date": "2026-12-01"}'
```

При создании магазина автоматически создаются **43 задачи** из встроенного справочника, пока без исполнителей и сроков.

---

## Структура проекта

```
max-task-manager/
├── backend/app/
│   ├── main.py          # FastAPI, webhook, кнопка меню Mini App
│   ├── config.py        # Настройки из .env
│   ├── models/          # Employee, Store, Task, Comment, Reminder, History
│   ├── schemas/         # Pydantic-схемы
│   ├── api/             # REST-роуты, /api/me, webhook
│   └── services/        # Telegram API, авторизация initData, уведомления, планировщик
├── frontend/            # Mini App: Alpine.js + Bootstrap 5 + Telegram WebApp SDK
├── docker-compose.yml
└── .env.example
```

## API

| Метод | URL | Описание |
|---|---|---|
| POST | `/webhook` | Входящие события Telegram |
| GET | `/api/me` | Текущий пользователь Mini App (по `X-Telegram-Init-Data`) |
| GET/POST | `/api/employees/` | Сотрудники |
| PATCH | `/api/employees/{id}` | Обновить сотрудника |
| PATCH | `/api/employees/{id}/notifications` | Настройки уведомлений |
| GET/POST | `/api/stores/` | Магазины |
| GET | `/api/stores/{id}/summary` | Сводка по магазину |
| GET/POST | `/api/templates/` | Справочник задач |
| GET/POST | `/api/tasks/` | Задачи (фильтры: assignee_id, store_id, status, section, overdue_only) |
| PATCH | `/api/tasks/{id}` | Статус, срок, исполнитель |
| GET | `/api/tasks/{id}/history` | История изменений |
| POST | `/api/tasks/{id}/reminders/preset` | Напоминание (1h/2h/3h/1d/2d/3d) |
| GET/POST | `/api/tasks/{id}/comments/` | Комментарии и файлы |
| GET | `/api/export/tasks.xlsx` | Экспорт в Excel |

Автор изменений, комментариев и задач определяется по подписи Telegram.

## Роли

- **Сотрудник**: свои задачи, смена статуса и срока, комментарии.
- **Руководитель** (`is_admin`): все задачи, назначение исполнителей, уведомления о критичных и просроченных задачах, экспорт.

## PostgreSQL

```bash
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/taskmanager
```
