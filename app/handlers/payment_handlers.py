import logging
import uuid
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, LabeledPrice, PreCheckoutQuery, Message

from app.models.postgresql_database import postgresql_db
from app.core.config import SUBSCRIPTION_PRICES, ADMIN_USER_ID
from app.utils.keyboards import (get_subscription_keyboard, get_payment_method_keyboard, 
                                get_crypto_currency_keyboard, get_back_keyboard, get_main_menu_keyboard,
                                get_contact_owner_keyboard, get_promo_code_keyboard)
from app.services.payment_services import aaio_service, crypto_service

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "buy_subscription")
async def callback_buy_subscription(callback: CallbackQuery):
    """Показать тарифы подписки"""
    text = "💎 **Выберите тариф подписки:**\n\n"
    
    for key, info in SUBSCRIPTION_PRICES.items():
        text += f"**{info['title']}**\n"
        
        if info.get('sbp_rub'):
            text += f"📲 СБП: {info['sbp_rub']} ₽\n"
        if info.get('crypto_usd'):
            text += f"💎 Крипта: ${info['crypto_usd']}\n"
        if info.get('stars'):
            text += f"⭐ Stars: {info['stars']}\n"
        
        if key == "3_months":
            text += "🔥 **Скидка 15%!**\n"
        elif key == "lifetime":
            text += "🔥 **НАВСЕГДА!**\n"
        
        text += "\n"
    
    text += "**Что включено:**\n"
    text += "🔹 Безлимитная генерация постов\n"
    text += "🔹 Автопостинг в ваши каналы\n"
    text += "🔹 Настройка под любую тематику\n"
    text += "🔹 Техническая поддержка"
    
    await callback.message.edit_text(text, reply_markup=get_subscription_keyboard())


@router.callback_query(F.data.startswith("select_plan_"))
async def callback_select_plan(callback: CallbackQuery):
    """Выбор способа оплаты для тарифа"""
    plan = callback.data.replace("select_plan_", "")
    
    if plan not in SUBSCRIPTION_PRICES:
        await callback.answer("❌ Неверный тариф", show_alert=True)
        return
    
    plan_info = SUBSCRIPTION_PRICES[plan]
    
    text = f"💳 **Способы оплаты для тарифа:**\n"
    text += f"**{plan_info['title']}**\n\n"
    
    # Проверяем, может ли пользователь использовать промокод TRIAL20
    user = await postgresql_db.get_user(callback.from_user.id)
    can_use_trial20 = (user and user.get('is_trial_used') and 
                      not await postgresql_db.is_subscription_active(callback.from_user.id))
    
    if can_use_trial20:
        text += "🎯 **У вас есть скидка 20% по промокоду TRIAL20!**\n\n"
    
    text += "Выберите удобный способ оплаты:"
    
    # Используем асинхронную функцию для клавиатуры
    keyboard = await get_payment_method_keyboard(plan, show_promo=can_use_trial20)
    await callback.message.edit_text(text, reply_markup=keyboard)


# Промокод обработчики
@router.callback_query(F.data.startswith("use_promo_"))
async def callback_use_promo(callback: CallbackQuery):
    """Применение промокода"""
    plan = callback.data.replace("use_promo_", "")
    
    if plan not in SUBSCRIPTION_PRICES:
        await callback.answer("❌ Неверный тариф", show_alert=True)
        return
    
    plan_info = SUBSCRIPTION_PRICES[plan]
    
    # Проверяем промокод TRIAL20
    promo_result = await postgresql_db.validate_promo_code("TRIAL20", callback.from_user.id)
    
    if not promo_result['valid']:
        await callback.answer(f"❌ {promo_result['error']}", show_alert=True)
        return
    
    discount_percent = promo_result['discount_percent']
    
    text = f"🎯 **Промокод TRIAL20 применен!**\n\n"
    text += f"📦 **Тариф:** {plan_info['title']}\n"
    text += f"🎁 **Скидка:** {discount_percent}%\n\n"
    
    # Показываем цены со скидкой
    if plan_info.get('sbp_rub'):
        original_price = plan_info['sbp_rub']
        discounted_price = await db.calculate_discounted_price(original_price, discount_percent)
        text += f"📲 СБП: ~~{original_price} ₽~~ → **{discounted_price} ₽**\n"
    
    if plan_info.get('crypto_usd'):
        original_price = plan_info['crypto_usd']
        discounted_price = await db.calculate_discounted_price(original_price, discount_percent)
        text += f"💎 Крипта: ~~${original_price}~~ → **${discounted_price}**\n"
    
    if plan_info.get('stars'):
        original_price = plan_info['stars']
        discounted_price = int(await db.calculate_discounted_price(original_price, discount_percent))
        text += f"⭐ Stars: ~~{original_price}~~ → **{discounted_price}**\n"
    
    text += f"\n💰 **Экономия: {discount_percent}%!**\n\n"
    text += "Выберите способ оплаты со скидкой:"
    
    keyboard = await get_payment_method_keyboard(plan, promo_code="TRIAL20")
    await callback.message.edit_text(text, reply_markup=keyboard)


# Обработчики недоступных методов оплаты
@router.callback_query(F.data.startswith("unavailable_"))
async def callback_unavailable_payment(callback: CallbackQuery):
    """Обработка нажатия на недоступный метод оплаты"""
    method = callback.data.replace("unavailable_", "")
    
    method_names = {
        'sbp': 'СБП',
        'crypto': 'Криптовалюта'
    }
    
    method_name = method_names.get(method, method)
    
    await callback.answer(
        f"⚠️ {method_name} временно недоступен.\n"
        f"Пожалуйста, выберите другой способ оплаты или обратитесь в службу поддержки.",
        show_alert=True
    )


@router.callback_query(F.data == "back_to_payment")
async def callback_back_to_payment(callback: CallbackQuery):
    """Возврат к выбору способа оплаты"""
    # Извлекаем план из предыдущего состояния или используем дефолтный
    await callback.message.edit_text(
        "💎 **Выберите тариф подписки:**\n\n"
        "Выберите тариф для просмотра доступных способов оплаты:",
        reply_markup=get_subscription_keyboard()
    )


# СБП платежи
@router.callback_query(F.data.startswith("pay_sbp_"))
async def callback_pay_sbp(callback: CallbackQuery):
    """Оплата через СБП"""
    from app.core.config_manager import config_manager
    
    # Проверяем доступность СБП
    if not await config_manager.is_payment_method_available('sbp'):
        await callback.answer(
            "⚠️ СБП временно недоступен. Пожалуйста, выберите другой способ оплаты.",
            show_alert=True
        )
        return
    
    # Парсим данные (может содержать промокод)
    data_parts = callback.data.replace("pay_sbp_", "").split("_promo_")
    plan = data_parts[0]
    promo_code = data_parts[1] if len(data_parts) > 1 else None
    
    plan_info = SUBSCRIPTION_PRICES.get(plan)
    if not plan_info:
        await callback.answer("❌ Неверный тариф", show_alert=True)
        return
    
    # Рассчитываем цену с учетом промокода
    original_amount = plan_info['sbp_rub']
    final_amount = original_amount
    discount_info = ""
    
    if promo_code:
        promo_result = await postgresql_db.validate_promo_code(promo_code, callback.from_user.id)
        if promo_result['valid']:
            final_amount = await postgresql_db.calculate_discounted_price(original_amount, promo_result['discount_percent'])
            discount_info = f"\n🎁 Скидка {promo_result['discount_percent']}%: -{original_amount - final_amount} ₽"
            
            # Записываем использование промокода
            await postgresql_db.record_promo_usage(
                callback.from_user.id, promo_code, promo_result['discount_percent'],
                original_amount, final_amount
            )
    
    # Создаем транзакцию в БД
    order_id = f"sbp_{callback.from_user.id}_{int(datetime.now().timestamp())}"
    
    transaction_id = await postgresql_db.create_transaction(
        user_id=callback.from_user.id,
        amount=final_amount,
        currency='RUB',
        method='sbp',
        subscription_type=plan,
        external_id=order_id
    )
    
    # Создаем платеж в AAIO
    webhook_url = "https://your-domain.com/webhook/aaio"  # Замените на ваш домен
    
    payment_data = await aaio_service.create_payment(
        amount=final_amount,
        order_id=order_id,
        description=f"Подписка NeuroFlow - {plan_info['title']}",
        user_id=callback.from_user.id,
        webhook_url=webhook_url
    )
    
    if payment_data and payment_data.get('url'):
        price_text = f"💰 Сумма: {final_amount} ₽"
        if discount_info:
            price_text += discount_info
        
        await callback.message.edit_text(
            f"💳 **Оплата через СБП**\n\n"
            f"{price_text}\n"
            f"📦 Тариф: {plan_info['title']}\n\n"
            f"🔗 Для оплаты перейдите по ссылке ниже и отсканируйте QR-код в банковском приложении:\n\n"
            f"[💳 Оплатить через СБП]({payment_data['url']})\n\n"
            f"⏱️ Подписка активируется автоматически после оплаты.",
            reply_markup=get_back_keyboard(),
            disable_web_page_preview=True
        )
        
        logger.info(f"SBP payment created for user {callback.from_user.id}: {order_id}, amount: {final_amount}")
    else:
        await callback.answer("❌ Ошибка создания платежа. Попробуйте позже.", show_alert=True)


# Криптовалютные платежи
@router.callback_query(F.data.startswith("pay_crypto_"))
async def callback_pay_crypto(callback: CallbackQuery):
    """Выбор криптовалюты"""
    from app.core.config_manager import config_manager
    
    # Проверяем доступность криптоплатежей
    if not await config_manager.is_payment_method_available('crypto'):
        await callback.answer(
            "⚠️ Криптоплатежи временно недоступны. Пожалуйста, выберите другой способ оплаты.",
            show_alert=True
        )
        return
    
    # Парсим данные (может содержать промокод)
    data_parts = callback.data.replace("pay_crypto_", "").split("_promo_")
    plan = data_parts[0]
    promo_code = data_parts[1] if len(data_parts) > 1 else None
    
    plan_info = SUBSCRIPTION_PRICES.get(plan)
    if not plan_info:
        await callback.answer("❌ Неверный тариф", show_alert=True)
        return
    
    # Рассчитываем цену с учетом промокода
    original_amount = plan_info['crypto_usd']
    final_amount = original_amount
    discount_info = ""
    
    if promo_code:
        promo_result = await postgresql_db.validate_promo_code(promo_code, callback.from_user.id)
        if promo_result['valid']:
            final_amount = await postgresql_db.calculate_discounted_price(original_amount, promo_result['discount_percent'])
            discount_info = f" (скидка {promo_result['discount_percent']}%)"
    
    text = f"💎 **Оплата криптовалютой**\n\n"
    text += f"📦 Тариф: {plan_info['title']}\n"
    text += f"💰 Сумма: ${final_amount}{discount_info}\n\n"
    text += "Выберите криптовалюту для оплаты:"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_crypto_currency_keyboard(plan, promo_code)
    )


@router.callback_query(F.data.startswith("crypto_currency_"))
async def callback_crypto_currency(callback: CallbackQuery):
    """Создание криптоинвойса"""
    # Парсим данные: crypto_currency_plan_currency или crypto_currency_plan_currency_promo_CODE
    data_parts = callback.data.replace("crypto_currency_", "").split("_")
    
    if len(data_parts) < 2:
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return
    
    plan = data_parts[0]
    currency = data_parts[1]
    promo_code = None
    
    # Проверяем наличие промокода
    if len(data_parts) >= 4 and data_parts[2] == "promo":
        promo_code = data_parts[3]
    
    plan_info = SUBSCRIPTION_PRICES.get(plan)
    
    if not plan_info or not crypto_service:
        await callback.answer("❌ Ошибка создания платежа", show_alert=True)
        return
    
    # Получаем курс валют
    rates = await crypto_service.get_exchange_rates()
    if not rates or currency not in rates:
        await callback.answer("❌ Курс валюты недоступен", show_alert=True)
        return
    
    # Рассчитываем сумму с учетом промокода
    original_usd_amount = plan_info['crypto_usd']
    final_usd_amount = original_usd_amount
    discount_info = ""
    
    if promo_code:
        promo_result = await postgresql_db.validate_promo_code(promo_code, callback.from_user.id)
        if promo_result['valid']:
            final_usd_amount = await postgresql_db.calculate_discounted_price(original_usd_amount, promo_result['discount_percent'])
            discount_info = f" (скидка {promo_result['discount_percent']}%)"
            
            # Записываем использование промокода
            await postgresql_db.record_promo_usage(
                callback.from_user.id, promo_code, promo_result['discount_percent'],
                original_usd_amount, final_usd_amount
            )
    
    # Рассчитываем сумму в криптовалюте
    crypto_amount = final_usd_amount / rates[currency]
    
    # Создаем транзакцию в БД
    payload = f"crypto_{callback.from_user.id}_{int(datetime.now().timestamp())}"
    
    transaction_id = await postgresql_db.create_transaction(
        user_id=callback.from_user.id,
        amount=crypto_amount,
        currency=currency,
        method='crypto',
        subscription_type=plan,
        external_id=payload
    )
    
    # Создаем инвойс в CryptoBot
    invoice_data = await crypto_service.create_invoice(
        amount=crypto_amount,
        currency=currency,
        description=f"NeuroFlow - {plan_info['title']}",
        payload=payload
    )
    
    if invoice_data and invoice_data.get('pay_url'):
        price_text = f"💰 Сумма: {crypto_amount:.8f} {currency}\n💵 Эквивалент: ${final_usd_amount}{discount_info}"
        
        await callback.message.edit_text(
            f"💎 **Оплата {currency}**\n\n"
            f"{price_text}\n"
            f"📦 Тариф: {plan_info['title']}\n\n"
            f"🔗 Для оплаты перейдите по ссылке:\n\n"
            f"[💎 Оплатить {currency}]({invoice_data['pay_url']})\n\n"
            f"⏱️ Подписка активируется автоматически после подтверждения транзакции в блокчейне.",
            reply_markup=get_back_keyboard(),
            disable_web_page_preview=True
        )
        
        logger.info(f"Crypto payment created for user {callback.from_user.id}: {payload}, amount: {crypto_amount} {currency}")
    else:
        await callback.answer("❌ Ошибка создания платежа. Попробуйте позже.", show_alert=True)


# Telegram Stars платежи (обновленный с поддержкой промокодов)
@router.callback_query(F.data.startswith("pay_stars_"))
async def callback_pay_stars(callback: CallbackQuery):
    """Оплата через Telegram Stars"""
    # Парсим данные (может содержать промокод)
    data_parts = callback.data.replace("pay_stars_", "").split("_promo_")
    plan = data_parts[0]
    promo_code = data_parts[1] if len(data_parts) > 1 else None
    
    if plan not in SUBSCRIPTION_PRICES:
        await callback.answer("❌ Неверный тип подписки", show_alert=True)
        return
    
    plan_info = SUBSCRIPTION_PRICES[plan]
    original_stars_amount = plan_info.get('stars')
    
    if not original_stars_amount:
        await callback.answer("❌ Оплата Stars недоступна для этого тарифа", show_alert=True)
        return
    
    # Рассчитываем цену с учетом промокода
    final_stars_amount = original_stars_amount
    discount_info = ""
    
    if promo_code:
        promo_result = await postgresql_db.validate_promo_code(promo_code, callback.from_user.id)
        if promo_result['valid']:
            final_stars_amount = int(await postgresql_db.calculate_discounted_price(original_stars_amount, promo_result['discount_percent']))
            discount_info = f" (скидка {promo_result['discount_percent']}%)"
            
            # Записываем использование промокода
            await postgresql_db.record_promo_usage(
                callback.from_user.id, promo_code, promo_result['discount_percent'],
                original_stars_amount, final_stars_amount
            )
    
    # Создаем инвойс
    prices = [LabeledPrice(label=plan_info["title"], amount=final_stars_amount)]
    
    try:
        description = f"Подписка на {plan_info['days']} дней\n"
        if discount_info:
            description += f"🎁 Скидка по промокоду: {original_stars_amount - final_stars_amount} Stars\n"
        description += (
            f"🔹 Безлимитная генерация постов\n"
            f"🔹 Автопостинг в каналы\n"
            f"🔹 Настройка под любую тематику"
        )
        
        payload_data = f"stars_{plan}_{callback.from_user.id}"
        if promo_code:
            payload_data += f"_promo_{promo_code}"
        
        await callback.message.answer_invoice(
            title=plan_info["title"] + discount_info,
            description=description,
            payload=payload_data,
            provider_token="",  # Для Telegram Stars не нужен
            currency="XTR",  # Telegram Stars
            prices=prices,
            start_parameter="subscription",
            photo_url="https://via.placeholder.com/400x300/4CAF50/FFFFFF?text=NeuroFlow",
            photo_width=400,
            photo_height=300,
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            send_phone_number_to_provider=False,
            send_email_to_provider=False,
            is_flexible=False,
            disable_notification=False,
            protect_content=False,
            reply_markup=None
        )
        
        await callback.answer("💳 Инвойс отправлен!")
        
    except Exception as e:
        logger.error(f"Ошибка при создании Stars инвойса: {e}")
        await callback.answer("❌ Ошибка при создании платежа", show_alert=True)


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    """Обработка предварительной проверки платежа Stars"""
    try:
        payload_parts = pre_checkout_query.invoice_payload.split("_")
        
        # Проверяем тип платежа
        if len(payload_parts) < 3:
            await pre_checkout_query.answer(ok=False, error_message="Неверный payload")
            return
        
        payment_type = payload_parts[0]
        
        if payment_type == "stars":
            # Обычная подписка
            plan = payload_parts[1]
            user_id = int(payload_parts[2])
            
            # Проверяем наличие промокода в payload
            promo_code = None
            if len(payload_parts) >= 5 and payload_parts[3] == "promo":
                promo_code = payload_parts[4]
            
            if plan not in SUBSCRIPTION_PRICES:
                await pre_checkout_query.answer(ok=False, error_message="Неверный тип подписки")
                return
            
            if user_id != pre_checkout_query.from_user.id:
                await pre_checkout_query.answer(ok=False, error_message="Неверный пользователь")
                return
            
            # Если есть промокод, проверяем его валидность
            if promo_code:
                promo_result = await postgresql_db.validate_promo_code(promo_code, user_id)
                if not promo_result['valid']:
                    await pre_checkout_query.answer(ok=False, error_message=f"Промокод недействителен: {promo_result['error']}")
                    return
        
        elif payment_type == "autopilot":
            # Подписка на автопилот
            rate_id = int(payload_parts[1])
            user_id = int(payload_parts[2])
            
            # Проверяем существование тарифа
            rate = await postgresql_db.get_autopilot_rate(rate_id)
            if not rate or not rate['is_active']:
                await pre_checkout_query.answer(ok=False, error_message="Тариф недоступен")
                return
            
            if user_id != pre_checkout_query.from_user.id:
                await pre_checkout_query.answer(ok=False, error_message="Неверный пользователь")
                return
        
        else:
            await pre_checkout_query.answer(ok=False, error_message="Неизвестный тип платежа")
            return
        
        await pre_checkout_query.answer(ok=True)
        
    except Exception as e:
        logger.error(f"Ошибка в pre_checkout_query: {e}")
        await pre_checkout_query.answer(ok=False, error_message="Внутренняя ошибка")


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """Обработка успешного платежа Stars"""
    try:
        payment = message.successful_payment
        payload_parts = payment.invoice_payload.split("_")
        
        if len(payload_parts) < 3:
            logger.error(f"Неверный payload в successful_payment: {payment.invoice_payload}")
            return
        
        payment_type = payload_parts[0]
        
        if payment_type == "stars":
            # Обычная подписка
            plan = payload_parts[1]
            user_id = int(payload_parts[2])
            
            # Проверяем наличие промокода
            promo_code = None
            if len(payload_parts) >= 5 and payload_parts[3] == "promo":
                promo_code = payload_parts[4]
            
            if plan not in SUBSCRIPTION_PRICES:
                logger.error(f"Неверный тип подписки: {plan}")
                return
            
            # Обрабатываем обычную подписку (существующая логика)
            await process_regular_subscription_payment(message, plan, user_id, promo_code, payment)
        
        elif payment_type == "autopilot":
            # Подписка на автопилот
            rate_id = int(payload_parts[1])
            user_id = int(payload_parts[2])
            
            await process_autopilot_subscription_payment(message, rate_id, user_id, payment)
        
        else:
            logger.error(f"Неизвестный тип платежа: {payment_type}")
            return
        
    except Exception as e:
        logger.error(f"Ошибка в successful_payment: {e}")


async def process_regular_subscription_payment(message: Message, plan: str, user_id: int, promo_code: str, payment):
    """Обработка платежа обычной подписки"""
    plan_info = SUBSCRIPTION_PRICES[plan]
    
    # Получаем количество дней подписки
    days = plan_info.get('days', 0)
    is_lifetime = plan_info.get('lifetime', False)
    
    # Обрабатываем промокод если есть
    original_amount = payment.total_amount
    discounted_amount = original_amount
    
    if promo_code:
        promo_result = await postgresql_db.validate_promo_code(promo_code, user_id)
        if promo_result['valid']:
            discounted_amount = await postgresql_db.calculate_discounted_price(
                original_amount, promo_result['discount_percent']
            )
            
            # Записываем использование промокода
            await postgresql_db.record_promo_usage(
                user_id, promo_code, promo_result['discount_percent'],
                original_amount, discounted_amount
            )
    
    # Обновляем подписку пользователя
    await postgresql_db.update_subscription(user_id, days, is_lifetime)
    
    # Записываем в аналитику
    from app.services.analytics_service import analytics_service
    await analytics_service.record_payment(
        user_id=user_id,
        method="stars",
        subscription_type=plan,
        amount=payment.total_amount,
        currency="XTR",
        transaction_id=payment.telegram_payment_charge_id
    )
    
    # Отправляем подтверждение
    success_text = f"✅ **Подписка активирована!**\n\n"
    success_text += f"📦 Тариф: {plan_info['title']}\n"
    success_text += f"💰 Оплачено: {payment.total_amount} Stars\n"
    
    if is_lifetime:
        success_text += f"⏰ Срок: Навсегда\n"
    else:
        success_text += f"⏰ Срок: {days} дней\n"
    
    if promo_code:
        success_text += f"🎁 Промокод: {promo_code}\n"
    
    success_text += f"\n🎉 Теперь вы можете создавать неограниченное количество постов!"
    
    await message.answer(success_text, reply_markup=get_main_menu_keyboard())
    
    logger.info(f"Successful Stars payment: user {user_id}, plan {plan}, amount {payment.total_amount}")


async def process_autopilot_subscription_payment(message: Message, rate_id: int, user_id: int, payment):
    """Обработка платежа подписки на автопилот"""
    try:
        # Получаем информацию о тарифе
        rate = await postgresql_db.get_autopilot_rate(rate_id)
        if not rate:
            logger.error(f"Autopilot rate not found: {rate_id}")
            return
        
        # Создаем запись о покупке
        purchase_id = await postgresql_db.create_autopilot_purchase(
            user_id=user_id,
            rate_id=rate_id,
            amount=payment.total_amount,
            currency="XTR",
            payment_method="stars",
            transaction_id=payment.telegram_payment_charge_id
        )
        
        # Активируем подписку
        success = await postgresql_db.activate_autopilot_subscription(user_id, purchase_id)
        
        if success:
            # Отправляем подтверждение
            success_text = f"✅ **Подписка на Автопилот активирована!**\n\n"
            success_text += f"📦 Тариф: {rate['name']}\n"
            success_text += f"📄 {rate['description']}\n"
            success_text += f"💰 Оплачено: {payment.total_amount} Stars\n"
            success_text += f"⏰ Срок: {rate['duration_days']} дней\n"
            success_text += f"📺 Максимум каналов: {rate['max_channels']}\n\n"
            success_text += f"🤖 Теперь вы можете добавлять каналы в автопилот!"
            
            from app.utils.keyboards import InlineKeyboardBuilder
            from aiogram.types import InlineKeyboardButton
            
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="🤖 Открыть Автопилот", callback_data="autopilot")
            )
            builder.row(
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")
            )
            
            await message.answer(success_text, reply_markup=builder.as_markup())
            
            logger.info(f"Successful autopilot payment: user {user_id}, rate {rate_id}, amount {payment.total_amount}")
        else:
            logger.error(f"Failed to activate autopilot subscription: user {user_id}, purchase {purchase_id}")
            await message.answer(
                "❌ Ошибка при активации подписки. Обратитесь в поддержку.",
                reply_markup=get_main_menu_keyboard()
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке autopilot payment: {e}")
        await message.answer(
            "❌ Произошла ошибка при обработке платежа. Обратитесь в поддержку.",
            reply_markup=get_back_keyboard()
        )

# Ручная оплата
@router.callback_query(F.data.startswith("pay_manual_"))
async def callback_pay_manual(callback: CallbackQuery):
    """Ручная оплата через владельца"""
    from app.core.config_manager import config_manager
    
    # Проверяем доступность ручной оплаты
    if not await config_manager.is_manual_payment_enabled():
        await callback.answer(
            "⚠️ Этот способ сейчас недоступен. Пожалуйста, выберите другой способ оплаты.",
            show_alert=True
        )
        return
    
    plan = callback.data.replace("pay_manual_", "")
    plan_info = SUBSCRIPTION_PRICES.get(plan)
    
    if not plan_info:
        await callback.answer("❌ Неверный тариф", show_alert=True)
        return
    
    # Формируем информацию о тарифе и ценах
    price_info = []
    if plan_info.get('sbp_rub'):
        price_info.append(f"📲 СБП: {plan_info['sbp_rub']} ₽")
    if plan_info.get('crypto_usd'):
        price_info.append(f"💎 Крипта: ${plan_info['crypto_usd']}")
    if plan_info.get('stars'):
        price_info.append(f"⭐ Stars: {plan_info['stars']}")
    
    text = (
        f"👨‍💻 **Ручная оплата**\n\n"
        f"📦 **Тариф:** {plan_info['title']}\n"
        f"💰 **Стоимость:**\n" + "\n".join(price_info) + "\n\n"
        f"**Для оплаты подписки напрямую у владельца нажмите кнопку ниже.**\n\n"
        f"После оплаты администратор активирует вам доступ вручную через панель управления.\n\n"
        f"📋 **Ваш ID для активации:** `{callback.from_user.id}`\n"
        f"*(Сообщите этот ID владельцу после оплаты)*"
    )
    
    # Создаем клавиатуру с кнопкой связи
    keyboard = await get_contact_owner_keyboard(callback.bot, plan)
    
    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    
    # Логируем запрос на ручную оплату
    logger.info(f"Manual payment request: user {callback.from_user.id}, plan {plan}")
    
    # Уведомляем админа о запросе (опционально)
    try:
        admin_text = (
            f"💰 **Запрос на ручную оплату**\n\n"
            f"👤 Пользователь: {callback.from_user.id}\n"
            f"👤 Имя: {callback.from_user.full_name}\n"
            f"📦 Тариф: {plan_info['title']}\n"
            f"💰 Стоимость: {' / '.join(price_info)}\n\n"
            f"**Инструкция:**\n"
            f"После получения оплаты используйте:\n"
            f"`/admin` → `👤 Пользователи` → введите ID `{callback.from_user.id}` → укажите дни подписки"
        )
        
        await callback.bot.send_message(ADMIN_USER_ID, admin_text)
    except Exception as e:
        logger.warning(f"Failed to notify admin about manual payment request: {e}")