"""
Redis Cache Service for Ultra-Scaling
High-performance caching for user states and temporary data
"""

import asyncio
import json
import logging
import time
from typing import Any, Optional, Dict, List
import redis.asyncio as redis
from app.core.config import REDIS_URL, REDIS_POOL_MAX_CONNECTIONS, REDIS_CACHE_TTL

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis cache service for high-performance data operations"""
    
    def __init__(self):
        """Инициализация Redis Cache"""
        self.pool: Optional[redis.ConnectionPool] = None
        self.redis: Optional[redis.Redis] = None
        self._lock = asyncio.Lock()
    
    async def init_pool(self):
        """Инициализация пула соединений Redis"""
        if self.pool is None:
            async with self._lock:
                if self.pool is None:  # Double-check locking
                    try:
                        self.pool = redis.ConnectionPool.from_url(
                            REDIS_URL,
                            max_connections=REDIS_POOL_MAX_CONNECTIONS,
                            retry_on_timeout=True,
                            socket_keepalive=True,
                            socket_keepalive_options={},
                            health_check_interval=30
                        )
                        
                        self.redis = redis.Redis(
                            connection_pool=self.pool,
                            decode_responses=True
                        )
                        
                        # Тестируем соединение
                        await self.redis.ping()
                        
                        logger.info(f"Redis pool initialized: {REDIS_POOL_MAX_CONNECTIONS} max connections")
                        
                    except Exception as e:
                        logger.error(f"Failed to initialize Redis pool: {e}")
                        # Fallback to in-memory cache
                        self._fallback_cache = {}
                        logger.warning("Using in-memory fallback cache")
    
    async def close_pool(self):
        """Закрытие пула соединений"""
        if self.redis:
            await self.redis.close()
            self.redis = None
        
        if self.pool:
            await self.pool.disconnect()
            self.pool = None
        
        logger.info("Redis pool closed")
    
    def _cleanup_expired_cache(self):
        """Очистка истекших записей из fallback кэша для предотвращения утечек памяти"""
        if not hasattr(self, '_fallback_cache'):
            self._fallback_cache = {}
            return
        
        current_time = time.time()
        expired_keys = [
            key for key, item in self._fallback_cache.items()
            if current_time >= item['expires']
        ]
        
        for key in expired_keys:
            del self._fallback_cache[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Установка значения в кэш"""
        try:
            if not self.redis:
                await self.init_pool()
            
            if not self.redis:
                # Fallback to in-memory with TTL cleanup
                self._cleanup_expired_cache()
                self._fallback_cache[key] = {
                    'value': value,
                    'expires': time.time() + (ttl or REDIS_CACHE_TTL)
                }
                return True
            
            # Сериализуем значение
            serialized_value = json.dumps(value) if not isinstance(value, str) else value
            
            # Устанавливаем TTL
            expire_time = ttl or REDIS_CACHE_TTL
            
            await self.redis.setex(key, expire_time, serialized_value)
            return True
            
        except Exception as e:
            logger.error(f"Redis set error for key {key}: {e}")
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """Получение значения из кэша"""
        try:
            if not self.redis:
                await self.init_pool()
            
            if not self.redis:
                # Fallback to in-memory
                if key in self._fallback_cache:
                    item = self._fallback_cache[key]
                    if time.time() < item['expires']:
                        return item['value']
                    else:
                        del self._fallback_cache[key]
                return None
            
            value = await self.redis.get(key)
            
            if value is None:
                return None
            
            # Пытаемся десериализовать JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
                
        except Exception as e:
            logger.error(f"Redis get error for key {key}: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """Удаление значения из кэша"""
        try:
            if not self.redis:
                await self.init_pool()
            
            if not self.redis:
                # Fallback to in-memory
                if key in self._fallback_cache:
                    del self._fallback_cache[key]
                return True
            
            result = await self.redis.delete(key)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Redis delete error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Проверка существования ключа"""
        try:
            if not self.redis:
                await self.init_pool()
            
            if not self.redis:
                # Fallback to in-memory
                if key in self._fallback_cache:
                    item = self._fallback_cache[key]
                    if time.time() < item['expires']:
                        return True
                    else:
                        del self._fallback_cache[key]
                return False
            
            result = await self.redis.exists(key)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Redis exists error for key {key}: {e}")
            return False
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Инкремент значения"""
        try:
            if not self.redis:
                await self.init_pool()
            
            if not self.redis:
                # Fallback to in-memory
                if key not in self._fallback_cache:
                    self._fallback_cache[key] = {
                        'value': 0,
                        'expires': time.time() + REDIS_CACHE_TTL
                    }
                
                self._fallback_cache[key]['value'] += amount
                return self._fallback_cache[key]['value']
            
            result = await self.redis.incrby(key, amount)
            return result
            
        except Exception as e:
            logger.error(f"Redis increment error for key {key}: {e}")
            return None
    
    async def set_hash(self, key: str, field: str, value: Any, ttl: int = None) -> bool:
        """Установка значения в хэш"""
        try:
            if not self.redis:
                await self.init_pool()
            
            if not self.redis:
                # Fallback to in-memory
                if key not in self._fallback_cache:
                    self._fallback_cache[key] = {
                        'value': {},
                        'expires': time.time() + (ttl or REDIS_CACHE_TTL)
                    }
                
                self._fallback_cache[key]['value'][field] = value
                return True
            
            serialized_value = json.dumps(value) if not isinstance(value, str) else value
            
            await self.redis.hset(key, field, serialized_value)
            
            if ttl:
                await self.redis.expire(key, ttl)
            
            return True
            
        except Exception as e:
            logger.error(f"Redis hset error for key {key}, field {field}: {e}")
            return False
    
    async def get_hash(self, key: str, field: str) -> Optional[Any]:
        """Получение значения из хэша"""
        try:
            if not self.redis:
                await self.init_pool()
            
            if not self.redis:
                # Fallback to in-memory
                if key in self._fallback_cache:
                    item = self._fallback_cache[key]
                    if time.time() < item['expires']:
                        return item['value'].get(field)
                    else:
                        del self._fallback_cache[key]
                return None
            
            value = await self.redis.hget(key, field)
            
            if value is None:
                return None
            
            # Пытаемся десериализовать JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
                
        except Exception as e:
            logger.error(f"Redis hget error for key {key}, field {field}: {e}")
            return None
    
    async def get_all_hash(self, key: str) -> Optional[Dict[str, Any]]:
        """Получение всех значений из хэша"""
        try:
            if not self.redis:
                await self.init_pool()
            
            if not self.redis:
                # Fallback to in-memory
                if key in self._fallback_cache:
                    item = self._fallback_cache[key]
                    if time.time() < item['expires']:
                        return item['value']
                    else:
                        del self._fallback_cache[key]
                return None
            
            hash_data = await self.redis.hgetall(key)
            
            if not hash_data:
                return None
            
            # Десериализуем все значения
            result = {}
            for field, value in hash_data.items():
                try:
                    result[field] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[field] = value
            
            return result
            
        except Exception as e:
            logger.error(f"Redis hgetall error for key {key}: {e}")
            return None
    
    # Специализированные методы для бота
    
    async def cache_user_state(self, user_id: int, state_data: Dict[str, Any], ttl: int = 3600) -> bool:
        """Кэширование состояния пользователя"""
        key = f"user_state:{user_id}"
        return await self.set(key, state_data, ttl)
    
    async def get_user_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение состояния пользователя"""
        key = f"user_state:{user_id}"
        return await self.get(key)
    
    async def cache_generation_result(self, user_id: int, content_type: str, result: Any, ttl: int = 1800) -> bool:
        """Кэширование результата генерации"""
        key = f"generation:{user_id}:{content_type}:{int(time.time())}"
        return await self.set(key, result, ttl)
    
    async def get_recent_generations(self, user_id: int, content_type: str, limit: int = 5) -> List[Any]:
        """Получение последних генераций пользователя"""
        try:
            if not self.redis:
                await self.init_pool()
            
            if not self.redis:
                return []
            
            pattern = f"generation:{user_id}:{content_type}:*"
            keys = await self.redis.keys(pattern)
            
            if not keys:
                return []
            
            # Сортируем по времени (последние сначала)
            keys.sort(reverse=True)
            keys = keys[:limit]
            
            results = []
            for key in keys:
                value = await self.get(key)
                if value:
                    results.append(value)
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting recent generations: {e}")
            return []
    
    async def cache_api_key_status(self, key_id: str, status_data: Dict[str, Any], ttl: int = 300) -> bool:
        """Кэширование статуса API ключа"""
        key = f"api_key_status:{key_id}"
        return await self.set(key, status_data, ttl)
    
    async def get_api_key_status(self, key_id: str) -> Optional[Dict[str, Any]]:
        """Получение статуса API ключа"""
        key = f"api_key_status:{key_id}"
        return await self.get(key)
    
    async def increment_api_usage(self, key_id: str, ttl: int = 3600) -> Optional[int]:
        """Инкремент использования API ключа"""
        key = f"api_usage:{key_id}:{int(time.time() // ttl)}"
        result = await self.increment(key)
        
        if result and self.redis:
            await self.redis.expire(key, ttl)
        
        return result
    
    async def get_api_usage(self, key_id: str, ttl: int = 3600) -> int:
        """Получение статистики использования API ключа"""
        key = f"api_usage:{key_id}:{int(time.time() // ttl)}"
        result = await self.get(key)
        return result or 0
    
    async def cache_image_generation_queue(self, queue_data: List[Dict[str, Any]], ttl: int = 1800) -> bool:
        """Кэширование очереди генерации изображений"""
        key = "image_generation_queue"
        return await self.set(key, queue_data, ttl)
    
    async def get_image_generation_queue(self) -> List[Dict[str, Any]]:
        """Получение очереди генерации изображений"""
        key = "image_generation_queue"
        result = await self.get(key)
        return result or []
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Получение статистики кэша"""
        try:
            if not self.redis:
                await self.init_pool()
            
            if not self.redis:
                return {
                    'status': 'fallback',
                    'type': 'in-memory',
                    'keys_count': len(getattr(self, '_fallback_cache', {}))
                }
            
            info = await self.redis.info()
            
            return {
                'status': 'connected',
                'type': 'redis',
                'used_memory': info.get('used_memory_human', 'N/A'),
                'connected_clients': info.get('connected_clients', 0),
                'total_commands_processed': info.get('total_commands_processed', 0),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'hit_rate': round(
                    info.get('keyspace_hits', 0) / 
                    max(info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0), 1) * 100, 2
                )
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def ping(self) -> bool:
        """Проверка соединения с Redis"""
        try:
            if not self.redis:
                await self.init_pool()
            
            if self.redis:
                result = await self.redis.ping()
                return result
            else:
                # Fallback cache всегда доступен
                return True
                
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False


# Глобальный экземпляр Redis кэша
redis_cache = RedisCache()