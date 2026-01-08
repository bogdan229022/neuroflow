"""
Менеджер конфигурации для динамического управления API-ключами
"""

import asyncio
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class ConfigManager:
    """Синглтон для управления конфигурацией"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        """Создание singleton экземпляра"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Инициализация ConfigManager"""
        if not self._initialized:
            self._config_cache: Dict[str, str] = {}
            self._lock = asyncio.Lock()
            self._initialized = True
    
    async def load_config(self):
        """Загрузка конфигурации из БД в кэш"""
        from app.models.postgresql_database import postgresql_db as db
        
        async with self._lock:
            try:
                configs = await db.get_all_configs()
                self._config_cache.update(configs)
                logger.info(f"Loaded {len(configs)} config keys from database")
            except Exception as e:
                logger.error(f"Error loading config from database: {e}")
    
    async def get(self, key: str, default: str = None) -> Optional[str]:
        """Получение значения конфигурации"""
        from app.models.postgresql_database import postgresql_db as db
        
        # Сначала проверяем кэш
        if key in self._config_cache:
            return self._config_cache[key]
        
        # Если нет в кэше, загружаем из БД
        try:
            value = await db.get_config(key)
            if value is not None:
                self._config_cache[key] = value
            return value or default
        except Exception as e:
            logger.error(f"Error getting config {key}: {e}")
            return default
    
    async def set(self, key: str, value: str, updated_by: int = None):
        """Установка значения конфигурации"""
        from app.models.postgresql_database import postgresql_db as db
        
        async with self._lock:
            try:
                await db.set_config(key, value, updated_by)
                self._config_cache[key] = value
                logger.info(f"Config {key} updated by user {updated_by}")
            except Exception as e:
                logger.error(f"Error setting config {key}: {e}")
                raise
    
    async def reload(self):
        """Перезагрузка конфигурации из БД"""
        await self.load_config()
    
    def get_cached(self, key: str, default: str = None) -> Optional[str]:
        """Получение значения из кэша (синхронно)"""
        return self._config_cache.get(key, default)
    
    async def is_payment_method_available(self, method: str) -> bool:
        """Проверка доступности метода оплаты"""
        from app.models.postgresql_database import postgresql_db as db
        return await db.is_payment_method_available(method)
    
    async def get_payment_methods_status(self) -> Dict[str, bool]:
        """Получение статуса всех методов оплаты"""
        from app.models.postgresql_database import postgresql_db as db
        return await db.get_payment_methods_status()
    
    # Удобные методы для получения API ключей
    async def get_groq_key(self) -> Optional[str]:
        """Получение основного Groq API ключа (для обратной совместимости)"""
        return await self.get('groq_api_key')
    
    async def get_groq_keys(self) -> List[str]:
        """Получение всех Groq API ключей"""
        keys = []
        
        # Получаем ключи из БД (поддерживаем до 4 ключей)
        for i in range(1, 5):
            key_name = f'groq_api_key_{i}' if i > 1 else 'groq_api_key'
            key = await self.get(key_name)
            if key and key.strip():
                keys.append(key.strip())
        
        # Если в БД нет ключей, используем из config.py
        if not keys:
            from app.core.config import GROQ_API_KEYS
            keys = [key for key in GROQ_API_KEYS if key and key.strip()]
        
        return keys
    
    async def set_groq_keys(self, keys: List[str], updated_by: int = None):
        """Установка всех Groq API ключей"""
        # Очищаем старые ключи
        for i in range(1, 5):
            key_name = f'groq_api_key_{i}' if i > 1 else 'groq_api_key'
            await self.set(key_name, '', updated_by)
        
        # Устанавливаем новые ключи
        for i, key in enumerate(keys[:4], 1):  # Максимум 4 ключа
            key_name = f'groq_api_key_{i}' if i > 1 else 'groq_api_key'
            await self.set(key_name, key.strip(), updated_by)
        
        # Переинициализируем пул ключей
        from app.services.api_pool_manager import reinitialize_groq_pool
        await reinitialize_groq_pool()
        
        logger.info(f"Updated {len(keys)} Groq API keys")
    
    async def add_groq_key(self, key: str, updated_by: int = None):
        """Добавление нового Groq API ключа"""
        current_keys = await self.get_groq_keys()
        
        if len(current_keys) >= 4:
            raise ValueError("Maximum 4 Groq API keys supported")
        
        if key.strip() in current_keys:
            raise ValueError("This API key is already added")
        
        current_keys.append(key.strip())
        await self.set_groq_keys(current_keys, updated_by)
    
    async def remove_groq_key(self, key_index: int, updated_by: int = None):
        """Удаление Groq API ключа по индексу"""
        current_keys = await self.get_groq_keys()
        
        if key_index < 0 or key_index >= len(current_keys):
            raise ValueError("Invalid key index")
        
        current_keys.pop(key_index)
        await self.set_groq_keys(current_keys, updated_by)
    
    async def get_crypto_token(self) -> Optional[str]:
        """Получение CryptoBot токена"""
        return await self.get('crypto_bot_token')
    
    async def get_aaio_keys(self) -> Dict[str, Optional[str]]:
        """Получение всех ключей AAIO"""
        return {
            'api_key': await self.get('aaio_api_key'),
            'shop_id': await self.get('aaio_shop_id'),
            'secret_key': await self.get('aaio_secret_key')
        }
    
    async def is_manual_payment_enabled(self) -> bool:
        """Проверка включена ли ручная оплата"""
        return await self.is_payment_method_available('manual')
    
    async def set_manual_payment_enabled(self, enabled: bool, updated_by: int = None):
        """Включение/отключение ручной оплаты"""
        value = 'true' if enabled else 'false'
        await self.set('manual_payment_enabled', value, updated_by)


# Глобальный экземпляр менеджера конфигурации
config_manager = ConfigManager()