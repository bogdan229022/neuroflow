import logging
import re
from datetime import datetime
from typing import Optional
from aiogram import Router, F
from aiogram.types import CallbackQuery
from pydantic import BaseModel, validator

from app.models.postgresql_database import postgresql_db as db
from app.utils.keyboards import get_autopost_keyboard, get_back_keyboard
from app.services.redis_cache import redis_cache

logger = logging.getLogger(__name__)
router = Router()


class AutopostInputValidator(BaseModel):
    """Валидатор для autopost команд"""
    user_id: int
    channel_id: Optional[str] = None
    topic: Optional[str] = None
    
    @validator('user_id')
    def validate_user_id(cls, v):
        """Валидация user_id"""
        if not isinstance(v, int) or v <= 0 or v > 9999999999:
            raise ValueError('Invalid user ID')
        return v
    
    @validator('channel_id')
    def validate_channel_id(cls, v):
        """Валидация channel_id"""
        if v is not None:
            if not isinstance(v, str) or len(v) > 100:
                raise ValueError('Invalid channel ID')
            # Проверяем формат channel ID
            if not re.match(r'^@?[a-zA-Z0-9_-]{1,50}$', v.replace('@', '')):
                raise ValueError('Invalid channel ID format')
        return v
    
    @validator('topic')
    def validate_topic(cls, v):
        """Валидация topic"""
        if v is not None:
            if not isinstance(v, str) or len(v) > 500:
                raise ValueError('Topic too long')
            # Проверяем на опасные символы
            if re.search(r'[<>"\';\\]', v):
                raise ValueError('Topic contains dangerous characters')
        return v


async def validate_autopost_access(user_id: int) -> bool:
    """Проверка доступа к автопостингу"""
    try:
        validator = AutopostInputValidator(user_id=user_id)
        
        # Проверяем подписку пользователя
        user_info = await db.get_user_info(user_id)
        if not user_info:
            return False
        
        # Проверяем активную подписку или триал
        current_time = int(datetime.now().timestamp())
        has_subscription = (
            user_info.get('is_lifetime') or
            (user_info.get('subscription_expiry', 0) > current_time) or
            (user_info.get('trial_expiry', 0) > current_time)
        )
        
        return has_subscription
    except Exception as e:
        logger.error(f"Autopost access validation error for user {user_id}: {e}")
        return False


async def check_autopost_rate_limit(user_id: int, action: str) -> bool:
    """Rate limiting для autopost действий"""
    try:
        cache_key = f"autopost_rate_limit:{user_id}:{action}"
        last_request = await redis_cache.get(cache_key)
        
        if last_request:
            return False
        
        # Устанавливаем лимит на 10 секунд для autopost действий
        await redis_cache.set(cache_key, "1", expire=10)
        return True
    except Exception as e:
        logger.error(f"Rate limiting error: {e}")
        return True


@router.callback_query(F.data == "autopost_start")
async def callback_autopost_start(callback: CallbackQuery):
    """Запуск автопостинга с полной валидацией"""
    try:
        user_id = callback.from_user.id
        
        # Валидация доступа
        if not await validate_autopost_access(user_id):
            await callback.answer("❌ Нет доступа к автопостингу", show_alert=True)
            return
        
        # Rate limiting
        if not await check_autopost_rate_limit(user_id, "start"):
            await callback.answer("⏳ Подождите перед повторным запуском", show_alert=True)
            return
        
        # Получаем настройки с обработкой ошибок
        try:
            settings = await db.get_user_settings(user_id)
        except Exception as e:
            logger.error(f"Error getting user settings: {e}")
            await callback.answer("❌ Ошибка получения настроек", show_alert=True)
            return
        
        if not settings:
            await callback.answer("❌ Настройки не найдены", show_alert=True)
            return
        
        # Валидация настроек
        try:
            validator = AutopostInputValidator(
                user_id=user_id,
                channel_id=settings.get('channel_id'),
                topic=settings.get('topic')
            )
        except Exception as e:
            logger.error(f"Settings validation error: {e}")
            await callback.answer("❌ Некорректные настройки", show_alert=True)
            return
        
        # Проверяем все необходимые настройки
        if not all([settings['channel_id'], settings['topic'], settings['system_instruction']]):
            await callback.answer(
                "❌ Для запуска автопостинга необходимо настроить канал, тему и промпт",
                show_alert=True
            )
            return
        
        # Активируем автопостинг
        try:
            await db.update_user_settings(user_id, is_active=True)
        except Exception as e:
            logger.error(f"Error updating user settings: {e}")
            await callback.answer("❌ Ошибка активации автопостинга", show_alert=True)
            return
        
        await callback.message.edit_text(
            "✅ **Автопостинг запущен!**\n\n"
            "📊 Статус: Активен\n"
            f"📢 Канал: {settings['channel_id']}\n"
            f"📝 Тема: {settings['topic']}\n"
            "⏰ Интервал: каждые 6 часов\n\n"
            "Первый пост будет опубликован в течение 6 часов.",
            reply_markup=get_autopost_keyboard(True)
        )
        
        logger.info(f"Автопостинг запущен для пользователя {user_id}")
        
    except Exception as e:
        logger.error(f"Unexpected error in autopost_start: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "autopost_stop")
async def callback_autopost_stop(callback: CallbackQuery):
    """Остановка автопостинга с валидацией"""
    try:
        user_id = callback.from_user.id
        
        # Валидация доступа
        if not await validate_autopost_access(user_id):
            await callback.answer("❌ Нет доступа к автопостингу", show_alert=True)
            return
        
        # Rate limiting
        if not await check_autopost_rate_limit(user_id, "stop"):
            await callback.answer("⏳ Подождите перед повторной остановкой", show_alert=True)
            return
        
        # Останавливаем автопостинг
        try:
            await db.update_user_settings(user_id, is_active=False)
        except Exception as e:
            logger.error(f"Error stopping autopost: {e}")
            await callback.answer("❌ Ошибка остановки автопостинга", show_alert=True)
            return
        
        await callback.message.edit_text(
            "⏸️ **Автопостинг остановлен**\n\n"
            "📊 Статус: Неактивен\n\n"
            "Вы можете запустить его снова в любое время.",
            reply_markup=get_autopost_keyboard(False)
        )
        
        logger.info(f"Автопостинг остановлен для пользователя {user_id}")
        
    except Exception as e:
        logger.error(f"Unexpected error in autopost_stop: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "autopost_status")
async def callback_autopost_status(callback: CallbackQuery):
    """Показать статус автопостинга"""
    try:
        user_id = callback.from_user.id
        
        # Валидация доступа
        if not await validate_autopost_access(user_id):
            await callback.answer("❌ Нет доступа к автопостингу", show_alert=True)
            return
        
        # Получаем настройки
        try:
            settings = await db.get_user_settings(user_id)
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            await callback.answer("❌ Ошибка получения настроек", show_alert=True)
            return
        
        if not settings:
            await callback.answer("❌ Настройки не найдены", show_alert=True)
            return
        
        # Формируем сообщение о статусе
        status = "Активен" if settings.get('is_active') else "Неактивен"
        status_emoji = "✅" if settings.get('is_active') else "⏸️"
        
        text = f"{status_emoji} **Статус автопостинга: {status}**\n\n"
        
        if settings.get('channel_id'):
            text += f"📢 Канал: {settings['channel_id']}\n"
        if settings.get('topic'):
            text += f"📝 Тема: {settings['topic']}\n"
        if settings.get('system_instruction'):
            text += f"🎯 Промпт: настроен\n"
        
        text += f"\n⏰ Интервал: каждые 6 часов"
        
        await callback.message.edit_text(
            text,
            reply_markup=get_autopost_keyboard(settings.get('is_active', False))
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in autopost_status: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)