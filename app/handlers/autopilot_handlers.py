import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.models.postgresql_database import postgresql_db as db
from app.core.autopilot import get_autopilot_manager
from app.utils.states import AutopilotStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "autopilot")
async def callback_autopilot_menu(callback: CallbackQuery):
    """Главное меню автопилота"""
    try:
        user_id = callback.from_user.id
        
        # Обновляем время взаимодействия
        await db.update_last_interaction(user_id)
        
        # Получаем ссылку на инструкцию из настроек
        instruction_url = await db.get_config("autopilot_instruction_url")
        if not instruction_url:
            instruction_url = "https://telegra.ph/Instrukciya-Kak-zapustit-II-Avtopilot-v-NeuroFlow-01-07"
            await db.set_config("autopilot_instruction_url", instruction_url)
        
        # Проверяем подписку на автопилот
        subscription_status = await db.get_autopilot_subscription_status(user_id)
        
        # Получаем конфигурации пользователя
        autopilot = get_autopilot_manager()
        if not autopilot:
            await callback.answer("❌ Автопилот недоступен", show_alert=True)
            return
        
        configs = await autopilot.get_user_autopilot_configs(user_id)
        
        text = "🤖 **ИИ-Автопилот для каналов**\n\n"
        text += "📖 *Перед настройкой рекомендуем ознакомиться с нашей [подробной инструкцией]({}) для профессионального ведения канала.*\n\n".format(instruction_url)
        
        builder = InlineKeyboardBuilder()
        
        if not subscription_status['is_active']:
            # Нет активной подписки - показываем рекламное меню
            text += "🚀 **Автономное ведение ваших Telegram-каналов с помощью ИИ!**\n\n"
            text += "✨ **Что умеет Автопилот:**\n"
            text += "• 🔍 Поиск актуальных новостей по вашей теме\n"
            text += "• 📝 Генерация уникального контента с помощью ИИ\n"
            text += "• 🖼️ Создание изображений к постам\n"
            text += "• ⏰ Автоматическая публикация по расписанию\n"
            text += "• 📊 Аналитика и статистика\n\n"
            text += "💎 **Тарифы автопилота:**\n"
            text += "• 📅 Месяц: 299 ₽\n"
            text += "• 📅 3 месяца: 799 ₽ (экономия 98 ₽)\n"
            text += "• 📅 Год: 2999 ₽ (экономия 589 ₽)\n\n"
            text += "🎁 **Специальное предложение:** Первые 3 дня бесплатно!"
            
            # Добавляем кнопку с инструкцией в начале
            builder.row(
                InlineKeyboardButton(text="📖 Читать инструкцию", url=instruction_url)
            )
            
            builder.row(
                InlineKeyboardButton(text="💎 Купить автопилот", callback_data="autopilot_buy")
            )
            
            builder.row(
                InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")
            )
        else:
            # Есть активная подписка - показываем обычное меню
            stats = await autopilot.get_autopilot_statistics(user_id)
            
            text += "Автономное ведение ваших Telegram-каналов с помощью ИИ!\n\n"
            
            # Информация о подписке
            days_left = subscription_status['days_left']
            if days_left > 0:
                text += f"💎 **Подписка активна:** {days_left} дн. осталось\n\n"
            else:
                text += f"💎 **Подписка:** истекает сегодня\n\n"
            
            if configs:
                text += f"📊 **Ваша статистика:**\n"
                text += f"• Конфигураций: {stats.get('total_configs', 0)}\n"
                text += f"• Активных: {stats.get('active_configs', 0)}\n"
                text += f"• Постов за месяц: {stats.get('total_posts', 0)}\n"
                text += f"• Успешность: {stats.get('success_rate', 0):.1f}%\n\n"
                
                text += "**Ваши каналы:**\n"
                for config in configs[:3]:  # Показываем первые 3
                    status = "🟢" if config['is_active'] else "🔴"
                    text += f"{status} @{config['channel_id']} - {config['topic']}\n"
                
                if len(configs) > 3:
                    text += f"... и еще {len(configs) - 3} каналов\n"
            else:
                text += "📝 У вас пока нет настроенных каналов.\n"
                text += "Создайте первую конфигурацию автопилота!\n"
            
            text += "\nВыберите действие:"
            
            # Добавляем кнопку с инструкцией в начале
            builder.row(
                InlineKeyboardButton(text="📖 Читать инструкцию", url=instruction_url)
            )
            
            if configs:
                builder.row(
                    InlineKeyboardButton(text="📋 Мои каналы", callback_data="autopilot_list"),
                    InlineKeyboardButton(text="📊 Статистика", callback_data="autopilot_stats")
                )
            
            builder.row(
                InlineKeyboardButton(text="➕ Добавить канал", callback_data="autopilot_add")
            )
            
            if configs:
                builder.row(
                    InlineKeyboardButton(text="🧪 Тестовый пост", callback_data="autopilot_test")
                )
            
            # Если подписка скоро истекает, показываем кнопку продления
            if days_left <= 7:
                builder.row(
                    InlineKeyboardButton(text="💎 Продлить подписку", callback_data="autopilot_extend")
                )
            
            builder.row(
                InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")
            )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"Error in autopilot menu: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "autopilot_buy")
async def callback_autopilot_buy(callback: CallbackQuery):
    """Покупка автопилота"""
    try:
        user_id = callback.from_user.id
        
        # Получаем тарифы автопилота
        rates = await db.get_autopilot_rates()
        
        if not rates:
            await callback.answer("❌ Тарифы временно недоступны", show_alert=True)
            return
        
        text = "💎 **Выберите тариф автопилота:**\n\n"
        
        builder = InlineKeyboardBuilder()
        
        for rate in rates:
            # Форматируем название тарифа
            if rate['duration_days'] == 30:
                duration_text = "1 месяц"
            elif rate['duration_days'] == 90:
                duration_text = "3 месяца"
            elif rate['duration_days'] == 365:
                duration_text = "1 год"
            else:
                duration_text = f"{rate['duration_days']} дней"
            
            text += f"📅 **{rate['name']}** ({duration_text})\n"
            text += f"💰 Цена: {rate['price_rub']} ₽\n"
            if rate['description']:
                text += f"📝 {rate['description']}\n"
            text += "\n"
            
            builder.row(
                InlineKeyboardButton(
                    text=f"{rate['name']} - {rate['price_rub']} ₽",
                    callback_data=f"autopilot_buy_{rate['id']}"
                )
            )
        
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="autopilot")
        )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"Error in autopilot buy: {e}")
        await callback.answer("❌ Ошибка загрузки тарифов", show_alert=True)


@router.callback_query(F.data.startswith("autopilot_buy_"))
async def callback_autopilot_buy_rate(callback: CallbackQuery):
    """Покупка конкретного тарифа автопилота"""
    try:
        rate_id = int(callback.data.replace("autopilot_buy_", ""))
        user_id = callback.from_user.id
        
        # Получаем информацию о тарифе
        rate = await db.get_autopilot_rate(rate_id)
        if not rate:
            await callback.answer("❌ Тариф не найден", show_alert=True)
            return
        
        # Создаем инвойс для оплаты
        from aiogram.types import LabeledPrice
        
        invoice = await callback.message.answer_invoice(
            title=f"Автопилот: {rate['name']}",
            description=f"Подписка на автопилот NeuroFlow на {rate['duration_days']} дней",
            payload=f"autopilot_{rate_id}_{user_id}",
            provider_token="",  # Для Telegram Stars не нужен
            currency="XTR",
            prices=[LabeledPrice(label=rate['name'], amount=rate['price_stars'])],
            start_parameter="autopilot_payment"
        )
        
    except Exception as e:
        logger.error(f"Error creating autopilot invoice: {e}")
        await callback.answer("❌ Ошибка создания платежа", show_alert=True)