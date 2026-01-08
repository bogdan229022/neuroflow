import asyncio
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from app.core.config import BOT_TOKEN, ADMIN_USER_ID, DATABASE_POOL_MIN_SIZE, DATABASE_POOL_MAX_SIZE
from app.models.postgresql_database import postgresql_db
from app.utils.middlewares import SubscriptionMiddleware, UserRegistrationMiddleware, AntiFloodMiddleware
from app.services.scheduler import init_scheduler, stop_scheduler
from app.handlers.webhook_handlers import setup_webhook_routes
from app.services.image_service import image_service
from app.services.redis_cache import redis_cache
from app.services.api_pool_manager import ultra_api_pool

# Импорт роутеров
from app.handlers.base_handlers import router as main_router
from app.handlers.payment_handlers import router as payment_router
from app.handlers.autopost_handlers import router as autopost_router
from app.handlers.admin_handlers import router as admin_router
from app.handlers.user_handlers import router as user_router
from app.handlers.autopilot_handlers import router as autopilot_router

# Настройка интеллектуального логирования с ротацией
def setup_logging():
    """Настройка логирования с ротацией файлов"""
    import os
    from pathlib import Path
    
    # Создаем папку logs если её нет
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)
    
    # Создаем форматтер
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Основной лог (все сообщения)
    main_handler = RotatingFileHandler(
        'logs/bot.log',
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    main_handler.setLevel(logging.INFO)
    main_handler.setFormatter(formatter)
    
    # Лог ошибок (только ошибки)
    error_handler = RotatingFileHandler(
        'logs/bot_errors.log',
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    
    # Лог платежей (критически важные операции)
    payment_handler = RotatingFileHandler(
        'logs/payments.log',
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=10,  # Храним больше логов платежей
        encoding='utf-8'
    )
    payment_handler.setLevel(logging.INFO)
    payment_handler.setFormatter(formatter)
    
    # Настраиваем root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(main_handler)
    root_logger.addHandler(error_handler)
    
    # Настраиваем logger для платежей
    payment_logger = logging.getLogger('payments')
    payment_logger.addHandler(payment_handler)
    payment_logger.propagate = False  # Не дублируем в основной лог
    
    # Консольный вывод для разработки
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    root_logger.addHandler(console_handler)
    
    # Настраиваем уровни для внешних библиотек
    logging.getLogger('aiogram').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('asyncpg').setLevel(logging.WARNING)
    
    logging.info("Logging system initialized with rotation")


async def init_services():
    """Инициализация всех сервисов"""
    logger = logging.getLogger(__name__)
    
    try:
        # 1. Инициализация базы данных
        logger.info("Initializing PostgreSQL database...")
        await postgresql_db.init_pool(
            min_size=DATABASE_POOL_MIN_SIZE,
            max_size=DATABASE_POOL_MAX_SIZE
        )
        logger.info("✅ PostgreSQL database initialized")
        
        # 2. Инициализация Redis
        logger.info("Initializing Redis cache...")
        await redis_cache.init_redis()
        logger.info("✅ Redis cache initialized")
        
        # 3. Инициализация API Pool Manager
        logger.info("Initializing API Pool Manager...")
        await ultra_api_pool.initialize()
        logger.info("✅ API Pool Manager initialized")
        
        # 4. Инициализация Image Service
        logger.info("Initializing Image Service...")
        await image_service.initialize()
        logger.info("✅ Image Service initialized")
        
        # 5. Проверка подключения к базе данных
        logger.info("Testing database connection...")
        async with postgresql_db.get_connection() as conn:
            result = await conn.fetchval("SELECT 1")
            if result == 1:
                logger.info("✅ Database connection test passed")
            else:
                raise Exception("Database connection test failed")
        
        # 6. Проверка Redis
        logger.info("Testing Redis connection...")
        await redis_cache.ping()
        logger.info("✅ Redis connection test passed")
        
        logger.info("🚀 All services initialized successfully!")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}")
        raise


async def shutdown_services():
    """Корректное завершение всех сервисов"""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Shutting down services...")
        
        # Останавливаем планировщик
        await stop_scheduler()
        logger.info("✅ Scheduler stopped")
        
        # Закрываем API Pool Manager
        await ultra_api_pool.close()
        logger.info("✅ API Pool Manager closed")
        
        # Закрываем Image Service
        await image_service.close()
        logger.info("✅ Image Service closed")
        
        # Закрываем Redis
        await redis_cache.close()
        logger.info("✅ Redis connection closed")
        
        # Закрываем базу данных
        await postgresql_db.close_pool()
        logger.info("✅ Database connection pool closed")
        
        logger.info("🔄 All services shut down gracefully")
        
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")


async def setup_bot_and_dispatcher():
    """Настройка бота и диспетчера"""
    logger = logging.getLogger(__name__)
    
    # Создаем бота с настройками по умолчанию
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.MARKDOWN,
            link_preview_is_disabled=True
        )
    )
    
    # Создаем диспетчер с хранилищем состояний
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Регистрируем middleware в правильном порядке
    logger.info("Setting up middleware...")
    
    # 1. Anti-flood middleware (первый - для защиты)
    dp.message.middleware(AntiFloodMiddleware())
    dp.callback_query.middleware(AntiFloodMiddleware())
    
    # 2. User registration middleware (регистрация пользователей)
    dp.message.middleware(UserRegistrationMiddleware())
    dp.callback_query.middleware(UserRegistrationMiddleware())
    
    # 3. Subscription middleware (проверка подписки)
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
    
    logger.info("✅ Middleware configured")
    
    # Регистрируем роутеры в правильном порядке
    logger.info("Registering routers...")
    
    dp.include_router(admin_router)      # Админские команды (высший приоритет)
    dp.include_router(payment_router)    # Платежи
    dp.include_router(autopilot_router)  # Автопилот
    dp.include_router(autopost_router)   # Автопостинг
    dp.include_router(user_router)       # Пользовательские функции
    dp.include_router(main_router)       # Основные команды (последний)
    
    logger.info("✅ All routers registered")
    
    return bot, dp


async def setup_webhook_server(bot: Bot, dp: Dispatcher):
    """Настройка webhook сервера"""
    logger = logging.getLogger(__name__)
    
    try:
        # Создаем aiohttp приложение
        app = web.Application()
        
        # Настраиваем webhook routes
        setup_webhook_routes(app, bot, dp)
        
        # Добавляем middleware для логирования
        async def logging_middleware(request, handler):
            start_time = asyncio.get_event_loop().time()
            try:
                response = await handler(request)
                process_time = asyncio.get_event_loop().time() - start_time
                logger.info(f"Request {request.method} {request.path} - {response.status} - {process_time:.3f}s")
                return response
            except Exception as e:
                process_time = asyncio.get_event_loop().time() - start_time
                logger.error(f"Request {request.method} {request.path} - ERROR: {e} - {process_time:.3f}s")
                raise
        
        app.middlewares.append(logging_middleware)
        
        # Health check endpoint
        async def health_check(request):
            try:
                # Проверяем базу данных
                async with postgresql_db.get_connection() as conn:
                    await conn.fetchval("SELECT 1")
                
                # Проверяем Redis
                await redis_cache.ping()
                
                return web.json_response({
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                    "services": {
                        "database": "ok",
                        "redis": "ok",
                        "bot": "ok"
                    }
                })
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return web.json_response({
                    "status": "unhealthy",
                    "error": str(e)
                }, status=503)
        
        app.router.add_get('/health', health_check)
        
        # Metrics endpoint для мониторинга
        async def metrics(request):
            try:
                async with postgresql_db.get_connection() as conn:
                    total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
                    active_users = await conn.fetchval("""
                        SELECT COUNT(*) FROM users 
                        WHERE last_interaction_date > NOW() - INTERVAL '24 hours'
                    """)
                
                return web.json_response({
                    "total_users": total_users,
                    "active_users_24h": active_users,
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"Metrics endpoint error: {e}")
                return web.json_response({"error": str(e)}, status=500)
        
        app.router.add_get('/metrics', metrics)
        
        logger.info("✅ Webhook server configured")
        return app
        
    except Exception as e:
        logger.error(f"❌ Failed to setup webhook server: {e}")
        raise


async def main():
    """Главная функция запуска бота"""
    # Настраиваем логирование
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Starting NeuroFlow Bot...")
    logger.info(f"Admin User ID: {ADMIN_USER_ID}")
    
    try:
        # Инициализируем сервисы
        await init_services()
        
        # Настраиваем бота и диспетчер
        bot, dp = await setup_bot_and_dispatcher()
        
        # Получаем информацию о боте
        bot_info = await bot.get_me()
        logger.info(f"✅ Bot initialized: @{bot_info.username} ({bot_info.full_name})")
        
        # Инициализируем планировщик задач
        logger.info("Initializing scheduler...")
        await init_scheduler(bot)
        logger.info("✅ Scheduler initialized")
        
        # Настраиваем webhook сервер
        app = await setup_webhook_server(bot, dp)
        
        # Уведомляем админа о запуске
        try:
            await bot.send_message(
                ADMIN_USER_ID,
                f"🚀 **NeuroFlow Bot запущен!**\n\n"
                f"🤖 Бот: @{bot_info.username}\n"
                f"⏰ Время запуска: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"🔧 Все сервисы инициализированы\n"
                f"📊 Планировщик активен\n\n"
                f"Система готова к работе! ✅"
            )
        except Exception as e:
            logger.warning(f"Could not send startup notification to admin: {e}")
        
        # Запускаем webhook сервер
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        
        logger.info("🌐 Webhook server started on http://0.0.0.0:8080")
        logger.info("🎯 NeuroFlow Bot is fully operational!")
        
        # Ожидаем завершения
        try:
            await asyncio.Future()  # Бесконечное ожидание
        except KeyboardInterrupt:
            logger.info("Received shutdown signal...")
        
    except Exception as e:
        logger.error(f"❌ Critical error in main: {e}")
        raise
    
    finally:
        logger.info("🔄 Shutting down...")
        
        # Уведомляем админа о завершении
        try:
            await bot.send_message(
                ADMIN_USER_ID,
                f"🔄 **NeuroFlow Bot завершает работу**\n\n"
                f"⏰ Время завершения: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"📊 Выполняется корректное завершение всех сервисов..."
            )
        except:
            pass
        
        # Корректно завершаем все сервисы
        await shutdown_services()
        
        # Закрываем сессию бота
        await bot.session.close()
        
        logger.info("✅ NeuroFlow Bot shut down gracefully")


def run_bot():
    """Функция для запуска бота"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🔄 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_bot()