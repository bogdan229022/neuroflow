import aiosqlite
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from app.core.config import DATABASE_PATH

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path

    async def init_db(self):
        """Инициализация базы данных"""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица пользователей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    subscription_expiry INTEGER,
                    is_admin BOOLEAN DEFAULT FALSE,
                    is_lifetime BOOLEAN DEFAULT FALSE,
                    is_trial_used BOOLEAN DEFAULT FALSE,
                    trial_expiry INTEGER,
                    last_interaction_date INTEGER DEFAULT (strftime('%s', 'now')),
                    upsell_sent BOOLEAN DEFAULT FALSE,
                    feedback_sent BOOLEAN DEFAULT FALSE,
                    created_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Таблица настроек пользователей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    channel_id TEXT,
                    topic TEXT,
                    system_instruction TEXT,
                    is_active BOOLEAN DEFAULT FALSE,
                    last_post_time INTEGER,
                    generate_images BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            # Таблица транзакций
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    external_id TEXT,
                    subscription_type TEXT NOT NULL,
                    created_at INTEGER DEFAULT (strftime('%s', 'now')),
                    completed_at INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            # Таблица системной конфигурации
            await db.execute("""
                CREATE TABLE IF NOT EXISTS system_config (
                    config_key TEXT PRIMARY KEY,
                    config_value TEXT,
                    is_encrypted BOOLEAN DEFAULT FALSE,
                    updated_at INTEGER DEFAULT (strftime('%s', 'now')),
                    updated_by INTEGER
                )
            """)
            
            # Таблица статистики
            await db.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY,
                    posts_count INTEGER DEFAULT 0,
                    images_count INTEGER DEFAULT 0,
                    subscriptions_stars INTEGER DEFAULT 0,
                    subscriptions_crypto INTEGER DEFAULT 0,
                    subscriptions_sbp INTEGER DEFAULT 0,
                    subscriptions_manual INTEGER DEFAULT 0,
                    revenue_stars REAL DEFAULT 0,
                    revenue_crypto_usd REAL DEFAULT 0,
                    revenue_crypto_btc REAL DEFAULT 0,
                    revenue_crypto_eth REAL DEFAULT 0,
                    revenue_crypto_ton REAL DEFAULT 0,
                    revenue_crypto_usdt REAL DEFAULT 0,
                    revenue_sbp_rub REAL DEFAULT 0,
                    revenue_manual_rub REAL DEFAULT 0,
                    last_updated INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Таблица истории платежей для отчетности
            await db.execute("""
                CREATE TABLE IF NOT EXISTS history_payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    payment_method TEXT NOT NULL,
                    subscription_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    transaction_id TEXT,
                    payment_date INTEGER DEFAULT (strftime('%s', 'now')),
                    week_number INTEGER,
                    year INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            await db.commit()
            
            # Миграция: добавляем новые поля для триала если их нет
            try:
                await db.execute("ALTER TABLE users ADD COLUMN is_trial_used BOOLEAN DEFAULT FALSE")
                await db.execute("ALTER TABLE users ADD COLUMN trial_expiry INTEGER")
                await db.execute("ALTER TABLE users ADD COLUMN last_interaction_date INTEGER DEFAULT (strftime('%s', 'now'))")
                await db.execute("ALTER TABLE users ADD COLUMN upsell_sent BOOLEAN DEFAULT FALSE")
                await db.execute("ALTER TABLE users ADD COLUMN feedback_sent BOOLEAN DEFAULT FALSE")
                await db.commit()
                logger.info("Добавлены поля для триала и retention в таблицу users")
            except Exception:
                # Поля уже существуют
                pass
            
            # Инициализируем базовые конфигурации если их нет
            await self._init_default_configs()
            
            # Инициализируем статистику если её нет
            await self._init_stats()

    async def add_user(self, user_id: int, is_admin: bool = False):
        """Добавление нового пользователя с автоматической активацией триала"""
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем, существует ли пользователь
            cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            existing_user = await cursor.fetchone()
            
            if not existing_user:
                # Новый пользователь - активируем триал на 24 часа
                current_time = int(datetime.now().timestamp())
                trial_expiry = current_time + (24 * 60 * 60)  # 24 часа
                
                await db.execute(
                    """INSERT INTO users (user_id, is_admin, is_trial_used, trial_expiry, subscription_expiry) 
                       VALUES (?, ?, TRUE, ?, ?)""",
                    (user_id, is_admin, trial_expiry, trial_expiry)
                )
                
                await db.execute(
                    "INSERT INTO user_settings (user_id) VALUES (?)",
                    (user_id,)
                )
                
                await db.commit()
                logger.info(f"Новый пользователь {user_id} добавлен с триалом на 24 часа")
                return True  # Возвращаем True если это новый пользователь
            
            return False  # Возвращаем False если пользователь уже существует

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о пользователе"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_subscription(self, user_id: int, days: int, is_lifetime: bool = False):
        """Обновление подписки пользователя"""
        current_time = int(datetime.now().timestamp())
        
        async with aiosqlite.connect(self.db_path) as db:
            if is_lifetime:
                # Пожизненная подписка
                await db.execute(
                    "UPDATE users SET is_lifetime = TRUE, subscription_expiry = ? WHERE user_id = ?",
                    (current_time + (100 * 365 * 24 * 60 * 60), user_id)  # 100 лет
                )
            else:
                # Получаем текущую дату окончания подписки
                cursor = await db.execute(
                    "SELECT subscription_expiry, is_lifetime FROM users WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()
                
                if row and row[1]:  # Если уже пожизненная
                    return  # Не изменяем пожизненную подписку
                
                if row and row[0] and row[0] > current_time:
                    # Если подписка еще активна, добавляем дни к текущей дате окончания
                    new_expiry = row[0] + (days * 24 * 60 * 60)
                else:
                    # Если подписки нет или она истекла, добавляем дни к текущему времени
                    new_expiry = current_time + (days * 24 * 60 * 60)
                
                await db.execute(
                    "UPDATE users SET subscription_expiry = ? WHERE user_id = ?",
                    (new_expiry, user_id)
                )
            
            await db.commit()

    async def is_subscription_active(self, user_id: int) -> bool:
        """Проверка активности подписки (включая триал)"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT subscription_expiry, is_lifetime, trial_expiry FROM users WHERE user_id = ?", 
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                return False
            
            current_time = int(datetime.now().timestamp())
            
            # Если пожизненная подписка
            if row[1]:
                return True
            
            # Проверяем триал
            if row[2] and row[2] > current_time:
                return True
            
            # Проверяем обычную подписку
            if row[0] and row[0] > current_time:
                return True
            
            return False

    async def get_user_settings(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение настроек пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_user_settings(self, user_id: int, **kwargs):
        """Обновление настроек пользователя (ИСПРАВЛЕНО: SQL injection защита)"""
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
        
        # Создаем параметризованный запрос с предопределенными полями
        fields = ", ".join([f"{key} = ?" for key in safe_kwargs.keys()])
        values = list(safe_kwargs.values()) + [user_id]
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE user_settings SET {fields} WHERE user_id = ?", values
            )
            await db.commit()
            
        logger.debug(f"Updated user settings for {user_id}: {list(safe_kwargs.keys())}")

    async def get_active_users_for_posting(self) -> list:
        """Получение пользователей с активным автопостингом (включая триал)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            current_time = int(datetime.now().timestamp())
            
            cursor = await db.execute("""
                SELECT us.*, u.subscription_expiry, u.trial_expiry, u.is_lifetime
                FROM user_settings us
                JOIN users u ON us.user_id = u.user_id
                WHERE us.is_active = TRUE 
                AND us.channel_id IS NOT NULL 
                AND us.topic IS NOT NULL 
                AND us.system_instruction IS NOT NULL
                AND (
                    u.is_lifetime = TRUE 
                    OR u.subscription_expiry > ?
                    OR u.trial_expiry > ?
                )
            """, (current_time, current_time))
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_admin_stats(self) -> Dict[str, Any]:
        """Получение статистики для админа (включая триал)"""
        async with aiosqlite.connect(self.db_path) as db:
            # Общее количество пользователей
            cursor = await db.execute("SELECT COUNT(*) FROM users")
            total_users = (await cursor.fetchone())[0]
            
            # Активные подписки (включая триал)
            current_time = int(datetime.now().timestamp())
            cursor = await db.execute(
                """SELECT COUNT(*) FROM users 
                   WHERE is_lifetime = TRUE 
                   OR subscription_expiry > ? 
                   OR trial_expiry > ?""", 
                (current_time, current_time)
            )
            active_subscriptions = (await cursor.fetchone())[0]
            
            # Пользователи на триале
            cursor = await db.execute(
                """SELECT COUNT(*) FROM users 
                   WHERE trial_expiry > ? 
                   AND (subscription_expiry IS NULL OR subscription_expiry <= trial_expiry)""",
                (current_time,)
            )
            trial_users = (await cursor.fetchone())[0]
            
            # Активные автопостинги
            cursor = await db.execute(
                "SELECT COUNT(*) FROM user_settings WHERE is_active = TRUE"
            )
            active_autoposting = (await cursor.fetchone())[0]
            
            return {
                "total_users": total_users,
                "active_subscriptions": active_subscriptions,
                "trial_users": trial_users,
                "active_autoposting": active_autoposting
            }

    async def get_subscription_status(self, user_id: int) -> Dict[str, Any]:
        """Получение детального статуса подписки пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT subscription_expiry, is_lifetime, trial_expiry, is_trial_used 
                   FROM users WHERE user_id = ?""", 
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                return {
                    "is_active": False,
                    "type": "none",
                    "expires_at": None,
                    "time_left": 0
                }
            
            current_time = int(datetime.now().timestamp())
            subscription_expiry, is_lifetime, trial_expiry, is_trial_used = row
            
            # Пожизненная подписка
            if is_lifetime:
                return {
                    "is_active": True,
                    "type": "lifetime",
                    "expires_at": None,
                    "time_left": float('inf')
                }
            
            # Активный триал
            if trial_expiry and trial_expiry > current_time:
                return {
                    "is_active": True,
                    "type": "trial",
                    "expires_at": trial_expiry,
                    "time_left": trial_expiry - current_time
                }
            
            # Обычная подписка
            if subscription_expiry and subscription_expiry > current_time:
                return {
                    "is_active": True,
                    "type": "subscription",
                    "expires_at": subscription_expiry,
                    "time_left": subscription_expiry - current_time
                }
            
            # Нет активной подписки
            return {
                "is_active": False,
                "type": "expired" if is_trial_used else "none",
                "expires_at": None,
                "time_left": 0
            }

    async def get_users_with_expiring_trial(self, hours_before: int = 1) -> list:
        """Получение пользователей с истекающим триалом"""
        current_time = int(datetime.now().timestamp())
        expiry_threshold = current_time + (hours_before * 60 * 60)
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT user_id, trial_expiry FROM users 
                   WHERE trial_expiry IS NOT NULL 
                   AND trial_expiry > ? 
                   AND trial_expiry <= ?
                   AND (subscription_expiry IS NULL OR subscription_expiry <= trial_expiry)""",
                (current_time, expiry_threshold)
            )
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def extend_trial(self, user_id: int, hours: int = 24):
        """Продление триала (только для админа)"""
        current_time = int(datetime.now().timestamp())
        new_expiry = current_time + (hours * 60 * 60)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE users SET trial_expiry = ?, subscription_expiry = ? 
                   WHERE user_id = ?""",
                (new_expiry, new_expiry, user_id)
            )
            await db.commit()
            logger.info(f"Триал пользователя {user_id} продлен на {hours} часов")

    async def update_last_interaction(self, user_id: int):
        """Обновление времени последнего взаимодействия"""
        current_time = int(datetime.now().timestamp())
        
        async with aiosqlite.connect(self.db_path) as db:
            # Сначала проверяем, есть ли поле last_interaction_date
            try:
                await db.execute(
                    "UPDATE users SET last_interaction_date = ? WHERE user_id = ?",
                    (current_time, user_id)
                )
            except Exception as e:
                if "no such column" in str(e):
                    # Поле не существует, добавляем его
                    try:
                        await db.execute("ALTER TABLE users ADD COLUMN last_interaction_date INTEGER")
                        await db.execute(
                            "UPDATE users SET last_interaction_date = ? WHERE user_id = ?",
                            (current_time, user_id)
                        )
                    except Exception as e2:
                        logger.warning(f"Не удалось добавить поле last_interaction_date: {e2}")
                        return
                else:
                    raise e
            
            await db.commit()

    async def get_users_for_upsell(self) -> list:
        """Получение пользователей для upsell сообщений (триал истек, upsell не отправлен)"""
        current_time = int(datetime.now().timestamp())
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT user_id, trial_expiry FROM users 
                   WHERE trial_expiry IS NOT NULL 
                   AND trial_expiry <= ?
                   AND upsell_sent = FALSE
                   AND is_trial_used = TRUE
                   AND (subscription_expiry IS NULL OR subscription_expiry <= trial_expiry)""",
                (current_time,)
            )
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def mark_upsell_sent(self, user_id: int):
        """Отметить что upsell сообщение отправлено"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET upsell_sent = TRUE WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()

    async def get_users_for_feedback(self) -> list:
        """Получение пользователей для сбора фидбека (72 часа после окончания триала)"""
        current_time = int(datetime.now().timestamp())
        feedback_threshold = current_time - (72 * 60 * 60)  # 72 часа назад
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT user_id, trial_expiry FROM users 
                   WHERE trial_expiry IS NOT NULL 
                   AND trial_expiry <= ?
                   AND feedback_sent = FALSE
                   AND is_trial_used = TRUE
                   AND (subscription_expiry IS NULL OR subscription_expiry <= trial_expiry)""",
                (feedback_threshold,)
            )
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def mark_feedback_sent(self, user_id: int):
        """Отметить что фидбек сообщение отправлено"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET feedback_sent = TRUE WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()

    async def get_expired_trial_users(self) -> list:
        """Получение пользователей с истекшим триалом для отключения автопостинга"""
        current_time = int(datetime.now().timestamp())
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT u.user_id, u.trial_expiry, us.is_active 
                   FROM users u
                   JOIN user_settings us ON u.user_id = us.user_id
                   WHERE u.trial_expiry IS NOT NULL 
                   AND u.trial_expiry <= ?
                   AND u.is_trial_used = TRUE
                   AND (u.subscription_expiry IS NULL OR u.subscription_expiry <= u.trial_expiry)
                   AND us.is_active = TRUE""",
                (current_time,)
            )
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # Методы для работы с промокодами
    async def validate_promo_code(self, code: str, user_id: int) -> Dict[str, Any]:
        """Валидация промокода"""
        code_upper = code.upper().strip()
        
        # Проверяем TRIAL20 промокод
        if code_upper == "TRIAL20":
            # Проверяем, использовал ли пользователь уже триал
            user = await self.get_user(user_id)
            if not user or not user.get('is_trial_used'):
                return {
                    'valid': False,
                    'error': 'Промокод TRIAL20 доступен только пользователям, завершившим пробный период'
                }
            
            # Проверяем, не активна ли уже подписка
            if await self.is_subscription_active(user_id):
                return {
                    'valid': False,
                    'error': 'У вас уже есть активная подписка'
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
        """Расчет цены со скидкой"""
        if discount_percent <= 0 or discount_percent >= 100:
            return original_price
        
        # Формула: Total = Price × (1 - discount/100)
        discounted_price = original_price * (1 - discount_percent / 100)
        return round(discounted_price, 2)
    
    async def record_promo_usage(self, user_id: int, promo_code: str, discount_percent: int, 
                               original_amount: float, discounted_amount: float):
        """Записать использование промокода"""
        async with aiosqlite.connect(self.db_path) as db:
            # Создаем таблицу для промокодов если её нет
            await db.execute("""
                CREATE TABLE IF NOT EXISTS promo_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    promo_code TEXT NOT NULL,
                    discount_percent INTEGER NOT NULL,
                    original_amount REAL NOT NULL,
                    discounted_amount REAL NOT NULL,
                    used_at INTEGER DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            await db.execute("""
                INSERT INTO promo_usage 
                (user_id, promo_code, discount_percent, original_amount, discounted_amount)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, promo_code, discount_percent, original_amount, discounted_amount))
            
            await db.commit()
            logger.info(f"Recorded promo usage: user {user_id}, code {promo_code}, discount {discount_percent}%")

    # Методы для работы с транзакциями
    async def create_transaction(self, user_id: int, amount: float, currency: str, 
                               method: str, subscription_type: str, external_id: str = None) -> int:
        """Создание новой транзакции"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO transactions (user_id, amount, currency, method, subscription_type, external_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, amount, currency, method, subscription_type, external_id))
            
            transaction_id = cursor.lastrowid
            await db.commit()
            return transaction_id

    async def update_transaction_status(self, transaction_id: int, status: str):
        """Обновление статуса транзакции"""
        async with aiosqlite.connect(self.db_path) as db:
            completed_at = int(datetime.now().timestamp()) if status == 'completed' else None
            await db.execute(
                "UPDATE transactions SET status = ?, completed_at = ? WHERE id = ?",
                (status, completed_at, transaction_id)
            )
            await db.commit()

    async def get_transaction(self, transaction_id: int) -> Optional[Dict[str, Any]]:
        """Получение транзакции по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_transaction_by_external_id(self, external_id: str) -> Optional[Dict[str, Any]]:
        """Получение транзакции по внешнему ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM transactions WHERE external_id = ?", (external_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_recent_transactions(self, limit: int = 50) -> list:
        """Получение последних транзакций"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT t.*, u.user_id as telegram_id 
                FROM transactions t
                JOIN users u ON t.user_id = u.user_id
                WHERE t.status = 'completed'
                ORDER BY t.completed_at DESC
                LIMIT ?
            """, (limit,))
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # Методы для работы с системной конфигурацией
    async def _init_default_configs(self):
        """Инициализация базовых конфигураций из .env"""
        from app.core.config import GROQ_API_KEY, CRYPTO_BOT_TOKEN, AAIO_API_KEY, AAIO_SHOP_ID, AAIO_SECRET_KEY
        
        default_configs = {
            'groq_api_key': GROQ_API_KEY or '',
            'crypto_bot_token': CRYPTO_BOT_TOKEN or '',
            'aaio_api_key': AAIO_API_KEY or '',
            'aaio_shop_id': AAIO_SHOP_ID or '',
            'aaio_secret_key': AAIO_SECRET_KEY or '',
            'telegram_stars_enabled': 'true',  # Stars всегда доступны
            'manual_payment_enabled': 'true'   # Ручная оплата включена по умолчанию
        }
        
        async with aiosqlite.connect(self.db_path) as db:
            for key, value in default_configs.items():
                # Проверяем, есть ли уже такой ключ
                cursor = await db.execute(
                    "SELECT config_key FROM system_config WHERE config_key = ?", (key,)
                )
                if not await cursor.fetchone():
                    # Добавляем только если ключа еще нет
                    await db.execute(
                        "INSERT INTO system_config (config_key, config_value, is_encrypted) VALUES (?, ?, ?)",
                        (key, value, False)  # Пока без шифрования для простоты
                    )
            await db.commit()

    async def get_config(self, key: str) -> Optional[str]:
        """Получение значения конфигурации"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT config_value FROM system_config WHERE config_key = ?", (key,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set_config(self, key: str, value: str, updated_by: int = None):
        """Установка значения конфигурации"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO system_config 
                (config_key, config_value, is_encrypted, updated_at, updated_by)
                VALUES (?, ?, ?, strftime('%s', 'now'), ?)
            """, (key, value, False, updated_by))
            await db.commit()

    async def get_all_configs(self) -> Dict[str, str]:
        """Получение всех конфигураций"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT config_key, config_value FROM system_config"
            )
            rows = await cursor.fetchall()
            return {row['config_key']: row['config_value'] for row in rows}

    async def is_payment_method_available(self, method: str) -> bool:
        """Проверка доступности метода оплаты"""
        if method == 'stars':
            # Telegram Stars всегда доступны
            return True
        elif method == 'sbp':
            # Для СБП нужны все ключи AAIO
            aaio_api = await self.get_config('aaio_api_key')
            aaio_shop = await self.get_config('aaio_shop_id')
            aaio_secret = await self.get_config('aaio_secret_key')
            return bool(aaio_api and aaio_shop and aaio_secret)
        elif method == 'crypto':
            # Для крипты нужен токен CryptoBot
            crypto_token = await self.get_config('crypto_bot_token')
            return bool(crypto_token)
        elif method == 'manual':
            # Для ручной оплаты проверяем настройку
            manual_enabled = await self.get_config('manual_payment_enabled')
            return manual_enabled == 'true'
        
        return False

    async def get_payment_methods_status(self) -> Dict[str, bool]:
        """Получение статуса всех методов оплаты"""
        return {
            'stars': await self.is_payment_method_available('stars'),
            'sbp': await self.is_payment_method_available('sbp'),
            'crypto': await self.is_payment_method_available('crypto'),
            'manual': await self.is_payment_method_available('manual')
        }

    # Методы для работы со статистикой
    async def _init_stats(self):
        """Инициализация статистики если её нет"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM stats")
            count = (await cursor.fetchone())[0]
            
            if count == 0:
                # Создаем первую запись статистики
                await db.execute("INSERT INTO stats DEFAULT VALUES")
                await db.commit()

    async def increment_posts_count(self):
        """Увеличить счетчик сгенерированных постов"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE stats SET 
                    posts_count = posts_count + 1,
                    last_updated = strftime('%s', 'now')
                WHERE id = 1
            """)
            await db.commit()

    async def increment_images_count(self):
        """Увеличить счетчик сгенерированных изображений"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE stats SET 
                    images_count = images_count + 1,
                    last_updated = strftime('%s', 'now')
                WHERE id = 1
            """)
            await db.commit()

    async def increment_subscription_stats(self, method: str, amount: float, currency: str):
        """Увеличить статистику подписок и доходов (ИСПРАВЛЕНО)"""
        # Whitelist разрешенных валют для предотвращения SQL-инъекций
        CRYPTO_CURRENCY_COLUMNS = {
            'usd': 'revenue_crypto_usd',
            'btc': 'revenue_crypto_btc', 
            'eth': 'revenue_crypto_eth',
            'ton': 'revenue_crypto_ton',
            'usdt': 'revenue_crypto_usdt'
        }
        
        async with aiosqlite.connect(self.db_path) as db:
            if method == 'stars':
                await db.execute("""
                    UPDATE stats SET 
                        subscriptions_stars = subscriptions_stars + 1,
                        revenue_stars = revenue_stars + ?,
                        last_updated = strftime('%s', 'now')
                    WHERE id = 1
                """, (amount,))
            elif method == 'crypto':
                # БЕЗОПАСНАЯ валидация валюты
                currency_lower = currency.lower()
                if currency_lower not in CRYPTO_CURRENCY_COLUMNS:
                    logger.warning(f"Unknown crypto currency: {currency}, defaulting to USD")
                    currency_lower = 'usd'
                
                column = CRYPTO_CURRENCY_COLUMNS[currency_lower]
                
                # Используем параметризованный запрос с предопределенным именем колонки
                if column == 'revenue_crypto_usd':
                    await db.execute("""
                        UPDATE stats SET 
                            subscriptions_crypto = subscriptions_crypto + 1,
                            revenue_crypto_usd = revenue_crypto_usd + ?,
                            last_updated = strftime('%s', 'now')
                        WHERE id = 1
                    """, (amount,))
                elif column == 'revenue_crypto_btc':
                    await db.execute("""
                        UPDATE stats SET 
                            subscriptions_crypto = subscriptions_crypto + 1,
                            revenue_crypto_btc = revenue_crypto_btc + ?,
                            last_updated = strftime('%s', 'now')
                        WHERE id = 1
                    """, (amount,))
                elif column == 'revenue_crypto_eth':
                    await db.execute("""
                        UPDATE stats SET 
                            subscriptions_crypto = subscriptions_crypto + 1,
                            revenue_crypto_eth = revenue_crypto_eth + ?,
                            last_updated = strftime('%s', 'now')
                        WHERE id = 1
                    """, (amount,))
                elif column == 'revenue_crypto_ton':
                    await db.execute("""
                        UPDATE stats SET 
                            subscriptions_crypto = subscriptions_crypto + 1,
                            revenue_crypto_ton = revenue_crypto_ton + ?,
                            last_updated = strftime('%s', 'now')
                        WHERE id = 1
                    """, (amount,))
                elif column == 'revenue_crypto_usdt':
                    await db.execute("""
                        UPDATE stats SET 
                            subscriptions_crypto = subscriptions_crypto + 1,
                            revenue_crypto_usdt = revenue_crypto_usdt + ?,
                            last_updated = strftime('%s', 'now')
                        WHERE id = 1
                    """, (amount,))
            elif method == 'sbp':
                await db.execute("""
                    UPDATE stats SET 
                        subscriptions_sbp = subscriptions_sbp + 1,
                        revenue_sbp_rub = revenue_sbp_rub + ?,
                        last_updated = strftime('%s', 'now')
                    WHERE id = 1
                """, (amount,))
            elif method == 'manual':
                await db.execute("""
                    UPDATE stats SET 
                        subscriptions_manual = subscriptions_manual + 1,
                        revenue_manual_rub = revenue_manual_rub + ?,
                        last_updated = strftime('%s', 'now')
                    WHERE id = 1
                """, (amount,))
            
            await db.commit()

    async def get_stats(self) -> Dict[str, Any]:
        """Получить текущую статистику"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM stats WHERE id = 1")
            row = await cursor.fetchone()
            return dict(row) if row else {}

    async def add_payment_history(self, user_id: int, method: str, subscription_type: str, 
                                amount: float, currency: str, transaction_id: str = None):
        """Добавить запись в историю платежей"""
        from datetime import datetime
        
        current_time = datetime.now()
        week_number = current_time.isocalendar()[1]  # Номер недели в году
        year = current_time.year
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO history_payments 
                (user_id, payment_method, subscription_type, amount, currency, 
                 transaction_id, week_number, year)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, method, subscription_type, amount, currency, 
                  transaction_id, week_number, year))
            await db.commit()

    async def get_weekly_stats(self, week_number: int = None, year: int = None) -> Dict[str, Any]:
        """Получить статистику за неделю"""
        from datetime import datetime
        
        if not week_number or not year:
            current_time = datetime.now()
            week_number = current_time.isocalendar()[1] - 1  # Прошлая неделя
            year = current_time.year
            
            # Если это первая неделя года, берем последнюю неделю прошлого года
            if week_number == 0:
                year -= 1
                week_number = 52  # Приблизительно последняя неделя года
        
        async with aiosqlite.connect(self.db_path) as db:
            # Статистика платежей за неделю
            cursor = await db.execute("""
                SELECT 
                    payment_method,
                    currency,
                    COUNT(*) as count,
                    SUM(amount) as total_amount
                FROM history_payments 
                WHERE week_number = ? AND year = ?
                GROUP BY payment_method, currency
            """, (week_number, year))
            
            payments_stats = {}
            async for row in cursor:
                method = row[0]
                currency = row[1]
                count = row[2]
                total = row[3]
                
                if method not in payments_stats:
                    payments_stats[method] = {}
                payments_stats[method][currency] = {
                    'count': count,
                    'total': total
                }
            
            # Новые пользователи за неделю
            week_start = datetime.fromisocalendar(year, week_number, 1).timestamp()
            week_end = datetime.fromisocalendar(year, week_number, 7).timestamp() + 86400
            
            cursor = await db.execute("""
                SELECT COUNT(*) FROM users 
                WHERE created_at BETWEEN ? AND ?
            """, (week_start, week_end))
            new_users = (await cursor.fetchone())[0]
            
            # Активные пользователи (те, кто генерировал посты)
            cursor = await db.execute("""
                SELECT COUNT(DISTINCT us.user_id) 
                FROM user_settings us
                JOIN users u ON us.user_id = u.user_id
                WHERE us.last_post_time BETWEEN ? AND ?
            """, (week_start, week_end))
            active_users = (await cursor.fetchone())[0]
            
            return {
                'week_number': week_number,
                'year': year,
                'payments_stats': payments_stats,
                'new_users': new_users,
                'active_users': active_users,
                'week_start': week_start,
                'week_end': week_end
            }

    async def export_payments_csv(self, start_date: int = None, end_date: int = None) -> str:
        """Экспорт платежей в CSV формат"""
        import csv
        import io
        from datetime import datetime
        
        # По умолчанию экспортируем за последний месяц
        if not start_date:
            start_date = int(datetime.now().timestamp()) - (30 * 24 * 60 * 60)
        if not end_date:
            end_date = int(datetime.now().timestamp())
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    hp.user_id,
                    hp.payment_method,
                    hp.subscription_type,
                    hp.amount,
                    hp.currency,
                    hp.transaction_id,
                    hp.payment_date,
                    u.user_id as telegram_id
                FROM history_payments hp
                JOIN users u ON hp.user_id = u.user_id
                WHERE hp.payment_date BETWEEN ? AND ?
                ORDER BY hp.payment_date DESC
            """, (start_date, end_date))
            
            # Создаем CSV в памяти
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Заголовки
            writer.writerow([
                'User ID', 'Payment Method', 'Subscription Type', 
                'Amount', 'Currency', 'Transaction ID', 'Date', 'Telegram ID'
            ])
            
            # Данные
            async for row in cursor:
                payment_date = datetime.fromtimestamp(row[6]).strftime('%Y-%m-%d %H:%M:%S')
                writer.writerow([
                    row[0], row[1], row[2], row[3], row[4], 
                    row[5] or '', payment_date, row[7]
                ])
            
            return output.getvalue()


# Глобальный экземпляр базы данных
db = Database()