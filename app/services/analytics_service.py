"""
Analytics Service - Система аналитики и отчетности
Обеспечивает сбор статистики, генерацию отчетов и экспорт данных
"""

import asyncio
import logging
import tempfile
import csv
import io
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from app.models.postgresql_database import postgresql_db

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Сервис аналитики и отчетности"""
    
    def __init__(self):
        self.db = postgresql_db
    
    async def record_payment(self, user_id: int, method: str, subscription_type: str, 
                           amount: float, currency: str = "RUB", transaction_id: str = None):
        """Записать платеж в аналитику"""
        try:
            # Записываем в основную таблицу транзакций
            await self.db.create_transaction(
                user_id=user_id,
                amount=amount,
                currency=currency,
                method=method,
                subscription_type=subscription_type,
                external_id=transaction_id
            )
            
            # Обновляем статистику
            await self.db.record_payment_stats(method, amount, currency)
            
            logger.info(f"Payment recorded: user={user_id}, method={method}, amount={amount}")
            
        except Exception as e:
            logger.error(f"Failed to record payment: {e}")
    
    async def get_instant_report(self) -> str:
        """Получить мгновенный отчет о состоянии системы"""
        try:
            # Получаем основную статистику
            stats = await self.db.get_stats()
            admin_stats = await self.db.get_admin_stats()
            revenue_stats = await self.db.get_revenue_stats()
            
            # Формируем отчет
            report = "📊 **МГНОВЕННЫЙ ОТЧЕТ NEUROFLOW**\n\n"
            
            # Пользователи
            report += "👥 **ПОЛЬЗОВАТЕЛИ:**\n"
            report += f"• Всего: {admin_stats.get('total_users', 0)}\n"
            report += f"• С подпиской: {admin_stats.get('active_subscriptions', 0)}\n"
            report += f"• Админы: {admin_stats.get('admin_count', 0)}\n\n"
            
            # Контент
            report += "📝 **КОНТЕНТ:**\n"
            report += f"• Постов сгенерировано: {stats.get('total_posts', 0)}\n"
            report += f"• Изображений создано: {stats.get('total_images', 0)}\n\n"
            
            # Доходы
            report += "💰 **ДОХОДЫ:**\n"
            total_revenue = 0
            for method, data in revenue_stats.items():
                if method != 'total_revenue':
                    amount = data.get('total_amount', 0)
                    count = data.get('transaction_count', 0)
                    report += f"• {method.upper()}: {amount:.2f} RUB ({count} транз.)\n"
                    total_revenue += amount
            
            report += f"\n💎 **ОБЩИЙ ДОХОД: {total_revenue:.2f} RUB**\n\n"
            
            # Время генерации
            report += f"🕐 Отчет сгенерирован: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            
            return report
            
        except Exception as e:
            logger.error(f"Failed to generate instant report: {e}")
            return "❌ Ошибка при генерации отчета"
    
    async def get_weekly_report(self, week_number: int = None, year: int = None) -> str:
        """Получить еженедельный отчет"""
        try:
            # Если не указаны параметры, берем прошлую неделю
            if week_number is None or year is None:
                now = datetime.now()
                # Получаем номер прошлой недели
                last_week = now - timedelta(days=7)
                week_number = last_week.isocalendar()[1]
                year = last_week.year
            
            # Получаем статистику за неделю
            weekly_stats = await self.db.get_weekly_stats(week_number, year)
            
            # Формируем отчет
            report = f"📈 **ЕЖЕНЕДЕЛЬНЫЙ ОТЧЕТ - НЕДЕЛЯ {week_number}/{year}**\n\n"
            
            if not weekly_stats:
                report += "📊 Данных за указанную неделю не найдено.\n"
                return report
            
            # Статистика платежей
            report += "💰 **ПЛАТЕЖИ ЗА НЕДЕЛЮ:**\n"
            total_weekly = 0
            
            for stat in weekly_stats:
                method = stat.get('payment_method', 'unknown')
                amount = stat.get('total_amount', 0)
                count = stat.get('transaction_count', 0)
                
                report += f"• {method.upper()}: {amount:.2f} RUB ({count} транз.)\n"
                total_weekly += amount
            
            report += f"\n💎 **ИТОГО ЗА НЕДЕЛЮ: {total_weekly:.2f} RUB**\n\n"
            
            # Сравнение с предыдущей неделей
            prev_week = week_number - 1 if week_number > 1 else 52
            prev_year = year if week_number > 1 else year - 1
            
            prev_stats = await self.db.get_weekly_stats(prev_week, prev_year)
            if prev_stats:
                prev_total = sum(stat.get('total_amount', 0) for stat in prev_stats)
                if prev_total > 0:
                    growth = ((total_weekly - prev_total) / prev_total) * 100
                    growth_emoji = "📈" if growth > 0 else "📉" if growth < 0 else "➡️"
                    report += f"{growth_emoji} **РОСТ К ПРОШЛОЙ НЕДЕЛЕ: {growth:+.1f}%**\n\n"
            
            # Время генерации
            report += f"🕐 Отчет сгенерирован: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            
            return report
            
        except Exception as e:
            logger.error(f"Failed to generate weekly report: {e}")
            return "❌ Ошибка при генерации еженедельного отчета"
    
    async def export_payments_report(self, days: int = 30) -> Optional[str]:
        """Экспорт отчета по платежам в CSV файл"""
        try:
            # Получаем данные за указанный период
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Получаем CSV данные из базы
            csv_data = await self.db.export_payments_csv(
                int(start_date.timestamp()),
                int(end_date.timestamp())
            )
            
            if not csv_data:
                logger.warning("No payment data found for CSV export")
                return None
            
            # Создаем временный файл
            temp_fd, temp_path = tempfile.mkstemp(suffix='.csv', prefix='neuroflow_payments_')
            
            try:
                # Записываем CSV данные в файл
                with open(temp_path, 'w', encoding='utf-8-sig', newline='') as f:
                    f.write(csv_data)
                
                logger.info(f"CSV report exported to: {temp_path}")
                return temp_path
                
            except Exception as e:
                # Если ошибка при записи, удаляем временный файл
                try:
                    import os
                    os.close(temp_fd)
                    os.unlink(temp_path)
                except:
                    pass
                raise e
            
        except Exception as e:
            logger.error(f"Failed to export CSV report: {e}")
            return None
    
    async def get_user_analytics(self, user_id: int) -> Dict[str, Any]:
        """Получить аналитику по конкретному пользователю"""
        try:
            # Получаем информацию о пользователе
            user = await self.db.get_user(user_id)
            if not user:
                return {}
            
            # Получаем транзакции пользователя
            transactions = await self.db.get_user_transactions(user_id)
            
            # Подсчитываем статистику
            total_spent = sum(t.get('amount', 0) for t in transactions if t.get('status') == 'completed')
            transaction_count = len([t for t in transactions if t.get('status') == 'completed'])
            
            # Получаем настройки пользователя
            settings = await self.db.get_user_settings(user_id)
            
            analytics = {
                'user_id': user_id,
                'registration_date': user.get('created_at'),
                'subscription_status': 'active' if await self.db.is_subscription_active(user_id) else 'inactive',
                'subscription_expiry': user.get('subscription_expiry'),
                'is_lifetime': user.get('is_lifetime', False),
                'total_spent': total_spent,
                'transaction_count': transaction_count,
                'autopost_enabled': settings.get('autopost_enabled', False) if settings else False,
                'images_enabled': settings.get('generate_images', False) if settings else False,
                'last_activity': user.get('last_interaction_date')
            }
            
            return analytics
            
        except Exception as e:
            logger.error(f"Failed to get user analytics for {user_id}: {e}")
            return {}
    
    async def get_system_health(self) -> Dict[str, Any]:
        """Получить информацию о здоровье системы"""
        try:
            health = {
                'timestamp': datetime.now().isoformat(),
                'database': 'unknown',
                'redis': 'unknown',
                'api_pool': 'unknown'
            }
            
            # Проверяем PostgreSQL
            try:
                async with self.db.get_connection() as conn:
                    await conn.fetchval('SELECT 1')
                health['database'] = 'healthy'
            except Exception as e:
                health['database'] = f'unhealthy: {str(e)}'
            
            # Проверяем Redis
            try:
                from app.services.redis_cache import redis_cache
                await redis_cache.ping()
                health['redis'] = 'healthy'
            except Exception as e:
                health['redis'] = f'unhealthy: {str(e)}'
            
            # Проверяем API Pool
            try:
                from app.services.api_pool_manager import ultra_api_pool
                status = await ultra_api_pool.get_pool_status()
                if status['available_keys'] > 0:
                    health['api_pool'] = f"healthy ({status['available_keys']}/{status['total_keys']} keys)"
                else:
                    health['api_pool'] = 'degraded (no available keys)'
            except Exception as e:
                health['api_pool'] = f'unhealthy: {str(e)}'
            
            return health
            
        except Exception as e:
            logger.error(f"Failed to get system health: {e}")
            return {'error': str(e)}


# Глобальный экземпляр сервиса
analytics_service = AnalyticsService()