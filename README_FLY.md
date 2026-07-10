# Деплой CS2-бота на Fly.io

Бот работает через **polling** (как и раньше), webhook не нужен — на Fly.io
фоновый процесс без объявленного `[[services]]` в `fly.toml` просто крутится
постоянно и не "засыпает".

## 0. Предварительно — смени ключи!
Старые STEAM_API_KEY и TELEGRAM_TOKEN были захардкожены в коде — считай их
слитыми. Прежде чем деплоить:
- Новый токен бота: у @BotFather команда `/revoke` для старого бота, либо
  создать нового через `/newbot`
- Новый Steam API key: https://steamcommunity.com/dev/apikey

## 1. Установка flyctl
```bash
curl -L https://fly.io/install.sh | sh
fly auth login
```

## 2. Инициализация приложения
Из папки с этими файлами (Dockerfile, fly.toml, cs2_watch_bot.py, requirements.txt):
```bash
fly launch --no-deploy
```
- На вопрос "Would you like to copy its configuration to the new app?" — да,
  используем существующий `fly.toml`.
- Имя приложения можно оставить/поменять (`app = "..."` в fly.toml).
- На вопрос про Postgres/Redis — откажись (не нужны).

Если `fly launch` перезапишет `fly.toml` своими настройками — просто верни
секцию `[mounts]` и убедись, что нет `[[services]]`/`[http_service]`.

## 3. Создать volume для хранения chat_ids.txt
```bash
fly volumes create cs2bot_data --region waw --size 1
```
(регион должен совпадать с `primary_region` в fly.toml; размер 1 GB — с запасом)

## 4. Задать секреты
```bash
fly secrets set \
  STEAM_API_KEY=твой_новый_ключ \
  TELEGRAM_TOKEN=твой_новый_токен \
  STEAM_ID=76561198161778886
```
Если Telegram у тебя заблокирован в стране хостинга (для Fly обычно не
актуально, серверы за границей) — можно не задавать TELEGRAM_PROXY.

## 5. Деплой
```bash
fly deploy
```

## 6. Проверка
```bash
fly logs
```
Должна появиться строка "Бот запущен...". Дальше пиши боту `/start` в Telegram.

## Полезные команды
- `fly status` — статус машины
- `fly logs` — логи в реальном времени
- `fly ssh console` — зайти внутрь контейнера
- `fly secrets list` — какие секреты заданы (без значений)
- `fly deploy` — передеплой после изменений в коде

## Почему не webhook
Webhook имеет смысл, когда у тебя много ботов/высокая нагрузка и не хочется
держать постоянный процесс, либо когда используешь serverless-платформу с
автоскейлингом в ноль по HTTP-трафику. Тут ничего из этого не требуется:
бот один, нагрузка минимальная, а polling проще — не нужен ни свой веб-сервер,
ни настройка TLS/домена/`setWebhook`. Fly.io отлично держит такие процессы
как обычные "воркеры" 24/7.
