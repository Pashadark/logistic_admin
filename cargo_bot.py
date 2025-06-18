import os
import uuid
import sqlite3
import logging
import sys
import csv
import io
import shutil
import pytz
import requests
from datetime import datetime, timedelta, time
from telegram import (
    Update,
    InputMediaPhoto,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    CallbackContext,
    JobQueue
)

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== КОНСТАНТЫ И НАСТРОЙКИ =====================
TOKEN = "7833491235:AAEeP3bJWIgWxAjdMhYv6zvTE6dIbe7Ob2U"
DB_NAME = "cargo_bot.db"
BACKUP_DIR = "backups"
GROUP_ID = -1002580459963
ADMIN_IDS = [185185047]

# Определяем MEDIA_ROOT
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
# Создаем подпапки
os.makedirs(os.path.join(MEDIA_ROOT, 'waybills'), exist_ok=True)
os.makedirs(os.path.join(MEDIA_ROOT, 'products'), exist_ok=True)

# Состояния диалога
(
    MAIN_MENU, SETTINGS_MENU, SEARCH_MENU,
    SEND_WAYBILL, SEND_PRODUCT, SEND_NUMBER, SEND_CITY,
    RECEIVE_WAYBILL, RECEIVE_PRODUCT, RECEIVE_NUMBER, RECEIVE_CITY,
    SEARCH_BY_DATE, SEARCH_BY_WAYBILL, ADD_COMMENT,
    ADMIN_PANEL, VIEW_ALL_SHIPMENTS, CHANGE_STATUS, BROADCAST_MESSAGE,
    EDIT_SHIPMENT, NOTIFICATION_SETTINGS
) = range(20)

# Статусы отправлений
STATUSES = {
    'created': '📝 Создано',
    'processing': '🔄 В обработке',
    'transit': '🚚 В пути',
    'delivered': '✅ Доставлено',
    'problem': '⚠️ Проблема'
}


# Визуальные стили
def format_section(title, content):
    return f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n🔹 {title.upper()} 🔹\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n{content}"


def format_info(items):
    return "\n".join([f"▪️ {key}: {value}" for key, value in items])


# ===================== БАЗА ДАННЫХ =====================
class Database:
    def __init__(self, db_name):
        self.db_name = db_name
        self.init_db()
        self.migrate_db()

    def init_db(self):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            # Таблица отправлений
            c.execute('''CREATE TABLE IF NOT EXISTS shipments
                        (id TEXT PRIMARY KEY,
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
                         telegram_product_file_id TEXT)''')

            # Таблица пользователей
            c.execute('''CREATE TABLE IF NOT EXISTS users
                        (user_id INTEGER PRIMARY KEY,
                         username TEXT,
                         first_name TEXT,
                         last_name TEXT,
                         notifications INTEGER DEFAULT 1,
                         created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

            # Таблица избранного
            c.execute('''CREATE TABLE IF NOT EXISTS favorites
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         shipment_id TEXT,
                         user_id INTEGER,
                         FOREIGN KEY(shipment_id) REFERENCES shipments(id))''')

            conn.commit()

    def migrate_db(self):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            # Добавляем столбец status если его нет
            c.execute("PRAGMA table_info(shipments)")
            columns = [col[1] for col in c.fetchall()]
            if 'status' not in columns:
                c.execute("ALTER TABLE shipments ADD COLUMN status TEXT DEFAULT 'created'")

            # Добавляем столбцы для Telegram file_id
            if 'telegram_waybill_file_id' not in columns:
                c.execute("ALTER TABLE shipments ADD COLUMN telegram_waybill_file_id TEXT")
            if 'telegram_product_file_id' not in columns:
                c.execute("ALTER TABLE shipments ADD COLUMN telegram_product_file_id TEXT")

            # Проверяем существование таблицы users
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not c.fetchone():
                c.execute('''CREATE TABLE users
                            (user_id INTEGER PRIMARY KEY,
                             username TEXT,
                             first_name TEXT,
                             last_name TEXT,
                             notifications INTEGER DEFAULT 1,
                             created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

            # Проверяем существование таблицы favorites
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='favorites'")
            if not c.fetchone():
                c.execute('''CREATE TABLE favorites
                            (id INTEGER PRIMARY KEY AUTOINCREMENT,
                             shipment_id TEXT,
                             user_id INTEGER,
                             FOREIGN KEY(shipment_id) REFERENCES shipments(id))''')

            conn.commit()

    def save_shipment(self, data):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            # Данные: (id, user_id, type, waybill_photo, product_photo, waybill_number, city, comment, telegram_waybill_file_id, telegram_product_file_id)
            full_data = (
                data[0], data[1], data[2], data[3],
                data[4], data[5], data[6], 'created', data[7],
                data[8], data[9]
            )
            c.execute('''INSERT INTO shipments 
                         (id, user_id, type, waybill_photo, product_photo, waybill_number, city, status, comment, telegram_waybill_file_id, telegram_product_file_id)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', full_data)
            conn.commit()

    def get_shipment_by_id(self, shipment_id):
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,))
            return c.fetchone()

    def update_shipment(self, shipment_id, field, value):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute(f"UPDATE shipments SET {field} = ? WHERE id = ?", (value, shipment_id))
            conn.commit()

    def get_user_settings(self, user_id):
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            return c.fetchone()

    def update_user_settings(self, user_id, field, value):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            if not self.get_user_settings(user_id):
                c.execute(f'''INSERT INTO users (user_id, {field}) VALUES (?, ?)''', (user_id, value))
            else:
                c.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
            conn.commit()

    def get_shipments_by_user(self, user_id, period_days=None):
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            if period_days:
                start_date = (datetime.now() - timedelta(days=period_days)).strftime('%Y-%m-%d %H:%M:%S')
                query = '''SELECT * FROM shipments 
                           WHERE user_id = ? AND timestamp >= ?
                           ORDER BY timestamp DESC'''
                c.execute(query, (user_id, start_date))
            else:
                query = '''SELECT * FROM shipments 
                           WHERE user_id = ? 
                           ORDER BY timestamp DESC'''
                c.execute(query, (user_id,))

            return c.fetchall()

    def get_shipments_by_date(self, user_id, date):
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            start_date = f"{date} 00:00:00"
            end_date = f"{date} 23:59:59"

            query = '''SELECT * FROM shipments 
                       WHERE user_id = ? AND timestamp BETWEEN ? AND ?
                       ORDER BY timestamp DESC'''
            c.execute(query, (user_id, start_date, end_date))
            return c.fetchall()

    def get_shipment_by_waybill(self, user_id, waybill_number):
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            query = '''SELECT * FROM shipments 
                       WHERE user_id = ? AND waybill_number = ?
                       ORDER BY timestamp DESC'''
            c.execute(query, (user_id, waybill_number))
            return c.fetchall()

    def update_comment(self, shipment_id, comment):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute("UPDATE shipments SET comment = ? WHERE id = ?", (comment, shipment_id))
            conn.commit()

    def update_status(self, shipment_id, status):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute("UPDATE shipments SET status = ? WHERE id = ?", (status, shipment_id))
            conn.commit()

    def get_all_shipments(self):
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM shipments ORDER BY timestamp DESC")
            return c.fetchall()

    def get_all_users(self):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute("SELECT DISTINCT user_id FROM shipments")
            return [row[0] for row in c.fetchall()]

    # Функции для избранного
    def toggle_favorite(self, shipment_id, user_id):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            # Проверяем, есть ли уже в избранном
            c.execute("SELECT id FROM favorites WHERE shipment_id = ? AND user_id = ?",
                      (shipment_id, user_id))
            exists = c.fetchone()

            if exists:
                # Удаляем из избранного
                c.execute("DELETE FROM favorites WHERE shipment_id = ? AND user_id = ?",
                          (shipment_id, user_id))
                action = "removed"
            else:
                # Добавляем в избранное
                c.execute("INSERT INTO favorites (shipment_id, user_id) VALUES (?, ?)",
                          (shipment_id, user_id))
                action = "added"

            conn.commit()
            return action

    def get_favorite_status(self, shipment_id, user_id):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM favorites WHERE shipment_id = ? AND user_id = ?",
                      (shipment_id, user_id))
            return bool(c.fetchone())


# Инициализация базы данных
db = Database(DB_NAME)


# ===================== ФУНКЦИИ БЭКАПА =====================
async def daily_backup(context: CallbackContext):
    """Ежедневное создание бэкапа базы данных"""
    try:
        # Создаем имя файла с датой
        date_str = datetime.now().strftime("%Y%m%d_%H%M")
        backup_filename = f"cargo_bot_backup_{date_str}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)

        # Копируем базу данных
        shutil.copyfile(DB_NAME, backup_path)

        # Отправляем уведомление администраторам
        message = f"✅ База данных успешно сохранена!\nФайл: {backup_filename}"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_document(
                    chat_id=admin_id,
                    document=open(backup_path, 'rb'),
                    filename=backup_filename,
                    caption=message
                )
            except Exception as e:
                logger.error(f"Ошибка отправки бэкапа администратору {admin_id}: {e}")

        # Отправляем уведомление в группу
        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=message
            )
        except Exception as e:
            logger.error(f"Ошибка отправки бэкапа в группу: {e}")

        logger.info(f"Создан бэкап базы данных: {backup_path}")

    except Exception as e:
        logger.error(f"Ошибка при создании бэкапа: {e}", exc_info=True)
        # Отправляем уведомление об ошибке администраторам
        error_msg = f"⚠️ Ошибка при создании бэкапа базы данных: {e}"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=error_msg)
            except Exception as e2:
                logger.error(f"Ошибка отправки уведомления об ошибке: {e2}")


# ===================== КЛАВИАТУРЫ =====================
def main_menu_keyboard(user_id=None):
    buttons = [
        ['📤 Отправить груз', '📥 Получить груз'],
        ['🔍 История отправлений', '⚙️ Настройки']
    ]
    if user_id and is_admin(user_id):
        buttons.append(['👑 Админ-панель'])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def settings_menu_keyboard(user_id=None):
    buttons = [
        ['🔔 Уведомления', 'ℹ️ О боте'],
        ['ℹ️ Помощь'],
        ['🔙 Назад']
    ]
    if user_id and is_admin(user_id):
        # Добавляем кнопки для администраторов
        buttons.insert(1, ['💾 Скачать базу SQLite', '📊 Скачать отчет Excel'])
        buttons.insert(2, ['👑 Админ-панель'])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def admin_menu_keyboard():
    """Клавиатура админ-панели в виде основного меню"""
    buttons = [
        ['📊 Скачать отчет', '📝 Все отправления'],
        ['🔄 Изменить статус', '✉️ Рассылка'],
        ['🔙 Назад в меню']
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def shipment_actions_keyboard(shipment_id, user_id=None):
    # Проверяем статус избранного
    is_favorite = db.get_favorite_status(shipment_id, user_id) if user_id else False
    favorite_text = "❌ Из избранного" if is_favorite else "⭐ В избранное"

    buttons = [
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f'edit_{shipment_id}')],
        [InlineKeyboardButton(favorite_text, callback_data=f'favorite_{shipment_id}')],
        [InlineKeyboardButton("🔄 Статус доставки", callback_data=f'status_{shipment_id}')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_details')]
    ]
    return InlineKeyboardMarkup(buttons)


def notification_settings_keyboard(user_id):
    """Динамическая клавиатура для уведомлений"""
    user_settings = db.get_user_settings(user_id)
    notifications_on = user_settings['notifications'] if user_settings and 'notifications' in user_settings else 1

    if notifications_on:
        on_button = "🔔 Уведомления: ВКЛ"
        off_button = "🔕 Выключить уведомления"
    else:
        on_button = "🔔 Включить уведомления"
        off_button = "🔕 Уведомления: ВЫКЛ"

    buttons = [
        [InlineKeyboardButton(on_button, callback_data='notif_on')],
        [InlineKeyboardButton(off_button, callback_data='notif_off')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_settings')]
    ]
    return InlineKeyboardMarkup(buttons)


def search_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("📅 За неделю", callback_data='search_week')],
        [InlineKeyboardButton("📆 За месяц", callback_data='search_month')],
        [InlineKeyboardButton("📅 По дате", callback_data='search_by_date')],
        [InlineKeyboardButton("🔢 По номеру накладной", callback_data='search_by_waybill')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_search')]
    ]
    return InlineKeyboardMarkup(buttons)


def cities_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Москва 🏙", callback_data='moscow')],
        [InlineKeyboardButton("СПб 🌉", callback_data='spb')],
        [InlineKeyboardButton("Новосибирск 🏢", callback_data='novosibirsk')]
    ])


def status_keyboard(shipment_id=None):
    buttons = []
    for status, status_text in STATUSES.items():
        callback_data = f"status_{status}_{shipment_id}" if shipment_id else f"status_{status}"
        buttons.append([InlineKeyboardButton(status_text, callback_data=callback_data)])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data='admin_back')])
    return InlineKeyboardMarkup(buttons)


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def get_operation_type_russian(operation_type):
    if operation_type == 'send':
        return "Отправка"
    elif operation_type == 'receive':
        return "Получение"
    return operation_type


def is_admin(user_id):
    return user_id in ADMIN_IDS


def generate_report():
    shipments = db.get_all_shipments()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'ID', 'User ID', 'Type', 'Waybill Number', 'City',
        'Status', 'Comment', 'Timestamp', 'Waybill Photo', 'Product Photo'
    ])

    for shipment in shipments:
        writer.writerow([
            shipment['id'],
            shipment['user_id'],
            shipment['type'],
            shipment['waybill_number'],
            shipment['city'],
            shipment['status'],
            shipment['comment'],
            shipment['timestamp'],
            shipment['waybill_photo'],
            shipment['product_photo']
        ])

    output.seek(0)
    return io.BytesIO(output.getvalue().encode('utf-8'))


# ===================== ОСНОВНЫЕ ОБРАБОТЧИКИ =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    logger.info(f"Пользователь {user.first_name} запустил бота")

    # Проверяем есть ли пользователь в базе
    if not db.get_user_settings(user.id):
        # Создаем запись о пользователе
        db.update_user_settings(user.id, 'first_name', user.first_name)
        if user.last_name:
            db.update_user_settings(user.id, 'last_name', user.last_name)
        if user.username:
            db.update_user_settings(user.id, 'username', user.username)

    welcome_msg = format_section(
        f"Добро пожаловать, {user.first_name}!",
        "🚛 <b>ИСКРА | Профессиональная логистическая платформа</b>\n\n"
        "Ваш универсальный инструмент для управления грузоперевозками:\n\n"
        "▫️ <b>Веб-панель</b> - полный контроль над отправлениями\n"
        "▫️ <b>Реальные уведомления</b> - мгновенные оповещения\n"
        "▫️ <b>История перевозок</b> - доступ ко всем данным\n"
        "▫️ <b>Документооборот</b> - удобное управление накладными\n\n"
        "Используйте меню ниже для работы с системой ⬇️"
    )

    await update.message.reply_text(
        welcome_msg,
        parse_mode='HTML',
        reply_markup=main_menu_keyboard(user.id)
    )
    return MAIN_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена текущего действия и возврат в главное меню"""
    user = update.message.from_user
    await update.message.reply_text(
        "❌ Действие отменено. Возврат в главное меню.",
        reply_markup=main_menu_keyboard(user.id)
    )
    context.user_data.clear()
    return MAIN_MENU


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора в главном меню"""
    text = update.message.text
    user_id = update.message.from_user.id
    context.user_data['conversation_state'] = MAIN_MENU

    if text == '📤 Отправить груз':
        return await start_send_process(update, context)
    elif text == '📥 Получить груз':
        return await start_receive_process(update, context)
    elif text == '🔍 История отправлений':
        return await show_search_menu(update, context)
    elif text == '⚙️ Настройки':
        return await show_settings(update, context)
    elif text == '👑 Админ-панель':
        return await admin_command(update, context)

    await update.message.reply_text("Пожалуйста, используйте кнопки меню ⬇️")
    return MAIN_MENU


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показ справки"""
    help_text = format_section(
        "Помощь",
        "📚 <b>Основные команды:</b>\n\n"
        "📤 <b>Отправить груз:</b>\n"
        "1. Сфотографируйте накладную\n"
        "2. Сфотографируйте товар\n"
        "3. Введите номер накладной\n"
        "4. Выберите город отправки\n\n"
        "📥 <b>Получить груз:</b>\n"
        "Аналогичный процесс с пометкой статуса\n\n"
        "🔍 <b>История отправлений:</b>\n"
        "Просмотр всех ваших отправлений с возможностью фильтрации\n\n"
        "⚙️ <b>Настройки:</b>\n"
        "Управление уведомлениями и другими параметрами\n\n"
        "👑 <b>Админ-панель:</b>\n"
        "Управление ботом для администраторов"
    )

    await update.message.reply_text(
        help_text,
        parse_mode='HTML',
        reply_markup=main_menu_keyboard(update.message.from_user.id)
    )
    return MAIN_MENU


async def show_search_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показ меню поиска"""
    context.user_data['conversation_state'] = SEARCH_MENU
    await update.message.reply_text(
        "🔍 <b>История отправлений:</b>\nВыберите вариант поиска:",
        parse_mode='HTML',
        reply_markup=search_menu_keyboard()
    )
    return SEARCH_MENU


async def handle_search_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора периода поиска с пагинацией"""
    query = update.callback_query
    await query.answer()

    try:
        user_id = query.from_user.id
        period_name = ""
        shipments = []

        # Обработка пагинации
        if query.data.startswith('page_'):
            # Получаем номер страницы из callback_data
            page = int(query.data.split('_')[1])
            context.user_data['search_page'] = page
            # Используем сохраненные данные о периоде и отправлениях
            period_name = context.user_data.get('search_period', '')
            shipments = context.user_data.get('search_shipments', [])
        else:
            # Обработка выбора периода
            context.user_data['search_page'] = 0  # Сброс на первую страницу

            if query.data == 'search_week':
                shipments = db.get_shipments_by_user(user_id, 7)
                period_name = "неделю"
            elif query.data == 'search_month':
                shipments = db.get_shipments_by_user(user_id, 30)
                period_name = "месяц"
            elif query.data == 'search_by_date':
                await query.edit_message_text("Введите дату в формате ДД.ММ.ГГГГ:")
                return SEARCH_BY_DATE
            elif query.data == 'search_by_waybill':
                await query.edit_message_text("Введите номер накладной:")
                return SEARCH_BY_WAYBILL
            elif query.data == 'back_search':
                # Изменено: используем ответ на сообщение вместо edit_message
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="Возвращаемся в главное меню...",
                    reply_markup=main_menu_keyboard(user_id),
                    parse_mode='HTML'
                )
                context.user_data['conversation_state'] = MAIN_MENU
                return MAIN_MENU

            # Сохраняем данные для пагинации
            context.user_data['search_period'] = period_name
            context.user_data['search_shipments'] = shipments

        # Настройки пагинации
        page = context.user_data.get('search_page', 0)
        items_per_page = 5
        start_index = page * items_per_page
        end_index = (page + 1) * items_per_page
        paginated_shipments = shipments[start_index:end_index]

        if not shipments:
            # Изменено: отправляем новое сообщение вместо редактирования
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"ℹ️ За последнюю {period_name} отправлений не найдено."
            )
        else:
            # Удаляем старое сообщение с кнопками
            try:
                await query.delete_message()
            except Exception:
                logger.warning("Не удалось удалить сообщение, возможно уже удалено")

            # Формируем сообщение
            message = f"🔍 Отправления за последнюю {period_name} (стр. {page + 1}):\n\n"

            for shipment in paginated_shipments:
                timestamp = datetime.strptime(shipment['timestamp'], '%Y-%m-%d %H:%M:%S')
                formatted_date = timestamp.strftime('%d.%m.%Y %H:%M')
                type_text = get_operation_type_russian(shipment['type'])
                status_text = STATUSES.get(shipment['status'], shipment['status'])

                # Исправлено: правильное получение комментария из Row
                comment = shipment['comment'] if 'comment' in shipment.keys() and shipment['comment'] else ''
                comment_line = f"   <b>Комментарий:</b> {comment}\n" if comment else ""

                message += (
                    f"▪️ <b>ID:</b> <code>{shipment['id']}</code>\n"
                    f"   <b>Тип:</b> {type_text}\n"
                    f"   <b>Город:</b> {shipment['city']}\n"
                    f"   <b>Накладная:</b> {shipment['waybill_number']}\n"
                    f"   <b>Дата:</b> {formatted_date}\n"
                    f"   <b>Статус:</b> {status_text}\n"
                    f"{comment_line}"
                    f"✏️ <b>Добавить комментарий</b> - /comment_{shipment['id']}\n"
                    f"👁️ <b>Подробнее</b> - /details_{shipment['id']}\n\n"
                )

            # Отправляем сообщение с результатами
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=message,
                parse_mode='HTML'
            )

        # Формируем клавиатуру пагинации
        total_pages = (len(shipments) // items_per_page) + 1
        buttons = []

        if total_pages > 1:
            if page > 0:
                buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f'page_{page - 1}'))
            if end_index < len(shipments):
                buttons.append(InlineKeyboardButton("Далее ➡️", callback_data=f'page_{page + 1}'))

        # Добавляем кнопку возврата
        buttons.append(InlineKeyboardButton("🔙 Назад в меню", callback_data='back_search'))

        # Отправляем клавиатуру
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"Страница {page + 1}/{total_pages}",
            reply_markup=InlineKeyboardMarkup([buttons]) if buttons else None
        )

        return SEARCH_MENU

    except Exception as e:
        logger.error(f"Ошибка при поиске отправлений: {e}", exc_info=True)
        # Изменено: отправляем новое сообщение вместо редактирования
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚠️ Произошла ошибка при поиске. Попробуйте позже."
        )
        context.user_data['conversation_state'] = MAIN_MENU
        return MAIN_MENU


async def handle_search_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка запроса поиска по дате"""
    user_input = update.message.text
    user_id = update.message.from_user.id

    try:
        datetime.strptime(user_input, '%d.%m.%Y')
        shipments = db.get_shipments_by_date(user_id, user_input)

        if not shipments:
            await update.message.reply_text(f"ℹ️ За дату {user_input} отправлений не найдено.")
        else:
            message = f"🔍 Отправления за {user_input}:\n\n"
            for shipment in shipments:
                timestamp = datetime.strptime(shipment['timestamp'], '%Y-%m-%d %H:%M:%S')
                formatted_date = timestamp.strftime('%d.%m.%Y %H:%M')
                type_text = get_operation_type_russian(shipment['type'])
                status_text = STATUSES.get(shipment['status'], shipment['status'])

                comment = shipment['comment'] if 'comment' in shipment.keys() and shipment['comment'] else ''
                comment_line = f"   <b>Комментарий:</b> {comment}\n" if comment else ""

                message += (
                    f"▪️ <b>ID:</b> <code>{shipment['id']}</code>\n"
                    f"   <b>Тип:</b> {type_text}\n"
                    f"   <b>Город:</b> {shipment['city']}\n"
                    f"   <b>Накладная:</b> {shipment['waybill_number']}\n"
                    f"   <b>Дата:</b> {formatted_date}\n"
                    f"   <b>Статус:</b> {status_text}\n"
                    f"{comment_line}"
                    f"✏️ <b>Добавить комментарий</b> - /comment_{shipment['id']}\n"
                    f"👁️ <b>Подробнее</b> - /details_{shipment['id']}\n\n"
                )

            await update.message.reply_text(message, parse_mode='HTML')

        return await show_search_menu(update, context)

    except ValueError:
        await update.message.reply_text("⚠️ Неверный формат даты. Пожалуйста, используйте формат ДД.ММ.ГГГГ.")
        return SEARCH_BY_DATE


async def handle_search_by_waybill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка запроса поиска по номеру накладной"""
    waybill_number = update.message.text
    user_id = update.message.from_user.id

    shipments = db.get_shipment_by_waybill(user_id, waybill_number)

    if not shipments:
        await update.message.reply_text(f"ℹ️ Отправлений с номером накладной '{waybill_number}' не найдено.")
    else:
        message = f"🔍 Результаты поиска для накладной {waybill_number}:\n\n"
        for shipment in shipments:
            timestamp = datetime.strptime(shipment['timestamp'], '%Y-%m-%d %H:%M:%S')
            formatted_date = timestamp.strftime('%d.%m.%Y %H:%M')
            type_text = get_operation_type_russian(shipment['type'])
            status_text = STATUSES.get(shipment['status'], shipment['status'])

            comment = shipment['comment'] if 'comment' in shipment.keys() and shipment['comment'] else ''
            comment_line = f"   <b>Комментарий:</b> {comment}\n" if comment else ""

            message += (
                f"▪️ <b>ID:</b> <code>{shipment['id']}</code>\n"
                f"   <b>Тип:</b> {type_text}\n"
                f"   <b>Город:</b> {shipment['city']}\n"
                f"   <b>Дата:</b> {formatted_date}\n"
                f"   <b>Статус:</b> {status_text}\n"
                f"{comment_line}"
                f"✏️ <b>Добавить комментарий</b> - /comment_{shipment['id']}\n"
                f"👁️ <b>Подробнее</b> - /details_{shipment['id']}\n\n"
            )

        await update.message.reply_text(message, parse_mode='HTML')

    return await show_search_menu(update, context)


async def add_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды комментария"""
    command = update.message.text.split('_')
    if len(command) > 1:
        shipment_id = command[1]
        context.user_data['current_shipment'] = shipment_id
        await update.message.reply_text("Введите ваш комментарий:")
        return ADD_COMMENT
    else:
        await update.message.reply_text("⚠️ Неверный формат команды. Используйте /comment_id")
        return SEARCH_MENU


async def save_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик сохранения комментария"""
    comment = update.message.text
    shipment_id = context.user_data.get('current_shipment')

    if not shipment_id:
        await update.message.reply_text("⚠️ Не удалось определить отправление. Попробуйте снова.")
        return await show_search_menu(update, context)

    db.update_comment(shipment_id, comment)
    await update.message.reply_text("✅ Комментарий сохранен!")
    return await show_search_menu(update, context)


async def start_send_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало процесса отправки"""
    context.user_data.clear()
    context.user_data['type'] = 'send'
    context.user_data['conversation_state'] = SEND_WAYBILL
    await update.message.reply_text(
        "📸 <b>Отправка груза:</b>\nСделайте фото накладной:",
        parse_mode='HTML'
    )
    return SEND_WAYBILL


async def handle_send_waybill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото накладной для отправки"""
    if update.message.photo:
        photo = update.message.photo[-1].file_id

        # Скачиваем фото
        file = await context.bot.get_file(photo)
        # Генерируем уникальное имя файла
        filename = f"waybill_{uuid.uuid4()}.jpg"
        full_path = os.path.join(MEDIA_ROOT, 'waybills', filename)
        await file.download_to_drive(custom_path=full_path)

        context.user_data['waybill_photo'] = f"waybills/{filename}"
        context.user_data['telegram_waybill_file_id'] = photo
        context.user_data['conversation_state'] = SEND_PRODUCT
        await update.message.reply_text("📦 Отлично! Теперь сделайте фото товара:")
        return SEND_PRODUCT

    await update.message.reply_text("⚠️ Пожалуйста, отправьте фото накладной.")
    return SEND_WAYBILL


async def handle_send_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото товара для отправки"""
    if update.message.photo:
        photo = update.message.photo[-1].file_id

        # Скачиваем фото
        file = await context.bot.get_file(photo)
        # Генерируем уникальное имя файла
        filename = f"product_{uuid.uuid4()}.jpg"
        full_path = os.path.join(MEDIA_ROOT, 'products', filename)
        await file.download_to_drive(custom_path=full_path)

        context.user_data['product_photo'] = f"products/{filename}"
        context.user_data['telegram_product_file_id'] = photo
        context.user_data['conversation_state'] = SEND_NUMBER
        await update.message.reply_text("🔢 Введите номер накладной:")
        return SEND_NUMBER

    await update.message.reply_text("⚠️ Пожалуйста, отправьте фото товара.")
    return SEND_PRODUCT


async def handle_send_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка номера накладной для отправки"""
    if update.message.text:
        context.user_data['waybill_number'] = update.message.text
        context.user_data['conversation_state'] = SEND_CITY
        await update.message.reply_text(
            "📍 Выберите город отправки:",
            reply_markup=cities_keyboard()
        )
        return SEND_CITY

    await update.message.reply_text("⚠️ Пожалуйста, введите номер накладной.")
    return SEND_NUMBER


async def start_receive_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало процесса получения"""
    context.user_data.clear()
    context.user_data['type'] = 'receive'
    context.user_data['conversation_state'] = RECEIVE_WAYBILL
    await update.message.reply_text(
        "📋 <b>Получение груза:</b>\nСтатус: Получение\n\n"
        "📸 Сделайте фото накладной:",
        parse_mode='HTML'
    )
    return RECEIVE_WAYBILL


async def handle_receive_waybill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото накладной для получения"""
    if update.message.photo:
        photo = update.message.photo[-1].file_id

        # Скачиваем фото
        file = await context.bot.get_file(photo)
        # Генерируем уникальное имя файла
        filename = f"waybill_{uuid.uuid4()}.jpg"
        full_path = os.path.join(MEDIA_ROOT, 'waybills', filename)
        await file.download_to_drive(custom_path=full_path)

        context.user_data['waybill_photo'] = f"waybills/{filename}"
        context.user_data['telegram_waybill_file_id'] = photo
        context.user_data['conversation_state'] = RECEIVE_PRODUCT
        await update.message.reply_text("📦 Отлично! Теперь сделайте фото товара:")
        return RECEIVE_PRODUCT

    await update.message.reply_text("⚠️ Пожалуйста, отправьте фото накладной.")
    return RECEIVE_WAYBILL


async def handle_receive_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото товара для получения"""
    if update.message.photo:
        photo = update.message.photo[-1].file_id

        # Скачиваем фото
        file = await context.bot.get_file(photo)
        # Генерируем уникальное имя файла
        filename = f"product_{uuid.uuid4()}.jpg"
        full_path = os.path.join(MEDIA_ROOT, 'products', filename)
        await file.download_to_drive(custom_path=full_path)

        context.user_data['product_photo'] = f"products/{filename}"
        context.user_data['telegram_product_file_id'] = photo
        context.user_data['conversation_state'] = RECEIVE_NUMBER
        await update.message.reply_text("🔢 Введите номер накладной:")
        return RECEIVE_NUMBER

    await update.message.reply_text("⚠️ Пожалуйста, отправьте фото товара.")
    return RECEIVE_PRODUCT


async def handle_receive_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка номера накладной для получения"""
    if update.message.text:
        context.user_data['waybill_number'] = update.message.text
        context.user_data['conversation_state'] = RECEIVE_CITY
        await update.message.reply_text(
            "📍 Выберите город получения:",
            reply_markup=cities_keyboard()
        )
        return RECEIVE_CITY

    await update.message.reply_text("⚠️ Пожалуйста, введите номер накладной.")
    return RECEIVE_NUMBER


async def handle_city_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора города с отправкой фото и текста в одном сообщении"""
    query = update.callback_query
    await query.answer()

    try:
        # Проверка наличия необходимых данных
        if 'waybill_photo' not in context.user_data or 'product_photo' not in context.user_data:
            await query.edit_message_text("⚠️ Отсутствуют фото! Начните заново.")
            context.user_data.clear()
            return await start(update, context)

        operation_type = context.user_data['type']
        city_map = {
            'moscow': 'Москва',
            'spb': 'Санкт-Петербург',
            'novosibirsk': 'Новосибирск'
        }
        city_name = city_map.get(query.data, query.data)
        shipment_id = str(uuid.uuid4())[:8].upper()
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M")

        data = (
            shipment_id,
            query.from_user.id,
            operation_type,
            context.user_data['waybill_photo'],  # путь к файлу
            context.user_data['product_photo'],  # путь к файлу
            context.user_data['waybill_number'],
            city_name,
            "",  # Пустой комментарий при создании
            context.user_data['telegram_waybill_file_id'],  # file_id
            context.user_data['telegram_product_file_id']  # file_id
        )

        db.save_shipment(data)

        if operation_type == 'send':
            operation_name = "Отправка"
        elif operation_type == 'receive':
            operation_name = "Получение"
        else:
            operation_name = operation_type

        message_text = (
            f"✅ <b>Груз зарегистрирован!</b>\n\n"
            f"▪️ ID операции: <code>{shipment_id}</code>\n"
            f"▪️ Тип: {operation_name}\n"
            f"▪️ Город: {city_name}\n"
            f"▪️ Накладная: {context.user_data['waybill_number']}\n"
            f"▪️ Дата и время: {current_time}\n"
            f"▪️ Статус: {STATUSES['created']}\n\n"
            "Данные сохранены в системе."
        )

        # Отправляем сообщение с информацией
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=message_text,
            parse_mode='HTML'
        )

        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=message_text,
                parse_mode='HTML'
            )
        except Exception as group_error:
            logger.error(f"Ошибка при отправке в группу: {group_error}")

        await query.edit_message_reply_markup(reply_markup=None)

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Выберите следующее действие:",
            reply_markup=main_menu_keyboard(query.from_user.id),
            parse_mode='HTML'
        )

        context.user_data.clear()
        context.user_data['conversation_state'] = MAIN_MENU
        return MAIN_MENU

    except Exception as e:
        logger.error(f"Ошибка при обработке города: {e}", exc_info=True)
        try:
            await query.edit_message_text("⚠️ Произошла ошибка при обработке данных. Возврат в главное меню.")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Выберите действие:",
                reply_markup=main_menu_keyboard(query.from_user.id)
            )
        except Exception as e2:
            logger.error(f"Ошибка при обработке ошибки: {e2}")
        context.user_data.clear()
        context.user_data['conversation_state'] = MAIN_MENU
        return MAIN_MENU


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показ меню настроек"""
    context.user_data['conversation_state'] = SETTINGS_MENU
    user_id = update.message.from_user.id
    await update.message.reply_text(
        "⚙️ <b>Настройки:</b>",
        parse_mode='HTML',
        reply_markup=settings_menu_keyboard(user_id)
    )
    return SETTINGS_MENU


async def handle_settings_menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора в меню настроек"""
    text = update.message.text
    user_id = update.message.from_user.id

    if text == '🔔 Уведомления':
        return await notification_settings(update, context)
    elif text == 'ℹ️ О боте':
        about_text = (
            "ℹ️ <b>Информация о боте:</b>\n\n"
            "▫️ Версия бота: <b>0.0.2</b>\n"
            "▫️ Дата сборки: <b>14.06.2025</b>\n"
            "▫️ Разработчик: <b>Pavel Sedov</b>\n\n"
            "Бот предназначен для управления грузоперевозками."
        )
        await update.message.reply_text(
            about_text,
            parse_mode='HTML',
            reply_markup=settings_menu_keyboard(user_id)
        )
        return SETTINGS_MENU
    elif text == '💾 Скачать базу SQLite':
        if not is_admin(user_id):
            await update.message.reply_text("❌ У вас нет прав доступа.")
            return SETTINGS_MENU

        # Создаем временную копию базы данных
        temp_db_name = f"cargo_bot_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copyfile(DB_NAME, temp_db_name)

        # Отправляем файл
        await update.message.reply_document(
            document=open(temp_db_name, 'rb'),
            filename=temp_db_name,
            caption="💾 База данных SQLite"
        )

        # Удаляем временный файл
        os.remove(temp_db_name)
        return SETTINGS_MENU
    elif text == '📊 Скачать отчет Excel':
        if not is_admin(user_id):
            await update.message.reply_text("❌ У вас нет прав доступа.")
            return SETTINGS_MENU

        report = generate_report()
        report_filename = f"cargo_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        await update.message.reply_document(
            document=report,
            filename=report_filename,
            caption="📊 Отчет по отправлениям (CSV)"
        )
        return SETTINGS_MENU
    elif text == '👑 Админ-панель':
        return await admin_command(update, context)
    elif text == 'ℹ️ Помощь':
        return await show_help(update, context)
    elif text == '🔙 Назад':
        await update.message.reply_text(
            "Возвращаемся в главное меню...",
            reply_markup=main_menu_keyboard(user_id)
        )
        context.user_data['conversation_state'] = MAIN_MENU
        return MAIN_MENU

    await update.message.reply_text("Пожалуйста, используйте кнопки меню ⬇️")
    return SETTINGS_MENU


async def notification_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Настройки уведомлений"""
    user_id = update.message.from_user.id
    # Убираем основную клавиатуру
    await update.message.reply_text(
        "🔔 <b>Настройки уведомлений</b>",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardRemove()
    )
    # Отправляем инлайн-клавиатуру
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=notification_settings_keyboard(user_id)
    )
    return NOTIFICATION_SETTINGS


async def handle_notification_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Переключение уведомлений с обработкой кнопки Назад"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    # Обработка кнопки "Назад"
    if query.data == 'back_to_settings':
        await query.edit_message_text("Возвращаемся в настройки...")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚙️ <b>Настройки:</b>",
            parse_mode='HTML',
            reply_markup=settings_menu_keyboard(user_id)
        )
        return SETTINGS_MENU

    # Обработка включения/выключения уведомлений
    if query.data == 'notif_on':
        db.update_user_settings(user_id, 'notifications', 1)
        status = "включены"
    elif query.data == 'notif_off':
        db.update_user_settings(user_id, 'notifications', 0)
        status = "выключены"
    else:
        return NOTIFICATION_SETTINGS

    # Обновляем сообщение с новым состоянием
    await query.edit_message_text(
        f"✅ Уведомления {status}!\n"
        "Вы будете получать уведомления об изменении статуса ваших отправлений.",
        parse_mode='HTML',
        reply_markup=notification_settings_keyboard(user_id)
    )
    return NOTIFICATION_SETTINGS


async def shipment_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показ деталей отправления"""
    if update.message:
        command = update.message.text.split('_')
        if len(command) > 1:
            shipment_id = command[1]
        else:
            await update.message.reply_text("⚠️ Неверный формат команды. Используйте /details_id")
            return SEARCH_MENU
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        shipment_id = query.data.split('_')[1]
    else:
        await update.message.reply_text("⚠️ Ошибка при обработке команды")
        return MAIN_MENU

    shipment = db.get_shipment_by_id(shipment_id)
    if not shipment:
        await update.message.reply_text("❌ Отправление не найдено")
        return MAIN_MENU

    shipment_info = format_info([
        ("ID", f"<code>{shipment['id']}</code>"),
        ("Тип", get_operation_type_russian(shipment['type'])),
        ("Статус", STATUSES.get(shipment['status'], shipment['status'])),
        ("Город", shipment['city']),
        ("Накладная", shipment['waybill_number']),
        ("Дата", datetime.strptime(shipment['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')),
        ("Комментарий", shipment['comment'] or "Отсутствует")
    ])

    message = format_section("ДЕТАЛИ ОТПРАВЛЕНИЯ", shipment_info)

    # Отправляем информацию
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=message,
        parse_mode='HTML'
    )

    # Кнопки действий
    user_id = update.message.from_user.id if update.message else update.callback_query.from_user.id
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите действие:",
        reply_markup=shipment_actions_keyboard(shipment_id, user_id)
    )
    context.user_data['current_shipment_id'] = shipment_id
    return MAIN_MENU


async def edit_shipment_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало редактирования отправления"""
    query = update.callback_query
    await query.answer()

    shipment_id = query.data.split('_')[1]
    context.user_data['editing_shipment'] = shipment_id

    # Предлагаем выбрать, что редактировать
    buttons = [
        [InlineKeyboardButton("✏️ Комментарий", callback_data='edit_comment')],
        [InlineKeyboardButton("📷 Фото товара", callback_data='edit_product_photo')],
        [InlineKeyboardButton("📷 Фото накладной", callback_data='edit_waybill_photo')],
        [InlineKeyboardButton("🔙 Назад", callback_data=f'details_{shipment_id}')]
    ]

    await query.edit_message_text(
        "✏️ <b>Редактирование отправления</b>\nВыберите что изменить:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return EDIT_SHIPMENT


async def handle_edit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора поля для редактирования"""
    query = update.callback_query
    await query.answer()

    choice = query.data
    shipment_id = context.user_data['editing_shipment']

    if choice == 'edit_comment':
        await query.edit_message_text("Введите новый комментарий:")
        context.user_data['edit_field'] = 'comment'
        return ADD_COMMENT

    elif choice == 'edit_product_photo':
        await query.edit_message_text("Отправьте новое фото товара:")
        context.user_data['edit_field'] = 'product_photo'
        return RECEIVE_PRODUCT

    elif choice == 'edit_waybill_photo':
        await query.edit_message_text("Отправьте новое фото накладной:")
        context.user_data['edit_field'] = 'waybill_photo'
        return RECEIVE_WAYBILL

    elif choice.startswith('details_'):
        return await shipment_details(update, context)


async def save_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение изменений"""
    shipment_id = context.user_data['editing_shipment']
    field = context.user_data['edit_field']

    if field == 'comment':
        value = update.message.text
    elif field in ['product_photo', 'waybill_photo']:
        value = update.message.photo[-1].file_id

    db.update_shipment(shipment_id, field, value)

    await update.message.reply_text("✅ Изменения сохранены!")
    return await shipment_details(update, context)


# ===================== ОБРАБОТЧИКИ КНОПОК =====================
async def handle_back_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок 'Назад'"""
    query = update.callback_query
    await query.answer()

    logger.info(f"Обработка кнопки Назад: {query.data} от пользователя {query.from_user.id}")

    if query.data == 'back_details':
        # Возврат из деталей отправления в меню поиска
        await show_search_menu(update, context)
        return SEARCH_MENU

    elif query.data == 'back_search':
        # Возврат из меню поиска в главное меню
        await query.edit_message_text("Возвращаемся в главное меню...")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Выберите действие:",
            reply_markup=main_menu_keyboard(query.from_user.id)
        )
        context.user_data['conversation_state'] = MAIN_MENU
        return MAIN_MENU

    # Для админ-панели
    elif query.data == 'admin_back':
        await query.edit_message_text("Возвращаемся в главное меню...")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Выберите действие:",
            reply_markup=main_menu_keyboard(query.from_user.id)
        )
        return MAIN_MENU


async def handle_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки 'Избранное'"""
    query = update.callback_query
    await query.answer()

    shipment_id = query.data.split('_')[1]
    user_id = query.from_user.id

    # Переключаем статус избранного
    action = db.toggle_favorite(shipment_id, user_id)

    # Формируем сообщение в зависимости от действия
    if action == "added":
        message = "✅ Добавлено в избранное"
    else:
        message = "❌ Удалено из избранного"

    # Обновляем клавиатуру
    is_favorite = db.get_favorite_status(shipment_id, user_id)
    favorite_text = "❌ Из избранного" if is_favorite else "⭐ В избранное"

    # Создаем обновленную клавиатуру
    buttons = [
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f'edit_{shipment_id}')],
        [InlineKeyboardButton(favorite_text, callback_data=f'favorite_{shipment_id}')],
        [InlineKeyboardButton("🔄 Статус доставки", callback_data=f'status_{shipment_id}')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_details')]
    ]

    # Обновляем сообщение
    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    # Отправляем подтверждение
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=message
    )

    # Возвращаемся в детали отправления
    return await shipment_details(update, context)


async def handle_status_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки 'Статус доставки' для пользователей"""
    query = update.callback_query
    await query.answer()

    shipment_id = query.data.split('_')[1]
    context.user_data['current_shipment'] = shipment_id

    # Сохраняем ID сообщения для последующего редактирования
    context.user_data['status_message_id'] = query.message.message_id

    # Показываем клавиатуру со статусами
    await context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        text="Выберите новый статус:",
        reply_markup=status_keyboard(shipment_id)
    )
    return MAIN_MENU


async def handle_user_status_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора статуса пользователем"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split('_')
    if len(parts) < 3:
        await query.edit_message_text("❌ Ошибка. Попробуйте снова.")
        return MAIN_MENU

    status = parts[1]
    shipment_id = parts[2]
    user_id = query.from_user.id

    # Проверяем принадлежит ли отправление пользователю
    shipment = db.get_shipment_by_id(shipment_id)
    if not shipment or shipment['user_id'] != user_id:
        await query.edit_message_text("❌ Вы не можете изменить статус этого отправления.")
        return MAIN_MENU

    # Обновляем статус
    db.update_status(shipment_id, status)
    status_text = STATUSES.get(status, status)

    # Удаляем сообщение с выбором статуса
    await context.bot.delete_message(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id
    )

    # Показываем обновленные детали отправления
    return await shipment_details(update, context)


async def back_to_search_menu_from_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат из деталей отправления в меню поиска"""
    query = update.callback_query
    await query.answer()

    # Удаляем сообщение с кнопками действий
    try:
        await context.bot.delete_message(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id
        )
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения: {e}")

    # Показываем меню поиска
    await show_search_menu(update, context)
    return SEARCH_MENU


# ===================== АДМИН-ПАНЕЛЬ =====================
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /admin"""
    user = update.message.from_user

    if not is_admin(user.id):
        await update.message.reply_text("❌ У вас нет прав доступа к этой команде.")
        return MAIN_MENU

    context.user_data['conversation_state'] = ADMIN_PANEL
    await update.message.reply_text(
        "👑 <b>Админ-панель</b>\nВыберите действие:",
        parse_mode='HTML',
        reply_markup=admin_menu_keyboard()
    )
    return ADMIN_PANEL


async def handle_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора в админ-панели"""
    text = update.message.text
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ У вас нет прав доступа.")
        return MAIN_MENU

    if text == '📊 Скачать отчет':
        report = generate_report()
        report_filename = f"cargo_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        await update.message.reply_document(
            document=report,
            filename=report_filename,
            caption="📊 Отчет по отправлениям"
        )
        return ADMIN_PANEL

    elif text == '📝 Все отправления':
        shipments = db.get_all_shipments()

        if not shipments:
            await update.message.reply_text("ℹ️ Нет данных об отправлениях.")
            return ADMIN_PANEL

        message = "📝 <b>Все отправления:</b>\n\n"
        for shipment in shipments[:10]:  # Ограничим вывод до 10 последних
            timestamp = datetime.strptime(shipment['timestamp'], '%Y-%m-%d %H:%M:%S')
            formatted_date = timestamp.strftime('%d.%m.%Y %H:%M')
            status_text = STATUSES.get(shipment['status'], shipment['status'])

            message += (
                f"▪️ <b>ID:</b> <code>{shipment['id']}</code>\n"
                f"   <b>Пользователь:</b> {shipment['user_id']}\n"
                f"   <b>Тип:</b> {get_operation_type_russian(shipment['type'])}\n"
                f"   <b>Статус:</b> {status_text}\n"
                f"   <b>Дата:</b> {formatted_date}\n\n"
            )

        if len(shipments) > 10:
            message += f"ℹ️ Показано 10 из {len(shipments)} записей\n"

        await update.message.reply_text(
            text=message,
            parse_mode='HTML'
        )
        return ADMIN_PANEL

    elif text == '🔄 Изменить статус':
        context.user_data['conversation_state'] = CHANGE_STATUS
        await update.message.reply_text(
            "✏️ Введите ID отправления для изменения статуса:",
            parse_mode='HTML'
        )
        return CHANGE_STATUS

    elif text == '✉️ Рассылка':
        context.user_data['conversation_state'] = BROADCAST_MESSAGE
        await update.message.reply_text(
            "✉️ Введите сообщение для рассылки всем пользователям:",
            parse_mode='HTML'
        )
        return BROADCAST_MESSAGE

    elif text == '🔙 Назад в меню':
        await update.message.reply_text(
            "Возвращаемся в главное меню...",
            reply_markup=main_menu_keyboard(user_id)
        )
        context.user_data['conversation_state'] = MAIN_MENU
        return MAIN_MENU

    await update.message.reply_text("Пожалуйста, используйте кнопки меню ⬇️")
    return ADMIN_PANEL


async def handle_change_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода ID отправления для изменения статуса"""
    shipment_id = update.message.text.strip()
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ У вас нет прав доступа.")
        return MAIN_MENU

    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,))
        shipment = c.fetchone()

    if not shipment:
        await update.message.reply_text("ℹ️ Отправление с таким ID не найдено. Попробуйте еще раз:")
        return CHANGE_STATUS

    context.user_data['current_shipment'] = shipment_id
    await update.message.reply_text(
        f"✏️ Выберите новый статус для отправления <code>{shipment_id}</code>:",
        parse_mode='HTML',
        reply_markup=status_keyboard(shipment_id)
    )
    return ADMIN_PANEL


async def handle_status_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора статуса"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ У вас нет прав доступа.")
        return ADMIN_PANEL

    parts = query.data.split('_')
    if len(parts) < 3:
        await query.edit_message_text("❌ Ошибка. Попробуйте снова.")
        return ADMIN_PANEL

    status = parts[1]
    shipment_id = parts[2]

    db.update_status(shipment_id, status)
    status_text = STATUSES.get(status, status)

    await query.edit_message_text(
        f"✅ Статус отправления <code>{shipment_id}</code> изменен на: {status_text}",
        parse_mode='HTML'
    )

    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT user_id FROM shipments WHERE id = ?", (shipment_id,))
            shipment = c.fetchone()

        if shipment:
            user_id = shipment['user_id']
            await context.bot.send_message(
                chat_id=user_id,
                text=f"ℹ️ Статус вашего отправления <code>{shipment_id}</code> изменен на: {status_text}",
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Ошибка уведомления пользователя: {e}")

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Выберите действие:",
        reply_markup=admin_menu_keyboard(),
        parse_mode='HTML'
    )
    return ADMIN_PANEL


async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка рассылки сообщений"""
    message_text = update.message.text
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ У вас нет прав доступа.")
        return MAIN_MENU

    user_ids = db.get_all_users()
    success = 0
    failed = 0

    for uid in user_ids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 Сообщение от администратора:\n\n{message_text}"
            )
            success += 1
        except Exception as e:
            logger.error(f"Ошибка рассылки пользователю {uid}: {e}")
            failed += 1

    await update.message.reply_text(
        f"✅ Рассылка завершена:\n"
        f"• Успешно: {success}\n"
        f"• Не удалось: {failed}\n\n"
        f"Текст сообщения:\n{message_text}"
    )

    await update.message.reply_text(
        "Выберите следующее действие:",
        reply_markup=admin_menu_keyboard(),
        parse_mode='HTML'
    )
    return ADMIN_PANEL


async def handle_invalid_input(update: Update, context: CallbackContext) -> int:
    """Обработчик неправильных сообщений"""
    try:
        message = update.effective_message
        chat_id = update.effective_chat.id
        current_state = context.user_data.get('conversation_state', MAIN_MENU)

        error_messages = {
            MAIN_MENU: "Пожалуйста, используйте кнопки меню ⬇️",
            SEARCH_MENU: "Пожалуйста, используйте кнопки меню поиска 🔍",
            SETTINGS_MENU: "Пожалуйста, используйте кнопки настроек ⚙️",
            SEND_WAYBILL: "Пожалуйста, отправьте фото накладной 📄",
            SEND_PRODUCT: "Пожалуйста, отправьте фото товара 📦",
            SEND_NUMBER: "Пожалуйста, введите номер накладной 🔢",
            SEND_CITY: "Пожалуйста, выберите город из списка 🏙️",
            RECEIVE_WAYBILL: "Пожалуйста, отправьте фото накладной 📄",
            RECEIVE_PRODUCT: "Пожалуйста, отправьте фото товара 📦",
            RECEIVE_NUMBER: "Пожалуйста, введите номер накладной 🔢",
            RECEIVE_CITY: "Пожалуйста, выберите город из списка 🏙️",
            SEARCH_BY_DATE: "Пожалуйста, введите дату в формате ДД.ММ.ГГГГ",
            SEARCH_BY_WAYBILL: "Пожалуйста, введите номер накладной",
            ADD_COMMENT: "Пожалуйста, введите текст комментария",
            NOTIFICATION_SETTINGS: "Пожалуйста, используйте кнопки настроек уведомлений",
            ADMIN_PANEL: "Пожалуйста, используйте кнопки админ-панели 👑"
        }

        text = error_messages.get(current_state, "Пожалуйста, используйте команду /start для начала работы")

        # Добавляем обработку неожиданных состояний
        if current_state not in error_messages:
            text = "⚠️ Непредвиденное состояние. Возврат в главное меню."
            context.user_data.clear()
            current_state = MAIN_MENU

        if current_state == MAIN_MENU:
            await message.reply_text(text, reply_markup=main_menu_keyboard(update.message.from_user.id))
        elif current_state == SEARCH_MENU:
            await message.reply_text(text, reply_markup=search_menu_keyboard())
        elif current_state == SETTINGS_MENU:
            await message.reply_text(text, reply_markup=settings_menu_keyboard(update.message.from_user.id))
        elif current_state == ADMIN_PANEL:
            await message.reply_text(text, reply_markup=admin_menu_keyboard())
        else:
            await message.reply_text(text)

        return current_state

    except Exception as e:
        logger.error(f"Ошибка в handle_invalid_input: {e}", exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Произошла непредвиденная ошибка. Пожалуйста, попробуйте снова.",
                reply_markup=main_menu_keyboard(update.message.from_user.id)
            )
        except Exception as e2:
            logger.error(f"Двойная ошибка в handle_invalid_input: {e2}")

        context.user_data['conversation_state'] = MAIN_MENU
        return MAIN_MENU


# ===================== ЗАПУСК БОТА =====================
def main() -> None:
    try:
        # Создаем директорию для бэкапов
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

        # Создаем приложение
        application = (
            Application.builder()
            .token(TOKEN)
            .concurrent_updates(True)
            .build()
        )

        # Настройка JobQueue
        if application.job_queue:
            job_queue = application.job_queue
            moscow_tz = pytz.timezone('Europe/Moscow')
            backup_time = time(hour=15, minute=0, second=0, tzinfo=moscow_tz)
            job_queue.run_daily(
                daily_backup,
                time=backup_time,
                days=(0, 1, 2, 3, 4, 5, 6),
                name="daily_backup"
            )
            logger.info("Регулярные бэкапы настроены")
        else:
            logger.warning("JobQueue недоступен! Регулярные бэкапы отключены.")

        # Основной обработчик
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                MAIN_MENU: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
                    CommandHandler('cancel', cancel),
                    # Обработка выбора статуса в главном меню
                    CallbackQueryHandler(handle_user_status_selection, pattern=r'^status_\w+_\w+'),
                    # Обработка кнопки "Назад" в деталях отправления
                    CallbackQueryHandler(back_to_search_menu_from_details, pattern=r'^back_details$')
                ],
                SEARCH_MENU: [
                    CallbackQueryHandler(handle_search_period),
                    MessageHandler(filters.Regex(r'^/comment_\w+'), add_comment),
                    MessageHandler(filters.Regex(r'^/details_\w+'), shipment_details)
                ],
                SETTINGS_MENU: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_settings_menu_choice)
                ],
                SEND_WAYBILL: [
                    MessageHandler(filters.PHOTO, handle_send_waybill),
                    CommandHandler('cancel', cancel)
                ],
                SEND_PRODUCT: [
                    MessageHandler(filters.PHOTO, handle_send_product),
                    CommandHandler('cancel', cancel)
                ],
                SEND_NUMBER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_send_number),
                    CommandHandler('cancel', cancel)
                ],
                SEND_CITY: [
                    CallbackQueryHandler(handle_city_selection),
                    CommandHandler('cancel', cancel)
                ],
                RECEIVE_WAYBILL: [
                    MessageHandler(filters.PHOTO, handle_receive_waybill),
                    CommandHandler('cancel', cancel)
                ],
                RECEIVE_PRODUCT: [
                    MessageHandler(filters.PHOTO, handle_receive_product),
                    CommandHandler('cancel', cancel)
                ],
                RECEIVE_NUMBER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_receive_number),
                    CommandHandler('cancel', cancel)
                ],
                RECEIVE_CITY: [
                    CallbackQueryHandler(handle_city_selection),
                    CommandHandler('cancel', cancel)
                ],
                SEARCH_BY_DATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_by_date),
                    CommandHandler('cancel', cancel)
                ],
                SEARCH_BY_WAYBILL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_by_waybill),
                    CommandHandler('cancel', cancel)
                ],
                ADD_COMMENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment),
                    CommandHandler('cancel', cancel)
                ],
                ADMIN_PANEL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_panel),
                    CommandHandler('cancel', cancel)
                ],
                CHANGE_STATUS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_change_status),
                    CommandHandler('cancel', cancel),
                    CallbackQueryHandler(handle_status_selection, pattern=r'^status_\w+_\w+')
                ],
                BROADCAST_MESSAGE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_message),
                    CommandHandler('cancel', cancel)
                ],
                EDIT_SHIPMENT: [
                    CallbackQueryHandler(handle_edit_choice)
                ],
                NOTIFICATION_SETTINGS: [
                    CallbackQueryHandler(handle_notification_toggle)
                ]
            },
            fallbacks=[CommandHandler('cancel', cancel)],
            name="main_conversation",
            allow_reentry=True
        )
        application.add_handler(conv_handler)

        # Обработчики для команд, не входящих в основной ConversationHandler
        application.add_handler(CommandHandler("notifications", notification_settings))
        application.add_handler(CommandHandler("admin", admin_command))

        # Обработчики для callback-запросов
        application.add_handler(CallbackQueryHandler(
            shipment_details,
            pattern=r'^details_'
        ))
        application.add_handler(CallbackQueryHandler(
            edit_shipment_start,
            pattern=r'^edit_'
        ))
        application.add_handler(CallbackQueryHandler(
            handle_favorite,
            pattern=r'^favorite_'
        ))
        application.add_handler(CallbackQueryHandler(
            handle_status_change,
            pattern=r'^status_'
        ))
        # Добавляем обработчик для пагинации
        application.add_handler(CallbackQueryHandler(
            handle_search_period,
            pattern=r'^page_'
        ))
        # Добавляем обработчик для кнопки "Назад" в деталях
        application.add_handler(CallbackQueryHandler(
            back_to_search_menu_from_details,
            pattern=r'^back_details$'
        ))

        # Специальный обработчик для уведомлений
        application.add_handler(CallbackQueryHandler(
            handle_notification_toggle,
            pattern=r'^notif_|back_to_settings'
        ))

        # Обработчик для нераспознанных сообщений
        application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_invalid_input))

        logger.info("Запуск бота...")
        application.run_polling()

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
    finally:
        logger.info("Бот завершил работу")


if __name__ == '__main__':
    main()