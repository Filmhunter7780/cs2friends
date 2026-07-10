import logging
import os
import requests

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ==== НАСТРОЙКИ ====
# На Fly.io ключи задаются через `fly secrets set ...` (см. README_FLY.md).
# Никаких значений по умолчанию тут больше нет — если переменная не задана,
# бот сразу упадёт с понятной ошибкой, а не будет молча работать с чужими ключами.
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
STEAM_ID = os.getenv("STEAM_ID")  # SteamID64 владельца, чей список друзей проверяем

CS2_APPID = "730"        # AppID CS2 (тот же, что был у CS:GO)
CHECK_INTERVAL = 60       # как часто проверять, кто зашёл (секунды)
SUMMARY_INTERVAL = 3600   # раз в час — сводка всех играющих

# /data — точка монтирования Fly Volume (см. fly.toml). Если volume не подключен
# (например, при локальном запуске), просто используем текущую папку.
DATA_DIR = os.getenv("DATA_DIR", "/data" if os.path.isdir("/data") else ".")
CHAT_IDS_FILE = os.path.join(DATA_DIR, "chat_ids.txt")

currently_playing = {}   # steamid -> имя
subscribed_chats = set() # чаты, куда слать уведомления


def load_chat_ids():
    if os.path.exists(CHAT_IDS_FILE):
        with open(CHAT_IDS_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    subscribed_chats.add(int(line))


def save_chat_id(chat_id):
    if chat_id in subscribed_chats:
        return
    subscribed_chats.add(chat_id)
    with open(CHAT_IDS_FILE, "a") as f:
        f.write(f"{chat_id}\n")


def get_friend_ids():
    url = "https://api.steampowered.com/ISteamUser/GetFriendList/v1/"
    params = {"key": STEAM_API_KEY, "steamid": STEAM_ID, "relationship": "friend"}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return [f["steamid"] for f in data.get("friendslist", {}).get("friends", [])]


def get_players_summary(steamids):
    url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
    result = []
    for i in range(0, len(steamids), 100):  # API отдаёт максимум 100 id за раз
        chunk = steamids[i:i + 100]
        params = {"key": STEAM_API_KEY, "steamids": ",".join(chunk)}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result.extend(data.get("response", {}).get("players", []))
    return result


def get_friends_in_cs2():
    friend_ids = get_friend_ids()
    if not friend_ids:
        return {}
    players = get_players_summary(friend_ids)
    return {
        p["steamid"]: p.get("personaname", p["steamid"])
        for p in players
        if p.get("gameid") == CS2_APPID
    }


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "Бот запущен!\n"
        "Буду присылать уведомление, когда кто-то из друзей зайдёт в CS2, "
        "и раз в час — сводку всех, кто сейчас играет.\n"
        "Команда /status — проверить прямо сейчас."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        playing = get_friends_in_cs2()
    except Exception as e:
        await update.message.reply_text(f"Ошибка запроса к Steam API: {e}")
        return

    if playing:
        text = "Сейчас в CS2:\n" + "\n".join(f"• {name}" for name in playing.values())
    else:
        text = "Сейчас никто из друзей не играет в CS2."
    await update.message.reply_text(text)


async def check_new_players(context: ContextTypes.DEFAULT_TYPE):
    global currently_playing
    try:
        playing = get_friends_in_cs2()
    except Exception as e:
        logger.error(f"Ошибка запроса к Steam API: {e}")
        return

    new_players = {sid: name for sid, name in playing.items() if sid not in currently_playing}
    currently_playing = playing

    if not new_players:
        return

    for chat_id in subscribed_chats:
        for name in new_players.values():
            try:
                await context.bot.send_message(chat_id, f"🎮 {name} зашёл в CS2!")
            except Exception as e:
                logger.error(f"Не смог отправить сообщение в {chat_id}: {e}")


async def send_hourly_summary(context: ContextTypes.DEFAULT_TYPE):
    try:
        playing = get_friends_in_cs2()
    except Exception as e:
        logger.error(f"Ошибка запроса к Steam API: {e}")
        return

    if not playing:
        # Никто не играет — ничего не отправляем, чтобы не спамить пустыми сводками.
        return

    text = "🕐 Сейчас в CS2 играют:\n" + "\n".join(f"• {name}" for name in playing.values())

    for chat_id in subscribed_chats:
        try:
            await context.bot.send_message(chat_id, text)
        except Exception as e:
            logger.error(f"Не смог отправить сообщение в {chat_id}: {e}")


def main():
    missing = [name for name, val in
               [("STEAM_API_KEY", STEAM_API_KEY), ("TELEGRAM_TOKEN", TELEGRAM_TOKEN), ("STEAM_ID", STEAM_ID)]
               if not val]
    if missing:
        raise SystemExit(
            "Не заданы переменные окружения: " + ", ".join(missing) + ".\n"
            "На Fly.io: fly secrets set STEAM_API_KEY=... TELEGRAM_TOKEN=... STEAM_ID=..."
        )

    load_chat_ids()

    # Если хостинг требует прокси для выхода в интернет (например, Telegram
    # заблокирован в стране хостинга), укажи адрес прокси через переменную
    # окружения TELEGRAM_PROXY, например:
    #   export TELEGRAM_PROXY=http://proxy.server:3128
    # Если прокси не нужен — просто не задавай эту переменную.
    proxy_url = os.getenv("TELEGRAM_PROXY", "")

    builder = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .get_updates_read_timeout(30)
        .connect_timeout(30)
        .read_timeout(30)
    )
    if proxy_url:
        builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)

    app = builder.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))

    app.job_queue.run_repeating(check_new_players, interval=CHECK_INTERVAL, first=5)
    app.job_queue.run_repeating(send_hourly_summary, interval=SUMMARY_INTERVAL, first=SUMMARY_INTERVAL)

    logger.info("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
