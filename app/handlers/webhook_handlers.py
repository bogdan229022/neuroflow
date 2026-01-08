"""
Обработчики вебхуков от платежных систем
"""

import logging
from aiogram import Router, Bot
from aiogram.types import Update
from aiohttp import web

from app.models.postgresql_database import postgresql_db as db
from app.core.config import SUBSCRIPTION_PRICES
from app.services.payment_services import aaio_service, crypto_service

logger = logging.getLogger(__name__)


async def handle_aaio_webhook(request):
    """Обработчик вебхука от AAIO (СБП)"""
    try:
        data = await request.json()
        logger.info("AAIO webhook received")  # Не логируем чувствительные данные
        
        # Проверяем наличие сервиса
        if not aaio_service:
            logger.error("AAIO webhook: service not configured")
            return web.Response(status=503, text="Service not configured")
        
        # Проверяем подпись
        if not aaio_service.verify_webhook(data.copy()):
            logger.warning("AAIO webhook signature verification failed")
            return web.Response(status=400, text="Invalid signature")
        
        # Проверяем статус платежа
        if data.get('status') != 'success':
            logger.info(f"AAIO payment not successful: {data.get('status')}")
            return web.Response(status=200, text="OK")
        
        order_id = data.get('order_id')
        if not order_id:
            logger.error("AAIO webhook: missing order_id")
            return web.Response(status=400, text="Missing order_id")
        
        # Находим транзакцию в БД
        transaction = await db.get_transaction_by_external_id(order_id)
        if not transaction:
            logger.error(f"AAIO webhook: transaction not found for order_id {order_id}")
            return web.Response(status=404, text="Transaction not found")
        
        # Проверяем, что транзакция еще не обработана
        if transaction['status'] == 'completed':
            logger.info(f"AAIO webhook: transaction {order_id} already completed")
            return web.Response(status=200, text="Already processed")
        
        # Обновляем статус транзакции
        await db.update_transaction_status(transaction['id'], 'completed')
        
        # Активируем подписку
        plan_info = SUBSCRIPTION_PRICES.get(transaction['subscription_type'])
        if plan_info:
            is_lifetime = (transaction['subscription_type'] == "lifetime")
            await db.update_subscription(
                transaction['user_id'], 
                plan_info['days'], 
                is_lifetime
            )
            
            # Записываем в аналитику
            from app.services.analytics_service import analytics_service
            await analytics_service.record_payment(
                user_id=transaction['user_id'],
                method="sbp",
                subscription_type=transaction['subscription_type'],
                amount=transaction['amount'],
                currency=transaction['currency'],
                transaction_id=str(transaction['id'])
            )
            
            logger.info(f"AAIO: subscription activated for user {transaction['user_id']}")
            
            # Отправляем уведомление пользователю (нужен экземпляр бота)
            # Это будет реализовано в main.py
        
        return web.Response(status=200, text="OK")
        
    except Exception as e:
        logger.error(f"AAIO webhook error: {e}")
        return web.Response(status=500, text="Internal error")


async def handle_crypto_webhook(request):
    """Обработчик вебхука от CryptoBot"""
    try:
        data = await request.json()
        logger.info("CryptoBot webhook received")  # Не логируем чувствительные данные
        
        # СТРОГАЯ проверка токена
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''
        
        if not token:
            logger.warning("CryptoBot webhook: missing authorization header")
            return web.Response(status=401, text="Missing authorization")
        
        # Проверяем наличие сервиса
        if not crypto_service:
            logger.error("CryptoBot webhook: service not configured")
            return web.Response(status=503, text="Service not configured")
        
        # Строгая проверка подписи
        if not crypto_service.verify_webhook(token, data):
            logger.warning("CryptoBot webhook: signature verification failed")
            return web.Response(status=401, text="Invalid signature")
        
        # Проверяем тип события
        if data.get('update_type') != 'invoice_paid':
            logger.info(f"CryptoBot webhook: ignoring update_type {data.get('update_type')}")
            return web.Response(status=200, text="OK")
        
        invoice_data = data.get('payload', {})
        payload = invoice_data.get('payload')
        
        if not payload:
            logger.error("CryptoBot webhook: missing payload")
            return web.Response(status=400, text="Missing payload")
        
        # Находим транзакцию в БД
        transaction = await db.get_transaction_by_external_id(payload)
        if not transaction:
            logger.error(f"CryptoBot webhook: transaction not found for payload {payload}")
            return web.Response(status=404, text="Transaction not found")
        
        # Проверяем, что транзакция еще не обработана
        if transaction['status'] == 'completed':
            logger.info(f"CryptoBot webhook: transaction {payload} already completed")
            return web.Response(status=200, text="Already processed")
        
        # Обновляем статус транзакции
        await db.update_transaction_status(transaction['id'], 'completed')
        
        # Активируем подписку
        plan_info = SUBSCRIPTION_PRICES.get(transaction['subscription_type'])
        if plan_info:
            is_lifetime = (transaction['subscription_type'] == "lifetime")
            await db.update_subscription(
                transaction['user_id'], 
                plan_info['days'], 
                is_lifetime
            )
            
            # Записываем в аналитику
            from app.services.analytics_service import analytics_service
            await analytics_service.record_payment(
                user_id=transaction['user_id'],
                method="crypto",
                subscription_type=transaction['subscription_type'],
                amount=transaction['amount'],
                currency=transaction['currency'],
                transaction_id=payload
            )
            
            logger.info(f"CryptoBot: subscription activated for user {transaction['user_id']}")
        
        return web.Response(status=200, text="OK")
        
    except Exception as e:
        logger.error(f"CryptoBot webhook error: {e}")
        return web.Response(status=500, text="Internal error")


def setup_webhook_routes(app):
    """Настройка маршрутов для вебхуков"""
    app.router.add_post('/webhook/aaio', handle_aaio_webhook)
    app.router.add_post('/webhook/crypto', handle_crypto_webhook)


async def notify_user_payment_success(bot: Bot, user_id: int, transaction: dict):
    """Уведомление пользователя об успешной оплате"""
    try:
        plan_info = SUBSCRIPTION_PRICES.get(transaction['subscription_type'])
        if not plan_info:
            return
        
        method_names = {
            'sbp': 'СБП',
            'crypto': 'Криптовалюта',
            'stars': 'Telegram Stars'
        }
        
        method_name = method_names.get(transaction['method'], transaction['method'])
        is_lifetime = (transaction['subscription_type'] == "lifetime")
        
        lifetime_text = " (ПОЖИЗНЕННО)" if is_lifetime else f" на {plan_info['days']} дней"
        
        text = (
            f"🎉 **Оплата успешно получена!**\n\n"
            f"✅ Подписка активирована{lifetime_text}\n"
            f"💰 Сумма: {transaction['amount']} {transaction['currency']}\n"
            f"💳 Способ: {method_name}\n"
            f"📦 Тариф: {plan_info['title']}\n\n"
            f"Теперь вы можете:\n"
            f"⚙️ Настроить канал и тему\n"
            f"🤖 Генерировать посты\n"
            f"📊 Запустить автопостинг"
        )
        
        await bot.send_message(user_id, text)
        
    except Exception as e:
        logger.error(f"Error notifying user {user_id}: {e}")