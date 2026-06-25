import telebot
from telebot import types
import psycopg2
from config import *


# Настройка бота
bot = telebot.TeleBot(BOT_TOKEN)

# Подключение к PostgreSQL
conn = psycopg2.connect(
    host=HOST,
    database=DB,
    user=USER,
    password=PAS
)
cur = conn.cursor()

# Создание таблицы
def create_table():
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        is_completed BOOLEAN DEFAULT FALSE,
        user_id BIGINT NOT NULL
    )
    """)
    conn.commit()
create_table()


# Обработчик /start
@bot.message_handler(commands=['start'])
def start_message(message):
    bot.reply_to(message, "Привет! Я бот для управления списком задач. Используйте /help для списка команд.")


# Обработчик /help
@bot.message_handler(commands=['help'])
def help_message(message):
    help_text = (
        "/start — начать работу\n"
        "/help — показать список команд\n"
        "/add <название> — добавить задачу\n"
        "/list — показать список задач\n"
        "/delete <номер> — удалить задачу\n"
        "/complete <номер> — отметить задачу как выполненную"
    )
    bot.reply_to(message, help_text)


# Обработчик /add
@bot.message_handler(commands=['add'])
def add_task(message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Укажите название задачи. Пример: /add Купить молоко")
        return
    name = ' '.join(args[1:])
    try:
        cur.execute(
            "INSERT INTO tasks (name, user_id) VALUES (%s, %s) RETURNING id",
            (name, user_id)
        )
        task_id = cur.fetchone()[0]
        conn.commit()
        bot.reply_to(message, f"Задача '{name}' добавлена. ID: {task_id}")
    except Exception as e:
        conn.rollback()
        bot.reply_to(message, "Ошибка при добавлении задачи. Попробуйте позже.")


# Обработчик /list
@bot.message_handler(commands=['list'])
def list_tasks(message):
    user_id = message.from_user.id
    cur.execute(
        "SELECT id, name, is_completed FROM tasks WHERE user_id = %s ORDER BY id",
        (user_id,)
    )
    rows = cur.fetchall()
    if not rows:
        bot.reply_to(message, "Ваш список задач пуст.")
        return
    task_list = []
    for row in rows:
        task_id, name, is_completed = row
        status = "✅" if is_completed else "❌"
        task_list.append(f"№{task_id}: {name} {status}")
    bot.reply_to(message, "Ваши задачи:\n" + "\n".join(task_list))


# Обработчик /delete
@bot.message_handler(commands=['delete'])
def delete_task(message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Неверный формат. Пример: /delete 1")
        return
    try:
        task_id = int(args[1])
    except ValueError:
        bot.reply_to(message, "Номер задачи должен быть числом.")
        return
    try:
        cur.execute(
            "DELETE FROM tasks WHERE id = %s AND user_id = %s RETURNING id",
            (task_id, user_id)
        )
        deleted = cur.fetchone()
        if deleted:
            conn.commit()
            bot.reply_to(message, f"Задача {task_id} удалена.")
        else:
            conn.rollback()
            bot.reply_to(message, "Такой задачи не существует или она не ваша.")
    except Exception as e:
        conn.rollback()
        bot.reply_to(message, "Ошибка при удалении задачи.")


# Обработчик /complete
@bot.message_handler(commands=['complete'])
def complete_task(message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Неверный формат. Пример: /complete 1")
        return
    try:
        task_id = int(args[1])
    except ValueError:
        bot.reply_to(message, "Номер задачи должен быть числом.")
        return
    try:
        cur.execute(
            "UPDATE tasks SET is_completed = TRUE WHERE id = %s AND user_id = %s RETURNING id",
            (task_id, user_id)
        )
        updated = cur.fetchone()
        if updated:
            conn.commit()
            bot.reply_to(message, f"Задача {task_id} отмечена как выполненная.")
        else:
            conn.rollback()
            bot.reply_to(message, "Такая задача не найдена или не ваша.")
    except Exception as e:
        conn.rollback()
        bot.reply_to(message, "Ошибка при обновлении статуса.")


# Обработка неизвестных команд
@bot.message_handler(func=lambda m: True)
def handle_unknown(message):
    bot.reply_to(message, "Неизвестная команда. Используйте /help.")


# Запуск бота
bot.polling(none_stop=True)
