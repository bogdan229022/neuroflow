"""
Image API Pool Manager - Multi-provider image generation with queue system
Handles multiple image generation providers with load balancing and queue management
"""

import asyncio
import aiohttp
import logging
import time
import json
import hashlib
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
from dataclasses import dataclass
from urllib.parse import quote

logger = logging.getLogger(__name__)


class ImageProvider(Enum):
    """Поддерживаемые провайдеры изображений"""
    POLLINATIONS = "pollinations"
    HUGGINGFACE = "huggingface"
    STABLE_DIFFUSION = "stable_diffusion"
    REPLICATE = "replicate"


@dataclass
class ImageProviderConfig:
    """Конфигурация провайдера изображений"""
    name: str
    base_url: str
    api_key: Optional[str] = None
    max_requests_per_minute: int = 60
    timeout: int = 30
    is_active: bool = True
    last_error: Optional[str] = None
    error_count: int = 0
    last_used: float = 0
    rate_limit_until: float = 0


class ImageProviderStatus:
    """Статус провайдера изображений"""
    
    def __init__(self, config: ImageProviderConfig):
        """Инициализация Image Provider Status"""
        self.config = config
        self.request_times: List[float] = []
        self.lock = asyncio.Lock()
    
    def is_rate_limited(self) -> bool:
        """Проверка заблокирован ли провайдер по rate limit"""
        return time.time() < self.config.rate_limit_until
    
    def can_make_request(self) -> bool:
        """Проверка можно ли сделать запрос"""
        if not self.config.is_active or self.is_rate_limited():
            return False
        
        # Проверяем лимит запросов в минуту
        current_time = time.time()
        minute_ago = current_time - 60
        
        # Удаляем старые запросы
        self.request_times = [t for t in self.request_times if t > minute_ago]
        
        return len(self.request_times) < self.config.max_requests_per_minute
    
    def record_request(self):
        """Записать запрос"""
        self.request_times.append(time.time())
        self.config.last_used = time.time()
    
    def record_error(self, error: str):
        """Записать ошибку"""
        self.config.last_error = error
        self.config.error_count += 1
        
        # Деактивируем провайдер при критических ошибках
        if self.config.error_count >= 5:
            self.config.is_active = False
            logger.error(f"Image provider {self.config.name} deactivated after {self.config.error_count} errors")
    
    def record_success(self):
        """Записать успех"""
        self.config.error_count = 0
        self.config.last_error = None
    
    def set_rate_limited(self, duration: int = 60):
        """Установить блокировку по rate limit"""
        self.config.rate_limit_until = time.time() + duration
        logger.warning(f"Image provider {self.config.name} rate limited for {duration} seconds")


class ImageAPIPool:
    """Пул API провайдеров изображений с балансировкой нагрузки"""
    
    def __init__(self):
        """Инициализация Image API Pool"""
        self.providers: Dict[ImageProvider, ImageProviderStatus] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.queue = asyncio.Queue()
        self.workers_running = False
        self.worker_tasks: List[asyncio.Task] = []
        
        # Инициализируем провайдеров
        self._init_providers()
    
    def _init_providers(self):
        """Инициализация провайдеров изображений (Ultra-Scaling: 5 провайдеров)"""
        # Pollinations.ai (бесплатный, быстрый)
        pollinations_config = ImageProviderConfig(
            name="Pollinations",
            base_url="https://image.pollinations.ai/prompt",
            max_requests_per_minute=120,  # Высокий лимит
            timeout=15
        )
        self.providers[ImageProvider.POLLINATIONS] = ImageProviderStatus(pollinations_config)
        
        # HuggingFace Inference API (требует API ключ)
        hf_api_key = self._get_huggingface_key()
        if hf_api_key:
            hf_config = ImageProviderConfig(
                name="HuggingFace",
                base_url="https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1",
                api_key=hf_api_key,
                max_requests_per_minute=30,
                timeout=30
            )
            self.providers[ImageProvider.HUGGINGFACE] = ImageProviderStatus(hf_config)
        
        # Stable Diffusion API (если настроен)
        sd_api_key = self._get_stable_diffusion_key()
        if sd_api_key:
            sd_config = ImageProviderConfig(
                name="Stable Diffusion",
                base_url="https://stablediffusionapi.com/api/v3/text2img",
                api_key=sd_api_key,
                max_requests_per_minute=20,
                timeout=45
            )
            self.providers[ImageProvider.STABLE_DIFFUSION] = ImageProviderStatus(sd_config)
        
        # Replicate API (резервный провайдер)
        replicate_api_key = self._get_replicate_key()
        if replicate_api_key:
            replicate_config = ImageProviderConfig(
                name="Replicate",
                base_url="https://api.replicate.com/v1/predictions",
                api_key=replicate_api_key,
                max_requests_per_minute=15,
                timeout=60
            )
            self.providers[ImageProvider.REPLICATE] = ImageProviderStatus(replicate_config)
        
        # Дополнительный Pollinations endpoint (резервный)
        if len(self.providers) < 5:
            pollinations_backup_config = ImageProviderConfig(
                name="Pollinations Backup",
                base_url="https://pollinations.ai/p",
                max_requests_per_minute=60,
                timeout=20
            )
            # Используем POLLINATIONS enum но с другой конфигурацией
            self.providers[f"{ImageProvider.POLLINATIONS}_backup"] = ImageProviderStatus(pollinations_backup_config)
        
        logger.info(f"Initialized Ultra-Scaling image pool with {len(self.providers)} providers")
    
    def _get_huggingface_key(self) -> Optional[str]:
        """Получение HuggingFace API ключа"""
        import os
        return os.getenv('HUGGINGFACE_API_KEY')
    
    def _get_replicate_key(self) -> Optional[str]:
        """Получение Replicate API ключа"""
        import os
        return os.getenv('REPLICATE_API_KEY')
    
    def _get_stable_diffusion_key(self) -> Optional[str]:
        """Получение Stable Diffusion API ключа"""
        import os
        return os.getenv('STABLE_DIFFUSION_API_KEY')
    
    def _get_replicate_key(self) -> Optional[str]:
        """Получение Replicate API ключа"""
        import os
        return os.getenv('REPLICATE_API_KEY')
    
    async def generate_image_direct_with_timeout(self, prompt: str, timeout: int = 7) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Генерация изображения с таймаутом и автоматическим переключением на резервный провайдер
        Ultra-Scaling: если основной провайдер не отвечает за 7 секунд, переключаемся на резервный
        """
        await self.init_session()
        
        # Получаем лучший провайдер
        primary_provider = self.get_best_provider()
        if not primary_provider:
            return None, "No available image providers"
        
        try:
            # Пытаемся с основным провайдером с таймаутом
            result = await asyncio.wait_for(
                self._generate_with_provider(prompt, primary_provider),
                timeout=timeout
            )
            return result
            
        except asyncio.TimeoutError:
            logger.warning(f"Primary provider {primary_provider.config.name} timed out after {timeout}s, trying backup")
            
            # Получаем резервный провайдер (исключаем уже использованный)
            available_providers = [p for p in self.get_available_providers() if p != primary_provider]
            
            if not available_providers:
                return None, f"Primary provider timeout and no backup available"
            
            # Пытаемся с резервным провайдером
            backup_provider = available_providers[0]  # Берем первый доступный
            
            try:
                result = await asyncio.wait_for(
                    self._generate_with_provider(prompt, backup_provider),
                    timeout=timeout
                )
                logger.info(f"Successfully switched to backup provider {backup_provider.config.name}")
                return result
                
            except asyncio.TimeoutError:
                return None, f"Both primary and backup providers timed out"
            except Exception as e:
                return None, f"Backup provider error: {str(e)}"
                
        except Exception as e:
            return None, f"Primary provider error: {str(e)}"
    
    async def init_session(self):
        """Инициализация HTTP сессии"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=60)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={'User-Agent': 'NeuroFlow Bot Image Generator'}
            )
    
    async def close_session(self):
        """Закрытие HTTP сессии"""
        if self.session:
            await self.session.close()
            self.session = None
    
    def get_available_providers(self) -> List[ImageProviderStatus]:
        """Получить список доступных провайдеров"""
        return [
            provider for provider in self.providers.values()
            if provider.config.is_active and provider.can_make_request()
        ]
    
    def get_best_provider(self) -> Optional[ImageProviderStatus]:
        """Получить лучший доступный провайдер"""
        available = self.get_available_providers()
        
        if not available:
            return None
        
        # Сортируем по приоритету: меньше ошибок, быстрее, недавно использовался
        available.sort(key=lambda p: (
            p.config.error_count,
            -p.config.max_requests_per_minute,
            time.time() - p.config.last_used
        ))
        
        return available[0]
    
    async def generate_image_direct(self, prompt: str, provider: ImageProvider = None) -> Tuple[Optional[bytes], Optional[str]]:
        """Прямая генерация изображения без очереди"""
        await self.init_session()
        
        if provider:
            provider_status = self.providers.get(provider)
            if not provider_status or not provider_status.can_make_request():
                return None, f"Provider {provider.value} not available"
        else:
            provider_status = self.get_best_provider()
            if not provider_status:
                return None, "No available image providers"
        
        return await self._generate_with_provider(prompt, provider_status)
    
    async def _generate_with_provider(self, prompt: str, provider_status: ImageProviderStatus) -> Tuple[Optional[bytes], Optional[str]]:
        """Генерация изображения с конкретным провайдером"""
        config = provider_status.config
        provider_status.record_request()
        
        try:
            if config.name == "Pollinations":
                return await self._generate_pollinations(prompt, provider_status)
            elif config.name == "HuggingFace":
                return await self._generate_huggingface(prompt, provider_status)
            elif config.name == "Stable Diffusion":
                return await self._generate_stable_diffusion(prompt, provider_status)
            else:
                return None, f"Unknown provider: {config.name}"
                
        except Exception as e:
            error_msg = str(e)
            provider_status.record_error(error_msg)
            logger.error(f"Error generating image with {config.name}: {error_msg}")
            return None, error_msg
    
    async def _generate_pollinations(self, prompt: str, provider_status: ImageProviderStatus) -> Tuple[Optional[bytes], Optional[str]]:
        """Генерация через Pollinations.ai"""
        config = provider_status.config
        
        # Очищаем и кодируем промпт
        clean_prompt = self._clean_prompt(prompt)
        encoded_prompt = quote(clean_prompt)
        
        # Добавляем параметры для лучшего качества
        url = f"{config.base_url}/{encoded_prompt}?width=1024&height=1024&model=flux&enhance=true"
        
        async with self.session.get(url, timeout=config.timeout) as response:
            if response.status == 200:
                image_data = await response.read()
                provider_status.record_success()
                logger.debug(f"Successfully generated image via Pollinations: {len(image_data)} bytes")
                return image_data, None
            elif response.status == 429:
                provider_status.set_rate_limited(60)
                return None, "Rate limit exceeded"
            else:
                error_msg = f"HTTP {response.status}: {await response.text()}"
                provider_status.record_error(error_msg)
                return None, error_msg
    
    async def _generate_huggingface(self, prompt: str, provider_status: ImageProviderStatus) -> Tuple[Optional[bytes], Optional[str]]:
        """Генерация через HuggingFace"""
        config = provider_status.config
        
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": self._clean_prompt(prompt),
            "parameters": {
                "num_inference_steps": 20,
                "guidance_scale": 7.5,
                "width": 1024,
                "height": 1024
            }
        }
        
        async with self.session.post(
            config.base_url, 
            json=payload, 
            headers=headers,
            timeout=config.timeout
        ) as response:
            if response.status == 200:
                image_data = await response.read()
                provider_status.record_success()
                logger.debug(f"Successfully generated image via HuggingFace: {len(image_data)} bytes")
                return image_data, None
            elif response.status == 429:
                provider_status.set_rate_limited(120)  # HF имеет более длительные блокировки
                return None, "Rate limit exceeded"
            else:
                error_msg = f"HTTP {response.status}: {await response.text()}"
                provider_status.record_error(error_msg)
                return None, error_msg
    
    async def _generate_stable_diffusion(self, prompt: str, provider_status: ImageProviderStatus) -> Tuple[Optional[bytes], Optional[str]]:
        """Генерация через Stable Diffusion API"""
        config = provider_status.config
        
        payload = {
            "key": config.api_key,
            "prompt": self._clean_prompt(prompt),
            "negative_prompt": "blurry, bad quality, distorted, ugly",
            "width": "1024",
            "height": "1024",
            "samples": "1",
            "num_inference_steps": "20",
            "guidance_scale": 7.5,
            "safety_checker": "yes",
            "enhance_prompt": "yes",
            "seed": None,
            "webhook": None,
            "track_id": None
        }
        
        async with self.session.post(
            config.base_url,
            json=payload,
            timeout=config.timeout
        ) as response:
            if response.status == 200:
                result = await response.json()
                
                if result.get("status") == "success" and result.get("output"):
                    # Скачиваем изображение по URL
                    image_url = result["output"][0]
                    async with self.session.get(image_url) as img_response:
                        if img_response.status == 200:
                            image_data = await img_response.read()
                            provider_status.record_success()
                            logger.debug(f"Successfully generated image via Stable Diffusion: {len(image_data)} bytes")
                            return image_data, None
                
                error_msg = f"API returned: {result}"
                provider_status.record_error(error_msg)
                return None, error_msg
            else:
                error_msg = f"HTTP {response.status}: {await response.text()}"
                provider_status.record_error(error_msg)
                return None, error_msg
    
    def _clean_prompt(self, prompt: str) -> str:
        """Очистка промпта для генерации изображений"""
        # Удаляем эмодзи и специальные символы
        import re
        
        # Базовая очистка
        clean = re.sub(r'[^\w\s\-.,!?]', ' ', prompt)
        clean = re.sub(r'\s+', ' ', clean).strip()
        
        # Ограничиваем длину
        if len(clean) > 200:
            clean = clean[:200].rsplit(' ', 1)[0]
        
        # Добавляем ключевые слова для лучшего качества
        quality_keywords = "high quality, detailed, professional, 4k"
        
        return f"{clean}, {quality_keywords}"
    
    # Система очередей с защитой от флуда
    async def add_to_queue(self, user_id: int, prompt: str, topic: str = None, priority: int = 0) -> int:
        """
        Добавление задачи в очередь изображений с защитой от флуда
        ЗАЩИТА: Максимум 3 изображения в очереди на пользователя
        """
        from app.models.postgresql_database import postgresql_db
        from app.services.redis_cache import redis_cache
        
        # КРИТИЧЕСКАЯ ЗАЩИТА: Проверяем лимит запросов пользователя
        user_queue_key = f"user_image_queue:{user_id}"
        current_queue_count = await redis_cache.get(user_queue_key) or 0
        
        # Максимум 3 изображения в очереди на пользователя
        MAX_QUEUE_PER_USER = 3
        if current_queue_count >= MAX_QUEUE_PER_USER:
            logger.warning(f"User {user_id} exceeded image queue limit: {current_queue_count}")
            raise ValueError(f"Превышен лимит очереди изображений ({MAX_QUEUE_PER_USER}). Дождитесь завершения текущих генераций.")
        
        # ЗАЩИТА ОТ СПАМА: Проверяем частоту запросов (не более 1 в 30 секунд)
        rate_limit_key = f"user_image_rate:{user_id}"
        last_request = await redis_cache.get(rate_limit_key)
        
        if last_request:
            time_since_last = time.time() - last_request
            if time_since_last < 30:  # 30 секунд между запросами
                remaining = 30 - int(time_since_last)
                raise ValueError(f"Слишком частые запросы. Попробуйте через {remaining} секунд.")
        
        # Записываем время запроса
        await redis_cache.set(rate_limit_key, time.time(), ttl=30)
        
        # Добавляем в очередь
        queue_id = await postgresql_db.add_image_to_queue(user_id, prompt, topic, priority)
        
        # Увеличиваем счетчик очереди пользователя
        await redis_cache.set(user_queue_key, current_queue_count + 1, ttl=1800)  # 30 минут TTL
        
        logger.info(f"Added image generation task to queue: {queue_id} for user {user_id} (queue: {current_queue_count + 1})")
        
        # Запускаем воркеры если они не запущены
        if not self.workers_running:
            await self.start_workers()
        
        return queue_id
    
    async def start_workers(self, num_workers: int = 3):
        """Запуск воркеров для обработки очереди"""
        if self.workers_running:
            return
        
        self.workers_running = True
        
        for i in range(num_workers):
            task = asyncio.create_task(self._worker(f"ImageWorker-{i+1}"))
            self.worker_tasks.append(task)
        
        logger.info(f"Started {num_workers} image generation workers")
    
    async def stop_workers(self):
        """Остановка воркеров"""
        self.workers_running = False
        
        for task in self.worker_tasks:
            task.cancel()
        
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        
        self.worker_tasks.clear()
        logger.info("Stopped all image generation workers")
    
    async def _worker(self, worker_name: str):
        """Воркер для обработки очереди изображений"""
        from app.models.postgresql_database import postgresql_db
        
        logger.info(f"{worker_name} started")
        
        while self.workers_running:
            try:
                # Получаем следующую задачу из очереди
                task = await postgresql_db.get_next_image_from_queue()
                
                if not task:
                    # Нет задач, ждем
                    await asyncio.sleep(1)
                    continue
                
                logger.info(f"{worker_name} processing task {task['id']} for user {task['user_id']}")
                
                # Генерируем изображение
                image_data, error = await self.generate_image_direct(task['prompt'])
                
                if image_data:
                    # Сохраняем изображение и обновляем статус
                    image_url = await self._save_image(image_data, task['id'])
                    await postgresql_db.update_image_queue_status(
                        task['id'], 'completed', image_url=image_url
                    )
                    
                    # Увеличиваем счетчик изображений
                    await postgresql_db.increment_images_count()
                    
                    # ОЧИЩАЕМ СЧЕТЧИК ОЧЕРЕДИ ПОЛЬЗОВАТЕЛЯ
                    from app.services.redis_cache import redis_cache
                    user_queue_key = f"user_image_queue:{task['user_id']}"
                    current_count = await redis_cache.get(user_queue_key) or 0
                    if current_count > 0:
                        await redis_cache.set(user_queue_key, current_count - 1, ttl=1800)
                    
                    logger.info(f"{worker_name} completed task {task['id']}")
                else:
                    # Ошибка генерации
                    status = 'failed' if task['attempts'] >= task['max_attempts'] - 1 else 'pending'
                    await postgresql_db.update_image_queue_status(
                        task['id'], status, error_message=error
                    )
                    
                    # Если задача окончательно провалена, очищаем счетчик
                    if status == 'failed':
                        from app.services.redis_cache import redis_cache
                        user_queue_key = f"user_image_queue:{task['user_id']}"
                        current_count = await redis_cache.get(user_queue_key) or 0
                        if current_count > 0:
                            await redis_cache.set(user_queue_key, current_count - 1, ttl=1800)
                        
                        logger.error(f"{worker_name} failed task {task['id']} after {task['max_attempts']} attempts: {error}")
                    else:
                        logger.warning(f"{worker_name} retrying task {task['id']} (attempt {task['attempts'] + 1}): {error}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"{worker_name} error: {e}")
                await asyncio.sleep(5)  # Пауза при ошибке
        
        logger.info(f"{worker_name} stopped")
    
    async def _save_image(self, image_data: bytes, task_id: int) -> str:
        """Сохранение изображения и возврат URL"""
        import os
        from pathlib import Path
        
        # Создаем директорию для изображений
        images_dir = Path("generated_images")
        images_dir.mkdir(exist_ok=True)
        
        # Генерируем имя файла
        filename = f"image_{task_id}_{int(time.time())}.jpg"
        filepath = images_dir / filename
        
        # Сохраняем файл
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        logger.debug(f"Saved image: {filepath} ({len(image_data)} bytes)")
        
        # Возвращаем относительный путь
        return str(filepath)
    
    # Методы для мониторинга и статистики
    def get_pool_status(self) -> Dict[str, Any]:
        """Получить статус пула провайдеров"""
        return {
            'total_providers': len(self.providers),
            'active_providers': len([p for p in self.providers.values() if p.config.is_active]),
            'available_providers': len(self.get_available_providers()),
            'workers_running': self.workers_running,
            'worker_count': len(self.worker_tasks),
            'providers_status': [
                {
                    'name': provider.config.name,
                    'is_active': provider.config.is_active,
                    'can_make_request': provider.can_make_request(),
                    'is_rate_limited': provider.is_rate_limited(),
                    'error_count': provider.config.error_count,
                    'last_error': provider.config.last_error,
                    'requests_per_minute': len(provider.request_times),
                    'max_requests_per_minute': provider.config.max_requests_per_minute
                }
                for provider in self.providers.values()
            ]
        }
    
    async def test_all_providers(self) -> Dict[str, Any]:
        """Тестирование всех провайдеров"""
        test_prompt = "a beautiful sunset over mountains, high quality, detailed"
        results = {}
        
        for provider_enum, provider_status in self.providers.items():
            if not provider_status.config.is_active:
                results[provider_enum.value] = {
                    'status': 'inactive',
                    'error': 'Provider is deactivated'
                }
                continue
            
            try:
                start_time = time.time()
                image_data, error = await self._generate_with_provider(test_prompt, provider_status)
                end_time = time.time()
                
                if image_data:
                    results[provider_enum.value] = {
                        'status': 'success',
                        'response_time': round(end_time - start_time, 2),
                        'image_size': len(image_data)
                    }
                else:
                    results[provider_enum.value] = {
                        'status': 'error',
                        'error': error,
                        'response_time': round(end_time - start_time, 2)
                    }
                    
            except Exception as e:
                results[provider_enum.value] = {
                    'status': 'exception',
                    'error': str(e)
                }
        
        return results


# Глобальный экземпляр пула изображений
image_pool = ImageAPIPool()