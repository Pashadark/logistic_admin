import os
import uuid
import logging
import sqlite3
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
TOKEN = "7833491235:AAEeP3bJWIgWxAjdMhYv6zvTE6dIbe7Ob2U"
GROUP_ID = -1002580459963
DB_PATH = "cargo_bot.db"

# Состояния диалога
(
    MAIN_MENU, SETTINGS_MENU,
    SEND_WAYBILL, SEND_PRODUCT, SEND_NUMBER, SEND_CITY, SEND_COMMENT,
    RECEIVE_WAYBILL, RECEIVE_PRODUCT, RECEIVE_NUMBER, RECEIVE_CITY, RECEIVE_COMMENT,
    TRANSFER_WAYBILL, TRANSFER_PRODUCT, TRANSFER_NUMBER, TRANSFER_CITY, TRANSFER_COMMENT
) = range(17)

# Статусы отправлений
STATUSES = {
    'created': '📝 Создано',
    'processing': '🔄 В обработке',
    'transit': '🚚 В пути',
    'delivered': '✅ Доставлено',
    'problem': '⚠️ Проблема'
}


def get_db_connection():
    """Создает соединение с базой данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Инициализирует базу данных при первом запуске"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shipments (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                type TEXT,
                waybill_photo TEXT,
                product_photo TEXT,
                waybill_number TEXT,
                city TEXT,
                status TEXT DEFAULT 'created',
                comment TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                telegram_waybill_file_id TEXT,
                telegram_product_file_id TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                notifications INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
    finally:
        conn.close()


def save_shipment(data):
    """Сохраняет отправление в базу данных"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO shipments 
            (id, user_id, type, waybill_number, city, status, comment, 
             waybill_photo, product_photo, telegram_waybill_file_id, telegram_product_file_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['id'],
            data['user_id'],
            data['type'],
            data['waybill_number'],
            data['city'],
            data.get('status', 'created'),
            data.get('comment', ''),
            data.get('waybill_photo', ''),
            data.get('product_photo', ''),
            data.get('telegram_waybill_file_id', ''),
            data.get('telegram_product_file_id', '')
        ))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка SQLite: {e}")
        return False
    finally:
        conn.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        telegram_id = user.id

        # Автоматическая регистрация нового пользователя
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name) 
            VALUES (?, ?, ?, ?)
        ''', (
            telegram_id,
            user.username,
            user.first_name,
            user.last_name
        ))
        conn.commit()
        conn.close()

        context.user_data['user_id'] = telegram_id

        await update.message.reply_text(
            f"Привет, {user.first_name}! Я бот для учета грузоперевозок.",
            reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Ошибка в start: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка. Попробуйте позже."
        )
        return ConversationHandler.END


def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📤 Отправление", callback_data='send')],
        [InlineKeyboardButton("📥 Получение", callback_data='receive')],
        [InlineKeyboardButton("🔄 Перемещение", callback_data='transfer')],
        [InlineKeyboardButton("⚙️ Настройки", callback_data='settings')]
    ]
    return InlineKeyboardMarkup(keyboard)


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text="Главное меню:",
        reply_markup=main_menu_keyboard()
    )
    return MAIN_MENU


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        text="⚙️ Настройки:\n\nЗдесь можно настроить уведомления и другие параметры.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Назад", callback_data='main')]
        ])
    )
    return SETTINGS_MENU


async def handle_shipment_start(update: Update, context: ContextTypes.DEFAULT_TYPE, shipment_type):
    query = update.callback_query
    await query.answer()

    type_name = {
        'send': 'отправки',
        'receive': 'получения',
        'transfer': 'перемещения'
    }.get(shipment_type, '')

    context.user_data['shipment_type'] = shipment_type

    await query.edit_message_text(
        text=f"Добавление {type_name}. Пришлите фото накладной:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Назад", callback_data='main')]
        ])
    )

    return {
        'send': SEND_WAYBILL,
        'receive': RECEIVE_WAYBILL,
        'transfer': TRANSFER_WAYBILL
    }.get(shipment_type)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, photo_type, next_state):
    try:
        photo = update.message.photo[-1]
        file_id = photo.file_id

        context.user_data[f'{photo_type}_file_id'] = file_id

        await update.message.reply_text(
            f"Фото {'накладной' if photo_type == 'waybill' else 'товара'} получено. " +
            ("Теперь пришлите фото товара:" if photo_type == 'waybill' else "Введите номер накладной:"),
            reply_markup=ReplyKeyboardRemove()
        )
        return next_state
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}")
        await update.message.reply_text(
            "Не удалось обработать фото. Попробуйте еще раз."
        )
        return MAIN_MENU


async def handle_waybill_number(update: Update, context: ContextTypes.DEFAULT_TYPE, next_state):
    waybill_number = update.message.text
    context.user_data['waybill_number'] = waybill_number

    await update.message.reply_text(
        "Номер накладной сохранен. Укажите город:",
        reply_markup=ReplyKeyboardRemove()
    )
    return next_state


async def handle_city(update: Update, context: ContextTypes.DEFAULT_TYPE, next_state):
    city = update.message.text
    context.user_data['city'] = city

    await update.message.reply_text(
        "Город сохранен. Добавьте комментарий (или нажмите /skip):",
        reply_markup=ReplyKeyboardRemove()
    )
    return next_state


async def skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['comment'] = ""
    return await finalize_shipment(update, context)


async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['comment'] = update.message.text
    return await finalize_shipment(update, context)


async def finalize_shipment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        shipment_id = str(uuid.uuid4())
        user_data = context.user_data

        success = save_shipment({
            'id': shipment_id,
            'user_id': user_data['user_id'],
            'type': user_data['shipment_type'],
            'waybill_number': user_data['waybill_number'],
            'city': user_data['city'],
            'comment': user_data.get('comment', ''),
            'telegram_waybill_file_id': user_data.get('waybill_file_id', ''),
            'telegram_product_file_id': user_data.get('product_file_id', '')
        })

        if not success:
            raise Exception("Ошибка сохранения в БД")

        type_name = {
            'send': 'ОТПРАВКА',
            'receive': 'ПОЛУЧЕНИЕ',
            'transfer': 'ПЕРЕМЕЩЕНИЕ'
        }.get(user_data['shipment_type'], 'ОТПРАВКА')

        message = (
            f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            f"🔹 НОВАЯ {type_name} 🔹\n"
            f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            f"▪️ Номер: {user_data['waybill_number']}\n"
            f"▪️ Город: {user_data['city']}\n"
            f"▪️ Статус: {STATUSES['created']}\n"
            f"▪️ Комментарий: {user_data.get('comment', 'нет')}"
        )

        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=message
        )

        await update.message.reply_text(
            "✅ Данные успешно сохранены!",
            reply_markup=main_menu_keyboard()
        )

        return MAIN_MENU
    except Exception as e:
        logger.error(f"Ошибка завершения отправки: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при сохранении. Попробуйте позже.",
            reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Ошибка:", exc_info=context.error)

    if update and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ Произошла ошибка. Попробуйте позже."
        )


def main():
    init_database()

    application = Application.builder() \
        .token(TOKEN) \
        .read_timeout(30) \
        .write_timeout(30) \
        .connect_timeout(30) \
        .build()

    def create_shipment_conv(shipment_type, waybill_state, product_state, number_state, city_state, comment_state):
        return ConversationHandler(
            entry_points=[CallbackQueryHandler(
                lambda u, c: handle_shipment_start(u, c, shipment_type),
                pattern=f'^{shipment_type}$')],
            states={
                waybill_state: [MessageHandler(
                    filters.PHOTO,
                    lambda u, c: handle_photo(u, c, 'waybill', product_state))],
                product_state: [MessageHandler(
                    filters.PHOTO,
                    lambda u, c: handle_photo(u, c, 'product', number_state))],
                number_state: [MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    lambda u, c: handle_waybill_number(u, c, city_state))],
                city_state: [MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    lambda u, c: handle_city(u, c, comment_state))],
                comment_state: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment),
                    CommandHandler('skip', skip_comment)
                ]
            },
            fallbacks=[CallbackQueryHandler(main_menu, pattern='^main$')],
            map_to_parent={MAIN_MENU: MAIN_MENU},
            per_message=False
        )

    main_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [
                create_shipment_conv('send', SEND_WAYBILL, SEND_PRODUCT, SEND_NUMBER, SEND_CITY, SEND_COMMENT),
                create_shipment_conv('receive', RECEIVE_WAYBILL, RECEIVE_PRODUCT, RECEIVE_NUMBER, RECEIVE_CITY,
                                     RECEIVE_COMMENT),
                create_shipment_conv('transfer', TRANSFER_WAYBILL, TRANSFER_PRODUCT, TRANSFER_NUMBER, TRANSFER_CITY,
                                     TRANSFER_COMMENT),
                CallbackQueryHandler(settings_menu, pattern='^settings$')
            ],
            SETTINGS_MENU: [
                CallbackQueryHandler(main_menu, pattern='^main$')
            ]
        },
        fallbacks=[]
    )

    application.add_handler(main_conv)
    application.add_error_handler(error_handler)

    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()