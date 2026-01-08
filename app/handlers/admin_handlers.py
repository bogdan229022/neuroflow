import logging
import asyncio
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.models.postgresql_database import postgresql_db as db
from app.utils.keyboards import get_admin_keyboard, get_back_keyboard
from app.core.config import ADMIN_USER_ID

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь админом"""
    return user_id == ADMIN_USER_ID


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Команда /admin с мониторингом"""
    try:
        if not is_admin(message.from_user.id):
            await message.answer("❌ У вас нет прав администратора.")
            return
        
        stats = await db.get_admin_stats()
        
        await message.answer(
            f"👑 **NeuroFlow Admin Dashboard**\n\n"
            f"📊 **Основная статистика:**\n"
            f"👥 Всего пользователей: {stats['total_users']}\n"
            f"✅ Активных подписок: {stats['active_subscriptions']}\n"
            f"🎁 На пробном периоде: {stats['trial_users']}\n"
            f"📊 Активных автопостингов: {stats['active_autoposting']}\n\n"
            f"Выберите действие:",
            reply_markup=get_admin_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error in admin command: {e}")
        await message.answer("❌ Ошибка загрузки админ панели")


@router.callback_query(F.data == "admin_stats")
async def callback_admin_stats(callback: CallbackQuery):
    """Показать детальную статистику"""
    try:
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Нет прав доступа", show_alert=True)
            return
        
        from app.services.analytics_service import analytics_service
        
        # Получаем мгновенный отчет
        report = await analytics_service.get_instant_report()
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📈 Еженедельный отчет", callback_data="weekly_report"),
            InlineKeyboardButton(text="📊 Экспорт CSV", callback_data="export_csv")
        )
        builder.row(
            InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")
        )
        
        await callback.message.edit_text(
            report,
            reply_markup=builder.as_markup()
        )
        
    except Exception as e:
        logger.error(f"Error in admin stats: {e}")
        await callback.answer("❌ Ошибка получения статистики", show_alert=True)


@router.callback_query(F.data == "back_to_admin")
async def callback_back_to_admin(callback: CallbackQuery, state: FSMContext):
    """Возврат в админ-панель"""
    try:
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Нет прав доступа", show_alert=True)
            return
        
        await state.clear()
        await cmd_admin(callback.message)
        
    except Exception as e:
        logger.error(f"Error returning to admin: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "weekly_report")
async def callback_weekly_report(callback: CallbackQuery):
    """Еженедельный отчет"""
    try:
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Нет прав доступа", show_alert=True)
            return
        
        from app.services.analytics_service import analytics_service
        
        report = await analytics_service.get_weekly_report()
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin_stats")
        )
        
        await callback.message.edit_text(
            report,
            reply_markup=builder.as_markup()
        )
        
    except Exception as e:
        logger.error(f"Error in weekly report: {e}")
        await callback.answer("❌ Ошибка получения отчета", show_alert=True)


@router.callback_query(F.data == "export_csv")
async def callback_export_csv(callback: CallbackQuery):
    """Экспорт CSV отчета"""
    try:
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Нет прав доступа", show_alert=True)
            return
        
        await callback.answer("📊 Генерирую CSV отчет...", show_alert=False)
        
        from app.services.analytics_service import analytics_service
        
        csv_file = await analytics_service.export_payments_report()
        
        if csv_file:
            # Отправляем файл
            document = FSInputFile(csv_file, filename="payments_report.csv")
            await callback.message.answer_document(
                document,
                caption="📊 **Отчет по платежам**\n\nВыгружены все транзакции за последние 30 дней."
            )
            
            # Удаляем временный файл
            import os
            try:
                os.remove(csv_file)
            except:
                pass
        else:
            await callback.answer("❌ Ошибка при создании отчета", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        await callback.answer("❌ Ошибка при экспорте", show_alert=True)