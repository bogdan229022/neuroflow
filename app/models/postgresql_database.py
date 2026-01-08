"""
PostgreSQL Database Implementation for NeuroFlow Bot
High-performance database with connection pooling for thousands of concurrent users
"""

import asyncio
import asyncpg
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import json
import os
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class PostgreSQLDatabase:
    """PostgreSQL database with connection pooling for high-performance operations"""
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv(
            'DATABASE_URL', 
            'postgresql://neuroflow:password@localhost:5432/neuroflow'
        )
        self.pool: Optional[asyncpg.Pool] = None
        self._lock = asyncio.Lock()
    
    async def init_pool(self, min_size: int = 10, max_size: int = 50):
        """Инициализация пула соединений"""
        if self.pool is None:
            async with self._lock:
                if self.pool is None:  # Double-check locking
                    try:
                        self.pool = await asyncpg.create_pool(
                            self.database_url,
                            min_size=min_size,
                            max_size=max_size,
                            command_timeout=30,
                            server_settings={
                                'jit': 'off',  # Отключаем JIT для стабильности
                                'application_name': 'NeuroFlow Bot'
                            }
                        )
                        logger.info(f"PostgreSQL pool initialized: {min_size}-{max_size} connections")
                        
                        # Инициализируем схему БД
                        await self.init_schema()
                        
                    except Exception as e:
                        logger.error(f"Failed to initialize PostgreSQL pool: {e}")
                        raise
    
    async def close_pool(self):
        """Закрытие пула соединений"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("PostgreSQL pool closed")
    
    @asynccontextmanager
    async def get_connection(self):
        """Контекстный менеджер для получения соединения из пула"""
        if not self.pool:
            await self.init_pool()
        
        async with self.pool.acquire() as connection:
            yield connection
    
    async def init_schema(self):
        """Инициализация схемы базы данных"""
        async with self.get_connection() as conn:
            # Создаем расширения
            await conn.execute("CREATE EXTENSION IF NOT EXISTS btree_gin;")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
            
            # Таблица пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    subscription_expiry BIGINT,
                    is_admin BOOLEAN DEFAULT FALSE,
                    is_lifetime BOOLEAN DEFAULT FALSE,
                    is_trial_used BOOLEAN DEFAULT FALSE,
                    trial_expiry BIGINT,
                    last_interaction_date BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                    upsell_sent BOOLEAN DEFAULT FALSE,
                    feedback_sent BOOLEAN DEFAULT FALSE,
                    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())
                );
            """)
            
            # Индексы для пользователей
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_subscription_expiry 
                ON users(subscription_expiry) WHERE subscription_expiry IS NOT NULL;
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_trial_expiry 
                ON users(trial_expiry) WHERE trial_expiry IS NOT NULL;
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_last_interaction 
                ON users(last_interaction_date);
            """)
            
            # Таблица настроек пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                    channel_id TEXT,
                    topic TEXT,
                    system_instruction TEXT,
                    is_active BOOLEAN DEFAULT FALSE,
                    last_post_time BIGINT,
                    generate_images BOOLEAN DEFAULT TRUE,
                    updated_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())
                );
            """)
            
            # Индексы для настроек
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_settings_active 
                ON user_settings(is_active) WHERE is_active = TRUE;
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_settings_last_post 
                ON user_settings(last_post_time) WHERE last_post_time IS NOT NULL;
            """)
            
            # Таблица транзакций
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id),
                    amount DECIMAL(10,2) NOT NULL,
                    currency VARCHAR(10) NOT NULL,
                    method VARCHAR(50) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    external_id TEXT,
                    subscription_type VARCHAR(50) NOT NULL,
                    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                    completed_at BIGINT
                );
            """)
            
            # Индексы для транзакций
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_external_id 
                ON transactions(external_id) WHERE external_id IS NOT NULL;
            """)
            
            # Таблица системной конфигурации
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS system_config (
                    config_key VARCHAR(100) PRIMARY KEY,
                    config_value TEXT,
                    is_encrypted BOOLEAN DEFAULT FALSE,
                    updated_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                    updated_by BIGINT
                );
            """)
            
            # Таблица статистики
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id SERIAL PRIMARY KEY,
                    posts_count BIGINT DEFAULT 0,
                    images_count BIGINT DEFAULT 0,
                    subscriptions_stars BIGINT DEFAULT 0,
                    subscriptions_crypto BIGINT DEFAULT 0,
                    subscriptions_sbp BIGINT DEFAULT 0,
                    subscriptions_manual BIGINT DEFAULT 0,
                    revenue_stars DECIMAL(10,2) DEFAULT 0,
                    revenue_crypto_usd DECIMAL(10,2) DEFAULT 0,
                    revenue_crypto_btc DECIMAL(15,8) DEFAULT 0,
                    revenue_crypto_eth DECIMAL(15,8) DEFAULT 0,
                    revenue_crypto_ton DECIMAL(15,8) DEFAULT 0,
                    revenue_crypto_usdt DECIMAL(10,2) DEFAULT 0,
                    revenue_sbp_rub DECIMAL(10,2) DEFAULT 0,
                    revenue_manual_rub DECIMAL(10,2) DEFAULT 0,
                    last_updated BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())
                );
            """)
            
            # Таблица истории платежей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS history_payments (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id),
                    payment_method VARCHAR(50) NOT NULL,
                    subscription_type VARCHAR(50) NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    currency VARCHAR(10) NOT NULL,
                    transaction_id TEXT,
                    payment_date BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                    week_number INTEGER,
                    year INTEGER
                );
            """)
            
            # Индексы для истории платежей
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_payments_user_id 
                ON history_payments(user_id);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_payments_date 
                ON history_payments(payment_date);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_payments_week 
                ON history_payments(year, week_number);
            """)
            
            # Таблица использования промокодов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS promo_usage (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id),
                    promo_code VARCHAR(50) NOT NULL,
                    discount_percent INTEGER NOT NULL,
                    original_amount DECIMAL(10,2) NOT NULL,
                    discounted_amount DECIMAL(10,2) NOT NULL,
                    used_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                    UNIQUE(user_id, promo_code)  -- КРИТИЧЕСКОЕ: предотвращает дублирование
                );
            """)
            
            # Индексы для промокодов
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_promo_usage_user_id ON promo_usage(user_id);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_promo_usage_code ON promo_usage(promo_code);
            """)
            
            # Таблица очереди изображений
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS image_queue (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id),
                    prompt TEXT NOT NULL,
                    topic TEXT,
                    status VARCHAR(20) DEFAULT 'pending',
                    provider VARCHAR(50),
                    image_url TEXT,
                    error_message TEXT,
                    attempts INTEGER DEFAULT 0,
                    max_attempts INTEGER DEFAULT 3,
                    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                    started_at BIGINT,
                    completed_at BIGINT,
                    priority INTEGER DEFAULT 0
                );
            """)
            
            # Индексы для очереди изображений
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_image_queue_status_priority 
                ON image_queue(status, priority DESC, created_at ASC) 
                WHERE status = 'pending';
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_image_queue_user_id ON image_queue(user_id);
            """)
            
            # ========== АВТОПИЛОТ СИСТЕМА (ОТДЕЛЬНЫЕ ПОДПИСКИ) ==========
            
            # Таблица тарифов автопилота
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS autopilot_rates (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    duration_days INTEGER NOT NULL,
                    price_rub DECIMAL(10,2) NOT NULL,
                    price_stars INTEGER NOT NULL,
                    max_channels INTEGER DEFAULT 5,
                    max_posts_per_day INTEGER DEFAULT 10,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                    updated_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())
                );
            """)
            
            # Таблица подписок на автопилот (ОТДЕЛЬНО от основных подписок)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS autopilot_subscriptions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id),
                    rate_id INTEGER REFERENCES autopilot_rates(id),
                    expires_at BIGINT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    max_channels INTEGER DEFAULT 5,
                    max_posts_per_day INTEGER DEFAULT 10,
                    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                    activated_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                    UNIQUE(user_id, is_active) DEFERRABLE INITIALLY DEFERRED
                );
            """)
            
            # Таблица покупок автопилота
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS autopilot_purchases (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id),
                    rate_id INTEGER REFERENCES autopilot_rates(id),
                    subscription_id INTEGER REFERENCES autopilot_subscriptions(id),
                    amount DECIMAL(10,2) NOT NULL,
                    currency VARCHAR(10) NOT NULL,
                    payment_method VARCHAR(50) NOT NULL,
                    transaction_id TEXT,
                    status VARCHAR(20) DEFAULT 'completed',
                    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())
                );
            """)
            
            # Таблица конфигураций каналов автопилота
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS autopilot_configs (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id),
                    channel_id VARCHAR(100) NOT NULL,
                    channel_name VARCHAR(200),
                    topic TEXT NOT NULL,
                    tone_of_voice VARCHAR(100) DEFAULT 'professional',
                    posts_per_day INTEGER DEFAULT 1,
                    keywords TEXT,
                    generate_images BOOLEAN DEFAULT TRUE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                    updated_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                    last_post_at BIGINT,
                    total_posts INTEGER DEFAULT 0,
                    successful_posts INTEGER DEFAULT 0,
                    UNIQUE(user_id, channel_id)
                );
            """)
            
            # Таблица постов автопилота (история)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS autopilot_posts (
                    id SERIAL PRIMARY KEY,
                    config_id INTEGER REFERENCES autopilot_configs(id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL REFERENCES users(user_id),
                    channel_id VARCHAR(100) NOT NULL,
                    post_content TEXT NOT NULL,
                    image_url TEXT,
                    news_sources TEXT, -- JSON с источниками новостей
                    status VARCHAR(20) DEFAULT 'published',
                    telegram_message_id BIGINT,
                    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW()),
                    published_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())
                );
            """)
            
            # Индексы для автопилота
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_autopilot_subscriptions_user_active 
                ON autopilot_subscriptions(user_id, is_active) WHERE is_active = TRUE;
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_autopilot_subscriptions_expires 
                ON autopilot_subscriptions(expires_at) WHERE is_active = TRUE;
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_autopilot_configs_user_active 
                ON autopilot_configs(user_id, is_active) WHERE is_active = TRUE;
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_autopilot_configs_channel 
                ON autopilot_configs(channel_id);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_autopilot_posts_config 
                ON autopilot_posts(config_id, created_at DESC);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_autopilot_posts_user 
                ON autopilot_posts(user_id, created_at DESC);
            """)
            
            # Инициализируем базовые данные
            await self._init_default_data(conn)
            
            logger.info("PostgreSQL schema initialized successfully")
    
    async def _init_default_data(self, conn):
        """Инициализация базовых данных"""
        # Инициализируем статистику если её нет
        stats_count = await conn.fetchval("SELECT COUNT(*) FROM stats")
        if stats_count == 0:
            await conn.execute("INSERT INTO stats DEFAULT VALUES")
        
        # Инициализируем тарифы автопилота если их нет
        rates_count = await conn.fetchval("SELECT COUNT(*) FROM autopilot_rates")
        if rates_count == 0:
            # Базовые тарифы автопилота (ОТДЕЛЬНЫЕ от основных подписок)
            await conn.execute("""
                INSERT INTO autopilot_rates (name, description, duration_days, price_rub, price_stars, max_channels, max_posts_per_day) VALUES
                ('Месяц', 'Автопилот на 1 месяц - до 3 каналов', 30, 299, 60, 3, 5),
                ('3 месяца', 'Автопилот на 3 месяца - до 5 каналов (экономия 98₽)', 90, 799, 160, 5, 8),
                ('Год', 'Автопилот на 1 год - до 10 каналов (экономия 589₽)', 365, 2999, 600, 10, 15)
            """)
            logger.info("Autopilot rates initialized")
        
        # Инициализируем базовые конфигурации
        from app.core.config import GROQ_API_KEYS
        
        default_configs = {
            'groq_api_key': GROQ_API_KEYS[0] if GROQ_API_KEYS else '',
            'groq_api_key_2': GROQ_API_KEYS[1] if len(GROQ_API_KEYS) > 1 else '',
            'groq_api_key_3': GROQ_API_KEYS[2] if len(GROQ_API_KEYS) > 2 else '',
            'groq_api_key_4': GROQ_API_KEYS[3] if len(GROQ_API_KEYS) > 3 else '',
            'telegram_stars_enabled': 'true',
            'manual_payment_enabled': 'true'
        }
        
        for key, value in default_configs.items():
            if value:  # Только если значение не пустое
                await conn.execute("""
                    INSERT INTO system_config (config_key, config_value) 
                    VALUES ($1, $2) 
                    ON CONFLICT (config_key) DO NOTHING
                """, key, value)
    
    # Методы для работы с пользователями
    async def add_user(self, user_id: int, is_admin: bool = False) -> bool:
        """Добавление нового пользователя с автоматической активацией триала"""
        async with self.get_connection() as conn:
            # Проверяем, существует ли пользователь
            existing = await conn.fetchval(
                "SELECT user_id FROM users WHERE user_id = $1", user_id
            )
            
            if not existing:
                # Новый пользователь - активируем триал на 24 часа
                current_time = int(datetime.now().timestamp())
                trial_expiry = current_time + (24 * 60 * 60)  # 24 часа
                
                async with conn.transaction():
                    await conn.execute("""
                        INSERT INTO users (user_id, is_admin, is_trial_used, trial_expiry, subscription_expiry) 
                        VALUES ($1, $2, TRUE, $3, $3)
                    """, user_id, is_admin, trial_expiry, trial_expiry)
                    
                    await conn.execute("""
                        INSERT INTO user_settings (user_id) VALUES ($1)
                    """, user_id)
                
                logger.info(f"New user {user_id} added with 24h trial")
                return True
            
            return False
    
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о пользователе"""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", user_id
            )
            return dict(row) if row else None
    
    async def update_subscription(self, user_id: int, days: int, is_lifetime: bool = False):
        """Обновление подписки пользователя"""
        current_time = int(datetime.now().timestamp())
        
        async with self.get_connection() as conn:
            if is_lifetime:
                # Пожизненная подписка
                await conn.execute("""
                    UPDATE users 
                    SET is_lifetime = TRUE, subscription_expiry = $1 
                    WHERE user_id = $2
                """, current_time + (100 * 365 * 24 * 60 * 60), user_id)
            else:
                # Получаем текущую дату окончания подписки
                current_expiry = await conn.fetchval(
                    "SELECT subscription_expiry FROM users WHERE user_id = $1", user_id
                )
                
                if current_expiry and current_expiry > current_time:
                    # Если подписка еще активна, добавляем дни к текущей дате окончания
                    new_expiry = current_expiry + (days * 24 * 60 * 60)
                else:
                    # Если подписки нет или она истекла, добавляем дни к текущему времени
                    new_expiry = current_time + (days * 24 * 60 * 60)
                
                await conn.execute("""
                    UPDATE users SET subscription_expiry = $1 WHERE user_id = $2
                """, new_expiry, user_id)
    
    async def is_subscription_active(self, user_id: int) -> bool:
        """Проверка активности подписки (включая триал)"""
        async with self.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT subscription_expiry, is_lifetime, trial_expiry 
                FROM users WHERE user_id = $1
            """, user_id)
            
            if not row:
                return False
            
            current_time = int(datetime.now().timestamp())
            
            # Если пожизненная подписка
            if row['is_lifetime']:
                return True
            
            # Проверяем триал
            if row['trial_expiry'] and row['trial_expiry'] > current_time:
                return True
            
            # Проверяем обычную подписку
            if row['subscription_expiry'] and row['subscription_expiry'] > current_time:
                return True
            
            return False
    
    async def update_last_interaction(self, user_id: int):
        """Обновление времени последнего взаимодействия (оптимизировано для высокой нагрузки)"""
        current_time = int(datetime.now().timestamp())
        
        async with self.get_connection() as conn:
            # Используем ON CONFLICT для upsert операции
            await conn.execute("""
                INSERT INTO users (user_id, last_interaction_date) 
                VALUES ($1, $2)
                ON CONFLICT (user_id) 
                DO UPDATE SET last_interaction_date = $2
            """, user_id, current_time)
    
    # Методы для работы с настройками пользователей
    async def get_user_settings(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение настроек пользователя"""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM user_settings WHERE user_id = $1", user_id
            )
            return dict(row) if row else None
    
    async def update_user_settings(self, user_id: int, **kwargs):
        """Обновление настроек пользователя (безопасно с whitelist)"""
        if not kwargs:
            return
        
        # БЕЗОПАСНАЯ валидация полей - только разрешенные поля
        ALLOWED_FIELDS = {
            'channel_id', 'topic', 'system_instruction', 'is_active', 
            'last_post_time', 'generate_images'
        }
        
        # Фильтруем только разрешенные поля
        safe_kwargs = {k: v for k, v in kwargs.items() if k in ALLOWED_FIELDS}
        
        if not safe_kwargs:
            logger.warning(f"No valid fields provided for user {user_id}: {list(kwargs.keys())}")
            return
        
        # Добавляем updated_at
        safe_kwargs['updated_at'] = int(datetime.now().timestamp())
        
        # Создаем динамический запрос
        fields = list(safe_kwargs.keys())
        values = list(safe_kwargs.values())
        placeholders = [f"${i+2}" for i in range(len(fields))]
        
        set_clause = ", ".join([f"{field} = {placeholder}" 
                               for field, placeholder in zip(fields, placeholders)])
        
        async with self.get_connection() as conn:
            await conn.execute(f"""
                UPDATE user_settings 
                SET {set_clause}
                WHERE user_id = $1
            """, user_id, *values)
    
    # Методы для работы с конфигурацией
    async def get_config(self, key: str) -> Optional[str]:
        """Получение значения конфигурации"""
        async with self.get_connection() as conn:
            return await conn.fetchval(
                "SELECT config_value FROM system_config WHERE config_key = $1", key
            )
    
    async def set_config(self, key: str, value: str, updated_by: int = None):
        """Установка значения конфигурации"""
        async with self.get_connection() as conn:
            await conn.execute("""
                INSERT INTO system_config (config_key, config_value, updated_by, updated_at)
                VALUES ($1, $2, $3, EXTRACT(EPOCH FROM NOW()))
                ON CONFLICT (config_key) 
                DO UPDATE SET 
                    config_value = $2, 
                    updated_by = $3, 
                    updated_at = EXTRACT(EPOCH FROM NOW())
            """, key, value, updated_by)
    
    async def get_all_configs(self) -> Dict[str, str]:
        """Получение всех конфигураций"""
        async with self.get_connection() as conn:
            rows = await conn.fetch(
                "SELECT config_key, config_value FROM system_config"
            )
            return {row['config_key']: row['config_value'] for row in rows}
    
    # Методы для работы с транзакциями
    async def create_transaction(self, user_id: int, amount: float, currency: str, 
                               method: str, subscription_type: str, external_id: str = None) -> int:
        """Создание новой транзакции"""
        async with self.get_connection() as conn:
            transaction_id = await conn.fetchval("""
                INSERT INTO transactions (user_id, amount, currency, method, subscription_type, external_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """, user_id, amount, currency, method, subscription_type, external_id)
            
            return transaction_id
    
    async def update_transaction_status(self, transaction_id: int, status: str):
        """Обновление статуса транзакции"""
        completed_at = int(datetime.now().timestamp()) if status == 'completed' else None
        
        async with self.get_connection() as conn:
            await conn.execute("""
                UPDATE transactions 
                SET status = $1, completed_at = $2 
                WHERE id = $3
            """, status, completed_at, transaction_id)
    
    # Методы для работы со статистикой
    async def increment_posts_count(self):
        """Увеличить счетчик сгенерированных постов"""
        async with self.get_connection() as conn:
            await conn.execute("""
                UPDATE stats SET 
                    posts_count = posts_count + 1,
                    last_updated = EXTRACT(EPOCH FROM NOW())
                WHERE id = 1
            """)
    
    async def increment_images_count(self):
        """Увеличить счетчик сгенерированных изображений"""
        async with self.get_connection() as conn:
            await conn.execute("""
                UPDATE stats SET 
                    images_count = images_count + 1,
                    last_updated = EXTRACT(EPOCH FROM NOW())
                WHERE id = 1
            """)
    
    # Методы для работы с очередью изображений
    async def add_image_to_queue(self, user_id: int, prompt: str, topic: str = None, 
                               priority: int = 0) -> int:
        """Добавление изображения в очередь"""
        async with self.get_connection() as conn:
            queue_id = await conn.fetchval("""
                INSERT INTO image_queue (user_id, prompt, topic, priority)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """, user_id, prompt, topic, priority)
            
            return queue_id
    
    async def get_next_image_from_queue(self) -> Optional[Dict[str, Any]]:
        """Получение следующего изображения из очереди"""
        async with self.get_connection() as conn:
            # Атомарно получаем и блокируем следующую задачу
            row = await conn.fetchrow("""
                UPDATE image_queue 
                SET status = 'processing', started_at = EXTRACT(EPOCH FROM NOW())
                WHERE id = (
                    SELECT id FROM image_queue 
                    WHERE status = 'pending' AND attempts < max_attempts
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING *
            """)
            
            return dict(row) if row else None
    
    async def update_image_queue_status(self, queue_id: int, status: str, 
                                      image_url: str = None, error_message: str = None,
                                      provider: str = None):
        """Обновление статуса задачи в очереди изображений"""
        async with self.get_connection() as conn:
            completed_at = int(datetime.now().timestamp()) if status in ['completed', 'failed'] else None
            
            await conn.execute("""
                UPDATE image_queue 
                SET status = $1, image_url = $2, error_message = $3, 
                    provider = $4, completed_at = $5, attempts = attempts + 1
                WHERE id = $6
            """, status, image_url, error_message, provider, completed_at, queue_id)
    
    # КРИТИЧЕСКИЕ МЕТОДЫ ДЛЯ ПРОМОКОДОВ (ИСПРАВЛЕНИЕ RACE CONDITION)
    async def validate_promo_code(self, code: str, user_id: int) -> Dict[str, Any]:
        """
        АТОМАРНАЯ валидация промокода с защитой от Race Condition
        Использует PostgreSQL транзакции для предотвращения множественного использования
        """
        code_upper = code.upper().strip()
        
        async with self.get_connection() as conn:
            # Начинаем атомарную транзакцию
            async with conn.transaction():
                # Проверяем TRIAL20 промокод
                if code_upper == "TRIAL20":
                    # АТОМАРНАЯ проверка: блокируем запись пользователя для чтения
                    user_row = await conn.fetchrow("""
                        SELECT user_id, is_trial_used, subscription_expiry, trial_expiry, is_lifetime
                        FROM users 
                        WHERE user_id = $1 
                        FOR UPDATE
                    """, user_id)
                    
                    if not user_row:
                        return {
                            'valid': False,
                            'error': 'Пользователь не найден'
                        }
                    
                    # Проверяем, использовал ли пользователь уже триал
                    if not user_row['is_trial_used']:
                        return {
                            'valid': False,
                            'error': 'Промокод TRIAL20 доступен только пользователям, завершившим пробный период'
                        }
                    
                    # Проверяем активность подписки АТОМАРНО
                    current_time = int(datetime.now().timestamp())
                    
                    # Если пожизненная подписка
                    if user_row['is_lifetime']:
                        return {
                            'valid': False,
                            'error': 'У вас уже есть активная подписка'
                        }
                    
                    # Проверяем триал
                    if user_row['trial_expiry'] and user_row['trial_expiry'] > current_time:
                        return {
                            'valid': False,
                            'error': 'У вас уже есть активная подписка'
                        }
                    
                    # Проверяем обычную подписку
                    if user_row['subscription_expiry'] and user_row['subscription_expiry'] > current_time:
                        return {
                            'valid': False,
                            'error': 'У вас уже есть активная подписка'
                        }
                    
                    # КРИТИЧЕСКАЯ ПРОВЕРКА: Проверяем, не использовал ли уже промокод
                    existing_usage = await conn.fetchval("""
                        SELECT COUNT(*) FROM promo_usage 
                        WHERE user_id = $1 AND promo_code = $2
                    """, user_id, code_upper)
                    
                    if existing_usage > 0:
                        return {
                            'valid': False,
                            'error': 'Промокод уже был использован'
                        }
                    
                    return {
                        'valid': True,
                        'discount_percent': 20,
                        'description': 'Скидка 20% для пользователей после пробного периода'
                    }
                
                # Другие промокоды можно добавить здесь
                return {
                    'valid': False,
                    'error': 'Неверный промокод'
                }
    
    async def calculate_discounted_price(self, original_price: float, discount_percent: int) -> float:
        """Расчет цены со скидкой с защитой от некорректных значений"""
        if discount_percent <= 0 or discount_percent >= 100:
            return original_price
        
        if original_price <= 0:
            return 0.0
        
        # Формула: Total = Price × (1 - discount/100)
        discounted_price = original_price * (1 - discount_percent / 100)
        return round(discounted_price, 2)
    
    async def record_promo_usage(self, user_id: int, promo_code: str, discount_percent: int, 
                               original_amount: float, discounted_amount: float):
        """
        АТОМАРНАЯ запись использования промокода
        Предотвращает дублирование записей через UNIQUE constraint
        """
        async with self.get_connection() as conn:
            async with conn.transaction():
                # Проверяем, не записан ли уже промокод (дополнительная защита)
                existing = await conn.fetchval("""
                    SELECT id FROM promo_usage 
                    WHERE user_id = $1 AND promo_code = $2
                """, user_id, promo_code)
                
                if existing:
                    logger.warning(f"Attempted duplicate promo usage: user {user_id}, code {promo_code}")
                    return
                
                # Атомарно записываем использование
                await conn.execute("""
                    INSERT INTO promo_usage 
                    (user_id, promo_code, discount_percent, original_amount, discounted_amount)
                    VALUES ($1, $2, $3, $4, $5)
                """, user_id, promo_code, discount_percent, original_amount, discounted_amount)
                
                logger.info(f"Recorded promo usage: user {user_id}, code {promo_code}, discount {discount_percent}%")

    # Методы для аналитики и отчетности
    async def get_admin_stats(self) -> Dict[str, Any]:
        """Получение статистики для админа"""
        async with self.get_connection() as conn:
            # Общее количество пользователей
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            
            # Активные подписки (включая триал)
            current_time = int(datetime.now().timestamp())
            active_subscriptions = await conn.fetchval("""
                SELECT COUNT(*) FROM users 
                WHERE is_lifetime = TRUE 
                   OR subscription_expiry > $1 
                   OR trial_expiry > $1
            """, current_time)
            
            # Пользователи на триале
            trial_users = await conn.fetchval("""
                SELECT COUNT(*) FROM users 
                WHERE trial_expiry > $1 
                  AND (subscription_expiry IS NULL OR subscription_expiry <= trial_expiry)
            """, current_time)
            
            # Активные автопостинги
            active_autoposting = await conn.fetchval(
                "SELECT COUNT(*) FROM user_settings WHERE is_active = TRUE"
            )
            
            return {
                "total_users": total_users,
                "active_subscriptions": active_subscriptions,
                "trial_users": trial_users,
                "active_autoposting": active_autoposting
            }
    
    async def get_active_users_for_posting(self) -> List[Dict[str, Any]]:
        """Получение пользователей с активным автопостингом"""
        current_time = int(datetime.now().timestamp())
        
        async with self.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT us.*, u.subscription_expiry, u.trial_expiry, u.is_lifetime
                FROM user_settings us
                JOIN users u ON us.user_id = u.user_id
                WHERE us.is_active = TRUE 
                  AND us.channel_id IS NOT NULL 
                  AND us.topic IS NOT NULL 
                  AND us.system_instruction IS NOT NULL
                  AND (
                      u.is_lifetime = TRUE 
                      OR u.subscription_expiry > $1
                      OR u.trial_expiry > $1
                  )
            """, current_time)
            
            return [dict(row) for row in rows]

    # ========== МЕТОДЫ ДЛЯ АВТОПИЛОТА (ОТДЕЛЬНЫЕ ПОДПИСКИ) ==========
    
    async def get_autopilot_rates(self) -> List[Dict[str, Any]]:
        """Получить все активные тарифы автопилота"""
        async with self.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT * FROM autopilot_rates 
                WHERE is_active = TRUE 
                ORDER BY duration_days ASC
            """)
            return [dict(row) for row in rows]
    
    async def get_autopilot_rate(self, rate_id: int) -> Optional[Dict[str, Any]]:
        """Получить конкретный тариф автопилота"""
        async with self.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM autopilot_rates 
                WHERE id = $1 AND is_active = TRUE
            """, rate_id)
            return dict(row) if row else None
    
    async def get_autopilot_subscription_status(self, user_id: int) -> Dict[str, Any]:
        """Получить статус подписки на автопилот (ОТДЕЛЬНО от основной подписки)"""
        current_time = int(datetime.now().timestamp())
        
        async with self.get_connection() as conn:
            # Получаем активную подписку на автопилот
            subscription = await conn.fetchrow("""
                SELECT s.*, r.name as rate_name, r.max_channels, r.max_posts_per_day
                FROM autopilot_subscriptions s
                JOIN autopilot_rates r ON s.rate_id = r.id
                WHERE s.user_id = $1 AND s.is_active = TRUE AND s.expires_at > $2
                ORDER BY s.expires_at DESC
                LIMIT 1
            """, user_id, current_time)
            
            if subscription:
                days_left = max(0, (subscription['expires_at'] - current_time) // 86400)
                return {
                    'is_active': True,
                    'subscription_id': subscription['id'],
                    'rate_name': subscription['rate_name'],
                    'expires_at': subscription['expires_at'],
                    'days_left': days_left,
                    'max_channels': subscription['max_channels'],
                    'max_posts_per_day': subscription['max_posts_per_day']
                }
            else:
                return {
                    'is_active': False,
                    'subscription_id': None,
                    'rate_name': None,
                    'expires_at': None,
                    'days_left': 0,
                    'max_channels': 0,
                    'max_posts_per_day': 0
                }
    
    async def create_autopilot_purchase(self, user_id: int, rate_id: int, amount: float, 
                                      currency: str, payment_method: str, transaction_id: str = None) -> int:
        """Создать запись о покупке автопилота"""
        async with self.get_connection() as conn:
            purchase_id = await conn.fetchval("""
                INSERT INTO autopilot_purchases 
                (user_id, rate_id, amount, currency, payment_method, transaction_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """, user_id, rate_id, amount, currency, payment_method, transaction_id)
            
            logger.info(f"Created autopilot purchase: {purchase_id} for user {user_id}")
            return purchase_id
    
    async def activate_autopilot_subscription(self, user_id: int, purchase_id: int) -> bool:
        """Активировать подписку на автопилот"""
        async with self.get_connection() as conn:
            async with conn.transaction():
                # Получаем информацию о покупке
                purchase = await conn.fetchrow("""
                    SELECT p.*, r.duration_days, r.max_channels, r.max_posts_per_day
                    FROM autopilot_purchases p
                    JOIN autopilot_rates r ON p.rate_id = r.id
                    WHERE p.id = $1 AND p.user_id = $2
                """, purchase_id, user_id)
                
                if not purchase:
                    logger.error(f"Purchase not found: {purchase_id} for user {user_id}")
                    return False
                
                current_time = int(datetime.now().timestamp())
                
                # Деактивируем предыдущие подписки на автопилот
                await conn.execute("""
                    UPDATE autopilot_subscriptions 
                    SET is_active = FALSE 
                    WHERE user_id = $1 AND is_active = TRUE
                """, user_id)
                
                # Создаем новую подписку на автопилот
                expires_at = current_time + (purchase['duration_days'] * 86400)
                
                subscription_id = await conn.fetchval("""
                    INSERT INTO autopilot_subscriptions 
                    (user_id, rate_id, expires_at, max_channels, max_posts_per_day)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                """, user_id, purchase['rate_id'], expires_at, 
                    purchase['max_channels'], purchase['max_posts_per_day'])
                
                # Обновляем покупку с ID подписки
                await conn.execute("""
                    UPDATE autopilot_purchases 
                    SET subscription_id = $1 
                    WHERE id = $2
                """, subscription_id, purchase_id)
                
                logger.info(f"Activated autopilot subscription: {subscription_id} for user {user_id}")
                return True
    
    async def get_user_autopilot_configs(self, user_id: int) -> List[Dict[str, Any]]:
        """Получить конфигурации автопилота пользователя"""
        async with self.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT * FROM autopilot_configs 
                WHERE user_id = $1 
                ORDER BY created_at DESC
            """, user_id)
            return [dict(row) for row in rows]
    
    async def create_autopilot_config(self, user_id: int, channel_id: str, topic: str, 
                                    tone_of_voice: str, posts_per_day: int, keywords: str = None) -> int:
        """Создать конфигурацию автопилота"""
        async with self.get_connection() as conn:
            config_id = await conn.fetchval("""
                INSERT INTO autopilot_configs 
                (user_id, channel_id, topic, tone_of_voice, posts_per_day, keywords)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """, user_id, channel_id, topic, tone_of_voice, posts_per_day, keywords)
            
            logger.info(f"Created autopilot config: {config_id} for user {user_id}")
            return config_id
    
    async def get_autopilot_config(self, config_id: int) -> Optional[Dict[str, Any]]:
        """Получить конфигурацию автопилота по ID"""
        async with self.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM autopilot_configs WHERE id = $1
            """, config_id)
            return dict(row) if row else None
    
    async def update_autopilot_config(self, config_id: int, is_active: bool = None, **kwargs) -> bool:
        """Обновить конфигурацию автопилота"""
        async with self.get_connection() as conn:
            updates = []
            values = []
            param_count = 1
            
            if is_active is not None:
                updates.append(f"is_active = ${param_count}")
                values.append(is_active)
                param_count += 1
            
            for key, value in kwargs.items():
                if key in ['topic', 'tone_of_voice', 'posts_per_day', 'keywords', 'generate_images']:
                    updates.append(f"{key} = ${param_count}")
                    values.append(value)
                    param_count += 1
            
            if not updates:
                return False
            
            updates.append(f"updated_at = ${param_count}")
            values.append(int(datetime.now().timestamp()))
            values.append(config_id)
            
            query = f"""
                UPDATE autopilot_configs 
                SET {', '.join(updates)}
                WHERE id = ${param_count + 1}
            """
            
            result = await conn.execute(query, *values)
            return result != "UPDATE 0"
    
    async def get_all_active_autopilot_configs(self) -> List[Dict[str, Any]]:
        """Получить все активные конфигурации автопилота"""
        current_time = int(datetime.now().timestamp())
        
        async with self.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT c.*, s.expires_at, s.max_posts_per_day as subscription_max_posts
                FROM autopilot_configs c
                JOIN autopilot_subscriptions s ON c.user_id = s.user_id
                WHERE c.is_active = TRUE 
                  AND s.is_active = TRUE 
                  AND s.expires_at > $1
            """, current_time)
            return [dict(row) for row in rows]
    
    async def save_autopilot_post(self, config_id: int, post_content: str, 
                                image_url: str = None, news_sources: str = None, 
                                telegram_message_id: int = None) -> int:
        """Сохранить пост автопилота"""
        async with self.get_connection() as conn:
            async with conn.transaction():
                # Получаем информацию о конфигурации
                config = await conn.fetchrow("""
                    SELECT user_id, channel_id FROM autopilot_configs WHERE id = $1
                """, config_id)
                
                if not config:
                    raise ValueError(f"Config not found: {config_id}")
                
                # Сохраняем пост
                post_id = await conn.fetchval("""
                    INSERT INTO autopilot_posts 
                    (config_id, user_id, channel_id, post_content, image_url, news_sources, telegram_message_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                """, config_id, config['user_id'], config['channel_id'], 
                    post_content, image_url, news_sources, telegram_message_id)
                
                # Обновляем статистику конфигурации
                await conn.execute("""
                    UPDATE autopilot_configs 
                    SET total_posts = total_posts + 1,
                        successful_posts = successful_posts + 1,
                        last_post_at = $1
                    WHERE id = $2
                """, int(datetime.now().timestamp()), config_id)
                
                return post_id
    
    async def get_last_autopilot_post(self, config_id: int) -> Optional[Dict[str, Any]]:
        """Получить последний пост автопилота для конфигурации"""
        async with self.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM autopilot_posts 
                WHERE config_id = $1 
                ORDER BY created_at DESC 
                LIMIT 1
            """, config_id)
            return dict(row) if row else None
    
    async def get_expiring_autopilot_subscriptions(self, hours: int) -> List[Dict[str, Any]]:
        """Получить подписки на автопилот, истекающие в ближайшие часы"""
        current_time = int(datetime.now().timestamp())
        expiry_threshold = current_time + (hours * 3600)
        
        async with self.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT s.user_id, s.expires_at as autopilot_subscription_expiry, r.name as rate_name
                FROM autopilot_subscriptions s
                JOIN autopilot_rates r ON s.rate_id = r.id
                WHERE s.is_active = TRUE 
                  AND s.expires_at > $1 
                  AND s.expires_at <= $2
            """, current_time, expiry_threshold)
            return [dict(row) for row in rows]


# Глобальный экземпляр PostgreSQL базы данных
postgresql_db = PostgreSQLDatabase()