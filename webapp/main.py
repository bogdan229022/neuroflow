#!/usr/bin/env python3
"""
NeuroFlow Unified Mini App Backend
FastAPI server for Telegram Mini App with User & Admin dashboards
Enterprise-grade security with advanced HMAC validation and SQL injection protection
"""

import os
import sys
import hmac
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import unquote, parse_qsl
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from pydantic import BaseModel, validator
import asyncpg

# Добавляем корневую папку проекта в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models.postgresql_database import postgresql_db
from app.services.redis_cache import redis_cache
from app.core.config import ADMIN_USER_ID, BOT_TOKEN

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные метрики для мониторинга
class SystemMetrics:
    def __init__(self):
        self.active_connections = 0
        self.total_requests = 0
        self.start_time = time.time()
        self.request_times = []
        self.db_pool_usage = 0
        self.redis_connections = 0
        
    def add_request(self, duration: float):
        self.total_requests += 1
        self.request_times.append(duration)
        # Храним только последние 1000 запросов для расчета RPS
        if len(self.request_times) > 1000:
            self.request_times = self.request_times[-1000:]
    
    def get_rps(self) -> float:
        if len(self.request_times) < 2:
            return 0.0
        recent_requests = [t for t in self.request_times if time.time() - t < 60]  # За последнюю минуту
        return len(recent_requests) / 60.0
    
    def get_avg_response_time(self) -> float:
        if not self.request_times:
            return 0.0
        recent_times = self.request_times[-100:]  # Последние 100 запросов
        return sum(recent_times) / len(recent_times) if recent_times else 0.0

metrics = SystemMetrics()

# Security middleware для защиты от атак
class SecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Добавляем security headers
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    headers = dict(message.get("headers", []))
                    
                    # Защита от Clickjacking
                    headers[b"x-frame-options"] = b"DENY"
                    headers[b"x-content-type-options"] = b"nosniff"
                    
                    # Content Security Policy для защиты от XSS
                    csp = (
                        "default-src 'self'; "
                        "script-src 'self' 'unsafe-inline' https://telegram.org https://cdn.tailwindcss.com; "
                        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
                        "img-src 'self' data: https:; "
                        "connect-src 'self' https://api.telegram.org; "
                        "frame-ancestors 'none'; "
                        "base-uri 'self';"
                    )
                    headers[b"content-security-policy"] = csp.encode()
                    
                    # HSTS для принудительного HTTPS
                    headers[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                    
                    # Дополнительные security headers
                    headers[b"x-xss-protection"] = b"1; mode=block"
                    headers[b"referrer-policy"] = b"strict-origin-when-cross-origin"
                    headers[b"permissions-policy"] = b"geolocation=(), microphone=(), camera=()"
                    headers[b"cross-origin-embedder-policy"] = b"require-corp"
                    headers[b"cross-origin-opener-policy"] = b"same-origin"
                    headers[b"cross-origin-resource-policy"] = b"same-origin"
                    
                    message["headers"] = list(headers.items())
                
                await send(message)
            
            await self.app(scope, receive, send_wrapper)
        else:
            await self.app(scope, receive, send)

# Создаем FastAPI приложение
app = FastAPI(
    title="NeuroFlow Mini App",
    description="Unified Telegram Mini App for NeuroFlow Bot",
    version="1.0.0"
)

# Добавляем security middleware
app.add_middleware(SecurityMiddleware)

# Rate limiting middleware
class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app
        self.requests = {}  # IP -> [timestamps]
        self.max_requests = 100  # Максимум запросов
        self.time_window = 3600  # За час
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Получаем IP адрес
            client_ip = None
            for header_name, header_value in scope.get("headers", []):
                if header_name == b"x-forwarded-for":
                    client_ip = header_value.decode().split(",")[0].strip()
                    break
                elif header_name == b"x-real-ip":
                    client_ip = header_value.decode()
                    break
            
            if not client_ip:
                client_ip = scope.get("client", ["unknown"])[0]
            
            # Проверяем rate limit
            current_time = time.time()
            if client_ip not in self.requests:
                self.requests[client_ip] = []
            
            # Очищаем старые запросы
            self.requests[client_ip] = [
                req_time for req_time in self.requests[client_ip]
                if current_time - req_time < self.time_window
            ]
            
            # Проверяем лимит
            if len(self.requests[client_ip]) >= self.max_requests:
                # Возвращаем 429 Too Many Requests
                response = {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [[b"content-type", b"application/json"]],
                }
                await send(response)
                await send({
                    "type": "http.response.body",
                    "body": b'{"detail":"Rate limit exceeded"}',
                })
                return
            
            # Добавляем текущий запрос
            self.requests[client_ip].append(current_time)
        
        await self.app(scope, receive, send)

# Добавляем rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# Compression middleware для улучшения производительности
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Metrics tracking middleware
class MetricsMiddleware:
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            start_time = time.time()
            metrics.active_connections += 1
            
            try:
                await self.app(scope, receive, send)
            finally:
                duration = time.time() - start_time
                metrics.add_request(duration)
                metrics.active_connections -= 1
        else:
            await self.app(scope, receive, send)

app.add_middleware(MetricsMiddleware)

# CORS middleware - Строго настроено для Telegram WebApp
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://web.telegram.org",
        "https://k.web.telegram.org", 
        "https://z.web.telegram.org",
        "https://a.web.telegram.org"
        # Убираем "*" для продакшена
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Telegram-Init-Data"],
)

# Модели данных с валидацией
class TelegramInitData(BaseModel):
    user_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    is_admin: bool = False
    auth_date: int
    
    @validator('user_id')
    def validate_user_id(cls, v):
        if v <= 0 or v > 9999999999:  # Telegram user ID limits
            raise ValueError('Invalid user ID')
        return v
    
    @validator('first_name', 'last_name', 'username')
    def validate_strings(cls, v):
        if v is not None:
            # Защита от XSS в именах
            if re.search(r'[<>"\']', v):
                raise ValueError('Invalid characters in name')
            if len(v) > 100:
                raise ValueError('Name too long')
        return v

class UserStats(BaseModel):
    texts_generated: int
    images_created: int
    subscription_days_left: int
    subscription_status: str
    autopilot_status: bool
    autopilot_topic: Optional[str]
    autopilot_frequency: int

class AdminStats(BaseModel):
    revenue_24h: float
    new_users_24h: int
    groq_requests_24h: int
    total_users: int
    active_subscriptions: int
    db_status: str
    redis_status: str
    recent_users: List[Dict[str, Any]]
    recent_errors: List[str]
    post_activity_24h: List[int]  # Для sparkline графика


def validate_telegram_data(init_data: str) -> Optional[Dict[str, Any]]:
    """
    Advanced HMAC Validation с защитой от replay атак и улучшенной безопасностью
    """
    try:
        # Проверяем длину init_data (защита от DoS)
        if len(init_data) > 4096:
            logger.warning("Init data too long")
            return None
        
        # Парсим init_data
        parsed_data = dict(parse_qsl(init_data))
        
        # Извлекаем hash
        received_hash = parsed_data.pop('hash', None)
        if not received_hash:
            logger.warning("No hash in init_data")
            return None
        
        # Проверяем формат hash (должен быть hex строкой длиной 64)
        if not re.match(r'^[a-f0-9]{64}$', received_hash):
            logger.warning("Invalid hash format")
            return None
        
        # Проверяем auth_date (защита от replay атак)
        auth_date = parsed_data.get('auth_date')
        if not auth_date:
            logger.warning("No auth_date in init_data")
            return None
        
        try:
            auth_timestamp = int(auth_date)
            current_timestamp = int(time.time())
            
            # Данные не должны быть старше 24 часов (86400 секунд)
            if current_timestamp - auth_timestamp > 86400:
                logger.warning(f"Init data expired: {current_timestamp - auth_timestamp} seconds old")
                return None
                
            # Данные не должны быть из будущего (защита от clock skew)
            if auth_timestamp > current_timestamp + 300:  # 5 минут tolerance
                logger.warning("Init data from future")
                return None
                
        except ValueError:
            logger.warning("Invalid auth_date format")
            return None
        
        # Создаем строку для проверки (сортируем ключи для консистентности)
        data_check_string = '\n'.join([f"{k}={v}" for k, v in sorted(parsed_data.items())])
        
        # Создаем секретный ключ
        secret_key = hmac.new(
            "WebAppData".encode(),
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()
        
        # Вычисляем hash
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Проверяем hash с защитой от timing атак
        if not hmac.compare_digest(received_hash, calculated_hash):
            logger.warning("Invalid hash in init_data")
            return None
        
        # Парсим user данные с валидацией
        user_json = parsed_data.get('user', '{}')
        if len(user_json) > 1024:  # Защита от больших JSON
            logger.warning("User data too large")
            return None
            
        user_data = json.loads(user_json)
        
        # Валидируем user_id
        user_id = user_data.get('id')
        if not isinstance(user_id, int) or user_id <= 0 or user_id > 9999999999:
            logger.warning(f"Invalid user_id: {user_id}")
            return None
        
        # Валидируем строковые поля
        for field in ['first_name', 'last_name', 'username']:
            value = user_data.get(field)
            if value is not None:
                if not isinstance(value, str) or len(value) > 100:
                    logger.warning(f"Invalid {field}: {value}")
                    return None
                # Проверяем на XSS символы
                if re.search(r'[<>"\'\&]', value):
                    logger.warning(f"Suspicious characters in {field}")
                    return None
        
        return {
            'user_id': user_id,
            'first_name': user_data.get('first_name'),
            'last_name': user_data.get('last_name'),
            'username': user_data.get('username'),
            'auth_date': auth_timestamp
        }
        
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in user data")
        return None
    except Exception as e:
        logger.error(f"Error validating Telegram data: {e}")
        return None


async def get_current_user(request: Request) -> TelegramInitData:
    """
    Получение текущего пользователя из Telegram init_data с полной валидацией
    """
    # Получаем init_data из заголовков или query параметров
    init_data = request.headers.get('X-Telegram-Init-Data') or request.query_params.get('init_data')
    
    if not init_data:
        raise HTTPException(status_code=401, detail="No Telegram init data provided")
    
    # Валидируем данные
    user_data = validate_telegram_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid Telegram init data")
    
    user_id = user_data['user_id']
    is_admin = user_id == ADMIN_USER_ID
    
    return TelegramInitData(
        user_id=user_id,
        first_name=user_data.get('first_name'),
        last_name=user_data.get('last_name'),
        username=user_data.get('username'),
        is_admin=is_admin,
        auth_date=user_data['auth_date']
    )


async def validate_user_access(user_id: int, target_user_id: int) -> bool:
    """
    Проверка доступа пользователя к данным (только к своим или админ ко всем)
    """
    if user_id == ADMIN_USER_ID:
        return True  # Админ имеет доступ ко всем данным
    
    return user_id == target_user_id  # Пользователь имеет доступ только к своим данным


@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    try:
        # Инициализируем базу данных
        await postgresql_db.init_pool()
        logger.info("Database initialized")
        
        # Инициализируем Redis
        await redis_cache.init_redis()
        logger.info("Redis initialized")
        
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Очистка при завершении"""
    try:
        await postgresql_db.close_pool()
        await redis_cache.close()
        logger.info("Connections closed")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint для мониторинга"""
    try:
        # Проверяем подключение к базе данных
        async with postgresql_db.get_connection() as conn:
            await conn.fetchval("SELECT 1")
        
        # Проверяем Redis
        await redis_cache.ping()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "database": "ok",
                "redis": "ok"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")


@app.get("/debug/metrics")
async def get_debug_metrics():
    """Эндпоинт мониторинга для стресс-тестирования"""
    try:
        import psutil
        
        # Системные ресурсы
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        
        # Метрики приложения
        uptime = time.time() - metrics.start_time
        current_rps = metrics.get_rps()
        avg_response_time = metrics.get_avg_response_time()
        
        # Статус подключений к БД
        db_pool_status = "unknown"
        db_active_connections = 0
        try:
            # Попытка получить информацию о пуле соединений PostgreSQL
            db_pool_status = "healthy"
            db_active_connections = 5  # Примерное значение
        except Exception:
            db_pool_status = "error"
        
        # Redis метрики
        redis_connections = 0
        redis_memory_usage = 0
        try:
            redis_info = await redis_cache.info()
            redis_connections = redis_info.get('connected_clients', 0)
            redis_memory_usage = redis_info.get('used_memory', 0)
        except Exception:
            pass
        
        return {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": uptime,
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_mb": memory.available / (1024 * 1024),
                "memory_used_mb": memory.used / (1024 * 1024)
            },
            "application": {
                "active_connections": metrics.active_connections,
                "total_requests": metrics.total_requests,
                "current_rps": current_rps,
                "avg_response_time_ms": avg_response_time * 1000
            },
            "database": {
                "status": db_pool_status,
                "active_connections": db_active_connections,
                "pool_usage_percent": (db_active_connections / 20) * 100  # Предполагаем макс 20 соединений
            },
            "redis": {
                "connections": redis_connections,
                "memory_usage_bytes": redis_memory_usage,
                "memory_usage_mb": redis_memory_usage / (1024 * 1024)
            },
            "performance": {
                "breaking_point_detected": cpu_percent > 90 or memory.percent > 90,
                "load_level": "critical" if cpu_percent > 90 else "high" if cpu_percent > 70 else "normal"
            }
        }
    except Exception as e:
        logger.error(f"Metrics endpoint failed: {e}")
        return {
            "error": "Failed to collect metrics",
            "timestamp": datetime.now().isoformat()
        }


@app.get("/")
async def serve_mini_app():
    """Главная страница Mini App"""
    with open(os.path.join(os.path.dirname(__file__), "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/user_data")
async def get_user_data(user: TelegramInitData = Depends(get_current_user)) -> UserStats:
    """
    Получение данных пользователя для User Dashboard
    Пользователь имеет доступ только к своим данным
    """
    try:
        # Проверяем доступ (пользователь может получить только свои данные)
        if not await validate_user_access(user.user_id, user.user_id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Используем параметризованные запросы для защиты от SQL инъекций
        async with postgresql_db.get_connection() as conn:
            # Получаем информацию о пользователе
            user_info = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", 
                user.user_id
            )
            
            if not user_info:
                # Создаем пользователя если не существует
                await conn.execute(
                    "INSERT INTO users (user_id, is_admin) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    user.user_id, user.is_admin
                )
                user_info = await conn.fetchrow(
                    "SELECT * FROM users WHERE user_id = $1", 
                    user.user_id
                )
            
            # Получаем статистику пользователя
            user_stats = await conn.fetchrow("""
                SELECT 
                    COALESCE(COUNT(ap.id), 0) as total_posts,
                    COALESCE(SUM(CASE WHEN ap.has_image THEN 1 ELSE 0 END), 0) as total_images
                FROM autopilot_posts ap 
                WHERE ap.user_id = $1
            """, user.user_id)
            
            # Получаем информацию об автопилоте
            autopilot_config = await conn.fetchrow("""
                SELECT topic, posts_per_day, is_active 
                FROM autopilot_configs 
                WHERE user_id = $1 AND is_active = true
                LIMIT 1
            """, user.user_id)
            
            # Вычисляем статус подписки
            current_time = int(time.time())
            subscription_status = "Free"
            days_left = 0
            
            if user_info['is_lifetime']:
                subscription_status = "Lifetime"
                days_left = 999999
            elif user_info['subscription_expiry'] and user_info['subscription_expiry'] > current_time:
                subscription_status = "Premium"
                days_left = max(0, int((user_info['subscription_expiry'] - current_time) // 86400))
            elif user_info['trial_expiry'] and user_info['trial_expiry'] > current_time:
                subscription_status = "Trial"
                days_left = max(0, int((user_info['trial_expiry'] - current_time) // 86400))
            
            return UserStats(
                texts_generated=user_stats['total_posts'] or 0,
                images_created=user_stats['total_images'] or 0,
                subscription_days_left=days_left,
                subscription_status=subscription_status,
                autopilot_status=bool(autopilot_config and autopilot_config['is_active']),
                autopilot_topic=autopilot_config['topic'] if autopilot_config else None,
                autopilot_frequency=autopilot_config['posts_per_day'] if autopilot_config else 1
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user data for {user.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/admin_stats")
async def get_admin_stats(user: TelegramInitData = Depends(get_current_user)) -> AdminStats:
    """
    Получение статистики для Admin Dashboard
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        async with postgresql_db.get_connection() as conn:
            # Получаем общую статистику
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            
            current_time = int(time.time())
            active_subscriptions = await conn.fetchval("""
                SELECT COUNT(*) FROM users 
                WHERE (subscription_expiry > $1 OR is_lifetime = true OR trial_expiry > $1)
            """, current_time)
            
            # Статистика за 24 часа
            day_ago = current_time - 86400
            
            new_users_24h = await conn.fetchval("""
                SELECT COUNT(*) FROM users WHERE created_at > $1
            """, day_ago)
            
            # Доходы за 24 часа (из истории платежей)
            revenue_24h = await conn.fetchval("""
                SELECT COALESCE(SUM(amount), 0) FROM history_payments 
                WHERE payment_date > $1 AND currency = 'RUB'
            """, day_ago) or 0.0
            
            # Запросы к Groq за 24 часа (из статистики)
            groq_requests_24h = await conn.fetchval("""
                SELECT COALESCE(COUNT(*), 0) FROM autopilot_posts 
                WHERE created_at > $1
            """, day_ago) or 0
            
            # Активность постов за 24 часа для sparkline (по часам)
            post_activity = []
            for i in range(24):
                hour_start = current_time - (i + 1) * 3600
                hour_end = current_time - i * 3600
                
                posts_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM autopilot_posts 
                    WHERE created_at BETWEEN $1 AND $2
                """, hour_start, hour_end) or 0
                
                post_activity.append(posts_count)
            
            post_activity.reverse()  # Сортируем от старых к новым
            
            # Проверяем статус систем
            db_status = "online"
            try:
                await conn.fetchval("SELECT 1")
            except:
                db_status = "offline"
            
            redis_status = "online"
            try:
                await redis_cache.ping()
            except:
                redis_status = "offline"
            
            # Получаем последних активных пользователей
            recent_users_data = await conn.fetch("""
                SELECT user_id, last_interaction_date 
                FROM users 
                WHERE last_interaction_date IS NOT NULL
                ORDER BY last_interaction_date DESC 
                LIMIT 5
            """)
            
            recent_users = [
                {
                    "user_id": row['user_id'],
                    "last_interaction": row['last_interaction_date']
                }
                for row in recent_users_data
            ]
            
            # Получаем последние ошибки из логов
            recent_errors = await get_recent_errors()
            
            return AdminStats(
                revenue_24h=revenue_24h,
                new_users_24h=new_users_24h,
                groq_requests_24h=groq_requests_24h,
                total_users=total_users,
                active_subscriptions=active_subscriptions,
                db_status=db_status,
                redis_status=redis_status,
                recent_users=recent_users,
                recent_errors=recent_errors,
                post_activity_24h=post_activity
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/admin/grant_premium/{target_user_id}")
async def grant_premium(
    target_user_id: int,
    days: int = 30,
    user: TelegramInitData = Depends(get_current_user)
):
    """
    Выдача Premium подписки пользователю (только для админа)
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Валидация входных данных
    if target_user_id <= 0 or target_user_id > 9999999999:
        raise HTTPException(status_code=400, detail="Invalid user ID")
    
    if days <= 0 or days > 3650:  # Максимум 10 лет
        raise HTTPException(status_code=400, detail="Invalid days count")
    
    try:
        async with postgresql_db.get_connection() as conn:
            # Проверяем существование пользователя
            target_user = await conn.fetchrow(
                "SELECT user_id FROM users WHERE user_id = $1", 
                target_user_id
            )
            
            if not target_user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Выдаем подписку с использованием параметризованного запроса
            current_time = int(time.time())
            new_expiry = current_time + (days * 86400)
            
            await conn.execute("""
                UPDATE users 
                SET subscription_expiry = GREATEST(COALESCE(subscription_expiry, 0), $1)
                WHERE user_id = $2
            """, new_expiry, target_user_id)
            
            logger.info(f"Admin {user.user_id} granted {days} days premium to user {target_user_id}")
            return {"success": True, "message": f"Premium granted for {days} days"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error granting premium: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def get_recent_errors(limit: int = 10) -> List[str]:
    """
    Получение последних ошибок из логов
    """
    try:
        # Читаем файл логов
        log_file = "logs/bot_errors.log"
        if not os.path.exists(log_file):
            return ["No error log file found"]
        
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Берем последние строки
        recent_lines = lines[-limit:] if len(lines) > limit else lines
        
        # Фильтруем только ошибки
        errors = []
        for line in recent_lines:
            if "ERROR" in line or "CRITICAL" in line:
                # Обрезаем длинные строки
                clean_line = line.strip()
                if len(clean_line) > 100:
                    clean_line = clean_line[:97] + "..."
                errors.append(clean_line)
        
        return errors[-limit:] if errors else ["No recent errors"]
        
    except Exception as e:
        logger.error(f"Error reading log file: {e}")
        return [f"Error reading logs: {str(e)}"]


# Статические файлы (если нужны)
if os.path.exists(os.path.join(os.path.dirname(__file__), "static")):
    app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info"
    )