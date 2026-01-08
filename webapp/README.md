# 🤖 NeuroFlow Unified Mini App

**Интегрированное Telegram Mini App для проекта NeuroFlow**

## 🎯 Описание

Современное веб-приложение с Cyberpunk Dark Mode дизайном, которое предоставляет единый интерфейс для пользователей и администраторов NeuroFlow. Приложение автоматически определяет роль пользователя и показывает соответствующий интерфейс.

## ✨ Особенности

### 🎨 Дизайн
- **Cyberpunk Dark Mode** с неоновыми акцентами
- **Стеклянные карточки** с backdrop-blur эффектами
- **Адаптивный дизайн** для iPhone и Android
- **Плавные анимации** и переходы
- **Градиентные элементы** и свечение

### 🔐 Безопасность
- **Валидация подписи Telegram** с HMAC-SHA256
- **Проверка времени авторизации** (не старше 24 часов)
- **Разделение ролей** на уровне API
- **Защита от подделки данных**

### 📱 User Dashboard
- **Статус подписки** с цветовой индикацией
- **Управление автопилотом** с настройкой частоты
- **Статистика использования** (тексты, изображения, дни подписки)
- **Быстрые действия** (продление подписки, настройка темы)

### 👑 Admin Dashboard
- **Глобальная статистика** (доходы, новые пользователи, запросы к API)
- **Мониторинг системы** (статус БД и Redis)
- **Управление пользователями** с выдачей Premium
- **Просмотр логов ошибок** в реальном времени

## 🏗️ Архитектура

### Backend (FastAPI)
```
webapp/
├── main.py              # Основное приложение FastAPI
├── requirements.txt     # Python зависимости
├── Dockerfile          # Docker конфигурация
└── test_miniapp.py     # Тесты приложения
```

### Frontend (HTML/Tailwind/JS)
```
webapp/
└── index.html          # Единый файл с полным интерфейсом
```

### Интеграция
- **База данных**: PostgreSQL (та же, что у бота)
- **Кэш**: Redis (тот же пул)
- **Конфигурация**: Общие переменные окружения

## 🚀 Быстрый старт

### Локальная разработка

1. **Установка зависимостей:**
```bash
cd webapp
pip install -r requirements.txt
```

2. **Настройка переменных окружения:**
```bash
# Скопируйте .env из корня проекта или создайте новый
cp ../.env .env

# Убедитесь, что установлены:
BOT_TOKEN=your_bot_token
ADMIN_USER_ID=your_admin_id
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
```

3. **Запуск приложения:**
```bash
python main.py
```

4. **Открытие в браузере:**
```
http://localhost:8080
```

### Docker развертывание

1. **Через docker-compose (рекомендуется):**
```bash
cd deployment
docker-compose up neuroflow_webapp
```

2. **Отдельный контейнер:**
```bash
cd webapp
docker build -t neuroflow-miniapp .
docker run -p 8081:8080 --env-file ../.env neuroflow-miniapp
```

## 🔧 API Endpoints

### Пользовательские данные
```http
GET /api/user_data
Headers: X-Telegram-Init-Data: <telegram_init_data>

Response:
{
  "texts_generated": 42,
  "images_created": 15,
  "subscription_days_left": 25,
  "subscription_status": "Premium",
  "autopilot_status": true,
  "autopilot_topic": "Технологии и ИИ",
  "autopilot_frequency": 3
}
```

### Админ статистика
```http
GET /api/admin_stats
Headers: X-Telegram-Init-Data: <admin_init_data>

Response:
{
  "revenue_24h": 15000.0,
  "new_users_24h": 25,
  "groq_requests_24h": 1500,
  "total_users": 5000,
  "active_subscriptions": 1200,
  "db_status": "online",
  "redis_status": "online",
  "recent_users": [...],
  "recent_errors": [...]
}
```

### Выдача Premium
```http
POST /api/admin/grant_premium/{user_id}?days=30
Headers: X-Telegram-Init-Data: <admin_init_data>

Response:
{
  "success": true,
  "message": "Premium granted for 30 days"
}
```

## 🎨 Дизайн система

### Цветовая палитра
```css
--cyber-black: #0a0a0a      /* Основной фон */
--cyber-dark: #1a1a1a       /* Темные элементы */
--cyber-blue: #00d4ff       /* Неоновый синий */
--cyber-blue-dark: #0099cc  /* Темный синий */
--cyber-purple: #8b5cf6     /* Фиолетовый акцент */
--cyber-green: #00ff88      /* Зеленый (успех) */
--cyber-red: #ff4757        /* Красный (ошибка) */
```

### Компоненты
- **Glass Cards**: `backdrop-filter: blur(10px)`
- **Cyber Buttons**: Градиентные кнопки с hover эффектами
- **Status Indicators**: Цветные индикаторы с свечением
- **Loading Spinner**: Анимированный спиннер

## 🧪 Тестирование

### Автоматические тесты
```bash
cd webapp
python test_miniapp.py
```

**Тесты включают:**
- ✅ Валидация конфигурации
- ✅ Проверка HTML структуры
- ✅ Тестирование API endpoints
- ✅ Проверка безопасности

### Ручное тестирование

1. **Пользовательский интерфейс:**
   - Откройте приложение как обычный пользователь
   - Проверьте отображение статистики
   - Протестируйте переключение настроек автопилота

2. **Админ интерфейс:**
   - Войдите как администратор (ADMIN_USER_ID)
   - Проверьте админ статистику
   - Протестируйте выдачу Premium подписки

## 🔒 Безопасность

### Валидация Telegram данных
```python
def validate_telegram_data(init_data: str) -> Optional[Dict]:
    # 1. Парсинг init_data
    # 2. Извлечение hash
    # 3. Создание секретного ключа из BOT_TOKEN
    # 4. Вычисление HMAC-SHA256
    # 5. Сравнение с полученным hash
    # 6. Проверка времени авторизации
```

### Защита API
- **Обязательная авторизация** для всех endpoints
- **Проверка ролей** на уровне сервера
- **Валидация входных данных** с Pydantic
- **Логирование всех действий**

## 📊 Мониторинг

### Логирование
```python
# Все действия логируются
logger.info(f"User {user_id} accessed dashboard")
logger.info(f"Admin {admin_id} granted premium to {target_id}")
logger.error(f"API error: {error}")
```

### Метрики
- **Время отклика API** (<100ms)
- **Статус систем** (БД, Redis)
- **Активность пользователей**
- **Ошибки в реальном времени**

## 🔄 Интеграция с ботом

### Общие ресурсы
- **База данных**: PostgreSQL с тем же пулом соединений
- **Кэш**: Redis с общими ключами
- **Конфигурация**: Единые переменные окружения
- **Логи**: Общая система логирования

### Синхронизация данных
- **Реальное время**: Данные обновляются каждые 30 секунд
- **Консистентность**: Использование транзакций БД
- **Кэширование**: Умное кэширование часто запрашиваемых данных

## 🚀 Развертывание в продакшене

### Через Docker Compose
```yaml
# В deployment/docker-compose.yml уже настроено
neuroflow_webapp:
  build: ../webapp
  ports:
    - "8081:8080"
  environment:
    - BOT_TOKEN=${BOT_TOKEN}
    - ADMIN_USER_ID=${ADMIN_USER_ID}
    - DATABASE_URL=postgresql://...
```

### Настройка Telegram Bot
```python
# В боте добавьте кнопку для Mini App
from aiogram.types import WebAppInfo, InlineKeyboardButton

webapp_button = InlineKeyboardButton(
    text="🚀 Открыть приложение",
    web_app=WebAppInfo(url="https://your-domain.com")
)
```

### Nginx конфигурация
```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 📱 Использование в Telegram

1. **Добавьте кнопку в бот:**
   ```python
   webapp_button = InlineKeyboardButton(
       text="🚀 Панель управления",
       web_app=WebAppInfo(url="https://your-domain.com")
   )
   ```

2. **Пользователи нажимают кнопку**
3. **Telegram открывает Mini App**
4. **Автоматическое определение роли**
5. **Показ соответствующего интерфейса**

## 🛠️ Разработка

### Структура кода
```
webapp/
├── main.py              # FastAPI приложение
│   ├── validate_telegram_data()  # Валидация Telegram
│   ├── get_current_user()        # Получение пользователя
│   ├── get_user_data()           # API пользователя
│   ├── get_admin_stats()         # API админа
│   └── grant_premium()           # Выдача Premium
├── index.html           # Frontend приложение
│   ├── initApp()                 # Инициализация
│   ├── loadUserData()            # Загрузка данных
│   ├── loadAdminData()           # Админ данные
│   └── switchTab()               # Переключение табов
└── test_miniapp.py      # Тесты
```

### Добавление новых функций

1. **Backend (FastAPI):**
```python
@app.get("/api/new_endpoint")
async def new_endpoint(user: TelegramInitData = Depends(get_current_user)):
    # Ваша логика
    return {"result": "success"}
```

2. **Frontend (JavaScript):**
```javascript
async function loadNewData() {
    const data = await apiRequest('/api/new_endpoint');
    // Обновление интерфейса
}
```

## 📞 Поддержка

### Логи и отладка
```bash
# Просмотр логов
docker logs neuroflow_webapp

# Отладка в реальном времени
docker logs -f neuroflow_webapp
```

### Частые проблемы

1. **Ошибка валидации Telegram:**
   - Проверьте BOT_TOKEN
   - Убедитесь, что приложение запущено из Telegram

2. **Ошибка подключения к БД:**
   - Проверьте DATABASE_URL
   - Убедитесь, что PostgreSQL запущен

3. **Админ панель недоступна:**
   - Проверьте ADMIN_USER_ID
   - Убедитесь, что вы входите с правильного аккаунта

## 🎉 Заключение

NeuroFlow Mini App предоставляет современный, безопасный и функциональный интерфейс для управления ботом. Cyberpunk дизайн создает уникальный пользовательский опыт, а разделение ролей обеспечивает гибкость использования.

**Готово к продакшену!** 🚀