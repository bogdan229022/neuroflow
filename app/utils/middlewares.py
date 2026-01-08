from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
import logging
import time
from collections import defaultdict

# Import PostgreSQL database instead of SQLite
from app.models.postgresql_database import postgresql_db as db

logger = logging.getLogger(__name__)


class AntiFloodMiddleware(BaseMiddleware):
    """Anti-flood middleware для защиты от спама (aiogram 3.x)"""
    
    def __init__(self, rate_limit: float = 2.0):
        """Инициализация AntiFlood Middleware"""
        self.rate_limit = rate_limit
        self.user_last_message = {}
        super().__init__()
        self.rate_limit = rate_limit  # Секунды между сообщениями
        self.user_last_message = defaultdict(float)
        self.user_warnings = defaultdict(int)
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Применяем только к сообщениям от пользователей
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)
        
        user_id = event.from_user.id
        current_time = time.time()
        last_message_time = self.user_last_message[user_id]
        
        # Проверяем, не слишком ли часто пользователь отправляет сообщения
        if current_time - last_message_time < self.rate_limit:
            self.user_warnings[user_id] += 1
            
            # Вежливое предупреждение
            if isinstance(event, Message):
                if self.user_warnings[user_id] <= 3:  # Не спамим предупреждениями
                    await event.answer(
                        "⏳ **Пожалуйста, не спешите!**\n\n"
                        "Дайте мне секунду, чтобы обработать ваш запрос. "
                        "Это поможет мне работать стабильнее и быстрее! 😊"
                    )
            elif isinstance(event, CallbackQuery):
                if self.user_warnings[user_id] <= 3:
                    await event.answer(
                        "⏳ Пожалуйста, подождите немного между запросами!",
                        show_alert=True
                    )
            
            return  # Блокируем обработку
        
        # Обновляем время последнего сообщения
        self.user_last_message[user_id] = current_time
        
        # Сбрасываем счетчик предупреждений при нормальном поведении
        if self.user_warnings[user_id] > 0:
            self.user_warnings[user_id] = max(0, self.user_warnings[user_id] - 1)
        
        return await handler(event, data)


class SubscriptionMiddleware(BaseMiddleware):
    """Middleware для проверки подписки пользователя (оптимизировано для PostgreSQL)"""
    
    def __init__(self):
        """Инициализация Subscription Middleware"""
        super().__init__()
        # Команды, доступные без подписки
        self.free_commands = {'/start', '/help', '/buy', '/profile'}
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем user_id из события
        user_id = None
        if isinstance(event, (Message, CallbackQuery)):
            user_id = event.from_user.id
        
        if not user_id:
            return await handler(event, data)
        
        # Добавляем пользователя в БД если его нет (PostgreSQL с upsert)
        await db.add_user(user_id)
        
        # Проверяем, является ли пользователь админом
        user_info = await db.get_user(user_id)
        if user_info and user_info.get('is_admin'):
            return await handler(event, data)
        
        # Проверяем команду
        command = None
        if isinstance(event, Message) and event.text:
            command = event.text.split()[0].lower()
        elif isinstance(event, CallbackQuery) and event.data:
            # Для callback-запросов проверяем префикс
            if event.data.startswith(('buy_', 'profile', 'help')):
                return await handler(event, data)
        
        # Если это бесплатная команда, пропускаем проверку подписки
        if command in self.free_commands:
            return await handler(event, data)
        
        # Проверяем активность подписки (оптимизированный запрос PostgreSQL)
        is_active = await db.is_subscription_active(user_id)
        if not is_active:
            if isinstance(event, Message):
                await event.answer(
                    "🔒 Для использования этой функции необходима активная подписка.\n\n"
                    "Используйте /buy для покупки подписки."
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "🔒 Необходима активная подписка!", 
                    show_alert=True
                )
            return
        
        return await handler(event, data)


class UserRegistrationMiddleware(BaseMiddleware):
    """Middleware для автоматической регистрации пользователей и отслеживания взаимодействий (PostgreSQL)"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, (Message, CallbackQuery)):
            user_id = event.from_user.id
        
        if user_id:
            # Добавляем пользователя если его нет (PostgreSQL с upsert)
            await db.add_user(user_id)
            
            # Обновляем время последнего взаимодействия (оптимизировано для PostgreSQL)
            try:
                await db.update_last_interaction(user_id)
            except Exception as e:
                logger.warning(f"Не удалось обновить время взаимодействия для пользователя {user_id}: {e}")
        
        return await handler(event, data)