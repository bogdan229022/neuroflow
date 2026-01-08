from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.core.config import SUBSCRIPTION_PRICES
from app.services.tunnel_service import tunnel_service
import asyncio


async def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню бота с динамическим WebApp URL"""
    builder = InlineKeyboardBuilder()
    
    # Получаем актуальный URL WebApp
    try:
        webapp_url = await tunnel_service.get_webapp_url()
        
        # Добавляем кнопку WebApp только если URL валиден
        if webapp_url and webapp_url != "https://localhost:8081":
            builder.row(
                InlineKeyboardButton(
                    text="🚀 Панель управления", 
                    web_app=WebAppInfo(url=webapp_url)
                )
            )
    except Exception as e:
        # Логируем ошибку, но не ломаем интерфейс
        import logging
        logging.getLogger(__name__).warning(f"Failed to get webapp URL: {e}")
    
    builder.row(
        InlineKeyboardButton(text="👤 Профиль/Подписка", callback_data="profile"),
        InlineKeyboardButton(text="⚙️ Настройки ИИ", callback_data="settings")
    )
    builder.row(
        InlineKeyboardButton(text="🎯 Генерация поста", callback_data="generate"),
        InlineKeyboardButton(text="🧪 Тестовый пост", callback_data="test_post")
    )
    builder.row(
        InlineKeyboardButton(text="🤖 Автопилот", callback_data="autopilot"),
        InlineKeyboardButton(text="📊 Автопостинг", callback_data="autopost")
    )
    builder.row(
        InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
        InlineKeyboardButton(text="📝 Инструкция", callback_data="instruction")
    )
    
    return builder.as_markup()


def get_main_menu_keyboard_sync() -> InlineKeyboardMarkup:
    """Синхронная версия главного меню (fallback)"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="👤 Профиль/Подписка", callback_data="profile"),
        InlineKeyboardButton(text="⚙️ Настройки ИИ", callback_data="settings")
    )
    builder.row(
        InlineKeyboardButton(text="🎯 Генерация поста", callback_data="generate"),
        InlineKeyboardButton(text="🧪 Тестовый пост", callback_data="test_post")
    )
    builder.row(
        InlineKeyboardButton(text="🤖 Автопилот", callback_data="autopilot"),
        InlineKeyboardButton(text="📊 Автопостинг", callback_data="autopost")
    )
    builder.row(
        InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
        InlineKeyboardButton(text="📝 Инструкция", callback_data="instruction")
    )
    
    return builder.as_markup()


def get_subscription_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора тарифа"""
    builder = InlineKeyboardBuilder()
    
    for key, info in SUBSCRIPTION_PRICES.items():
        title = info['title']
        if key == "lifetime":
            title = "🔥 " + title
        
        builder.row(
            InlineKeyboardButton(
                text=title,
                callback_data=f"select_plan_{key}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")
    )
    
    return builder.as_markup()


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="📢 Настроить канал", callback_data="set_channel"),
        InlineKeyboardButton(text="📝 Настроить тему", callback_data="set_topic")
    )
    builder.row(
        InlineKeyboardButton(text="🤖 Настроить промпт", callback_data="set_prompt"),
        InlineKeyboardButton(text="🖼️ Изображения", callback_data="toggle_images")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")
    )
    
    return builder.as_markup()


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Простая клавиатура с кнопкой назад"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")
    )
    return builder.as_markup()


def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для админ-панели с Ultra-Scaling мониторингом"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="🚀 Ultra-Scaling", callback_data="ultra_scaling_status")
    )
    builder.row(
        InlineKeyboardButton(text="💰 Транзакции", callback_data="admin_transactions"),
        InlineKeyboardButton(text="👤 Пользователи", callback_data="admin_users")
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Настройка API", callback_data="admin_api_config"),
        InlineKeyboardButton(text="💾 Redis Cache", callback_data="redis_management")
    )
    builder.row(
        InlineKeyboardButton(text="📢 Массовая рассылка", callback_data="mass_broadcast"),
        InlineKeyboardButton(text="🤖 Цены: Автопилот", callback_data="autopilot_pricing")
    )
    builder.row(
        InlineKeyboardButton(text="📖 Настройка инструкций", callback_data="admin_instructions"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")
    )
    
    return builder.as_markup()


async def get_payment_method_keyboard(plan: str, show_promo: bool = False, promo_code: str = None) -> InlineKeyboardMarkup:
    """Клавиатура для выбора способа оплаты"""
    from app.core.config_manager import config_manager
    
    builder = InlineKeyboardBuilder()
    
    plan_info = SUBSCRIPTION_PRICES.get(plan, {})
    payment_status = await config_manager.get_payment_methods_status()
    
    # Если есть промокод, добавляем его к callback_data
    promo_suffix = f"_promo_{promo_code}" if promo_code else ""
    
    # СБП
    if plan_info.get('sbp_rub'):
        if payment_status.get('sbp', False):
            price = plan_info['sbp_rub']
            if promo_code:
                from app.models.postgresql_database import postgresql_db as db
                discounted_price = await db.calculate_discounted_price(price, 20)  # TRIAL20 = 20%
                price_text = f"📲 СБП - {discounted_price} ₽ (скидка!)"
            else:
                price_text = f"📲 СБП - {price} ₽"
            
            builder.row(
                InlineKeyboardButton(
                    text=price_text,
                    callback_data=f"pay_sbp_{plan}{promo_suffix}"
                )
            )
        else:
            builder.row(
                InlineKeyboardButton(
                    text="📲 СБП [Недоступен]",
                    callback_data=f"unavailable_sbp"
                )
            )
    
    # Криптовалюта
    if plan_info.get('crypto_usd'):
        if payment_status.get('crypto', False):
            price = plan_info['crypto_usd']
            if promo_code:
                from app.models.postgresql_database import postgresql_db as db
                discounted_price = await db.calculate_discounted_price(price, 20)  # TRIAL20 = 20%
                price_text = f"💎 Криптовалюта - ${discounted_price} (скидка!)"
            else:
                price_text = f"💎 Криптовалюта - ${price}"
            
            builder.row(
                InlineKeyboardButton(
                    text=price_text,
                    callback_data=f"pay_crypto_{plan}{promo_suffix}"
                )
            )
        else:
            builder.row(
                InlineKeyboardButton(
                    text="💎 Криптовалюта [Недоступна]",
                    callback_data=f"unavailable_crypto"
                )
            )
    
    # Telegram Stars (всегда доступны)
    if plan_info.get('stars'):
        price = plan_info['stars']
        if promo_code:
            from app.models.postgresql_database import postgresql_db as db
            discounted_price = int(await db.calculate_discounted_price(price, 20))  # TRIAL20 = 20%
            price_text = f"⭐ Telegram Stars - {discounted_price} Stars (скидка!)"
        else:
            price_text = f"⭐ Telegram Stars - {price} Stars"
        
        builder.row(
            InlineKeyboardButton(
                text=price_text,
                callback_data=f"pay_stars_{plan}{promo_suffix}"
            )
        )
    
    # Ручная оплата
    if payment_status.get('manual', False):
        builder.row(
            InlineKeyboardButton(
                text="👨‍💻 Ручная оплата (СБП/Другое)",
                callback_data=f"pay_manual_{plan}"
            )
        )
    
    # Кнопка применения промокода (только если промокод еще не применен и пользователь может его использовать)
    if show_promo and not promo_code:
        builder.row(
            InlineKeyboardButton(
                text="🎯 Применить промокод TRIAL20 (-20%)",
                callback_data=f"use_promo_{plan}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="🔙 Назад к тарифам", callback_data="buy_subscription")
    )
    
    return builder.as_markup()


def get_crypto_currency_keyboard(plan: str, promo_code: str = None) -> InlineKeyboardMarkup:
    """Клавиатура для выбора криптовалюты"""
    builder = InlineKeyboardBuilder()
    
    from app.core.config import CRYPTO_CURRENCIES
    
    # Добавляем промокод к callback_data если он есть
    promo_suffix = f"_promo_{promo_code}" if promo_code else ""
    
    for currency in CRYPTO_CURRENCIES:
        builder.row(
            InlineKeyboardButton(
                text=f"{currency}",
                callback_data=f"crypto_currency_{plan}_{currency}{promo_suffix}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"select_plan_{plan}")
    )
    
    return builder.as_markup()


def get_autopost_keyboard(is_active: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура управления автопостингом"""
    builder = InlineKeyboardBuilder()
    
    if is_active:
        builder.row(
            InlineKeyboardButton(text="⏸️ Остановить автопостинг", callback_data="autopost_stop")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="▶️ Запустить автопостинг", callback_data="autopost_start")
        )
    
    builder.row(
        InlineKeyboardButton(text="📊 Статус", callback_data="autopost_status"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")
    )
    
    return builder.as_markup()


def get_confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}"),
        InlineKeyboardButton(text="❌ Нет", callback_data="back_to_menu")
    )
    
    return builder.as_markup()


def get_api_config_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для настройки API ключей"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🤖 Groq API", callback_data="config_groq"),
        InlineKeyboardButton(text="💎 CryptoBot", callback_data="config_crypto")
    )
    builder.row(
        InlineKeyboardButton(text="📲 AAIO (СБП)", callback_data="config_aaio"),
        InlineKeyboardButton(text="👨‍💻 Ручная оплата", callback_data="config_manual")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статус API", callback_data="api_status"),
        InlineKeyboardButton(text="🧪 Тест API", callback_data="test_apis")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")
    )
    
    return builder.as_markup()


def get_aaio_config_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для настройки AAIO"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🔑 API Key", callback_data="aaio_api_key"),
        InlineKeyboardButton(text="🏪 Shop ID", callback_data="aaio_shop_id")
    )
    builder.row(
        InlineKeyboardButton(text="🔐 Secret Key", callback_data="aaio_secret_key")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_api_config")
    )
    
    return builder.as_markup()


async def get_unavailable_payment_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для недоступного метода оплаты"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🔙 Выбрать другой способ", callback_data="back_to_payment")
    )
    
    return builder.as_markup()


async def get_contact_owner_keyboard(bot, plan: str) -> InlineKeyboardMarkup:
    """Клавиатура для связи с владельцем"""
    from app.core.config import ADMIN_USER_ID
    
    builder = InlineKeyboardBuilder()
    
    try:
        # Пытаемся получить username владельца
        admin_chat = await bot.get_chat(ADMIN_USER_ID)
        if admin_chat.username:
            contact_url = f"https://t.me/{admin_chat.username}"
        else:
            # Если username нет, используем прямую ссылку по ID
            contact_url = f"tg://user?id={ADMIN_USER_ID}"
    except:
        # В случае ошибки используем прямую ссылку по ID
        contact_url = f"tg://user?id={ADMIN_USER_ID}"
    
    builder.row(
        InlineKeyboardButton(
            text="👨‍💻 Написать владельцу",
            url=contact_url
        )
    )
    
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад к способам оплаты", 
            callback_data=f"select_plan_{plan}"
        )
    )
    
    return builder.as_markup()


def get_promo_code_keyboard(plan: str) -> InlineKeyboardMarkup:
    """Клавиатура для применения промокода"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="🎯 Применить TRIAL20 (-20%)",
            callback_data=f"use_promo_{plan}"
        )
    )
    
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"select_plan_{plan}")
    )
    
    return builder.as_markup()


def get_manual_payment_config_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для настройки ручной оплаты в админке"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="✅ Включить", callback_data="manual_payment_enable"),
        InlineKeyboardButton(text="❌ Отключить", callback_data="manual_payment_disable")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_api_config")
    )
    
    return builder.as_markup()


def get_instruction_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для инструкции с кнопкой перехода на Telegraph"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="📖 Прочитать инструкцию",
            url="https://telegra.ph/NeuroFlow-kak-sozdavat-shedevry-s-pomoshchyu-II-01-05"
        )
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")
    )
    
    return builder.as_markup()
