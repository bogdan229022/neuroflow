import asyncio
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot

from app.models.postgresql_database import postgresql_db as db
from app.services.ai_service import ai_service
from app.core.config import AUTO_POST_INTERVAL_HOURS

logger = logging.getLogger(__name__)


class AutoPostScheduler:
    def __init__(self, bot: Bot):
        """Инициализация AutoPost Scheduler"""
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        
    async def start(self):
        """Запуск планировщика"""
        # Добавляем задачу автопостинга
        self.scheduler.add_job(
            self.auto_post_job,
            IntervalTrigger(hours=AUTO_POST_INTERVAL_HOURS),
            id='auto_post_job',
            name='Автопостинг в каналы пользователей',
            replace_existing=True
        )
        
        # Добавляем задачу еженедельного отчета (каждый понедельник в 09:00)
        from apscheduler.triggers.cron import CronTrigger
        
        self.scheduler.add_job(
            self.weekly_report_job,
            CronTrigger(day_of_week=0, hour=9, minute=0),  # Понедельник в 09:00
            id='weekly_report_job',
            name='Еженедельный отчет администратору',
            replace_existing=True
        )
        
        # Добавляем задачу уведомлений о истекающем триале (каждый час)
        self.scheduler.add_job(
            self.trial_expiry_notification_job,
            IntervalTrigger(hours=1),
            id='trial_expiry_job',
            name='Уведомления о истекающем триале',
            replace_existing=True
        )
        
        # Добавляем задачу автопилота (каждые 30 минут)
        self.scheduler.add_job(
            self.autopilot_job,
            IntervalTrigger(minutes=30),
            id='autopilot_job',
            name='ИИ-Автопилот для каналов',
            replace_existing=True
        )
        
        # Добавляем задачу upsell сообщений (каждые 30 минут)
        self.scheduler.add_job(
            self.upsell_notification_job,
            IntervalTrigger(minutes=30),
            id='upsell_job',
            name='Upsell сообщения для истекших триалов',
            replace_existing=True
        )
        
        # Добавляем задачу сбора фидбека (каждые 6 часов)
        self.scheduler.add_job(
            self.feedback_collection_job,
            IntervalTrigger(hours=6),
            id='feedback_job',
            name='Сбор фидбека от неактивных пользователей',
            replace_existing=True
        )
        
        # Добавляем задачу отключения автопостинга для истекших триалов (каждые 15 минут)
        self.scheduler.add_job(
            self.disable_expired_trials_job,
            IntervalTrigger(minutes=15),
            id='disable_trials_job',
            name='Отключение автопостинга для истекших триалов',
            replace_existing=True
        )
        
        # Добавляем задачу уведомлений об истекающих подписках автопилота (каждые 6 часов)
        self.scheduler.add_job(
            self.autopilot_expiry_notification_job,
            IntervalTrigger(hours=6),
            id='autopilot_expiry_job',
            name='Уведомления об истекающих подписках автопилота',
            replace_existing=True
        )
        
        # Добавляем задачу автоочистки временных файлов (каждые 2 часа)
        self.scheduler.add_job(
            self.cleanup_temp_files_job,
            IntervalTrigger(hours=2),
            id='cleanup_temp_files_job',
            name='Автоочистка временных файлов изображений',
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info(f"Планировщик запущен:")
        logger.info(f"- Автопостинг: каждые {AUTO_POST_INTERVAL_HOURS} часов")
        logger.info(f"- Еженедельные отчеты: понедельник в 09:00")
        logger.info(f"- Уведомления о триале: каждый час")
        logger.info(f"- Upsell сообщения: каждые 30 минут")
        logger.info(f"- Сбор фидбека: каждые 6 часов")
        logger.info(f"- Отключение истекших триалов: каждые 15 минут")
        logger.info(f"- Автоочистка временных файлов: каждые 2 часа")
    
    async def stop(self):
        """Остановка планировщика"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Планировщик автопостинга остановлен")
    
    async def auto_post_job(self):
        """Основная задача автопостинга"""
        try:
            logger.info("Запуск задачи автопостинга")
            
            # Получаем всех пользователей с активным автопостингом
            active_users = await db.get_active_users_for_posting()
            
            if not active_users:
                logger.info("Нет пользователей с активным автопостингом")
                return
            
            logger.info(f"Найдено {len(active_users)} пользователей с активным автопостингом")
            
            # Обрабатываем каждого пользователя
            for user_data in active_users:
                try:
                    await self.process_user_autopost(user_data)
                except Exception as e:
                    logger.error(f"Ошибка при обработке автопостинга для пользователя {user_data['user_id']}: {e}")
                    continue
            
            logger.info("Задача автопостинга завершена")
            
        except Exception as e:
            logger.error(f"Критическая ошибка в задаче автопостинга: {e}")
    
    async def process_user_autopost(self, user_data: dict):
        """Обработка автопостинга для одного пользователя"""
        user_id = user_data['user_id']
        channel_id = user_data['channel_id']
        topic = user_data['topic']
        system_instruction = user_data['system_instruction']
        last_post_time = user_data.get('last_post_time', 0)
        
        # Проверяем, прошло ли достаточно времени с последнего поста
        current_time = datetime.now().timestamp()
        time_since_last_post = current_time - last_post_time
        min_interval = AUTO_POST_INTERVAL_HOURS * 3600  # Конвертируем часы в секунды
        
        if time_since_last_post < min_interval:
            logger.debug(f"Пользователь {user_id}: слишком рано для нового поста")
            return
        
        logger.info(f"Генерация поста для пользователя {user_id}, канал {channel_id}")
        
        # Получаем настройки пользователя для проверки генерации изображений
        settings = await db.get_user_settings(user_id)
        generate_images = settings.get('generate_images', True) if settings else True
        
        # Генерируем пост с изображением или без
        if generate_images:
            post_content, image_data = await ai_service.generate_post_with_image(
                topic, system_instruction, generate_image=True
            )
        else:
            post_content = await ai_service.generate_post(topic, system_instruction)
            image_data = None
        
        if not post_content:
            logger.error(f"Не удалось сгенерировать пост для пользователя {user_id}")
            return
        
        # Публикуем пост в канал
        try:
            if image_data:
                # Отправляем изображение с подписью
                from aiogram.types import BufferedInputFile
                
                image_file = BufferedInputFile(image_data, filename="autopost.jpg")
                
                await self.bot.send_photo(
                    chat_id=channel_id,
                    photo=image_file,
                    caption=post_content,
                    parse_mode=None  # Отключаем парсинг разметки для безопасности
                )
                
                logger.info(f"Пост с изображением успешно опубликован для пользователя {user_id}")
            else:
                # Отправляем только текст
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=post_content,
                    parse_mode=None  # Отключаем парсинг разметки для безопасности
                )
                
                logger.info(f"Текстовый пост успешно опубликован для пользователя {user_id}")
            
            # Обновляем время последнего поста
            await db.update_user_settings(
                user_id, 
                last_post_time=int(current_time)
            )
            
            # Отправляем уведомление пользователю
            try:
                notification_text = f"✅ **Автопост опубликован!**\n\n"
                notification_text += f"📢 Канал: {channel_id}\n"
                notification_text += f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                
                if image_data:
                    notification_text += f"🖼️ С изображением\n"
                
                notification_text += f"\nСледующий пост будет опубликован через {AUTO_POST_INTERVAL_HOURS} часов."
                
                await self.bot.send_message(
                    chat_id=user_id,
                    text=notification_text
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка при публикации поста для пользователя {user_id}: {e}")
            
            # Отправляем уведомление об ошибке пользователю
            try:
                error_message = "❌ **Ошибка автопостинга**\n\n"
                
                if "chat not found" in str(e).lower():
                    error_message += "Канал не найден. Проверьте правильность ID канала."
                elif "not enough rights" in str(e).lower() or "forbidden" in str(e).lower():
                    error_message += "Бот не имеет прав для публикации в канале. Убедитесь, что бот добавлен как администратор с правами на публикацию сообщений."
                else:
                    error_message += f"Произошла ошибка при публикации поста: {str(e)[:100]}"
                
                error_message += f"\n\n📢 Канал: {channel_id}\n⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                error_message += f"\n\nПроверьте настройки канала или обратитесь в поддержку."
                
                await self.bot.send_message(chat_id=user_id, text=error_message)
                
                # Временно отключаем автопостинг при критических ошибках
                if any(keyword in str(e).lower() for keyword in ["chat not found", "forbidden", "not enough rights"]):
                    await db.update_user_settings(user_id, is_active=False)
                    await self.bot.send_message(
                        chat_id=user_id,
                        text="⚠️ Автопостинг временно отключен из-за ошибки доступа к каналу. "
                             "Исправьте проблему и запустите автопостинг заново."
                    )
                    logger.info(f"Автопостинг отключен для пользователя {user_id} из-за ошибки доступа")
                
            except Exception as notify_error:
                logger.error(f"Не удалось отправить уведомление об ошибке пользователю {user_id}: {notify_error}")

    async def trial_expiry_notification_job(self):
        """Задача уведомлений о истекающем триале"""
        try:
            logger.debug("Проверка пользователей с истекающим триалом")
            
            # Получаем пользователей с триалом, истекающим в течение часа
            expiring_users = await db.get_users_with_expiring_trial(hours_before=1)
            
            if not expiring_users:
                return
            
            logger.info(f"Найдено {len(expiring_users)} пользователей с истекающим триалом")
            
            for user_data in expiring_users:
                try:
                    user_id = user_data['user_id']
                    trial_expiry = user_data['trial_expiry']
                    
                    # Вычисляем оставшееся время
                    current_time = int(datetime.now().timestamp())
                    time_left = trial_expiry - current_time
                    minutes_left = max(0, int(time_left // 60))
                    
                    # Формируем сообщение
                    message_text = (
                        f"⏰ **Ваш пробный период скоро истечет!**\n\n"
                        f"🎁 Осталось: {minutes_left} минут\n\n"
                        f"💎 **Не упустите возможность продолжить использование NeuroFlow!**\n\n"
                        f"🔹 Генерация уникального контента с ИИ\n"
                        f"🔹 Автоматическая публикация в каналы\n"
                        f"🔹 Создание изображений к постам\n\n"
                        f"Оформите подписку прямо сейчас и продолжайте создавать качественный контент!"
                    )
                    
                    # Импортируем клавиатуру для покупки подписки
                    from app.utils.keyboards import get_subscription_keyboard
                    
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=message_text,
                        reply_markup=get_subscription_keyboard()
                    )
                    
                    logger.info(f"Уведомление о истекающем триале отправлено пользователю {user_id}")
                    
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления о триале пользователю {user_data.get('user_id', 'unknown')}: {e}")
            
        except Exception as e:
            logger.error(f"Критическая ошибка в задаче уведомлений о триале: {e}")

    async def disable_expired_trials_job(self):
        """Задача отключения автопостинга для истекших триалов с upsell сообщением"""
        try:
            logger.debug("Проверка пользователей с истекшим триалом для отключения автопостинга")
            
            # Получаем пользователей с истекшим триалом и активным автопостингом
            expired_users = await db.get_expired_trial_users()
            
            if not expired_users:
                return
            
            logger.info(f"Найдено {len(expired_users)} пользователей с истекшим триалом для отключения")
            
            for user_data in expired_users:
                try:
                    user_id = user_data['user_id']
                    
                    # Отключаем автопостинг
                    await db.update_user_settings(user_id, is_active=False)
                    
                    # Отправляем upsell сообщение с промокодом
                    upsell_message = (
                        f"⏰ **Ваш пробный период NeuroFlow завершен.**\n\n"
                        f"🚀 **Чтобы не прерывать рост вашего канала, активируйте полную подписку "
                        f"в ближайшие 2 часа и получите скидку 20% по промокоду TRIAL20!**\n\n"
                        f"💎 **Что вы получите:**\n"
                        f"🔹 Безлимитная генерация контента с ИИ\n"
                        f"🔹 Автоматические изображения к постам\n"
                        f"🔹 Непрерывный автопостинг в каналы\n"
                        f"🔹 Приоритетная поддержка\n\n"
                        f"⚡ **До возобновления автопостинга осталось всего несколько кликов!**\n\n"
                        f"🎯 Промокод: **TRIAL20** (скидка 20%)"
                    )
                    
                    # Импортируем клавиатуру для покупки подписки
                    from app.utils.keyboards import get_subscription_keyboard
                    
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=upsell_message,
                        reply_markup=get_subscription_keyboard()
                    )
                    
                    # Отмечаем что upsell отправлен
                    await db.mark_upsell_sent(user_id)
                    
                    logger.info(f"Автопостинг отключен и upsell отправлен пользователю {user_id}")
                    
                except Exception as e:
                    logger.error(f"Ошибка при обработке истекшего триала для пользователя {user_data.get('user_id', 'unknown')}: {e}")
            
        except Exception as e:
            logger.error(f"Критическая ошибка в задаче отключения истекших триалов: {e}")

    async def upsell_notification_job(self):
        """Задача отправки upsell сообщений (дополнительная проверка)"""
        try:
            logger.debug("Дополнительная проверка пользователей для upsell")
            
            # Получаем пользователей для upsell (если что-то пропустили)
            upsell_users = await db.get_users_for_upsell()
            
            if not upsell_users:
                return
            
            logger.info(f"Найдено {len(upsell_users)} пользователей для дополнительного upsell")
            
            for user_data in upsell_users:
                try:
                    user_id = user_data['user_id']
                    
                    # Проверяем, что пользователь все еще без подписки
                    subscription_status = await db.get_subscription_status(user_id)
                    if subscription_status['is_active']:
                        continue  # Пользователь уже купил подписку
                    
                    # Отправляем upsell сообщение
                    upsell_message = (
                        f"🎯 **Последний шанс вернуть автопостинг!**\n\n"
                        f"Ваш канал ждет новый контент. Активируйте подписку NeuroFlow "
                        f"со скидкой 20% по промокоду **TRIAL20**\n\n"
                        f"⏰ Предложение действует ограниченное время!"
                    )
                    
                    from app.utils.keyboards import get_subscription_keyboard
                    
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=upsell_message,
                        reply_markup=get_subscription_keyboard()
                    )
                    
                    await db.mark_upsell_sent(user_id)
                    
                    logger.info(f"Дополнительный upsell отправлен пользователю {user_id}")
                    
                except Exception as e:
                    logger.error(f"Ошибка при отправке дополнительного upsell пользователю {user_data.get('user_id', 'unknown')}: {e}")
            
        except Exception as e:
            logger.error(f"Критическая ошибка в задаче дополнительного upsell: {e}")

    async def feedback_collection_job(self):
        """Задача сбора фидбека от неактивных пользователей (через 72 часа)"""
        try:
            logger.debug("Проверка пользователей для сбора фидбека")
            
            # Получаем пользователей для сбора фидбека
            feedback_users = await db.get_users_for_feedback()
            
            if not feedback_users:
                return
            
            logger.info(f"Найдено {len(feedback_users)} пользователей для сбора фидбека")
            
            for user_data in feedback_users:
                try:
                    user_id = user_data['user_id']
                    
                    # Проверяем, что пользователь все еще без подписки
                    subscription_status = await db.get_subscription_status(user_id)
                    if subscription_status['is_active']:
                        await db.mark_feedback_sent(user_id)  # Отмечаем как отправленное
                        continue  # Пользователь уже купил подписку
                    
                    # Формируем сообщение для сбора фидбека
                    from app.core.config import ADMIN_USER_ID
                    
                    # Получаем ссылку на админа
                    try:
                        admin_chat = await self.bot.get_chat(ADMIN_USER_ID)
                        if admin_chat.username:
                            admin_link = f"@{admin_chat.username}"
                        else:
                            admin_link = f"[Написать админу](tg://user?id={ADMIN_USER_ID})"
                    except:
                        admin_link = f"[Написать админу](tg://user?id={ADMIN_USER_ID})"
                    
                    feedback_message = (
                        f"😔 **Нам очень жаль, что вы перестали использовать NeuroFlow.**\n\n"
                        f"🤔 **Подскажите, чего вам не хватило?**\n"
                        f"• Качество генерируемого текста?\n"
                        f"• Выбор тем и настройки?\n"
                        f"• Сложность настройки каналов?\n"
                        f"• Что-то еще?\n\n"
                        f"💬 **Напишите честный отзыв нашему админу {admin_link}, "
                        f"и мы дарим вам еще 1 день подписки за помощь в развитии проекта!**\n\n"
                        f"🎁 Ваше мнение поможет нам стать лучше!"
                    )
                    
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=feedback_message,
                        parse_mode="Markdown"
                    )
                    
                    await db.mark_feedback_sent(user_id)
                    
                    logger.info(f"Запрос фидбека отправлен пользователю {user_id}")
                    
                except Exception as e:
                    logger.error(f"Ошибка при отправке запроса фидбека пользователю {user_data.get('user_id', 'unknown')}: {e}")
            
        except Exception as e:
            logger.error(f"Критическая ошибка в задаче сбора фидбека: {e}")

    async def weekly_report_job(self):
        """Задача еженедельного отчета администратору"""
        try:
            from app.services.analytics_service import analytics_service
            from app.core.config import ADMIN_USER_ID
            
            logger.info("Генерация еженедельного отчета для администратора")
            
            # Получаем отчет за прошлую неделю
            report = await analytics_service.get_weekly_report()
            
            # Отправляем отчет администратору
            try:
                await self.bot.send_message(
                    chat_id=ADMIN_USER_ID,
                    text=f"🤖 **АВТОМАТИЧЕСКИЙ ЕЖЕНЕДЕЛЬНЫЙ ОТЧЕТ**\n\n{report}\n\n"
                         f"📊 Для получения детальной статистики используйте /admin"
                )
                
                logger.info("Еженедельный отчет успешно отправлен администратору")
                
            except Exception as e:
                logger.error(f"Ошибка при отправке еженедельного отчета: {e}")
            
        except Exception as e:
            logger.error(f"Критическая ошибка в задаче еженедельного отчета: {e}")


# Глобальный экземпляр планировщика
scheduler = None


async def init_scheduler(bot: Bot):
    """Инициализация планировщика"""
    global scheduler
    scheduler = AutoPostScheduler(bot)
    await scheduler.start()


async def stop_scheduler():
    """Остановка планировщика"""
    global scheduler
    if scheduler:
        await scheduler.stop()
    
    async def autopilot_job(self):
        """Задача ИИ-Автопилота - выполняется каждые 30 минут"""
        try:
            from app.core.autopilot import get_autopilot_manager
            
            autopilot = get_autopilot_manager()
            if autopilot:
                await autopilot.run_autopilot_cycle()
                logger.info("Autopilot cycle completed successfully")
            else:
                logger.warning("Autopilot manager not initialized")
                
        except Exception as e:
            logger.error(f"Error in autopilot job: {e}")
            
            # Уведомляем админа об ошибке
            from app.core.config import ADMIN_USER_ID
            if ADMIN_USER_ID:
                try:
                    await self.bot.send_message(
                        ADMIN_USER_ID,
                        f"⚠️ **Ошибка в автопилоте**\n\n"
                        f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                        f"Ошибка: {str(e)[:200]}...\n\n"
                        f"Проверьте логи для подробностей."
                    )
                except:
                    pass  # Игнорируем ошибки отправки уведомлений
    async def autopilot_expiry_notification_job(self):
        """Уведомления об истекающих подписках автопилота"""
        try:
            from app.models.postgresql_database import postgresql_db
            
            logger.info("Запуск задачи уведомлений об истекающих подписках автопилота")
            
            # Получаем подписки, истекающие в ближайшие 24 часа
            expiring_subscriptions = await postgresql_db.get_expiring_autopilot_subscriptions(24)
            
            if not expiring_subscriptions:
                logger.info("Нет истекающих подписок автопилота")
                return
            
            logger.info(f"Найдено {len(expiring_subscriptions)} истекающих подписок автопилота")
            
            for subscription in expiring_subscriptions:
                try:
                    user_id = subscription['user_id']
                    expiry_timestamp = subscription['autopilot_subscription_expiry']
                    
                    # Вычисляем оставшееся время
                    current_time = datetime.now().timestamp()
                    hours_left = (expiry_timestamp - current_time) / 3600
                    
                    if hours_left <= 0:
                        # Подписка уже истекла
                        notification_text = (
                            "🤖 **Подписка на Автопилот истекла**\n\n"
                            "Ваша подписка на ИИ-Автопилот закончилась.\n"
                            "Автоматическая публикация постов остановлена.\n\n"
                            "💎 Продлите подписку, чтобы продолжить использование автопилота!"
                        )
                    elif hours_left <= 1:
                        # Истекает в течение часа
                        notification_text = (
                            "🤖 **Подписка на Автопилот истекает через час!**\n\n"
                            "Ваша подписка на ИИ-Автопилот заканчивается менее чем через час.\n"
                            "Не забудьте продлить подписку, чтобы автопилот продолжил работу.\n\n"
                            "💎 Продлите сейчас и не прерывайте автоматическую публикацию!"
                        )
                    elif hours_left <= 24:
                        # Истекает в течение суток
                        hours_text = f"{int(hours_left)} час{'ов' if int(hours_left) > 4 else 'а' if int(hours_left) > 1 else ''}"
                        notification_text = (
                            f"🤖 **Подписка на Автопилот истекает через {hours_text}**\n\n"
                            "Ваша подписка на ИИ-Автопилот скоро закончится.\n"
                            "Продлите подписку заранее, чтобы избежать перерыва в работе автопилота.\n\n"
                            "💎 Продлите подписку прямо сейчас!"
                        )
                    else:
                        continue  # Не отправляем уведомление
                    
                    # Создаем клавиатуру с кнопкой продления
                    from aiogram.utils.keyboard import InlineKeyboardBuilder
                    from aiogram.types import InlineKeyboardButton
                    
                    builder = InlineKeyboardBuilder()
                    builder.row(
                        InlineKeyboardButton(text="💎 Продлить подписку", callback_data="autopilot_extend")
                    )
                    builder.row(
                        InlineKeyboardButton(text="🤖 Открыть Автопилот", callback_data="autopilot")
                    )
                    
                    # Отправляем уведомление
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=notification_text,
                        reply_markup=builder.as_markup()
                    )
                    
                    logger.info(f"Отправлено уведомление об истекающей подписке автопилота пользователю {user_id}")
                    
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления об автопилоте пользователю {subscription.get('user_id', 'unknown')}: {e}")
                    continue
            
            logger.info("Задача уведомлений об истекающих подписках автопилота завершена")
            
        except Exception as e:
            logger.error(f"Критическая ошибка в задаче уведомлений автопилота: {e}")
    
    async def cleanup_temp_files_job(self):
        """Задача автоочистки временных файлов изображений"""
        try:
            from app.services.image_service import image_service
            
            logger.info("Запуск автоочистки временных файлов")
            
            # Очищаем старые временные файлы (старше 1 часа)
            await image_service.auto_cleanup_old_temp_files(max_age_hours=1)
            
            # Очищаем старые элементы очереди изображений (старше 7 дней)
            cleaned_queue_items = await image_service.cleanup_old_queue_items(days_old=7)
            
            if cleaned_queue_items > 0:
                logger.info(f"Очищено {cleaned_queue_items} старых элементов очереди изображений")
            
            logger.info("Автоочистка временных файлов завершена")
            
        except Exception as e:
            logger.error(f"Ошибка в задаче автоочистки временных файлов: {e}")