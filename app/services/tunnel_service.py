#!/usr/bin/env python3
"""
Tunnel Service
Сервис для динамического получения URL туннеля из базы данных/Redis
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta

from app.models.postgresql_database import postgresql_db
from app.services.redis_cache import redis_cache

logger = logging.getLogger(__name__)


class TunnelService:
    """Сервис для работы с динамическими URL туннелей"""
    
    def __init__(self):
        """Инициализация Tunnel Service"""
        self.cached_url = None
        self.cache_expiry = None
        self.cache_duration = 300  # 5 минут кэш
        
    async def get_webapp_url(self, fallback_url: str = "https://localhost:8081") -> str:
        """
        Получение актуального URL WebApp из базы данных или кэша
        
        Args:
            fallback_url: URL по умолчанию если туннель недоступен
            
        Returns:
            str: Актуальный URL для WebApp
        """
        try:
            # Проверяем локальный кэш
            if self.cached_url and self.cache_expiry and datetime.now() < self.cache_expiry:
                logger.debug(f"Using cached webapp URL: {self.cached_url}")
                return self.cached_url
            
            # Пытаемся получить из Redis (быстрее)
            url = await self._get_url_from_redis()
            
            # Если Redis недоступен, пытаемся получить из PostgreSQL
            if not url:
                url = await self._get_url_from_database()
            
            # Если получили URL, кэшируем его
            if url and self._validate_url(url):
                self.cached_url = url
                self.cache_expiry = datetime.now() + timedelta(seconds=self.cache_duration)
                logger.info(f"✅ Retrieved webapp URL: {url}")
                return url
            else:
                logger.warning(f"⚠️ No valid tunnel URL found, using fallback: {fallback_url}")
                return fallback_url
                
        except Exception as e:
            logger.error(f"❌ Error getting webapp URL: {e}")
            return fallback_url
    
    async def _get_url_from_redis(self) -> Optional[str]:
        """Получение URL из Redis"""
        try:
            if hasattr(redis_cache, 'redis') and redis_cache.redis:
                url = await redis_cache.get("webapp_url")
                if url:
                    logger.debug(f"Found webapp URL in Redis: {url}")
                    return url
        except Exception as e:
            logger.debug(f"Redis unavailable: {e}")
        
        return None
    
    async def _get_url_from_database(self) -> Optional[str]:
        """Получение URL из PostgreSQL"""
        try:
            async with postgresql_db.get_connection() as conn:
                # Создаем таблицу если не существует
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS system_configs (
                        key VARCHAR(255) PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())
                    )
                """)
                
                # Получаем URL
                row = await conn.fetchrow("""
                    SELECT value, updated_at 
                    FROM system_configs 
                    WHERE key = $1
                """, "webapp_url")
                
                if row:
                    url = row['value']
                    updated_at = datetime.fromtimestamp(row['updated_at'])
                    
                    # Проверяем, что URL не слишком старый (не старше 24 часов)
                    if datetime.now() - updated_at < timedelta(hours=24):
                        logger.debug(f"Found webapp URL in database: {url}")
                        return url
                    else:
                        logger.warning(f"Webapp URL in database is too old: {updated_at}")
                
        except Exception as e:
            logger.debug(f"Database unavailable: {e}")
        
        return None
    
    def _validate_url(self, url: str) -> bool:
        """Валидация URL"""
        if not url or not isinstance(url, str):
            return False
        
        # Проверяем базовый формат
        if not url.startswith(('http://', 'https://')):
            return False
        
        # Проверяем длину
        if len(url) < 10 or len(url) > 500:
            return False
        
        return True
    
    async def set_webapp_url(self, url: str) -> bool:
        """
        Установка нового URL WebApp (для административных целей)
        
        Args:
            url: Новый URL для установки
            
        Returns:
            bool: True если успешно установлен
        """
        try:
            if not self._validate_url(url):
                logger.error(f"Invalid URL format: {url}")
                return False
            
            # Сохраняем в Redis
            try:
                if hasattr(redis_cache, 'redis') and redis_cache.redis:
                    await redis_cache.set("webapp_url", url, ttl=86400)  # 24 часа
                    logger.info(f"✅ Saved webapp URL to Redis: {url}")
            except Exception as e:
                logger.warning(f"Failed to save to Redis: {e}")
            
            # Сохраняем в PostgreSQL
            try:
                async with postgresql_db.get_connection() as conn:
                    await conn.execute("""
                        INSERT INTO system_configs (key, value, updated_at)
                        VALUES ($1, $2, EXTRACT(EPOCH FROM NOW()))
                        ON CONFLICT (key) 
                        DO UPDATE SET 
                            value = EXCLUDED.value,
                            updated_at = EXCLUDED.updated_at
                    """, "webapp_url", url)
                    logger.info(f"✅ Saved webapp URL to database: {url}")
            except Exception as e:
                logger.warning(f"Failed to save to database: {e}")
            
            # Обновляем локальный кэш
            self.cached_url = url
            self.cache_expiry = datetime.now() + timedelta(seconds=self.cache_duration)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error setting webapp URL: {e}")
            return False
    
    async def clear_cache(self):
        """Очистка кэша URL"""
        self.cached_url = None
        self.cache_expiry = None
        logger.info("🗑️ Webapp URL cache cleared")
    
    async def get_url_status(self) -> dict:
        """
        Получение статуса URL для мониторинга
        
        Returns:
            dict: Информация о статусе URL
        """
        try:
            redis_url = await self._get_url_from_redis()
            db_url = await self._get_url_from_database()
            
            return {
                'cached_url': self.cached_url,
                'cache_expiry': self.cache_expiry.isoformat() if self.cache_expiry else None,
                'redis_url': redis_url,
                'database_url': db_url,
                'urls_match': redis_url == db_url if redis_url and db_url else None,
                'last_check': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting URL status: {e}")
            return {
                'error': str(e),
                'last_check': datetime.now().isoformat()
            }


# Создаем глобальный экземпляр сервиса
tunnel_service = TunnelService()