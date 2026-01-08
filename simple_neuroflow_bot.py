#!/usr/bin/env python3
"""
Simplified NeuroFlow Bot
This is a minimal version that works with basic dependencies
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import aiogram
try:
    from aiogram import Bot, Dispatcher, types
    from aiogram.filters import Command
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    from aiogram import F
except ImportError as e:
    print(f"❌ Error importing aiogram: {e}")
    print("Install it with: pip3 install aiogram")
    sys.exit(1)

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://c6b6044d06e9bb7f-155-212-160-99.serveousercontent.com")

if not BOT_TOKEN:
    print("❌ Error: BOT_TOKEN not found in .env file!")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Create bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# User data storage (in-memory for simplicity)
users = {}

def get_main_keyboard():
    """Create main menu keyboard with WebApp"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🧠 Открыть NeuroFlow",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ],
        [
            InlineKeyboardButton(text="ℹ️ О боте", callback_data="about"),
            InlineKeyboardButton(text="💎 Подписка", callback_data="subscription")
        ],
        [
            InlineKeyboardButton(text="📞 Поддержка", callback_data="support")
        ]
    ])
    return keyboard

@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Handle /start command"""
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    
    # Register user
    users[user_id] = {
        "username": username,
        "first_seen": datetime.now(),
        "last_interaction": datetime.now()
    }
    
    logger.info(f"New user: {user_id} (@{username})")
    
    welcome_text = f"""
🧠 **Добро пожаловать в NeuroFlow!**

Привет, {message.from_user.first_name}! 

NeuroFlow - это мощный AI-ассистент для генерации контента, изображений и автоматизации задач.

🚀 **Возможности:**
• Генерация текстов с помощью AI
• Создание изображений по описанию  
• Автопостинг в каналы
• Аналитика и статистика
• И многое другое!

Нажмите кнопку ниже, чтобы открыть приложение:
"""
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "about")
async def about_callback(callback: types.CallbackQuery):
    """Handle about button"""
    about_text = """
🧠 **О NeuroFlow**

NeuroFlow - это современный AI-бот для Telegram, который поможет вам:

🎯 **Основные функции:**
• Генерация текстов с помощью Groq AI
• Создание изображений по описанию
• Автопостинг контента в каналы
• Аналитика и статистика
• Управление подписками

💎 **Преимущества:**
• Быстрая обработка запросов
• Высокое качество генерации
• Простой и понятный интерфейс
• Регулярные обновления

🔧 **Версия:** 2.0
📅 **Обновлено:** Январь 2026
"""
    
    await callback.message.edit_text(
        about_text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "subscription")
async def subscription_callback(callback: types.CallbackQuery):
    """Handle subscription button"""
    sub_text = """
💎 **Подписка NeuroFlow**

Получите полный доступ ко всем функциям!

📋 **Тарифы:**
• 1 месяц - 500₽
• 3 месяца - 1275₽ (скидка 15%)
• Пожизненная - 5000₽

🎁 **Что включено:**
• Безлимитная генерация текстов
• Создание изображений
• Автопостинг в каналы
• Приоритетная поддержка
• Все будущие обновления

Для оформления подписки обратитесь к администратору.
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Связаться с админом", url=f"tg://user?id={ADMIN_USER_ID}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(
        sub_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support_callback(callback: types.CallbackQuery):
    """Handle support button"""
    support_text = """
📞 **Поддержка NeuroFlow**

Нужна помощь? Мы всегда готовы помочь!

🔧 **Способы связи:**
• Написать администратору
• Задать вопрос в чате поддержки
• Изучить документацию

⏰ **Время работы:**
Поддержка работает 24/7

💬 **Частые вопросы:**
• Как оформить подписку?
• Как использовать генерацию изображений?
• Проблемы с доступом к функциям?

Все ответы вы найдете в нашем WebApp!
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Написать админу", url=f"tg://user?id={ADMIN_USER_ID}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(
        support_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery):
    """Handle back to main button"""
    welcome_text = """
🧠 **NeuroFlow - AI Assistant**

Выберите действие из меню ниже:
"""
    
    await callback.message.edit_text(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    """Show bot statistics (admin only)"""
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("❌ Эта команда доступна только администратору.")
        return
    
    total_users = len(users)
    stats_text = f"""
📊 **Статистика бота**

👥 Всего пользователей: {total_users}
🕐 Время работы: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
🌐 WebApp URL: {WEBAPP_URL}

📋 **Последние пользователи:**
"""
    
    # Show last 5 users
    recent_users = list(users.items())[-5:]
    for user_id, user_data in recent_users:
        stats_text += f"• @{user_data['username']} (ID: {user_id})\n"
    
    await message.answer(stats_text, parse_mode="Markdown")

@dp.message(Command("broadcast"))
async def broadcast_command(message: types.Message):
    """Broadcast message to all users (admin only)"""
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("❌ Эта команда доступна только администратору.")
        return
    
    # Get message text after command
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("❌ Укажите текст для рассылки после команды.")
        return
    
    sent_count = 0
    failed_count = 0
    
    for user_id in users.keys():
        try:
            await bot.send_message(user_id, text, parse_mode="Markdown")
            sent_count += 1
        except Exception as e:
            logger.warning(f"Failed to send message to {user_id}: {e}")
            failed_count += 1
    
    await message.answer(
        f"📤 Рассылка завершена!\n"
        f"✅ Отправлено: {sent_count}\n"
        f"❌ Ошибок: {failed_count}"
    )

@dp.message()
async def handle_all_messages(message: types.Message):
    """Handle all other messages"""
    user_id = message.from_user.id
    
    # Update user interaction time
    if user_id in users:
        users[user_id]["last_interaction"] = datetime.now()
    
    # Simple response
    await message.answer(
        "🧠 Привет! Используйте кнопки меню для навигации или откройте WebApp для полного функционала.",
        reply_markup=get_main_keyboard()
    )

async def main():
    """Main function"""
    logger.info("🚀 Starting NeuroFlow Bot (Simple Version)...")
    logger.info(f"Bot Token: {BOT_TOKEN[:10]}...")
    logger.info(f"Admin ID: {ADMIN_USER_ID}")
    logger.info(f"WebApp URL: {WEBAPP_URL}")
    
    try:
        # Get bot info
        bot_info = await bot.get_me()
        logger.info(f"✅ Bot started: @{bot_info.username}")
        
        # Notify admin
        if ADMIN_USER_ID:
            try:
                await bot.send_message(
                    ADMIN_USER_ID,
                    f"🚀 **NeuroFlow Bot запущен!**\n\n"
                    f"🤖 Бот: @{bot_info.username}\n"
                    f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                    f"🌐 WebApp: {WEBAPP_URL}\n\n"
                    f"Система готова к работе! ✅",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Could not notify admin: {e}")
        
        # Start polling
        logger.info("🔄 Starting polling...")
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🔄 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)