import asyncio
from typing import Optional, Tuple
import logging
from app.services.api_pool_manager import get_groq_pool

logger = logging.getLogger(__name__)


class AIService:
    def __init__(self):
        """Инициализация AI Service"""
        self.model = "llama-3.3-70b-versatile"

    async def generate_post(self, topic: str, system_instruction: str) -> Optional[str]:
        """Генерация поста с помощью ИИ с использованием пула API ключей"""
        try:
            # Получаем пул API ключей
            groq_pool = await get_groq_pool()
            if not groq_pool:
                logger.error("Groq API pool not available - no API keys configured")
                return None

            # Создаем промпт для генерации поста
            user_prompt = f"""
            Создай интересный и привлекательный пост для Telegram-канала на тему: {topic}
            
            Требования к посту:
            - Длина: 200-500 символов
            - Используй эмодзи для привлекательности
            - Сделай пост информативным и полезным
            - Добавь призыв к действию или вопрос для вовлечения аудитории
            - Пост должен быть готов к публикации без дополнительного редактирования
            """

            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ]

            # Выполняем запрос через пул с автоматическими повторами
            response = await groq_pool.generate_completion(
                messages=messages,
                model=self.model,
                max_tokens=1000,
                temperature=0.7
            )
            
            if not response:
                logger.error("Failed to generate post - all API keys exhausted")
                return None
            
            post_content = response.choices[0].message.content
            
            # Проверяем на пустой или некорректный ответ
            if not post_content or not post_content.strip():
                logger.warning("AI returned empty response")
                return None
            
            post_content = post_content.strip()
            
            # Проверяем минимальную длину (защита от слишком коротких ответов)
            if len(post_content) < 50:
                logger.warning(f"AI returned too short response: {len(post_content)} chars")
                return None
            
            # Увеличиваем счетчик сгенерированных постов
            from app.models.postgresql_database import postgresql_db
            await postgresql_db.increment_posts_count()
            
            logger.info("Post generated successfully using API pool")
            return post_content
            
        except Exception as e:
            logger.error(f"Ошибка при генерации поста: {e}")
            return None

    async def generate_post_with_image(self, topic: str, system_instruction: str, 
                                     generate_image: bool = True) -> Tuple[Optional[str], Optional[bytes]]:
        """
        Генерация поста с изображением
        Возвращает: (post_text, image_data) или (post_text, None)
        """
        try:
            # Сначала генерируем текст поста
            post_text = await self.generate_post(topic, system_instruction)
            
            if not post_text:
                return None, None
            
            # Если генерация изображений отключена, возвращаем только текст
            if not generate_image:
                return post_text, None
            
            # Генерируем изображение с помощью нового image service
            from app.services.image_service import image_service
            image_data, error = await image_service.create_post_with_image(post_text, topic)
            
            if error:
                logger.warning(f"Image generation failed: {error}")
            
            return post_text, image_data
            
        except Exception as e:
            logger.error(f"Ошибка при генерации поста с изображением: {e}")
            return None, None

    async def test_connection(self) -> bool:
        """Тестирование подключения к API пулу"""
        try:
            groq_pool = await get_groq_pool()
            if not groq_pool:
                logger.error("Groq API pool not available")
                return False

            # Тестируем пул ключей
            test_results = await groq_pool.test_connection()
            
            # Считаем успешным если хотя бы один ключ работает
            success = test_results['active_keys'] > 0
            
            if success:
                logger.info(f"API pool test successful: {test_results['active_keys']}/{test_results['total_keys']} keys active")
            else:
                logger.error(f"API pool test failed: no active keys out of {test_results['total_keys']}")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка тестирования API пула: {e}")
            return False

    async def get_pool_status(self) -> Optional[dict]:
        """Получить статус пула API ключей"""
        try:
            groq_pool = await get_groq_pool()
            if not groq_pool:
                return None
            
            return groq_pool.get_pool_status()
            
        except Exception as e:
            logger.error(f"Ошибка получения статуса пула: {e}")
            return None


# Глобальный экземпляр AI сервиса
ai_service = AIService()