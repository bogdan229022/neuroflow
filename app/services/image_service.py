"""
Enhanced Image Service with Pool Manager Integration
High-performance image generation with multiple providers and queue system
"""

import asyncio
import logging
import time
import os
import tempfile
from typing import Optional, Tuple, Dict, Any
from app.services.image_pool_manager import image_pool

logger = logging.getLogger(__name__)


class ImageService:
    """Enhanced image service with pool manager integration"""
    
    def __init__(self):
        """Инициализация Image Service"""
        self.pool = image_pool
        self.temp_files = set()  # Отслеживание временных файлов для автоудаления
    
    async def create_post_with_image(self, post_text: str, topic: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Создание изображения для поста (Ultra-Scaling с 7-секундным таймаутом)
        Возвращает: (image_data, error_message)
        """
        try:
            # Генерируем промпт для изображения на основе поста и темы
            image_prompt = self._create_image_prompt(post_text, topic)
            
            # Генерируем изображение с таймаутом и автоматическим переключением
            image_data, error = await self.pool.generate_image_direct_with_timeout(image_prompt, timeout=7)
            
            if image_data:
                logger.info(f"Image generated successfully for topic: {topic}")
                return image_data, None
            else:
                logger.warning(f"Failed to generate image for topic: {topic}, error: {error}")
                # Возвращаем None вместо пустой строки для корректной обработки
                return None, error or "Не удалось сгенерировать изображение"
                
        except Exception as e:
            error_msg = f"Image generation error: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    async def create_temp_image_file(self, image_data: bytes, suffix: str = '.jpg') -> Optional[str]:
        """
        Создание временного файла изображения с автоматическим отслеживанием
        Возвращает путь к файлу или None при ошибке
        """
        try:
            # Создаем временный файл
            temp_fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix='neuroflow_img_')
            
            # Записываем данные изображения
            with os.fdopen(temp_fd, 'wb') as temp_file:
                temp_file.write(image_data)
            
            # Добавляем в список для отслеживания
            self.temp_files.add(temp_path)
            
            logger.debug(f"Created temporary image file: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Failed to create temporary image file: {e}")
            return None
    
    async def cleanup_temp_file(self, file_path: str):
        """Удаление временного файла"""
        try:
            if file_path in self.temp_files:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    logger.debug(f"Deleted temporary file: {file_path}")
                self.temp_files.discard(file_path)
        except Exception as e:
            logger.warning(f"Failed to delete temporary file {file_path}: {e}")
    
    async def cleanup_all_temp_files(self):
        """Удаление всех временных файлов"""
        temp_files_copy = self.temp_files.copy()
        for file_path in temp_files_copy:
            await self.cleanup_temp_file(file_path)
        
        logger.info(f"Cleaned up {len(temp_files_copy)} temporary files")
    
    async def auto_cleanup_old_temp_files(self, max_age_hours: int = 1):
        """Автоматическая очистка старых временных файлов"""
        try:
            current_time = time.time()
            temp_files_copy = self.temp_files.copy()
            cleaned_count = 0
            
            for file_path in temp_files_copy:
                try:
                    if os.path.exists(file_path):
                        file_age = current_time - os.path.getmtime(file_path)
                        if file_age > (max_age_hours * 3600):  # Старше указанного времени
                            await self.cleanup_temp_file(file_path)
                            cleaned_count += 1
                    else:
                        # Файл уже не существует, убираем из отслеживания
                        self.temp_files.discard(file_path)
                except Exception as e:
                    logger.warning(f"Error checking temp file {file_path}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"Auto-cleaned {cleaned_count} old temporary files")
                
        except Exception as e:
            logger.error(f"Error during auto-cleanup: {e}")
    
    async def queue_image_generation(self, user_id: int, post_text: str, topic: str, priority: int = 0) -> int:
        """
        Добавление генерации изображения в очередь (для массовой обработки)
        Возвращает: queue_id
        """
        try:
            # Генерируем промпт для изображения
            image_prompt = self._create_image_prompt(post_text, topic)
            
            # Добавляем в очередь
            queue_id = await self.pool.add_to_queue(user_id, image_prompt, topic, priority)
            
            logger.info(f"Image generation queued for user {user_id}, queue_id: {queue_id}")
            return queue_id
            
        except Exception as e:
            logger.error(f"Failed to queue image generation: {e}")
            raise
    
    async def get_queued_image(self, queue_id: int) -> Tuple[Optional[str], Optional[str], str]:
        """
        Получение результата генерации из очереди
        Возвращает: (image_url, error_message, status)
        """
        try:
            from app.models.postgresql_database import postgresql_db
            
            async with postgresql_db.get_connection() as conn:
                row = await conn.fetchrow(
                    "SELECT image_url, error_message, status FROM image_queue WHERE id = $1",
                    queue_id
                )
                
                if not row:
                    return None, "Queue item not found", "not_found"
                
                return row['image_url'], row['error_message'], row['status']
                
        except Exception as e:
            logger.error(f"Failed to get queued image {queue_id}: {e}")
            return None, str(e), "error"
    
    def _create_image_prompt(self, post_text: str, topic: str) -> str:
        """Создание промпта для генерации изображения на основе поста и темы"""
        # Извлекаем ключевые слова из поста (убираем эмодзи и лишние символы)
        import re
        
        # Очищаем текст от эмодзи и специальных символов
        clean_text = re.sub(r'[^\w\s\-.,!?]', ' ', post_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Берем первые 100 символов для промпта
        text_snippet = clean_text[:100] if len(clean_text) > 100 else clean_text
        
        # Создаем промпт на основе темы и содержания поста
        if topic:
            prompt = f"{topic}, {text_snippet}"
        else:
            prompt = text_snippet
        
        # Добавляем ключевые слова для улучшения качества
        quality_keywords = [
            "high quality", "detailed", "professional", "modern", "clean",
            "vibrant colors", "well-lit", "sharp focus", "4k resolution"
        ]
        
        # Ограничиваем длину промпта
        if len(prompt) > 150:
            prompt = prompt[:150].rsplit(' ', 1)[0]
        
        # Добавляем качественные ключевые слова
        final_prompt = f"{prompt}, {', '.join(quality_keywords[:3])}"
        
        return final_prompt
    
    async def test_image_generation(self) -> Dict[str, Any]:
        """Тестирование генерации изображений"""
        test_prompt = "beautiful sunset over mountains"
        test_topic = "nature"
        
        start_time = time.time()
        
        try:
            # Тестируем прямую генерацию
            image_data, error = await self.create_post_with_image(test_prompt, test_topic)
            end_time = time.time()
            
            if image_data:
                return {
                    'status': 'success',
                    'response_time': round(end_time - start_time, 2),
                    'image_size': len(image_data),
                    'providers_status': self.pool.get_pool_status()
                }
            else:
                return {
                    'status': 'error',
                    'error': error,
                    'response_time': round(end_time - start_time, 2),
                    'providers_status': self.pool.get_pool_status()
                }
                
        except Exception as e:
            end_time = time.time()
            return {
                'status': 'exception',
                'error': str(e),
                'response_time': round(end_time - start_time, 2),
                'providers_status': self.pool.get_pool_status()
            }
    
    async def get_service_status(self) -> Dict[str, Any]:
        """Получение статуса сервиса изображений"""
        try:
            pool_status = self.pool.get_pool_status()
            
            # Получаем статистику очереди из базы данных
            from app.models.postgresql_database import postgresql_db
            
            async with postgresql_db.get_connection() as conn:
                # Статистика очереди
                pending_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM image_queue WHERE status = 'pending'"
                )
                processing_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM image_queue WHERE status = 'processing'"
                )
                completed_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM image_queue WHERE status = 'completed'"
                )
                failed_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM image_queue WHERE status = 'failed'"
                )
                
                # Средняя скорость обработки (последние 100 задач)
                avg_processing_time = await conn.fetchval("""
                    SELECT AVG(completed_at - started_at) 
                    FROM image_queue 
                    WHERE status = 'completed' 
                    AND completed_at IS NOT NULL 
                    AND started_at IS NOT NULL
                    ORDER BY completed_at DESC 
                    LIMIT 100
                """)
            
            return {
                'pool_status': pool_status,
                'queue_stats': {
                    'pending': pending_count,
                    'processing': processing_count,
                    'completed': completed_count,
                    'failed': failed_count,
                    'total': pending_count + processing_count + completed_count + failed_count
                },
                'performance': {
                    'avg_processing_time_seconds': round(avg_processing_time or 0, 2)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get service status: {e}")
            return {
                'error': str(e),
                'pool_status': self.pool.get_pool_status() if self.pool else None
            }
    
    async def cleanup_old_queue_items(self, days_old: int = 7):
        """Очистка старых элементов очереди"""
        try:
            from app.models.postgresql_database import postgresql_db
            import time
            
            cutoff_time = int(time.time()) - (days_old * 24 * 60 * 60)
            
            async with postgresql_db.get_connection() as conn:
                # Удаляем завершенные и неудачные задачи старше указанного времени
                deleted_count = await conn.fetchval("""
                    DELETE FROM image_queue 
                    WHERE status IN ('completed', 'failed') 
                    AND created_at < $1
                    RETURNING COUNT(*)
                """, cutoff_time)
                
                logger.info(f"Cleaned up {deleted_count} old queue items (older than {days_old} days)")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup old queue items: {e}")
            return 0
    
    async def retry_failed_images(self, max_retries: int = 3):
        """Повторная попытка генерации неудачных изображений"""
        try:
            from app.models.postgresql_database import postgresql_db
            
            async with postgresql_db.get_connection() as conn:
                # Находим неудачные задачи с количеством попыток меньше максимального
                failed_tasks = await conn.fetch("""
                    SELECT id, attempts, max_attempts 
                    FROM image_queue 
                    WHERE status = 'failed' 
                    AND attempts < max_attempts 
                    AND attempts < $1
                    ORDER BY created_at DESC
                    LIMIT 50
                """, max_retries)
                
                retry_count = 0
                for task in failed_tasks:
                    # Сбрасываем статус на pending для повторной обработки
                    await conn.execute("""
                        UPDATE image_queue 
                        SET status = 'pending', error_message = NULL 
                        WHERE id = $1
                    """, task['id'])
                    retry_count += 1
                
                if retry_count > 0:
                    logger.info(f"Queued {retry_count} failed images for retry")
                    
                    # Запускаем воркеры если они не запущены
                    if not self.pool.workers_running:
                        await self.pool.start_workers()
                
                return retry_count
                
        except Exception as e:
            logger.error(f"Failed to retry failed images: {e}")
            return 0
    
    async def start_workers(self, num_workers: int = 3):
        """Запуск воркеров для обработки очереди изображений"""
        await self.pool.start_workers(num_workers)
    
    async def stop_workers(self):
        """Остановка воркеров"""
        await self.pool.stop_workers()
    
    async def close(self):
        """Закрытие сервиса"""
        # Очищаем все временные файлы перед закрытием
        await self.cleanup_all_temp_files()
        
        await self.pool.stop_workers()
        await self.pool.close_session()


# Глобальный экземпляр сервиса изображений
image_service = ImageService()