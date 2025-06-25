import os
import uuid
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackContext
)
from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist
from datetime import datetime

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
GROUP_ID = -1002580459963
MEDIA_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'media')
os.makedirs(os.path.join(MEDIA_ROOT, 'waybills'), exist_ok=True)
os.makedirs(os.path.join(MEDIA_ROOT, 'products'), exist_ok=True)

# Состояния диалога
(
    MAIN_MENU, TYPE_SELECTION, WAYBILL_NUMBER, CITY_SELECTION,
    WEIGHT_INPUT, COMMENT_INPUT, WAYBILL_PHOTO, PRODUCT_PHOTO,
    SETTINGS_MENU
) = range(9)

# Статусы для уведомлений
STATUS_EMOJI = {
    'created': '📝',
    'processing': '🔄',
    'transit': '🚚',
    'delivered': '✅',
    'problem': '⚠️'
}


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
    shipment = Shipment.objects.create(
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
    return shipment


@sync_to_async
def get_user_shipments(user_id):
    return list(Shipment.objects.filter(user_id=user_id).order_by('-id')[:5])


@sync_to_async
def get_shipment_status(shipment_id):
    try:
        shipment = Shipment.objects.get(id=shipment_id)
        return shipment.status, shipment.get_status_display()
    except ObjectDoesNotExist:
        return None, None


async def send_to_group(context: CallbackContext, message: str, photos=None):
    try:
        if photos and len(photos) > 0:
            media = []
            for i, photo_path in enumerate(photos):
                with open(photo_path, 'rb') as photo_file:
                    if i == 0:
                        media.append(InputMediaPhoto(photo_file, caption=message, parse_mode='HTML'))
                    else:
                        media.append(InputMediaPhoto(photo_file))
            await context.bot.send_media_group(chat_id=GROUP_ID, media=media)
        else:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=message,
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Ошибка отправки в группу: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    logger.info(f"Пользователь {user.first_name} запустил бота")

    user_obj, created = await get_or_create_user(
        user.id,
        user.first_name,
        user.last_name
    )

    context.user_data['user_id'] = user_obj.id
    return await show_main_menu(update, context)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = ReplyKeyboardMarkup([
        ['📤 Новая отправка'],
        ['📦 Мои отправки', '⚙️ Настройки']
    ], resize_keyboard=True)

    await update.message.reply_text(
        "🚛 <b>Главное меню</b>\nВыберите действие:",
        parse_mode='HTML',
        reply_markup=keyboard
    )
    return MAIN_MENU


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text

    if text == '📤 Новая отправка':
        return await ask_shipment_type(update, context)
    elif text == '📦 Мои отправки':
        return await show_user_shipments(update, context)
    elif text == '⚙️ Настройки':
        return await show_settings(update, context)

    await update.message.reply_text("Пожалуйста, используйте кнопки меню")
    return MAIN_MENU


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = ReplyKeyboardMarkup([
        ['🔔 Настройка уведомлений'],
        ['◀️ Назад в меню']
    ], resize_keyboard=True)

    await update.message.reply_text(
        "⚙️ <b>Настройки</b>\nВыберите опцию:",
        parse_mode='HTML',
        reply_markup=keyboard
    )
    return SETTINGS_MENU


async def handle_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text

    if text == '◀️ Назад в меню':
        return await show_main_menu(update, context)
    elif text == '🔔 Настройка уведомлений':
        await update.message.reply_text(
            "🔔 Уведомления включены\nИзменить статус можно в веб-интерфейсе",
            reply_markup=ReplyKeyboardMarkup([['◀️ Назад в меню']], resize_keyboard=True)
        )
        return SETTINGS_MENU

    await update.message.reply_text("Пожалуйста, используйте кнопки меню")
    return SETTINGS_MENU


async def show_user_shipments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = context.user_data['user_id']
    shipments = await get_user_shipments(user_id)

    if not shipments:
        await update.message.reply_text(
            "У вас пока нет отправлений",
            reply_markup=ReplyKeyboardMarkup([['📤 Новая отправка', '◀️ Назад в меню']], resize_keyboard=True)
        )
        return MAIN_MENU

    message = "📦 <b>Ваши последние отправки:</b>\n\n"
    for shipment in shipments:
        message += (
            f"{STATUS_EMOJI.get(shipment.status, '📌')} <b>ID:</b> <code>{shipment.id}</code>\n"
            f"📋 <b>Накладная:</b> {shipment.waybill_number}\n"
            f"🏙 <b>Город:</b> {shipment.city}\n"
            f"📅 <b>Дата:</b> {shipment.timestamp.strftime('%d.%m.%Y %H:%M')}\n"
            f"🔄 <b>Статус:</b> {shipment.get_status_display()}\n\n"
        )

    keyboard = ReplyKeyboardMarkup([['📤 Новая отправка', '◀️ Назад в меню']], resize_keyboard=True)
    await update.message.reply_text(
        message,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    return MAIN_MENU


async def ask_shipment_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = ReplyKeyboardMarkup([
        ['📤 Отправка', '📥 Получение'],
        ['🔄 Перемещение', '◀️ Назад в меню']
    ], resize_keyboard=True)

    await update.message.reply_text(
        "📦 <b>Тип отправки</b>\nВыберите тип:",
        parse_mode='HTML',
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

    if text == '◀️ Назад в меню':
        return await show_main_menu(update, context)

    if text not in type_map:
        await update.message.reply_text("Пожалуйста, выберите тип из предложенных вариантов")
        return await ask_shipment_type(update, context)

    context.user_data['shipment_data'] = {'type': type_map[text]}
    return await ask_waybill_number(update, context)


async def ask_waybill_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📋 <b>Номер накладной</b>\nВведите номер накладной:",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardMarkup([['◀️ Назад']], resize_keyboard=True)
    )
    return WAYBILL_NUMBER


async def handle_waybill_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == '◀️ Назад':
        return await ask_shipment_type(update, context)

    if not update.message.text:
        await update.message.reply_text("Пожалуйста, введите номер накладной")
        return await ask_waybill_number(update, context)

    context.user_data['shipment_data']['waybill_number'] = update.message.text.strip()
    return await ask_city(update, context)


async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = ReplyKeyboardMarkup([
        ['Москва', 'Санкт-Петербург'],
        ['Новосибирск', 'Екатеринбург'],
        ['Другой город', '◀️ Назад']
    ], resize_keyboard=True)

    await update.message.reply_text(
        "🏙 <b>Город</b>\nВыберите город:",
        parse_mode='HTML',
        reply_markup=keyboard
    )
    return CITY_SELECTION


async def handle_city_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text

    if text == '◀️ Назад':
        return await ask_waybill_number(update, context)

    if text == 'Другой город':
        await update.message.reply_text(
            "Введите название города:",
            reply_markup=ReplyKeyboardMarkup([['◀️ Назад']], resize_keyboard=True)
        )
        return CITY_SELECTION

    context.user_data['shipment_data']['city'] = text
    return await ask_weight(update, context)


async def ask_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "⚖️ <b>Вес (кг)</b>\nВведите вес в килограммах (например: 12.5):\n\n"
        "Отправьте '0' если вес неизвестен",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardMarkup([['◀️ Назад']], resize_keyboard=True)
    )
    return WEIGHT_INPUT


async def handle_weight_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text

    if text == '◀️ Назад':
        return await ask_city(update, context)

    try:
        weight = float(text)
        if weight < 0:
            raise ValueError
        context.user_data['shipment_data']['weight'] = weight if weight != 0 else None
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число (например: 12.5)")
        return await ask_weight(update, context)

    return await ask_comment(update, context)


async def ask_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📝 <b>Комментарий</b>\nВведите дополнительную информацию (или отправьте '-' чтобы пропустить):",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardMarkup([['◀️ Назад']], resize_keyboard=True)
    )
    return COMMENT_INPUT


async def handle_comment_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text

    if text == '◀️ Назад':
        return await ask_weight(update, context)

    if text != '-':
        context.user_data['shipment_data']['comment'] = text

    return await ask_waybill_photo(update, context)


async def ask_waybill_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📄 <b>Фото накладной</b>\nОтправьте фото накладной (JPG/PNG, макс. 5MB):\n\n"
        "Отправьте '-' чтобы пропустить",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardMarkup([['◀️ Назад']], resize_keyboard=True)
    )
    return WAYBILL_PHOTO


async def handle_waybill_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message.text else ""

    if text == '◀️ Назад':
        return await ask_comment(update, context)

    if text == '-':
        context.user_data['shipment_data']['waybill_photo'] = None
        return await ask_product_photo(update, context)

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
        "📦 <b>Фото товара</b>\nОтправьте фото товара (JPG/PNG, макс. 5MB):\n\n"
        "Отправьте '-' чтобы пропустить",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardMarkup([['◀️ Назад']], resize_keyboard=True)
    )
    return PRODUCT_PHOTO


async def handle_product_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message.text else ""

    if text == '◀️ Назад':
        return await ask_waybill_photo(update, context)

    if text == '-':
        context.user_data['shipment_data']['product_photo'] = None
    elif not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте фото товара")
        return await ask_product_photo(update, context)
    else:
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

        # Подготовка фото для отправки
        photos = []
        if shipment.waybill_photo:
            photos.append(shipment.waybill_photo.path)
        if shipment.product_photo:
            photos.append(shipment.product_photo.path)

        # Красивое сообщение о создании
        message = (
            f"🎉 <b>Отправка успешно создана!</b>\n\n"
            f"{STATUS_EMOJI['created']} <b>ID:</b> <code>{shipment.id}</code>\n"
            f"📦 <b>Тип:</b> {shipment.get_type_display()}\n"
            f"📋 <b>Накладная:</b> {shipment.waybill_number}\n"
            f"🏙 <b>Город:</b> {shipment.city}\n"
            f"⚖️ <b>Вес:</b> {shipment.weight if shipment.weight else 'не указан'} кг\n"
            f"📅 <b>Дата:</b> {shipment.timestamp.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Статус можно изменить в веб-интерфейсе"
        )

        if photos:
            media = []
            for i, photo_path in enumerate(photos):
                if os.path.exists(photo_path):
                    with open(photo_path, 'rb') as photo_file:
                        if i == 0:
                            media.append(InputMediaPhoto(photo_file, caption=message, parse_mode='HTML'))
                        else:
                            media.append(InputMediaPhoto(photo_file))

            if media:
                await update.message.reply_media_group(media=media)
        else:
            await update.message.reply_text(
                message,
                parse_mode='HTML'
            )

        # Отправляем уведомление в группу
        group_message = (
            f"📌 <b>Новая отправка</b>\n\n"
            f"👤 <b>Пользователь:</b> {update.message.from_user.full_name}\n"
            f"📦 <b>Тип:</b> {shipment.get_type_display()}\n"
            f"📋 <b>Накладная:</b> {shipment.waybill_number}\n"
            f"🏙 <b>Город:</b> {shipment.city}\n"
            f"🆔 <b>ID:</b> <code>{shipment.id}</code>"
        )

        group_photos = []
        if shipment.waybill_photo and os.path.exists(shipment.waybill_photo.path):
            group_photos.append(shipment.waybill_photo.path)
        if shipment.product_photo and os.path.exists(shipment.product_photo.path):
            group_photos.append(shipment.product_photo.path)

        if group_photos:
            media = []
            for i, photo_path in enumerate(group_photos):
                with open(photo_path, 'rb') as photo_file:
                    if i == 0:
                        media.append(InputMediaPhoto(photo_file, caption=group_message, parse_mode='HTML'))
                    else:
                        media.append(InputMediaPhoto(photo_file))
            await context.bot.send_media_group(chat_id=GROUP_ID, media=media)
        else:
            await send_to_group(context, group_message)

    except Exception as e:
        logger.error(f"Ошибка сохранения: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Произошла ошибка при сохранении. Попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )

    context.user_data.pop('shipment_data', None)
    return await show_main_menu(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Действие отменено",
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return await show_main_menu(update, context)


async def notify_status_change(shipment_id, old_status, new_status, context: CallbackContext):
    status_display = {
        'created': 'Создано',
        'processing': 'В обработке',
        'transit': 'В пути',
        'delivered': 'Доставлено',
        'problem': 'Проблема'
    }

    try:
        shipment = await sync_to_async(Shipment.objects.get)(id=shipment_id)
        user = await sync_to_async(lambda: shipment.user)()

        message = (
            f"🔄 <b>Изменение статуса отправки</b>\n\n"
            f"🆔 <b>ID:</b> <code>{shipment.id}</code>\n"
            f"📦 <b>Тип:</b> {shipment.get_type_display()}\n"
            f"📋 <b>Накладная:</b> {shipment.waybill_number}\n"
            f"👤 <b>Пользователь:</b> {user.first_name} {user.last_name}\n\n"
            f"Статус изменен:\n"
            f"{STATUS_EMOJI.get(old_status, '')} {status_display.get(old_status, old_status)} → "
            f"{STATUS_EMOJI.get(new_status, '')} {status_display.get(new_status, new_status)}"
        )

        # Подготовка фото для отправки
        photos = []
        if shipment.waybill_photo:
            photos.append(shipment.waybill_photo.path)
        if shipment.product_photo:
            photos.append(shipment.product_photo.path)

        # Отправляем пользователю
        if photos:
            media = []
            for i, photo_path in enumerate(photos):
                if os.path.exists(photo_path):
                    with open(photo_path, 'rb') as photo_file:
                        if i == 0:
                            media.append(InputMediaPhoto(photo_file, caption=message, parse_mode='HTML'))
                        else:
                            media.append(InputMediaPhoto(photo_file))

            if media:
                await context.bot.send_media_group(
                    chat_id=user.username,
                    media=media
                )
        else:
            await context.bot.send_message(
                chat_id=user.username,
                text=message,
                parse_mode='HTML'
            )

        # Отправляем в группу
        if photos:
            media = []
            for i, photo_path in enumerate(photos):
                if os.path.exists(photo_path):
                    with open(photo_path, 'rb') as photo_file:
                        if i == 0:
                            media.append(InputMediaPhoto(photo_file, caption=message, parse_mode='HTML'))
                        else:
                            media.append(InputMediaPhoto(photo_file))

            if media:
                await context.bot.send_media_group(chat_id=GROUP_ID, media=media)
        else:
            await send_to_group(context, message)

    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")


async def check_status_changes(context: CallbackContext):
    """Проверяем изменения статусов и отправляем уведомления"""
    try:
        # Здесь должна быть логика проверки изменений в базе данных
        pass
    except Exception as e:
        logger.error(f"Ошибка при проверке изменений статуса: {e}")


def main() -> None:
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu)],
            SETTINGS_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_settings)],
            TYPE_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_type_selection)],
            WAYBILL_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_waybill_number)],
            CITY_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city_selection)],
            WEIGHT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_weight_input)],
            COMMENT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment_input)],
            WAYBILL_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, handle_waybill_photo)],
            PRODUCT_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, handle_product_photo)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )

    application.add_handler(conv_handler)

    # Добавляем обработчик для уведомлений об изменении статуса
    application.job_queue.run_repeating(
        check_status_changes,
        interval=60.0,
        first=10.0,
        name='check_status_changes'
    )

    logger.info("Бот запущен")
    application.run_polling()


if __name__ == '__main__':
    main()