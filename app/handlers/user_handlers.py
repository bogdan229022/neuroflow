import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.models.postgresql_database import postgresql_db as db
from app.utils.keyboards import get_instruction_keyboard, get_main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "instruction")
async def callback_instruction(callback: CallbackQuery):
    """Обработчик кнопки 'Инструкция'"""
    user_id = callback.from_user.id
    
    # Обновляем время последнего взаимодействия для системы удержания
    await db.update_last_interaction(user_id)
    
    # Красиво оформленное сообщение с призывом к действию
    instruction_text = (
        "📝 **Создавайте шедевры с NeuroFlow!**\n\n"
        "🎯 Чтобы создавать по-настоящему крутой контент, "
        "рекомендуем ознакомиться с нашей пошаговой инструкцией "
        "по созданию промтов!\n\n"
        "💡 **Вы узнаете:**\n"
        "🔹 Как писать эффективные промты\n"
        "🔹 Секреты создания вирусного контента\n"
        "🔹 Примеры успешных постов\n"
        "🔹 Настройка под разные ниши\n\n"
        "📖 Нажмите кнопку ниже, чтобы прочитать полную инструкцию!"
    )
    
    try:
        await callback.message.edit_text(
            instruction_text,
            reply_markup=get_instruction_keyboard()
        )
        
        # Логируем использование инструкции для аналитики
        logger.info(f"User {user_id} accessed instruction guide")
        
    except Exception as e:
        logger.error(f"Error showing instruction to user {user_id}: {e}")
        await callback.answer("❌ Произошла ошибка. Попробуйте еще раз.")


@router.callback_query(F.data == "back_to_menu")
async def callback_back_to_menu(callback: CallbackQuery):
    """Возврат в главное меню"""
    user_id = callback.from_user.id
    
    # Обновляем время последнего взаимодействия
    await db.update_last_interaction(user_id)
    
    try:
        await callback.message.edit_text(
            "🧠 **NeuroFlow - Главное меню**\n\n"
            "Выберите действие:",
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error returning to main menu for user {user_id}: {e}")
        await callback.answer("❌ Произошла ошибка. Попробуйте еще раз.")