"""
Ultra-Scaling API Pool Manager - 7 Groq Keys with Weighted Round Robin
High-performance load balancing with smart cooldown and Redis caching
"""

import asyncio
import aiohttp
import logging
import time
import hashlib
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

from app.core.config import GROQ_API_KEYS
from app.services.redis_cache import redis_cache

logger = logging.getLogger(__name__)


class APIKeyStatus(Enum):
    """Статусы API ключей"""
    ACTIVE = "active"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    COOLDOWN = "cooldown"


@dataclass
class APIKeyInfo:
    """Информация об API ключе"""
    key: str
    key_id: str
    status: APIKeyStatus = APIKeyStatus.ACTIVE
    requests_made: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    last_used: float = 0
    last_error: Optional[str] = None
    cooldown_until: float = 0
    rate_limit_reset: float = 0
    weight: float = 1.0  # Вес для Weighted Round Robin
    response_times: List[float] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Процент успешных запросов"""
        if self.requests_made == 0:
            return 100.0
        return (self.successful_requests / self.requests_made) * 100
    
    @property
    def avg_response_time(self) -> float:
        """Среднее время ответа"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times[-10:]) / len(self.response_times[-10:])  # Последние 10
    
    @property
    def is_available(self) -> bool:
        """Доступен ли ключ для использования"""
        current_time = time.time()
        return (
            self.status == APIKeyStatus.ACTIVE and
            current_time > self.cooldown_until and
            current_time > self.rate_limit_reset
        )
    
    def record_request(self, success: bool, response_time: float, error: str = None):
        """Записать результат запроса"""
        self.requests_made += 1
        self.last_used = time.time()
        
        if success:
            self.successful_requests += 1
            self.status = APIKeyStatus.ACTIVE
            self.last_error = None
        else:
            self.failed_requests += 1
            self.last_error = error
            
            # Определяем статус на основе ошибки
            if "429" in str(error) or "rate limit" in str(error).lower():
                self.status = APIKeyStatus.RATE_LIMITED
            else:
                self.status = APIKeyStatus.ERROR
        
        # Записываем время ответа
        self.response_times.append(response_time)
        if len(self.response_times) > 20:  # Храним только последние 20
            self.response_times = self.response_times[-20:]
        
        # Обновляем вес на основе производительности
        self._update_weight()
    
    def _update_weight(self):
        """Обновление веса ключа на основе производительности"""
        base_weight = 1.0
        
        # Учитываем успешность
        success_factor = self.success_rate / 100.0
        
        # Учитываем скорость ответа (инвертируем - чем быстрее, тем больше вес)
        speed_factor = 1.0
        if self.avg_response_time > 0:
            speed_factor = max(0.1, 2.0 - (self.avg_response_time / 5.0))  # 5 секунд = базовая скорость
        
        self.weight = base_weight * success_factor * speed_factor
        self.weight = max(0.1, min(2.0, self.weight))  # Ограничиваем от 0.1 до 2.0
    
    def set_rate_limited(self, retry_after: int = None):
        """Установить статус rate limit"""
        self.status = APIKeyStatus.RATE_LIMITED
        
        # Умный cooldown на основе заголовка Retry-After или экспоненциальная задержка
        if retry_after:
            self.rate_limit_reset = time.time() + retry_after
        else:
            # Экспоненциальная задержка на основе количества неудач
            cooldown_time = min(300, 60 * (2 ** min(self.failed_requests, 5)))  # Максимум 5 минут
            self.rate_limit_reset = time.time() + cooldown_time
        
        logger.warning(f"API key {self.key_id} rate limited until {self.rate_limit_reset}")
    
    def set_cooldown(self, duration: int = 60):
        """Установить cooldown"""
        self.status = APIKeyStatus.COOLDOWN
        self.cooldown_until = time.time() + duration
        logger.info(f"API key {self.key_id} on cooldown for {duration} seconds")


class UltraScalingAPIPool:
    """Ultra-scaling API pool с 7 ключами и Weighted Round Robin"""
    
    def __init__(self):
        """Инициализация Ultra Scaling API Pool"""
        self.api_keys: List[APIKeyInfo] = []
        self.session: Optional[aiohttp.ClientSession] = None
        self.current_key_index = 0
        self.total_requests = 0
        self.total_successful = 0
        self.admin_chat_id: Optional[int] = None
        self.alert_thresholds = {
            'keys_down': 5,  # Алерт если 5+ ключей недоступны
            'success_rate': 80,  # Алерт если общий success rate < 80%
            'avg_response_time': 10  # Алерт если среднее время > 10 сек
        }
        
        self._init_api_keys()
    
    def _init_api_keys(self):
        """Инициализация API ключей с безопасным логированием"""
        for i, key in enumerate(GROQ_API_KEYS):
            if key and key.strip():
                # БЕЗОПАСНОЕ МАСКИРОВАНИЕ: показываем только первые 8 и последние 4 символа
                masked_key = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***masked***"
                key_id = f"groq_{i+1}_{hashlib.md5(key.encode()).hexdigest()[:8]}"
                api_key_info = APIKeyInfo(
                    key=key,
                    key_id=key_id
                )
                self.api_keys.append(api_key_info)
        
        logger.info(f"Initialized Ultra-Scaling API pool with {len(self.api_keys)} keys (keys masked for security)")
    
    async def init_session(self):
        """Инициализация HTTP сессии"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={'User-Agent': 'NeuroFlow Ultra-Scaling Bot'}
            )
    
    async def close_session(self):
        """Закрытие HTTP сессии"""
        if self.session:
            await self.session.close()
            self.session = None
    
    def get_available_keys(self) -> List[APIKeyInfo]:
        """Получить доступные ключи"""
        return [key for key in self.api_keys if key.is_available]
    
    def get_best_key_weighted(self) -> Optional[APIKeyInfo]:
        """Получить лучший ключ с учетом весов (Weighted Round Robin)"""
        available_keys = self.get_available_keys()
        
        if not available_keys:
            return None
        
        # Weighted Round Robin: выбираем ключ на основе весов
        total_weight = sum(key.weight for key in available_keys)
        
        if total_weight == 0:
            # Если все веса 0, используем обычный round robin
            self.current_key_index = (self.current_key_index + 1) % len(available_keys)
            return available_keys[self.current_key_index]
        
        # Генерируем случайное число от 0 до total_weight
        import random
        target_weight = random.uniform(0, total_weight)
        
        current_weight = 0
        for key in available_keys:
            current_weight += key.weight
            if current_weight >= target_weight:
                return key
        
        # Fallback на последний ключ
        return available_keys[-1]
    
    async def generate_completion(self, messages: List[Dict], model: str = "llama-3.3-70b-versatile", 
                                max_tokens: int = 1000, temperature: float = 0.7, 
                                max_retries: int = None) -> Optional[Any]:
        """Генерация с автоматическими повторами и балансировкой нагрузки"""
        await self.init_session()
        
        if max_retries is None:
            max_retries = min(len(self.api_keys), 7)  # Максимум 7 попыток
        
        last_error = None
        
        for attempt in range(max_retries):
            # Получаем лучший доступный ключ
            api_key = self.get_best_key_weighted()
            
            if not api_key:
                # Если нет доступных ключей, ждем и пробуем снова
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                else:
                    await self._send_alert("critical", "Все API ключи недоступны!")
                    break
            
            start_time = time.time()
            
            try:
                # Кэшируем статус ключа
                await redis_cache.cache_api_key_status(api_key.key_id, {
                    'status': api_key.status.value,
                    'requests_made': api_key.requests_made,
                    'success_rate': api_key.success_rate,
                    'last_used': api_key.last_used
                })
                
                # Инкрементируем использование
                await redis_cache.increment_api_usage(api_key.key_id)
                
                # Выполняем запрос
                headers = {
                    "Authorization": f"Bearer {api_key.key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "messages": messages,
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                
                async with self.session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    response_time = time.time() - start_time
                    
                    if response.status == 200:
                        result = await response.json()
                        
                        # Записываем успешный запрос
                        api_key.record_request(True, response_time)
                        self.total_requests += 1
                        self.total_successful += 1
                        
                        logger.debug(f"Successful request with key {api_key.key_id} in {response_time:.2f}s")
                        return result
                    
                    elif response.status == 429:
                        # Rate limit
                        retry_after = response.headers.get('Retry-After')
                        retry_after_int = int(retry_after) if retry_after else None
                        
                        api_key.set_rate_limited(retry_after_int)
                        api_key.record_request(False, response_time, f"Rate limit (429)")
                        
                        last_error = f"Rate limit on key {api_key.key_id}"
                        logger.warning(last_error)
                        
                        # Продолжаем с другим ключом
                        continue
                    
                    else:
                        # Другие HTTP ошибки - НЕ ЛОГИРУЕМ ПОЛНЫЙ ОТВЕТ (может содержать ключи)
                        error_msg = f"HTTP {response.status}"
                        
                        api_key.record_request(False, response_time, error_msg)
                        last_error = f"API error with key {api_key.key_id}: {error_msg}"
                        
                        if response.status in [401, 403]:
                            # Ключ недействителен
                            api_key.status = APIKeyStatus.ERROR
                            api_key.set_cooldown(3600)  # 1 час cooldown
                        
                        logger.error(last_error)
                        continue
            
            except asyncio.TimeoutError:
                response_time = time.time() - start_time
                api_key.record_request(False, response_time, "Timeout")
                last_error = f"Timeout with key {api_key.key_id}"
                logger.warning(last_error)
                continue
            
            except Exception as e:
                response_time = time.time() - start_time
                api_key.record_request(False, response_time, str(e))
                last_error = f"Exception with key {api_key.key_id}: {str(e)}"
                logger.error(last_error)
                continue
        
        # Все попытки неудачны
        self.total_requests += 1
        await self._check_and_send_alerts()
        
        logger.error(f"All {max_retries} attempts failed. Last error: {last_error}")
        return None
    
    async def _send_alert(self, level: str, message: str):
        """Отправка алерта админу"""
        if not self.admin_chat_id:
            return
        
        try:
            # Импортируем бота для отправки сообщения
            from app.core.main import bot
            
            emoji = "🚨" if level == "critical" else "⚠️"
            alert_text = f"{emoji} **Ultra-Scaling Alert**\n\n{message}\n\nВремя: {time.strftime('%H:%M:%S')}"
            
            await bot.send_message(self.admin_chat_id, alert_text)
            logger.info(f"Alert sent to admin: {message}")
            
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    async def _check_and_send_alerts(self):
        """Проверка условий для отправки алертов"""
        available_keys = len(self.get_available_keys())
        total_keys = len(self.api_keys)
        unavailable_keys = total_keys - available_keys
        
        # Алерт о недоступных ключах
        if unavailable_keys >= self.alert_thresholds['keys_down']:
            await self._send_alert(
                "warning",
                f"Внимание! {unavailable_keys} из {total_keys} ключей недоступны!\n"
                f"Доступно: {available_keys} ключей"
            )
        
        # Алерт о низком success rate
        if self.total_requests > 10:  # Минимум 10 запросов для статистики
            success_rate = (self.total_successful / self.total_requests) * 100
            if success_rate < self.alert_thresholds['success_rate']:
                await self._send_alert(
                    "warning",
                    f"Низкий success rate: {success_rate:.1f}%\n"
                    f"Успешных запросов: {self.total_successful}/{self.total_requests}"
                )
        
        # Алерт о медленных ответах
        avg_response_times = [key.avg_response_time for key in self.api_keys if key.avg_response_time > 0]
        if avg_response_times:
            overall_avg = sum(avg_response_times) / len(avg_response_times)
            if overall_avg > self.alert_thresholds['avg_response_time']:
                await self._send_alert(
                    "warning",
                    f"Медленные ответы API: {overall_avg:.1f}s в среднем\n"
                    f"Рекомендуется проверить нагрузку на сервисы"
                )
    
    def set_admin_chat_id(self, chat_id: int):
        """Установка ID чата админа для алертов"""
        self.admin_chat_id = chat_id
        logger.info(f"Admin chat ID set to {chat_id}")
    
    async def get_pool_status(self) -> Dict[str, Any]:
        """Получение детального статуса пула"""
        available_keys = self.get_available_keys()
        
        keys_status = []
        for key in self.api_keys:
            keys_status.append({
                'key_id': key.key_id,
                'status': key.status.value,
                'is_available': key.is_available,
                'requests_made': key.requests_made,
                'success_rate': round(key.success_rate, 1),
                'avg_response_time': round(key.avg_response_time, 2),
                'weight': round(key.weight, 2),
                'last_used': key.last_used,
                'last_error': key.last_error,
                'cooldown_until': key.cooldown_until,
                'rate_limit_reset': key.rate_limit_reset
            })
        
        overall_success_rate = 0
        if self.total_requests > 0:
            overall_success_rate = (self.total_successful / self.total_requests) * 100
        
        # Получаем статистику из Redis
        cache_stats = await redis_cache.get_cache_stats()
        
        return {
            'total_keys': len(self.api_keys),
            'available_keys': len(available_keys),
            'unavailable_keys': len(self.api_keys) - len(available_keys),
            'total_requests': self.total_requests,
            'successful_requests': self.total_successful,
            'overall_success_rate': round(overall_success_rate, 1),
            'keys_status': keys_status,
            'cache_stats': cache_stats,
            'alert_thresholds': self.alert_thresholds,
            'admin_chat_id': self.admin_chat_id
        }
    
    async def test_connection(self) -> Dict[str, Any]:
        """Тестирование всех ключей"""
        test_messages = [
            {"role": "user", "content": "Test message for API key validation"}
        ]
        
        results = {}
        
        for key in self.api_keys:
            start_time = time.time()
            
            try:
                # Временно делаем ключ доступным для теста
                original_status = key.status
                key.status = APIKeyStatus.ACTIVE
                key.cooldown_until = 0
                key.rate_limit_reset = 0
                
                # Тестируем ключ
                result = await self.generate_completion(
                    messages=test_messages,
                    max_tokens=10,
                    max_retries=1
                )
                
                response_time = time.time() - start_time
                
                if result:
                    results[key.key_id] = {
                        'status': 'success',
                        'response_time': round(response_time, 2)
                    }
                else:
                    results[key.key_id] = {
                        'status': 'failed',
                        'response_time': round(response_time, 2),
                        'error': key.last_error
                    }
                
                # Восстанавливаем оригинальный статус
                key.status = original_status
                
            except Exception as e:
                results[key.key_id] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        return results
    
    async def reset_key_stats(self, key_id: str = None):
        """Сброс статистики ключей"""
        if key_id:
            # Сброс конкретного ключа
            for key in self.api_keys:
                if key.key_id == key_id:
                    key.requests_made = 0
                    key.successful_requests = 0
                    key.failed_requests = 0
                    key.response_times = []
                    key.weight = 1.0
                    key.last_error = None
                    if key.status == APIKeyStatus.ERROR:
                        key.status = APIKeyStatus.ACTIVE
                    break
        else:
            # Сброс всех ключей
            for key in self.api_keys:
                key.requests_made = 0
                key.successful_requests = 0
                key.failed_requests = 0
                key.response_times = []
                key.weight = 1.0
                key.last_error = None
                if key.status == APIKeyStatus.ERROR:
                    key.status = APIKeyStatus.ACTIVE
            
            # Сброс общей статистики
            self.total_requests = 0
            self.total_successful = 0
        
        logger.info(f"Reset stats for {'all keys' if not key_id else key_id}")


# Глобальный экземпляр Ultra-Scaling API пула
ultra_api_pool = UltraScalingAPIPool()


async def get_groq_pool() -> UltraScalingAPIPool:
    """Получение экземпляра Ultra-Scaling API пула"""
    return ultra_api_pool