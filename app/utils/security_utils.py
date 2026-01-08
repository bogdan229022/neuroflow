"""
Утилиты безопасности для NeuroFlow
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


def sanitize_ai_input(text: str) -> str:
    """
    Санитизация пользовательского ввода для защиты от prompt injection
    """
    if not text:
        return ""
    
    # Удаляем потенциально опасные фразы
    dangerous_patterns = [
        r'ignore\s+previous\s+instructions',
        r'ignore\s+all\s+previous',
        r'system\s+prompt',
        r'api\s+key',
        r'reveal\s+',
        r'you\s+are\s+now\s+',
        r'jailbreak',
        r'dan\s+mode',
        r'developer\s+mode',
        r'admin\s+mode',
        r'root\s+access',
        r'bypass\s+',
        r'override\s+',
        r'execute\s+',
        r'run\s+command',
        r'system\s+command',
        r'</prompt>',
        r'<prompt>',
        r'</system>',
        r'<system>',
        r'\\n\\n',
        r'---',
        r'###'
    ]
    
    cleaned = text
    for pattern in dangerous_patterns:
        cleaned = re.sub(pattern, '[FILTERED]', cleaned, flags=re.IGNORECASE)
    
    # Удаляем множественные переносы строк (попытки разделить промпт)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    
    # Удаляем подозрительные символы
    cleaned = re.sub(r'[<>{}[\]\\]', '', cleaned)
    
    # Ограничиваем длину
    if len(cleaned) > 1000:
        cleaned = cleaned[:1000] + "..."
        logger.warning(f"Input truncated due to length: {len(text)} -> 1000")
    
    return cleaned.strip()


def validate_topic(topic: str) -> Tuple[bool, str]:
    """Валидация темы канала"""
    if not topic:
        return False, "Тема не может быть пустой"
    
    topic = topic.strip()
    
    if len(topic) < 5:
        return False, "Тема слишком короткая (минимум 5 символов)"
    
    if len(topic) > 200:
        return False, "Тема слишком длинная (максимум 200 символов)"
    
    # Проверяем на допустимые символы
    if not re.match(r'^[а-яА-Яa-zA-Z0-9\s\-.,!?()]+$', topic):
        return False, "Тема содержит недопустимые символы"
    
    return True, ""


def validate_prompt(prompt: str) -> Tuple[bool, str]:
    """Валидация системного промпта"""
    if not prompt:
        return False, "Промпт не может быть пустым"
    
    prompt = prompt.strip()
    
    if len(prompt) < 20:
        return False, "Промпт слишком короткий (минимум 20 символов)"
    
    if len(prompt) > 2000:
        return False, "Промпт слишком длинный (максимум 2000 символов)"
    
    return True, ""


def validate_channel_id(channel_id: str) -> Tuple[bool, str]:
    """Валидация ID канала"""
    if not channel_id:
        return False, "ID канала не может быть пустым"
    
    channel_id = channel_id.strip()
    
    # Проверяем формат канала
    if not (channel_id.startswith('@') or channel_id.startswith('-') or channel_id.isdigit()):
        return False, "Неверный формат канала. Используйте @username или ID канала"
    
    return True, ""


def mask_api_key(key: str) -> str:
    """Безопасное маскирование API ключа"""
    if not key or len(key) < 8:
        return "***"
    
    # Показываем только первые и последние 4 символа
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"