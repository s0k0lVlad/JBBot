import asyncio
import logging
import sqlite3
import json
from datetime import datetime
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "8468761099:AAEPMmi9gYqAYZCy4He1lY0hGULa1sNV5_M"
ADMIN_USER_IDS = [1929149706]
PRICE_PER_COMPLAINT = 250
DATABASE_NAME = "neterror_bot.db"

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ ГРУПП ФОТО ====================
media_groups = defaultdict(list)
processing_groups = set()

# Добавьте глобальные переменные в начало
user_media_groups = defaultdict(list)
user_media_timers = {}

# ==================== БАЗА ДАННЫХ ====================
def init_database():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        total_complaints INTEGER DEFAULT 0,
        successful_complaints INTEGER DEFAULT 0,
        joined_date TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        target_username TEXT,
        target_id TEXT,
        problem_description TEXT,
        status TEXT DEFAULT 'pending',
        created_date TEXT,
        admin_id INTEGER,
        screenshots TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS payment_keys (
        key TEXT PRIMARY KEY,
        amount INTEGER,
        used BOOLEAN DEFAULT FALSE,
        created_by INTEGER
    )
    ''')

    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return {
            'user_id': user[0],
            'username': user[1],
            'balance': user[2],
            'total_complaints': user[3],
            'successful_complaints': user[4],
            'joined_date': user[5]
        }
    return None


def create_user(user_id, username):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR IGNORE INTO users (user_id, username, joined_date) 
    VALUES (?, ?, ?)
    ''', (user_id, username, datetime.now().strftime("%d.%m.%Y")))
    conn.commit()
    conn.close()


def update_user_balance(user_id, amount):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()


def add_order(user_id, target_username, target_id, problem_description, screenshots):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO orders (user_id, target_username, target_id, problem_description, created_date, screenshots)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (
    user_id, target_username, target_id, problem_description, datetime.now().strftime("%d.%m.%Y %H:%M"), screenshots))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id


def update_order_status(order_id, status, admin_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE orders SET status = ?, admin_id = ? WHERE order_id = ?', (status, admin_id, order_id))

    cursor.execute('SELECT user_id FROM orders WHERE order_id = ?', (order_id,))
    result = cursor.fetchone()
    if result:
        user_id = result[0]
        if status == 'completed':
            cursor.execute(
                'UPDATE users SET total_complaints = total_complaints + 1, successful_complaints = successful_complaints + 1 WHERE user_id = ?',
                (user_id,))
        elif status == 'rejected':
            cursor.execute('UPDATE users SET total_complaints = total_complaints + 1 WHERE user_id = ?', (user_id,))

    conn.commit()
    conn.close()


def get_order(order_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,))
    order = cursor.fetchone()
    conn.close()

    if order:
        return {
            'order_id': order[0],
            'user_id': order[1],
            'target_username': order[2],
            'target_id': order[3],
            'problem_description': order[4],
            'status': order[5],
            'created_date': order[6],
            'admin_id': order[7],
            'screenshots': order[8]
        }
    return None


# ==================== СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ ====================
user_states = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    create_user(user_id, user.username)
    user_data = get_user(user_id)

    keyboard = [
        [InlineKeyboardButton("💎 Пополнить баланс", callback_data="topup"),
         InlineKeyboardButton("🎯 Заказать картошку фри", callback_data="send_complaint")],
        [InlineKeyboardButton("💰 Мой баланс", callback_data="balance"),
         InlineKeyboardButton("📊 Статистика", callback_data="stats")],
    ]

    if user_id in ADMIN_USER_IDS:
        keyboard.append([InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(
            f"🔥 Aegis French Fries приветствует!\n\n"
            f"⭐ Ваш баланс: {user_data['balance']} звезд\n"
            f"🎯 Цена за 1 доставку картошки фри: {PRICE_PER_COMPLAINT} звезд\n",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(

            reply_markup=reply_markup
        )


async def start_from_query(query):
    user = query.from_user
    user_id = user.id

    create_user(user_id, user.username)
    user_data = get_user(user_id)

    keyboard = [
        [InlineKeyboardButton("💎 Пополнить баланс", callback_data="topup"),
         InlineKeyboardButton("🎯 Заказать картошку фри", callback_data="send_complaint")],
        [InlineKeyboardButton("💰 Мой баланс", callback_data="balance"),
         InlineKeyboardButton("📊 Статистика", callback_data="stats")],
    ]

    if user_id in ADMIN_USER_IDS:
        keyboard.append([InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # ДОБАВЬ ЭТОТ ТЕКСТ:
    await query.edit_message_text(
        f"🔥 Aegis French Fries приветствует!\n\n"
        f"⭐ Ваш баланс: {user_data['balance']} звезд\n"
        f"🎯 Цена за 1 доставку картошки фри: {PRICE_PER_COMPLAINT} звезд\n",
        reply_markup=reply_markup
    )


def get_payment_keys_stats():
    """Статистика по ключам"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM payment_keys WHERE used = FALSE')
    active_keys = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM payment_keys WHERE used = TRUE')
    used_keys = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM payment_keys')
    total_keys = cursor.fetchone()[0]

    cursor.execute('SELECT SUM(amount) FROM payment_keys WHERE used = FALSE')
    total_amount = cursor.fetchone()[0] or 0

    conn.close()

    return {
        'active': active_keys,
        'used': used_keys,
        'total': total_keys,
        'total_amount': total_amount
    }


async def handle_send_complaint(query):
    user_id = query.from_user.id
    user_data = get_user(user_id)

    if user_data['balance'] < PRICE_PER_COMPLAINT:
        keyboard = [
            [InlineKeyboardButton("💎 Пополнить баланс", callback_data="topup")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "❌ Недостаточно звезд!\n\n"
            f"⭐ Требуется: {PRICE_PER_COMPLAINT} звезд\n"
            f"💎 Ваш баланс: {user_data['balance']} звезд\n\n"
            f"Пополните баланс чтобы заказать картошки фри",
            reply_markup=reply_markup
        )
        return

    user_states[user_id] = {'step': 'waiting_target'}

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🎯 Заказ картошки фри\n\n"
        "Отправьте @username или ID пользователя, которому хотите заказать картошку фри:\n\n"
        "📝 Примеры:\n"
        "• @username - для юзернейма\n"
        "• 123456789 - для ID пользователя\n\n"
        "Или нажмите 'Назад' чтобы вернуться",
        reply_markup=reply_markup
    )


async def handle_target_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_states or user_states[user_id]['step'] != 'waiting_target':
        return

    target_input = update.message.text.strip()
    user_states[user_id] = {
        'step': 'waiting_description',
        'target': target_input
    }

    keyboard = [
        [InlineKeyboardButton("⬅️ Отменить заказ", callback_data="send_complaint")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📝 Описание проблемы\n\n"
        "Опишите подробно проблему и причину жалобы:\n\n"
        "💬 Пример: 'Пользователь занимается мошенничеством, обманывает людей'\n\n"
        "Или нажмите 'Отменить заказ' чтобы вернуться",
        reply_markup=reply_markup
    )



async def handle_description_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_states or user_states[user_id]['step'] != 'waiting_description':
        return

    description = update.message.text
    user_states[user_id] = {
        'step': 'waiting_screenshots',
        'target': user_states[user_id]['target'],
        'description': description
    }

    keyboard = [
        [InlineKeyboardButton("⏩ Пропустить", callback_data="skip_screenshots")],
        [InlineKeyboardButton("⬅️ Назад к описанию", callback_data="back_to_description")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📸 Доказательства\n\n"
        "Пришлите скриншоты-доказательства (фотографии):\n\n"
        "📎 Можно отправить несколько фото\n"
        "⏩ Или нажмите 'Пропустить' чтобы продолжить без фото\n"
        "⬅️ Или 'Назад' чтобы изменить описание",
        reply_markup=reply_markup
    )


async def process_media_group(media_group_id, user_id):
    """Обрабатывает собранную группу фотографий"""
    if media_group_id not in media_groups:
        return None

    group_items = media_groups[media_group_id]

    # Собираем уникальные фото по file_unique_id (берем самое качественное из каждой группы)
    unique_photos = {}
    for item in group_items:
        photo = item['photo']
        if photo.file_unique_id not in unique_photos:
            unique_photos[photo.file_unique_id] = photo
        else:
            # Если нашли фото большего размера - обновляем
            if photo.file_size > unique_photos[photo.file_unique_id].file_size:
                unique_photos[photo.file_unique_id] = photo

    screenshot_ids = [photo.file_id for photo in unique_photos.values()]

    print(f"Обработана группа фото: {len(group_items)} сообщений -> {len(screenshot_ids)} уникальных изображений")

    # Очищаем группу
    del media_groups[media_group_id]
    processing_groups.discard(media_group_id)

    return screenshot_ids


async def handle_screenshots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_states or user_states[user_id]['step'] != 'waiting_screenshots':
        return

    if update.message.photo:
        # Берем самое качественное фото из сообщения
        highest_quality_photo = update.message.photo[-1]

        # Если это группа медиа
        if update.message.media_group_id:
            media_group_id = update.message.media_group_id

            # Добавляем фото в группу пользователя
            user_media_groups[user_id].append({
                'photo': highest_quality_photo,
                'media_group_id': media_group_id,
                'timestamp': datetime.now()
            })

            print(f"Добавлено фото в группу пользователя {user_id}. Всего: {len(user_media_groups[user_id])}")

            # Запускаем/перезапускаем таймер обработки группы
            if user_id in user_media_timers:
                user_media_timers[user_id].cancel()

            # Ждем 3 секунды после последнего фото в группе
            user_media_timers[user_id] = asyncio.create_task(
                process_user_media_group(user_id, update, context)
            )

        else:
            # Одиночное фото - обрабатываем сразу
            screenshot_ids = [highest_quality_photo.file_id]
            user_states[user_id]['screenshots'] = json.dumps(screenshot_ids)

            print(f"Одиночное фото пользователя {user_id}: 1 изображение")

            # Очищаем возможные предыдущие группы
            if user_id in user_media_groups:
                del user_media_groups[user_id]
            if user_id in user_media_timers:
                user_media_timers[user_id].cancel()
                del user_media_timers[user_id]

            await create_complaint_order(update, context, user_id)
    else:
        await update.message.reply_text("❌ Пожалуйста, отправьте фото!")


async def process_user_media_group(user_id, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает группу фото пользователя после задержки"""
    try:
        # Ждем 3 секунды чтобы собрать все фото из группы
        await asyncio.sleep(3)

        if user_id not in user_media_groups or not user_media_groups[user_id]:
            return

        # Получаем все фото пользователя
        user_photos = user_media_groups[user_id]

        # Группируем по media_group_id (на случай если несколько групп)
        groups = defaultdict(list)
        for photo_data in user_photos:
            groups[photo_data['media_group_id']].append(photo_data)

        # Обрабатываем каждую группу
        all_screenshot_ids = []
        for media_group_id, group_photos in groups.items():
            # Берем уникальные фото из группы
            unique_photos = {}
            for photo_data in group_photos:
                photo = photo_data['photo']
                if photo.file_unique_id not in unique_photos:
                    unique_photos[photo.file_unique_id] = photo
                else:
                    # Берем фото большего размера
                    if photo.file_size > unique_photos[photo.file_unique_id].file_size:
                        unique_photos[photo.file_unique_id] = photo

            # Добавляем file_id уникальных фото
            for photo in unique_photos.values():
                all_screenshot_ids.append(photo.file_id)

        print(
            f"Обработана группа фото пользователя {user_id}: {len(user_photos)} фото -> {len(all_screenshot_ids)} уникальных")

        # Сохраняем в состоянии пользователя (правильный ключ)
        user_states[user_id]['screenshots'] = json.dumps(all_screenshot_ids)  # ← ИСПРАВЛЕНО

        # Очищаем группу пользователя
        if user_id in user_media_groups:
            del user_media_groups[user_id]
        if user_id in user_media_timers:
            del user_media_timers[user_id]

        # Создаем заявку
        await create_complaint_order(update, context, user_id)

    except Exception as e:
        print(f"Ошибка обработки группы фото пользователя {user_id}: {e}")

async def handle_skip_screenshots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_states or user_states[user_id]['step'] != 'waiting_screenshots':
        return

    user_states[user_id]['screenshots'] = json.dumps([])
    await create_complaint_order(update, context, user_id)


async def create_complaint_order(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    user_data = get_user(user_id)

    if user_data['balance'] < PRICE_PER_COMPLAINT:
        await update.message.reply_text(
            "❌ Недостаточно звезд!\n\n"
            f"⭐ Требуется: {PRICE_PER_COMPLAINT} звезд\n"
            f"💎 Ваш баланс: {user_data['balance']} звезд"
        )
        if user_id in user_states:
            del user_states[user_id]
        return

    target = user_states[user_id]['target']
    description = user_states[user_id]['description']
    screenshots = user_states[user_id]['screenshots']

    # Определяем тип цели
    target_type = "username" if target.startswith('@') else "id"
    target_value = target.replace('@', '')

    # Создаем заявку
    order_id = add_order(user_id, target_value if target_type == "username" else None,
                         target_value if target_type == "id" else None, description, screenshots)

    # Списываем звезды
    update_user_balance(user_id, -PRICE_PER_COMPLAINT)

    # Отправляем заявку админам
    for admin_id in ADMIN_USER_IDS:
        try:
            keyboard = [
                [InlineKeyboardButton("✅ Выполнил", callback_data=f"complete_{order_id}"),
                 InlineKeyboardButton("❌ Не выполнил", callback_data=f"reject_{order_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message_text = (
                f"🆕 НОВАЯ ЗАЯВКА #{order_id}\n\n"
                f"👤 От пользователя: @{update.effective_user.username or 'Нет username'} ({user_id})\n"
                f"🎯 Цель: {target}\n"
                f"📝 Описание проблемы: {description}\n"
                f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"⭐ Стоимость: {PRICE_PER_COMPLAINT} звезд"
            )

            await context.bot.send_message(
                chat_id=admin_id,
                text=message_text,
                reply_markup=reply_markup
            )

            # Отправляем скриншоты если есть
            screenshots_list = json.loads(screenshots)
            print(f"Отправка админу {admin_id}: {len(screenshots_list)} скриншотов")

            if screenshots_list:
                for i, screenshot_id in enumerate(screenshots_list):
                    print(f"Отправка скриншота {i + 1}")
                    await context.bot.send_photo(admin_id, screenshot_id)

        except Exception as e:
            print(f"Ошибка отправки админу {admin_id}: {e}")

    # Уведомляем пользователя
    user_balance = get_user(user_id)['balance']
    await update.message.reply_text(
        f"✅ Картошка фри заказана! (#{order_id})\n\n"
        f"🎯 Цель: {target}\n"
        f"📝 Ваша жалоба отправлена администраторам\n"
        f"⏳ Ожидайте решения в течение 24 часов\n"
        f"⭐ Списано: {PRICE_PER_COMPLAINT} звезд\n"
        f"💎 Текущий баланс: {user_balance} звезд"
    )

    # Очищаем состояние пользователя
    if user_id in user_states:
        del user_states[user_id]


async def handle_order_complete(query, order_id, context: ContextTypes.DEFAULT_TYPE):
    order = get_order(order_id)
    if not order:
        await query.edit_message_text("❌ Заявка не найдена!")
        return

    update_order_status(order_id, 'completed', query.from_user.id)

    try:
        safe_target = order['target_username'] or order['target_id']
        safe_admin = query.from_user.username or "Администратор"

        await context.bot.send_message(  # ← ИСПРАВЛЕНО: context.bot вместо query.bot
            chat_id=order['user_id'],
            text=f"✅ ЗАЯВКА ВЫПОЛНЕНА (#{order_id})\n\n"
                 f"🎯 Цель: {safe_target}\n"
                 f"📝 Статус: Ожидайте удаление аккаунта\n"
                 f"👮 Администратор: @{safe_admin}"
        )
    except Exception as e:
        print(f"Ошибка уведомления пользователя: {e}")

    await query.edit_message_text(
        f"✅ Заявка #{order_id} выполнена\n\n"
        f"👤 Пользователь уведомлен"
    )


async def handle_order_reject(query, order_id, context: ContextTypes.DEFAULT_TYPE):
    order = get_order(order_id)
    if not order:
        await query.edit_message_text("❌ Заявка не найдена!")
        return

    update_order_status(order_id, 'rejected', query.from_user.id)
    update_user_balance(order['user_id'], PRICE_PER_COMPLAINT)

    try:
        safe_target = order['target_username'] or order['target_id']
        safe_admin = query.from_user.username or "Администратор"

        await context.bot.send_message(  # ← ИСПРАВЛЕНО: context.bot вместо query.bot
            chat_id=order['user_id'],
            text=f"❌ ЗАЯВКА ОТКЛОНЕНА (#{order_id})\n\n"
                 f"🎯 Цель: {safe_target}\n"
                 f"📝 Причина: Аккаунт снести не получилось\n"
                 f"💎 Возвращено: {PRICE_PER_COMPLAINT} звезд\n"
                 f"👮 Администратор: @{safe_admin}"
        )
    except Exception as e:
        print(f"Ошибка уведомления пользователя: {e}")

    await query.edit_message_text(
        f"❌ Заявка #{order_id} отклонена\n\n"
        f"👤 Пользователю возвращены звезды"
    )


# ==================== ОБРАБОТЧИКИ КНОПОК ====================
def generate_payment_key(amount, admin_id):
    """Генерация ключа пополнения"""
    import random
    import string

    key = f"AEGIS-{''.join(random.choices(string.ascii_uppercase + string.digits, k=12))}"

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO payment_keys (key, amount, created_by) VALUES (?, ?, ?)',
                   (key, amount, admin_id))
    conn.commit()
    conn.close()
    return key


def activate_payment_key(key, user_id):
    """Активация ключа"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM payment_keys WHERE key = ? AND used = FALSE', (key,))
    key_data = cursor.fetchone()

    if key_data:
        amount = key_data[1]
        cursor.execute('UPDATE payment_keys SET used = TRUE WHERE key = ?', (key,))
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        conn.close()
        return amount
    else:
        conn.close()
        return None


async def handle_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода ключа"""
    user_id = update.effective_user.id

    if user_id not in user_states or user_states[user_id]['step'] != 'waiting_key':
        return

    key = update.message.text.strip().upper()
    amount = activate_payment_key(key, user_id)

    if amount:
        user_data = get_user(user_id)
        await update.message.reply_text(
            f"✅ Ключ активирован!\n\n"
            f"💎 Пополнено: {amount} звезд\n"
            f"💰 Новый баланс: {user_data['balance']} звезд"
        )
    else:
        await update.message.reply_text(
            "❌ Неверный или уже использованный ключ!\n\n"
            "Проверьте правильность ввода и попробуйте снова."
        )

    # Очищаем состояние
    if user_id in user_states:
        del user_states[user_id]


async def handle_admin_panel(query):
    """Обработка админ панели"""
    user_id = query.from_user.id

    if user_id not in ADMIN_USER_IDS:
        await query.edit_message_text("❌ Доступ запрещен!")
        return

    keys_stats = get_payment_keys_stats()

    keyboard = [
        [InlineKeyboardButton("🔑 Сгенерировать ключ", callback_data="generate_key")],
        [InlineKeyboardButton("📋 Список ключей", callback_data="list_keys")],
        [InlineKeyboardButton("📊 Статистика бота", callback_data="bot_stats")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"👑 Админ панель\n\n"
        f"🔑 Ключи:\n"
        f"• Активных: {keys_stats['active']}\n"
        f"• Использовано: {keys_stats['used']}\n"
        f"• Общая сумма: {keys_stats['total_amount']} звезд\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )


async def handle_list_keys(query):
    """Показ списка ключей"""
    user_id = query.from_user.id

    if user_id not in ADMIN_USER_IDS:
        await query.edit_message_text("❌ Доступ запрещен!")
        return

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Активные ключи
    cursor.execute('SELECT key, amount FROM payment_keys WHERE used = FALSE ORDER BY rowid DESC LIMIT 10')
    active_keys = cursor.fetchall()

    # Использованные ключи
    cursor.execute('SELECT key, amount FROM payment_keys WHERE used = TRUE ORDER BY rowid DESC LIMIT 10')
    used_keys = cursor.fetchall()

    conn.close()

    text = "🔑 Активные ключи:\n"
    if active_keys:
        for key, amount in active_keys:
            text += f"• {key} - {amount} звезд\n"
    else:
        text += "Нет активных ключей\n"

    text += "\n📋 Использованные ключи:\n"
    if used_keys:
        for key, amount in used_keys:
            text += f"• {key} - {amount} звезд\n"
    else:
        text += "Нет использованных ключей\n"

    keyboard = [
        [InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    print(f"DEBUG: Нажата кнопка: {data}")  # ← Добавь эту строку


    if data == "topup":
        print("DEBUG: Переход в topup")
        await handle_topup(query)
    elif data == "activate_key":
        await handle_activate_key(query)
    elif data == "send_complaint":
        await handle_send_complaint(query)
    elif data == "balance":
        await handle_balance(query)
    elif data == "stats":
        await handle_stats(query)
    elif data == "admin_panel":
        await handle_admin_panel(query)
    elif data == "back_to_main":
        print("DEBUG: Обрабатываю back_to_main")
        await start_from_query(query)
    elif data == "back_to_description":
        await handle_back_to_description(query)
    elif data == "skip_screenshots":
        user_id = query.from_user.id
        user_states[user_id]['screenshots'] = json.dumps([])
    elif data == "generate_key":
        await handle_generate_key(query)
    elif data == "bot_stats":
        await handle_bot_stats(query)
    elif data.startswith("complete_"):
        order_id = int(data.replace("complete_", ""))
        await handle_order_complete(query, order_id, context)
    elif data.startswith("reject_"):
        order_id = int(data.replace("reject_", ""))
        await handle_order_reject(query, order_id, context)
    elif data == "list_keys":
        await handle_list_keys(query)
    else:
        await query.edit_message_text("❌ Неизвестная команда!")


async def handle_generate_key(query):
    """Генерация ключа пополнения"""
    user_id = query.from_user.id

    if user_id not in ADMIN_USER_IDS:
        await query.edit_message_text("❌ Доступ запрещен!")
        return

    # Устанавливаем состояние ожидания суммы
    user_states[user_id] = {'step': 'waiting_key_amount'}

    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🔑 Генерация ключа\n\n"
        "Введите сумму пополнения (число):\n\n",
        reply_markup=reply_markup
    )


async def handle_bot_stats(query):
    """Статистика бота"""
    user_id = query.from_user.id

    if user_id not in ADMIN_USER_IDS:
        await query.edit_message_text("❌ Доступ запрещен!")
        return

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Статистика пользователей
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]

    cursor.execute('SELECT SUM(balance) FROM users')
    total_balance = cursor.fetchone()[0] or 0

    cursor.execute('SELECT COUNT(*) FROM orders')
    total_orders = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM orders WHERE status = "completed"')
    completed_orders = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM orders WHERE status = "pending"')
    pending_orders = cursor.fetchone()[0]

    conn.close()

    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"📊 Статистика бота\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"💎 Общий баланс: {total_balance} звезд\n"
        f"📦 Всего заказов: {total_orders}\n"
        f"✅ Выполнено: {completed_orders}\n"
        f"⏳ Ожидают: {pending_orders}",
        reply_markup=reply_markup
    )


async def handle_balance(query):
    """Показ баланса с кнопкой назад"""
    user_id = query.from_user.id
    user_data = get_user(user_id)

    keyboard = [
        [InlineKeyboardButton("💎 Пополнить баланс", callback_data="topup")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"💰 Ваш баланс: {user_data['balance']} звезд\n\n"
        f"📊 Статистика:\n"
        f"• Всего заказов: {user_data['total_complaints']}\n"
        f"• Успешных: {user_data['successful_complaints']}",
        reply_markup=reply_markup
    )

async def handle_stats(query):
    """Показ статистики с кнопкой назад"""
    user_id = query.from_user.id
    user_data = get_user(user_id)

    success_rate = (user_data['successful_complaints'] / user_data['total_complaints'] * 100) if user_data[
                                                                                                     'total_complaints'] > 0 else 0

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"📊 Ваша статистика\n\n"
        f"🎯 Всего заказов: {user_data['total_complaints']}\n"
        f"✅ Успешных: {user_data['successful_complaints']}\n"
        f"📈 Процент успеха: {success_rate:.1f}%\n"
        f"📅 Дата регистрации: {user_data['joined_date']}",
        reply_markup=reply_markup
    )

async def handle_back_to_description(query):
    """Возврат к описанию проблемы"""
    user_id = query.from_user.id
    user_states[user_id] = {
        'step': 'waiting_description',
        'target': user_states[user_id]['target']  # Сохраняем target
    }

    keyboard = [
        [InlineKeyboardButton("⬅️ Отменить заказ", callback_data="send_complaint")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "📝 Описание проблемы\n\n"
        "Опишите подробно проблему и причину жалобы:\n\n"
        "💬 Пример: 'Пользователь занимается мошенничеством, обманывает людей'\n\n"
        "Или нажмите 'Отменить заказ' чтобы вернуться",
        reply_markup=reply_markup
    )


async def handle_topup(query):
    """Обработка пополнения баланса"""
    keyboard = [
        [InlineKeyboardButton("🔑 Активировать ключ", callback_data="activate_key")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "💎 Пополнение баланса\n\n"
        "🔑 Активировать ключ - ввести промокод для пополнения баланса\n\n"
        "Для покупки ключа необходимо обратиться к @aegis_def",
        reply_markup=reply_markup
    )


async def handle_activate_key(query):
    """Обработка активации ключа"""
    user_id = query.from_user.id
    user_states[user_id] = {'step': 'waiting_key'}

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="topup")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🔑 Активация ключа\n\n"
        "Отправьте ключ для пополнения баланса:\n\n"
        "📝 Пример: AEGIS-XXXX-XXXX-XXXX\n\n"
        "Или нажмите 'Назад' чтобы вернуться",
        reply_markup=reply_markup
    )


async def handle_key_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода суммы для генерации ключа"""
    user_id = update.effective_user.id

    if user_id not in user_states or user_states[user_id]['step'] != 'waiting_key_amount':
        return

    try:
        amount = int(update.message.text.strip())

        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть положительной!")
            return

        if amount > 100000:  # Максимальная сумма
            await update.message.reply_text("❌ Слишком большая сумма! Максимум 100,000 звезд")
            return

        # Генерируем ключ
        key = generate_payment_key(amount, user_id)

        # Очищаем состояние
        keyboard = [
            [InlineKeyboardButton("🔑 Создать еще ключ", callback_data="generate_key")],
            [InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Не очищаем состояние - пусть админ продолжает работать
        # del user_states[user_id]  # ← ЗАКОММЕНТИРУЙ ЭТУ СТРОКУ

        await update.message.reply_text(
            f"🔑 Ключ успешно создан!\n\n"
            f"💎 Сумма: {amount} звезд\n"
            f"🔑 Ключ: `{key}`\n\n",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка генерации ключа: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    print(f"DEBUG: Получено сообщение от {user_id}, состояние: {user_states.get(user_id, 'нет состояния')}")  # ← ДОБАВЬ ЭТУ СТРОКУ

    if user_id in user_states:
        state = user_states[user_id]['step']
        print(f"DEBUG: Обрабатываем состояние: {state}")  # ← И ЭТУ

        if state == 'waiting_target':
            await handle_target_input(update, context)
        elif state == 'waiting_description':
            await handle_description_input(update, context)
        elif state == 'waiting_key':
            await handle_key_input(update, context)
        elif state == 'waiting_key_amount':
            await handle_key_amount_input(update, context)


async def handle_skip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_states and user_states[user_id]['step'] == 'waiting_screenshots':
        await handle_skip_screenshots(update, context)


def main():
    init_database()

    application = Application.builder().token(BOT_TOKEN).build()

    # Сначала специфические обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("skip", handle_skip_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshots))  # Фото сначала!

    # Текстовые сообщения ПОСЛЕДНИМИ
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🔥 Aegis French Fries ЗАПУЩЕН!")
    application.run_polling()


if __name__ == "__main__":
    main()