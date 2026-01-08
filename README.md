# NeuroFlow - AI Telegram Bot

🧠 Мощный AI-ассистент для Telegram с генерацией контента, изображений и автоматизацией задач.

## 🚀 Быстрая установка

### Автоматическая установка одной командой:

```bash
curl -sSL https://raw.githubusercontent.com/your-username/neuroflow/main/install.sh | bash
```

### Или клонирование репозитория:

```bash
git clone https://github.com/your-username/neuroflow.git
cd neuroflow
chmod +x install.sh
./install.sh
```

## ✨ Возможности

- 🤖 **Генерация текстов** с помощью Groq AI
- 🎨 **Создание изображений** по описанию
- 📊 **Автопостинг** в каналы Telegram
- 💎 **Система подписок** с гибкими тарифами
- 📈 **Аналитика** и статистика использования
- 🌐 **WebApp** интерфейс для удобного управления
- 🔒 **Безопасность** и защита данных

## 📋 Требования

- Ubuntu/Debian сервер
- Python 3.8+
- 1GB RAM (рекомендуется 2GB)
- 10GB свободного места

## 🔧 Конфигурация

После установки отредактируйте файл `.env`:

```bash
nano /opt/neuroflow/.env
```

Основные параметры:
- `BOT_TOKEN` - токен вашего Telegram бота
- `ADMIN_USER_ID` - ваш Telegram ID
- `GROQ_API_KEY` - API ключ для Groq
- `WEBAPP_URL` - URL вашего WebApp

## 🎮 Управление

### Systemd сервис:
```bash
# Запуск
systemctl start neuroflow

# Остановка
systemctl stop neuroflow

# Статус
systemctl status neuroflow

# Логи
journalctl -u neuroflow -f
```

### Скрипты:
```bash
cd /opt/neuroflow

# Запуск
./start.sh

# Остановка
./stop.sh

# Обновление
./update.sh
```

## 🌐 WebApp

После установки WebApp будет доступен по адресу:
- http://YOUR_SERVER_IP
- Интегрирован в Telegram бота

## 📊 Структура проекта

```
/opt/neuroflow/
├── bot.py              # Основной файл бота
├── .env                # Конфигурация
├── requirements.txt    # Python зависимости
├── webapp/
│   └── index.html     # WebApp интерфейс
├── logs/              # Логи
├── venv/              # Виртуальное окружение
├── start.sh           # Скрипт запуска
├── stop.sh            # Скрипт остановки
└── update.sh          # Скрипт обновления
```

## 🔐 Безопасность

- Все API ключи хранятся в `.env` файле
- Виртуальное окружение Python
- Systemd сервис с автоперезапуском
- Логирование всех операций

## 📞 Поддержка

- 📧 Email: support@neuroflow.com
- 💬 Telegram: @neuroflow_support
- 🐛 Issues: GitHub Issues
- 📖 Документация: Wiki

## 📄 Лицензия

MIT License - см. файл [LICENSE](LICENSE)

## 🤝 Участие в разработке

1. Fork репозитория
2. Создайте feature branch
3. Commit изменения
4. Push в branch
5. Создайте Pull Request

## 📈 Статистика

- ⭐ GitHub Stars
- 🍴 Forks
- 📦 Releases
- 👥 Contributors

---

**NeuroFlow** - Делаем AI доступным для всех! 🚀