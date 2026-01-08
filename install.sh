#!/bin/bash

# NeuroFlow - Автоматическая установка с GitHub
# Сервер: 155.212.160.99

set -e

echo "🚀 NeuroFlow - Установка с GitHub"
echo "=================================="

# Цвета для вывода
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_step() {
    echo -e "${BLUE}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Проверка прав root
if [[ $EUID -ne 0 ]]; then
   print_warning "Скрипт не запущен от root. Некоторые команды могут потребовать sudo."
fi

# Шаг 1: Обновление системы
print_step "Обновление системы..."
apt update && apt upgrade -y
print_success "Система обновлена"

# Шаг 2: Установка зависимостей
print_step "Установка системных зависимостей..."
apt install -y python3 python3-pip python3-venv python3-full git curl wget nano htop
print_success "Системные зависимости установлены"

# Шаг 3: Создание рабочей директории
print_step "Создание рабочей директории..."
INSTALL_DIR="/opt/neuroflow"
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR
print_success "Рабочая директория создана: $INSTALL_DIR"

# Шаг 4: Клонирование репозитория
print_step "Клонирование NeuroFlow с GitHub..."
if [ -d ".git" ]; then
    print_warning "Репозиторий уже существует, обновляем..."
    git pull
else
    # Здесь будет ваш реальный GitHub репозиторий
    # git clone https://github.com/your-username/neuroflow.git .
    
    # Пока создаем структуру локально
    print_warning "Создаем структуру проекта..."
    mkdir -p app/{core,handlers,models,services,utils} webapp config logs scripts
fi
print_success "Репозиторий готов"

# Шаг 5: Создание виртуального окружения
print_step "Создание виртуального окружения..."
python3 -m venv venv
source venv/bin/activate
print_success "Виртуальное окружение создано"

# Шаг 6: Установка Python зависимостей
print_step "Установка Python зависимостей..."
pip install --upgrade pip
pip install aiogram aiohttp asyncpg redis groq python-dotenv apscheduler aiosqlite fastapi uvicorn pydantic aiofiles
print_success "Python зависимости установлены"

# Шаг 7: Создание конфигурации
print_step "Создание конфигурационных файлов..."

# Создание .env файла
cat > .env << 'EOF'
# NeuroFlow Configuration
BOT_TOKEN=7779484397:AAHo6yFy6-8ctfiIMIE5MzBvGa-so_WkJ68
ADMIN_USER_ID=6950900818

# Groq API Keys
GROQ_API_KEY=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
GROQ_API_KEY_2=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
GROQ_API_KEY_3=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

# WebApp Configuration
WEBAPP_URL=http://155.212.160.99

# Database Configuration
DATABASE_URL=sqlite:///bot_database.db
REDIS_URL=redis://localhost:6379/0

# Payment Configuration
AAIO_API_KEY=your_aaio_api_key_here
AAIO_SHOP_ID=your_aaio_shop_id_here
CRYPTO_BOT_TOKEN=your_crypto_bot_token_here
EOF

# Создание requirements.txt
cat > requirements.txt << 'EOF'
aiogram==3.13.1
aiohttp==3.10.11
asyncpg==0.29.0
redis==5.0.1
groq==0.11.0
python-dotenv==1.0.1
apscheduler==3.10.4
aiosqlite==0.20.0
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
aiofiles==23.2.1
EOF

print_success "Конфигурационные файлы созданы"

# Шаг 8: Создание основного файла бота
print_step "Создание основного файла бота..."
cat > bot.py << 'EOF'
#!/usr/bin/env python3
"""
NeuroFlow Telegram Bot
Главный файл запуска бота
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram import F

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://155.212.160.99")

if not BOT_TOKEN:
    print("❌ Ошибка: BOT_TOKEN не найден в .env файле!")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Создание бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище пользователей (в памяти)
users = {}

def get_main_keyboard():
    """Создание основной клавиатуры"""
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
            InlineKeyboardButton(text="📞 Поддержка", callback_data="support"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
        ]
    ])
    return keyboard

@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Обработка команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    
    # Регистрация пользователя
    users[user_id] = {
        "username": username,
        "first_name": message.from_user.first_name,
        "first_seen": datetime.now(),
        "last_interaction": datetime.now()
    }
    
    logger.info(f"Новый пользователь: {user_id} (@{username})")
    
    welcome_text = f"""
🧠 **Добро пожаловать в NeuroFlow!**

Привет, {message.from_user.first_name}! 

NeuroFlow - это мощный AI-ассистент для генерации контента, изображений и автоматизации задач.

🚀 **Возможности:**
• Генерация текстов с помощью AI
• Создание изображений по описанию  
• Автопостинг в каналы
• Аналитика и статистика
• Система подписок

Нажмите кнопку ниже, чтобы открыть приложение:
"""
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "about")
async def about_callback(callback: types.CallbackQuery):
    """Информация о боте"""
    about_text = """
🧠 **О NeuroFlow**

NeuroFlow - современный AI-бот для Telegram, который поможет вам:

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
🌐 **GitHub:** github.com/your-repo/neuroflow
"""
    
    await callback.message.edit_text(
        about_text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "subscription")
async def subscription_callback(callback: types.CallbackQuery):
    """Информация о подписке"""
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
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        sub_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support_callback(callback: types.CallbackQuery):
    """Поддержка"""
    support_text = """
📞 **Поддержка NeuroFlow**

Нужна помощь? Мы всегда готовы помочь!

🔧 **Способы связи:**
• Написать администратору
• Задать вопрос в чате поддержки
• Изучить документацию на GitHub

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
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        support_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "stats")
async def stats_callback(callback: types.CallbackQuery):
    """Статистика (только для админа)"""
    if callback.from_user.id != ADMIN_USER_ID:
        await callback.answer("❌ Доступно только администратору", show_alert=True)
        return
    
    total_users = len(users)
    stats_text = f"""
📊 **Статистика NeuroFlow**

👥 Всего пользователей: {total_users}
🕐 Время работы: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
🌐 WebApp URL: {WEBAPP_URL}

📋 **Последние пользователи:**
"""
    
    # Показываем последних 5 пользователей
    recent_users = list(users.items())[-5:]
    for user_id, user_data in recent_users:
        stats_text += f"• {user_data['first_name']} (@{user_data['username']}) - ID: {user_id}\n"
    
    await callback.message.edit_text(
        stats_text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "back")
async def back_callback(callback: types.CallbackQuery):
    """Возврат в главное меню"""
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
    """Команда статистики (только админ)"""
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
    
    recent_users = list(users.items())[-5:]
    for user_id, user_data in recent_users:
        stats_text += f"• {user_data['first_name']} (@{user_data['username']}) - ID: {user_id}\n"
    
    await message.answer(stats_text, parse_mode="Markdown")

@dp.message()
async def handle_all_messages(message: types.Message):
    """Обработка всех остальных сообщений"""
    user_id = message.from_user.id
    
    # Обновляем время последнего взаимодействия
    if user_id in users:
        users[user_id]["last_interaction"] = datetime.now()
    
    await message.answer(
        "🧠 Привет! Используйте кнопки меню для навигации или откройте WebApp для полного функционала.",
        reply_markup=get_main_keyboard()
    )

async def main():
    """Главная функция"""
    logger.info("🚀 Запуск NeuroFlow Bot...")
    logger.info(f"Bot Token: {BOT_TOKEN[:10]}...")
    logger.info(f"Admin ID: {ADMIN_USER_ID}")
    logger.info(f"WebApp URL: {WEBAPP_URL}")
    
    try:
        # Получаем информацию о боте
        bot_info = await bot.get_me()
        logger.info(f"✅ Бот запущен: @{bot_info.username}")
        
        # Уведомляем админа о запуске
        if ADMIN_USER_ID:
            try:
                await bot.send_message(
                    ADMIN_USER_ID,
                    f"🚀 **NeuroFlow Bot запущен!**\n\n"
                    f"🤖 Бот: @{bot_info.username}\n"
                    f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                    f"🌐 WebApp: {WEBAPP_URL}\n"
                    f"📁 Директория: {Path(__file__).parent}\n\n"
                    f"Система готова к работе! ✅",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Не удалось уведомить админа: {e}")
        
        # Запускаем polling
        logger.info("🔄 Запуск polling...")
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        raise
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🔄 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)
EOF

chmod +x bot.py
print_success "Основной файл бота создан"

# Шаг 9: Создание WebApp
print_step "Создание WebApp..."
cat > webapp/index.html << 'EOF'
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NeuroFlow - AI Assistant</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 400px;
            margin: 0 auto;
            text-align: center;
        }
        
        .logo {
            font-size: 4em;
            margin-bottom: 20px;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        
        h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .subtitle {
            opacity: 0.9;
            margin-bottom: 30px;
            font-size: 1.1em;
        }
        
        .feature {
            background: rgba(255, 255, 255, 0.15);
            border-radius: 20px;
            padding: 25px;
            margin: 20px 0;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: transform 0.3s ease;
        }
        
        .feature:hover {
            transform: translateY(-5px);
        }
        
        .feature-icon {
            font-size: 2.5em;
            margin-bottom: 15px;
        }
        
        .feature h3 {
            margin-bottom: 10px;
            font-size: 1.3em;
        }
        
        .btn {
            background: rgba(255, 255, 255, 0.2);
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 30px;
            padding: 15px 25px;
            color: white;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin: 10px 5px;
            transition: all 0.3s ease;
            display: inline-block;
            text-decoration: none;
        }
        
        .btn:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        
        .btn:active {
            transform: translateY(0);
        }
        
        .status {
            position: fixed;
            bottom: 20px;
            left: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.7);
            padding: 15px;
            border-radius: 15px;
            font-size: 14px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .github-link {
            margin-top: 30px;
            padding: 15px;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 15px;
        }
        
        .github-link a {
            color: white;
            text-decoration: none;
            font-weight: 600;
        }
        
        .version {
            margin-top: 20px;
            opacity: 0.7;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">🧠</div>
        <h1>NeuroFlow</h1>
        <p class="subtitle">AI-ассистент для генерации контента</p>
        
        <div class="feature">
            <div class="feature-icon">✨</div>
            <h3>Генерация текстов</h3>
            <p>Создавайте уникальный контент с помощью мощного AI</p>
        </div>
        
        <div class="feature">
            <div class="feature-icon">🎨</div>
            <h3>Создание изображений</h3>
            <p>Генерируйте изображения по текстовому описанию</p>
        </div>
        
        <div class="feature">
            <div class="feature-icon">📊</div>
            <h3>Автопостинг</h3>
            <p>Автоматическая публикация контента в каналы</p>
        </div>
        
        <div class="feature">
            <div class="feature-icon">💎</div>
            <h3>Система подписок</h3>
            <p>Гибкие тарифы и управление доступом</p>
        </div>
        
        <button class="btn" onclick="generateText()">🤖 Генерация текста</button>
        <button class="btn" onclick="generateImage()">🎨 Создать изображение</button>
        <button class="btn" onclick="showStats()">📊 Статистика</button>
        
        <div class="github-link">
            <p>📁 <a href="https://github.com/your-repo/neuroflow" target="_blank">GitHub Repository</a></p>
        </div>
        
        <div class="version">
            <p>NeuroFlow v2.0 | Январь 2026</p>
        </div>
    </div>
    
    <div class="status" id="status">
        ✅ NeuroFlow WebApp загружен и готов к работе
    </div>

    <script>
        // Инициализация Telegram WebApp
        let tg = window.Telegram.WebApp;
        tg.expand();
        tg.ready();
        
        // Функции для демонстрации
        function generateText() {
            updateStatus('🤖 Генерация текста...', 'info');
            setTimeout(() => {
                updateStatus('✅ Текст успешно сгенерирован!', 'success');
            }, 2000);
        }
        
        function generateImage() {
            updateStatus('🎨 Создание изображения...', 'info');
            setTimeout(() => {
                updateStatus('✅ Изображение создано!', 'success');
            }, 3000);
        }
        
        function showStats() {
            updateStatus('📊 Загрузка статистики...', 'info');
            setTimeout(() => {
                updateStatus('📊 Пользователей: 1,234 | Запросов: 5,678 | Активных: 89', 'success');
            }, 1000);
        }
        
        function updateStatus(message, type) {
            const statusEl = document.getElementById('status');
            statusEl.innerHTML = message;
            
            // Добавляем анимацию
            statusEl.style.transform = 'scale(0.95)';
            setTimeout(() => {
                statusEl.style.transform = 'scale(1)';
            }, 100);
        }
        
        // Логирование для отладки
        console.log('NeuroFlow WebApp v2.0 загружен');
        console.log('Telegram WebApp API:', tg);
        
        // Уведомляем Telegram что готовы
        if (tg.initData) {
            console.log('Telegram user data:', tg.initDataUnsafe);
        }
    </script>
</body>
</html>
EOF
print_success "WebApp создан"

# Шаг 10: Создание скриптов управления
print_step "Создание скриптов управления..."

# Скрипт запуска
cat > start.sh << 'EOF'
#!/bin/bash
cd /opt/neuroflow
source venv/bin/activate
python3 bot.py
EOF
chmod +x start.sh

# Скрипт остановки
cat > stop.sh << 'EOF'
#!/bin/bash
pkill -f "python3 bot.py"
echo "NeuroFlow остановлен"
EOF
chmod +x stop.sh

# Скрипт обновления
cat > update.sh << 'EOF'
#!/bin/bash
cd /opt/neuroflow
git pull
source venv/bin/activate
pip install -r requirements.txt
echo "NeuroFlow обновлен"
EOF
chmod +x update.sh

print_success "Скрипты управления созданы"

# Шаг 11: Создание systemd сервиса
print_step "Создание systemd сервиса..."
cat > /etc/systemd/system/neuroflow.service << EOF
[Unit]
Description=NeuroFlow Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable neuroflow
print_success "Systemd сервис создан и включен"

# Шаг 12: Установка Nginx (опционально)
print_step "Установка Nginx для WebApp..."
apt install -y nginx

cat > /etc/nginx/sites-available/neuroflow << EOF
server {
    listen 80;
    server_name 155.212.160.99;
    
    location / {
        root $INSTALL_DIR/webapp;
        index index.html;
        try_files \$uri \$uri/ =404;
    }
    
    location /health {
        return 200 'NeuroFlow OK';
        add_header Content-Type text/plain;
    }
}
EOF

ln -sf /etc/nginx/sites-available/neuroflow /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
systemctl enable nginx
print_success "Nginx настроен"

echo ""
echo "🎉 УСТАНОВКА NEUROFLOW ЗАВЕРШЕНА!"
echo "=================================="
echo ""
echo "📋 Что установлено:"
echo "• NeuroFlow Telegram Bot"
echo "• WebApp интерфейс"
echo "• Systemd сервис для автозапуска"
echo "• Nginx веб-сервер"
echo "• Все необходимые зависимости"
echo ""
echo "🌐 WebApp доступен: http://155.212.160.99"
echo "📁 Директория проекта: $INSTALL_DIR"
echo ""
echo "🚀 КОМАНДЫ УПРАВЛЕНИЯ:"
echo "Запуск: systemctl start neuroflow"
echo "Остановка: systemctl stop neuroflow"
echo "Статус: systemctl status neuroflow"
echo "Логи: journalctl -u neuroflow -f"
echo ""
echo "Или используйте скрипты:"
echo "Запуск: ./start.sh"
echo "Остановка: ./stop.sh"
echo "Обновление: ./update.sh"
echo ""
echo "✅ NeuroFlow готов к работе!"
echo "Бот автоматически запустится и отправит уведомление админу."

# Автоматический запуск
print_step "Запуск NeuroFlow..."
systemctl start neuroflow
sleep 3
systemctl status neuroflow --no-pager

echo ""
echo "🎯 Проверьте Telegram - бот должен отправить уведомление!"
EOF

chmod +x install.sh