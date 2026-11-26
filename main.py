import logging
import time
import psycopg2
import telebot
from contextlib import contextmanager

from config import (
    BOT_TOKEN,
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

bot = telebot.TeleBot(BOT_TOKEN)


@contextmanager
def db():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_table():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    is_completed BOOLEAN DEFAULT FALSE,
                    is_archived BOOLEAN DEFAULT FALSE,
                    user_id BIGINT NOT NULL
                )
            """)


@bot.message_handler(commands=["start"])
def start_message(message):
    bot.reply_to(
        message,
        "Привет! Я бот для управления списком задач. Используйте /help для списка команд.",
    )


@bot.message_handler(commands=["help"])
def help_message(message):
    help_text = (
        "/start — начать работу\n"
        "/add <название> — добавить задачу\n"
        "/list — показать активные задачи\n"
        "/archive — показать архивные задачи\n"
        "/complete <id> — отметить задачу выполненной\n"
        "/delete <id> — переместить задачу в архив\n"
        "/help — показать список команд\n"
    )
    bot.reply_to(message, help_text)


@bot.message_handler(commands=["add"])
def add_task(message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)

    if len(args) < 2 or not args[1].strip():
        bot.reply_to(message, "Укажите название задачи. Пример: /add Купить молоко")
        return

    name = args[1].strip()
    if len(name) > 500:
        bot.reply_to(message, "Слишком длинное название задачи. Максимум 500 символов.")
        return

    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tasks (name, user_id) VALUES (%s, %s) RETURNING id",
                    (name, user_id),
                )
                task_id = cur.fetchone()[0]

        bot.reply_to(message, f"Задача '{name}' добавлена. ID: {task_id}")
    except Exception:
        logging.exception("Ошибка при добавлении задачи")
        bot.reply_to(message, "Ошибка при добавлении задачи. Попробуйте позже.")


@bot.message_handler(commands=["list"])
def list_tasks(message):
    user_id = message.from_user.id

    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, is_completed
                    FROM tasks
                    WHERE user_id = %s AND is_archived = FALSE
                    ORDER BY id
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
    except Exception:
        logging.exception("Ошибка при получении списка задач")
        bot.reply_to(message, "Ошибка при получении списка задач.")
        return

    if not rows:
        bot.reply_to(message, "Ваш список задач пуст.")
        return

    task_list = []
    for task_id, name, is_completed in rows:
        status = "✅" if is_completed else "⏳"
        task_list.append(f"- id {task_id}: {name} {status}")

    bot.reply_to(message, "Ваши задачи:\n" + "\n".join(task_list))


@bot.message_handler(commands=["archive"])
def archive_tasks(message):
    user_id = message.from_user.id

    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, is_completed
                    FROM tasks
                    WHERE user_id = %s AND is_archived = TRUE
                    ORDER BY id
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
    except Exception:
        logging.exception("Ошибка при получении архива")
        bot.reply_to(message, "Ошибка при получении архива.")
        return

    if not rows:
        bot.reply_to(message, "Ваш архив пуст.")
        return

    task_list = []
    for task_id, name, is_completed in rows:
        status = "✅" if is_completed else "⏳"
        task_list.append(f"- id {task_id}: {name} {status}")

    bot.reply_to(message, "Ваши архивные задачи:\n" + "\n".join(task_list))


def get_task_id(message):
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Неверный формат. Пример: /delete 68")
        return None

    try:
        return int(args[1])
    except ValueError:
        bot.reply_to(message, "ID задачи должен быть числом.")
        return None


@bot.message_handler(commands=["delete"])
def delete_task(message):
    user_id = message.from_user.id
    task_id = get_task_id(message)
    if task_id is None:
        return

    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tasks
                    SET is_archived = TRUE
                    WHERE id = %s
                      AND user_id = %s
                      AND is_archived = FALSE
                    RETURNING id
                    """,
                    (task_id, user_id),
                )
                updated = cur.fetchone()

        if updated:
            bot.reply_to(message, f"Задача с id {task_id} перемещена в архив.")
        else:
            bot.reply_to(message, "Активная задача с таким id не найдена.")
    except Exception:
        logging.exception("Ошибка при архивировании задачи")
        bot.reply_to(message, "Ошибка при архивировании задачи.")


@bot.message_handler(commands=["complete"])
def complete_task(message):
    user_id = message.from_user.id
    task_id = get_task_id(message)
    if task_id is None:
        return

    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tasks
                    SET is_completed = TRUE
                    WHERE id = %s
                      AND user_id = %s
                      AND is_archived = FALSE
                      AND is_completed = FALSE
                    RETURNING id
                    """,
                    (task_id, user_id),
                )
                updated = cur.fetchone()

        if updated:
            bot.reply_to(message, f"Задача с id {task_id} отмечена как выполненная.")
        else:
            bot.reply_to(
                message,
                "Активная невыполненная задача с таким id не найдена.",
            )
    except Exception:
        logging.exception("Ошибка при выполнении задачи")
        bot.reply_to(message, "Ошибка при обновлении статуса задачи.")


@bot.message_handler(func=lambda m: True)
def handle_unknown(message):
    bot.reply_to(message, "Неизвестная команда. Используйте /help.")



if __name__ == "__main__":
    create_table()

    print("Бот запущен...")
    while True:
        try:
            bot.infinity_polling(
                skip_pending=True,
                timeout=60,
                long_polling_timeout=60,
            )
        except KeyboardInterrupt:
            logging.info("Остановка по Ctrl+C")
            break
        except Exception as e:
            logging.error(
                "Критическая ошибка в polling: %s. Перезапуск через 15 секунд...", e
            )
            time.sleep(15)
