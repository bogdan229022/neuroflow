import os
from pathlib import Path
from dotenv import load_dotenv
from typing import List

# Загружаем .env из корня проекта
project_root = Path(__file__).parent.parent.parent
env_path = project_root / '.env'
load_dotenv(env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Groq API Keys Pool - Ultra-Scaling (7 Keys)
GROQ_API_KEYS = [
    os.getenv("GROQ_API_KEY"),  # Основной ключ
    os.getenv("GROQ_API_KEY_2"),  # Дополнительный ключ 2
    os.getenv("GROQ_API_KEY_3"),  # Дополнительный ключ 3
    os.getenv("GROQ_API_KEY_4"),  # Дополнительный ключ 4
    os.getenv("GROQ_API_KEY_5"),  # Дополнительный ключ 5
    os.getenv("GROQ_API_KEY_6"),  # Дополнительный ключ 6
    os.getenv("GROQ_API_KEY_7"),  # Дополнительный ключ 7
]

# Фильтруем пустые ключи
GROQ_API_KEYS = [key for key in GROQ_API_KEYS if key and key.strip()]

# Fallback на старую переменную если новые не заданы
if not GROQ_API_KEYS:
    legacy_key = os.getenv("GROQ_API_KEY")
    if legacy_key:
        GROQ_API_KEYS = [legacy_key]

# Redis Configuration for Ultra-Scaling
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_POOL_MAX_CONNECTIONS = int(os.getenv("REDIS_POOL_MAX_CONNECTIONS", "50"))
REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL", "3600"))  # 1 hour default

ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))

# WebApp Configuration
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://localhost:8081")

# PostgreSQL Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neuroflow:password@localhost:5432/neuroflow")
DATABASE_POOL_MIN_SIZE = int(os.getenv("DATABASE_POOL_MIN_SIZE", "10"))
DATABASE_POOL_MAX_SIZE = int(os.getenv("DATABASE_POOL_MAX_SIZE", "50"))

# Image Generation API Keys
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
STABLE_DIFFUSION_API_KEY = os.getenv("STABLE_DIFFUSION_API_KEY")
REPLICATE_API_KEY = os.getenv("REPLICATE_API_KEY")

# Новые платежные системы
AAIO_API_KEY = os.getenv("AAIO_API_KEY")
AAIO_SHOP_ID = os.getenv("AAIO_SHOP_ID")
AAIO_SECRET_KEY = os.getenv("AAIO_SECRET_KEY")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")

# Цены подписки (в рублях для СБП, в долларах для крипты, в Stars для Telegram)
SUBSCRIPTION_PRICES = {
    "1_month": {
        "days": 30, 
        "title": "Подписка на 1 месяц",
        "sbp_rub": 500,
        "crypto_usd": 5,
        "stars": 100
    },
    "3_months": {
        "days": 90, 
        "title": "Подписка на 3 месяца (скидка 15%)",
        "sbp_rub": 1275,  # 500*3*0.85
        "crypto_usd": 12.75,  # 5*3*0.85
        "stars": 213  # 100*3*0.85
    },
    "lifetime": {
        "days": 36500,  # 100 лет
        "title": "ПОЖИЗНЕННАЯ подписка",
        "sbp_rub": 5000,
        "crypto_usd": 50,
        "stars": 1000
    }
}

# Поддерживаемые криптовалюты
CRYPTO_CURRENCIES = ["USDT", "TON", "BTC", "ETH"]

# Настройки автопостинга
AUTO_POST_INTERVAL_HOURS = 6  # Интервал автопостинга в часах
DATABASE_PATH = "bot_database.db"