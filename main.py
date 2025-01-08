from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import sqlite3
import pandas as pd
import random

# === Инициализация базы данных ===
def init_db():
    conn = sqlite3.connect("participants.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS participants (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        twitch_nick TEXT,
        consent INTEGER
    )
    """)
    conn.commit()
    conn.close()

# === Добавление пользователя в базу ===
def add_participant(user_id, username, twitch_nick, consent):
    conn = sqlite3.connect("participants.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO participants VALUES (?, ?, ?, ?)",
                   (user_id, username, twitch_nick, consent))
    conn.commit()
    conn.close()

# === Получение количества участников ===
def get_participant_count():
    conn = sqlite3.connect("participants.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM participants")
    count = cursor.fetchone()[0]
    conn.close()
    return count

# === Получение номера участника ===
def get_participant_number(user_id):
    conn = sqlite3.connect("participants.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM participants ORDER BY rowid")
    participants = cursor.fetchall()
    conn.close()
    for index, participant in enumerate(participants, start=1):
        if participant[0] == user_id:
            return index
    return None

# === Проверка подписки на канал ===
async def check_subscription(user_id: int, channel_id: str, context) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

# === Функция выбора случайного участника ===
def roll_participant():
    conn = sqlite3.connect("participants.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM participants")
    participants = cursor.fetchall()
    conn.close()
    if participants:
        return random.choice(participants)
    return None

# === Команда /start ===
async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("Даю согласие", callback_data="consent")]
    ]
    await update.message.reply_text(
        "Добро пожаловать! Для участия в розыгрыше:\n"
        "1. Подпишитесь на наш Telegram-канал.\n"
        "2. Укажите ваш ник Twitch.\n"
        "Нажмите 'Даю согласие', чтобы продолжить.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# === Обработка согласия ===
async def button_handler(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id
    channel_id = "@streamakhno"  # Замените на username вашего канала

    is_subscribed = await check_subscription(user_id, channel_id, context)

    if query.data == "consent":
        if is_subscribed:
            await query.message.reply_text("Введите ваш ник Twitch:")
            context.user_data["consent"] = True
        else:
            await query.message.reply_text(
                "Вы не подписаны на наш канал! Подпишитесь здесь: "
                "https://t.me/streamakhno"
            )

# === Обработка Twitch ника ===
async def twitch_handler(update: Update, context):
    if context.user_data.get("consent"):
        twitch_nick = update.message.text
        user = update.message.from_user
        add_participant(user.id, user.username, twitch_nick, 1)

        participant_count = get_participant_count()
        participant_number = get_participant_number(user.id)

        await update.message.reply_text(
            f"Ваши данные успешно сохранены! Спасибо за участие.\n"
            f"В розыгрыше участвуют {participant_count} участников.\n"
        )
        context.user_data.clear()

# === Ограничение доступа к командам ===
def is_creator(user_id):
    CREATOR_ID = 7014335873
    return user_id == CREATOR_ID

async def restricted_command(update: Update, context):
    await update.message.reply_text("У вас нет прав для выполнения этой команды.")

# === Команда /roll ===
async def roll(update: Update, context):
    if not is_creator(update.effective_user.id):
        await restricted_command(update, context)
        return

    participant = roll_participant()
    if participant:
        user_id, username, twitch_nick, _ = participant
        await update.message.reply_text(
            f"Поздравляем! Победитель:\n"
            f"ID: {user_id}\n"
            f"Username: {username}\n"
            f"Twitch: {twitch_nick}"
        )
    else:
        await update.message.reply_text("В базе данных пока нет участников.")

# === Команда /info ===
async def info(update: Update, context):
    if not is_creator(update.effective_user.id):
        await restricted_command(update, context)
        return

    user = update.effective_user
    await update.message.reply_text(
        f"Ваши данные:\n"
        f"ID: {user.id}\n"
        f"Username: {user.username}\n"
        f"Имя: {user.first_name}\n"
        f"Фамилия: {user.last_name}"
    )

# === Команда /export ===
async def export_csv(update: Update, context):
    if not is_creator(update.effective_user.id):
        await restricted_command(update, context)
        return

    conn = sqlite3.connect("participants.db")
    df = pd.read_sql_query("SELECT * FROM participants", conn)
    df.index += 1  # Добавляем нумерацию
    df.to_csv("participants.csv", index_label="Номер")
    conn.close()
    await update.message.reply_document(open("participants.csv", "rb"))

# === Команда /reset ===
async def reset(update: Update, context):
    if not is_creator(update.effective_user.id):
        await restricted_command(update, context)
        return

    conn = sqlite3.connect("participants.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM participants")
    conn.commit()
    conn.close()

    await update.message.reply_text("Список участников успешно сброшен.")

# === Основной блок ===
def main():
    init_db()
    app = Application.builder().token("1").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, twitch_handler))
    app.add_handler(CommandHandler("export", export_csv))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("reset", reset))

    app.run_polling()

if __name__ == "__main__":
    main()
