# TechBase AI — Ассистент по СКУД и СВН b

AI чат-бот для менеджеров по системам безопасности. Знает всех производителей, ищет актуальную документацию в интернете, отвечает на уровне инженера.

## Что умеет

- Знает всех вендоров — Болид, Hikvision, Dahua, Sigur, PERCo, Trassir, Axis, RusGuard
- Веб-поиск — находит актуальные инструкции прямо с сайтов производителей
- Пошаговые ответы — схемы подключения, настройка, сброс паролей, расчёты
- Стриминг — текст появляется по мере генерации, как в claude.ai
- Без VPN — менеджеры заходят по обычной ссылке

## Деплой: GitHub + Railway за 10 минут

### Шаг 1: Создайте репозиторий на GitHub
1. github.com → New repository → Название: techbase-ai → Private → Create

### Шаг 2: Загрузите все файлы из этого архива в репозиторий

### Шаг 3: Railway
1. railway.app → залогиньтесь через GitHub
2. New Project → Deploy from GitHub repo → выберите techbase-ai

### Шаг 4: Добавьте API ключ в Railway
1. Variables → добавьте: ANTHROPIC_API_KEY = sk-ant-ваш-ключ

### Шаг 5: Получите ссылку
1. Settings → Networking → Generate Domain
2. Отправьте ссылку менеджерам

## Стоимость
- Railway: $5/мес
- Один вопрос менеджера: ~$0.01-0.03
- 100 вопросов/день: ~$30-90/мес

## Структура проекта
- server.py — бэкенд (FastAPI + Claude API + Web Search)
- static/index.html — фронтенд (чат-интерфейс)
- requirements.txt — зависимости Python
- Procfile — команда запуска для Railway
- railway.toml — конфигурация Railway
