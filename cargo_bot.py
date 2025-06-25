import os
import uuid
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
from asgiref.sync import sync_to_async

# Инициализация Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'logistic_admin.settings')
import django

django.setup()

from core.models import Shipment, User

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
TOKEN = "7833491235:AAEeP3bJWIgWxAjdMhYv6zvTE6dIbe7Ob2U"
MEDIA_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'media')
os.makedirs(os.path.join(MEDIA_ROOT, 'waybills'), exist_ok=True)
os.makedirs(os.path.join(MEDIA_ROOT, 'products'), exist_ok=True)

# Состояния диалога
(
    MAIN_MENU, TYPE_SELECTION, WAYBILL_NUMBER, CITY_SELECTION,
    WEIGHT_INPUT, COMMENT_INPUT, WAYBILL_PHOTO, PRODUCT_PHOTO
) = range(8)


def generate_short_id():
    return str(uuid.uuid4().int)[:6].upper()


@sync_to_async
def get_or_create_user(user_id, first_name, last_name):
    return User.objects.get_or_create(
        username=str(user_id),
        defaults={
            'first_name': first_name or '',
            'last_name': last_name or '',
        }
    )


@sync_to_async
def create_shipment(user_id, shipment_data):
    user = User.objects.get(id=user_id)
    return Shipment.objects.create(
        id=generate_short_id(),
        user=user,
        type=shipment_data['type'],
        waybill_number=shipment_data['waybill_number'],
        city=shipment_data['city'],
        weight=shipment_data.get('weight'),
        comment=shipment_data.get('comment'),
        status='created',
        waybill_photo=shipment_data['waybill_photo'],
        product_photo=shipment_data['product_photo'],
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    logger.info(f"Пользователь {user.first_name} запустил бота")

    user_obj, created = await get_or_create_user(
        user.id,
        user.first_name,
        user.last_name
    )

    context.user_data['user_id'] = user_obj.id
    await update.message.reply_text(
        "🚛 Добро пожаловать в бот для управления грузоперевозками!",
        reply_markup=ReplyKeyboardRemove()
    )
    return await ask_shipment_type(update, context)


async def ask_shipment_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = ReplyKeyboardMarkup([
        ['📤 Отправка', '📥 Получение'],
        ['🔄 Перемещение']
    ], resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        "Тип отправки\nВыберите тип:",
        reply_markup=keyboard
    )
    return TYPE_SELECTION


async def handle_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    type_map = {
        '📤 Отправка': 'send',
        '📥 Получение': 'receive',
        '🔄 Перемещение': 'transfer'
    }

    if text not in type_map:
        await update.message.reply_text("Пожалуйста, выберите тип из предложенных вариантов")
        return await ask_shipment_type(update, context)

    context.user_data['shipment_data'] = {'type': type_map[text]}
    return await ask_waybill_number(update, context)


async def ask_waybill_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Номер накладной\nВведите номер накладной:",
        reply_markup=ReplyKeyboardRemove()
    )
    return WAYBILL_NUMBER


async def handle_waybill_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.text:
        await update.message.reply_text("Пожалуйста, введите номер накладной")
        return await ask_waybill_number(update, context)

    context.user_data['shipment_data']['waybill_number'] = update.message.text.strip()
    return await ask_city(update, context)


async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = ReplyKeyboardMarkup([
        ['Москва', 'Санкт-Петербург'],
        ['Новосибирск', 'Екатеринбург'],
        ['Другой город']
    ], resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        "Город\nВыберите город:",
        reply_markup=keyboard
    )
    return CITY_SELECTION


async def handle_city_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    if city == 'Другой город':
        await update.message.reply_text(
            "Введите название города:",
            reply_markup=ReplyKeyboardRemove()
        )
        return CITY_SELECTION

    context.user_data['shipment_data']['city'] = city
    return await ask_weight(update, context)


async def ask_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Вес (кг)\nВведите вес в килограммах (например: 12.5):",
        reply_markup=ReplyKeyboardRemove()
    )
    return WEIGHT_INPUT


async def handle_weight_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        weight = float(update.message.text)
        context.user_data['shipment_data']['weight'] = weight
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число (например: 12.5)")
        return await ask_weight(update, context)

    return await ask_comment(update, context)


async def ask_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Комментарий\nВведите дополнительную информацию (или отправьте '-' чтобы пропустить):",
        reply_markup=ReplyKeyboardRemove()
    )
    return COMMENT_INPUT


async def handle_comment_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    comment = update.message.text
    if comment != '-':
        context.user_data['shipment_data']['comment'] = comment

    return await ask_waybill_photo(update, context)


async def ask_waybill_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Фото накладной\nОтправьте фото накладной (JPG/PNG, макс. 5MB):",
        reply_markup=ReplyKeyboardRemove()
    )
    return WAYBILL_PHOTO


async def handle_waybill_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте фото накладной")
        return await ask_waybill_photo(update, context)

    photo = update.message.photo[-1]
    filename = f"waybill_{generate_short_id()}.jpg"
    rel_path = os.path.join('waybills', filename)
    full_path = os.path.join(MEDIA_ROOT, rel_path)

    file = await photo.get_file()
    await file.download_to_drive(full_path)

    context.user_data['shipment_data']['waybill_photo'] = rel_path
    return await ask_product_photo(update, context)


async def ask_product_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Фото товара\nОтправьте фото товара (JPG/PNG, макс. 5MB):",
        reply_markup=ReplyKeyboardRemove()
    )
    return PRODUCT_PHOTO


async def handle_product_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте фото товара")
        return await ask_product_photo(update, context)

    photo = update.message.photo[-1]
    filename = f"product_{generate_short_id()}.jpg"
    rel_path = os.path.join('products', filename)
    full_path = os.path.join(MEDIA_ROOT, rel_path)

    file = await photo.get_file()
    await file.download_to_drive(full_path)

    context.user_data['shipment_data']['product_photo'] = rel_path

    # Сохраняем отправку
    try:
        shipment = await create_shipment(
            context.user_data['user_id'],
            context.user_data['shipment_data']
        )

        await update.message.reply_text(
            f"✅ Отправка успешно зарегистрирована!\n"
            f"ID: <code>{shipment.id}</code>\n"
            f"Тип: {shipment.get_type_display()}\n"
            f"Накладная: {shipment.waybill_number}\n"
            f"Город: {shipment.city}\n"
            f"Вес: {shipment.weight} кг",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )

    except Exception as e:
        logger.error(f"Ошибка сохранения: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Произошла ошибка при сохранении. Попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )

    context.user_data.pop('shipment_data', None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Действие отменено",
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END


def main() -> None:
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            TYPE_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_type_selection)],
            WAYBILL_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_waybill_number)],
            CITY_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city_selection)],
            WEIGHT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_weight_input)],
            COMMENT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment_input)],
            WAYBILL_PHOTO: [MessageHandler(filters.PHOTO, handle_waybill_photo)],
            PRODUCT_PHOTO: [MessageHandler(filters.PHOTO, handle_product_photo)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )

    application.add_handler(conv_handler)

    logger.info("Бот запущен")
    application.run_polling()


if __name__ == '__main__':
    main()