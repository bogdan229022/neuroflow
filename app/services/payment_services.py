"""
Сервисы для работы с платежными системами
"""

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Optional, Dict, Any
import aiohttp

from app.core.config_manager import config_manager

logger = logging.getLogger(__name__)


class AAIOService:
    """Сервис для работы с AAIO (СБП)"""
    
    def __init__(self):
        """Инициализация AAIO Service"""
        self.base_url = "https://aaio.so/api"
    
    async def _get_credentials(self) -> Optional[Dict[str, str]]:
        """Получение актуальных учетных данных AAIO"""
        credentials = await config_manager.get_aaio_keys()
        
        if not all([credentials['api_key'], credentials['shop_id'], credentials['secret_key']]):
            logger.error("AAIO credentials not fully configured")
            return None
        
        return credentials
    
    def _generate_signature(self, params: dict, secret_key: str) -> str:
        """Генерация подписи для AAIO"""
        # Сортируем параметры и создаем строку для подписи
        sorted_params = sorted(params.items())
        sign_string = ":".join([f"{k}:{v}" for k, v in sorted_params if k != 'sign'])
        sign_string += f":{secret_key}"
        
        return hashlib.sha256(sign_string.encode()).hexdigest()
    
    async def create_payment(self, amount: float, order_id: str, description: str, 
                           user_id: int, webhook_url: str) -> Optional[Dict[str, Any]]:
        """Создание платежа через AAIO"""
        try:
            credentials = await self._get_credentials()
            if not credentials:
                return None

            params = {
                'merchant_id': credentials['shop_id'],
                'amount': amount,
                'currency': 'RUB',
                'order_id': order_id,
                'description': description,
                'method': 'sbp',  # Система быстрых платежей
                'webhook_url': webhook_url,
                'success_url': f'https://t.me/your_bot?start=success_{order_id}',
                'fail_url': f'https://t.me/your_bot?start=fail_{order_id}',
                'lang': 'ru'
            }
            
            # Добавляем подпись
            params['sign'] = self._generate_signature(params, credentials['secret_key'])
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/create-pay",
                    json=params,
                    headers={'X-API-KEY': credentials['api_key']}
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"AAIO payment created: {order_id}")
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"AAIO payment creation failed: {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"AAIO payment creation error: {e}")
            return None
    
    async def verify_webhook(self, data: dict) -> bool:
        """Проверка подписи вебхука от AAIO"""
        try:
            credentials = await self._get_credentials()
            if not credentials:
                return False

            received_sign = data.pop('sign', '')
            calculated_sign = self._generate_signature(data, credentials['secret_key'])
            return hmac.compare_digest(received_sign, calculated_sign)
        except Exception as e:
            logger.error(f"AAIO webhook verification error: {e}")
            return False


class CryptoBotService:
    """Сервис для работы с CryptoBot API"""
    
    def __init__(self):
        """Инициализация CryptoBot Service"""
        self.base_url = "https://pay.crypt.bot/api"
    
    async def _get_token(self) -> Optional[str]:
        """Получение актуального токена CryptoBot"""
        token = await config_manager.get_crypto_token()
        if not token:
            logger.error("CryptoBot token not configured")
        return token
    
    async def create_invoice(self, amount: float, currency: str, description: str,
                           payload: str) -> Optional[Dict[str, Any]]:
        """Создание инвойса в CryptoBot"""
        try:
            token = await self._get_token()
            if not token:
                return None

            params = {
                'currency_type': 'crypto',
                'asset': currency,
                'amount': str(amount),
                'description': description,
                'payload': payload,
                'paid_btn_name': 'callback',
                'paid_btn_url': f'https://t.me/your_bot?start=crypto_success'
            }
            
            headers = {
                'Crypto-Pay-API-Token': token,
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/createInvoice",
                    json=params,
                    headers=headers
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        if data.get('ok'):
                            logger.info(f"CryptoBot invoice created: {payload}")
                            return data['result']
                        else:
                            logger.error(f"CryptoBot API error: {data}")
                            return None
                    else:
                        error_text = await response.text()
                        logger.error(f"CryptoBot invoice creation failed: {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"CryptoBot invoice creation error: {e}")
            return None
    
    async def get_invoice(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации об инвойсе"""
        try:
            token = await self._get_token()
            if not token:
                return None

            headers = {
                'Crypto-Pay-API-Token': token
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/getInvoices",
                    params={'invoice_ids': invoice_id},
                    headers=headers
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        if data.get('ok') and data.get('result', {}).get('items'):
                            return data['result']['items'][0]
                    
                    return None
                    
        except Exception as e:
            logger.error(f"CryptoBot get invoice error: {e}")
            return None
    
    async def get_exchange_rates(self) -> Optional[Dict[str, float]]:
        """Получение курсов валют"""
        try:
            token = await self._get_token()
            if not token:
                return None

            headers = {
                'Crypto-Pay-API-Token': token
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/getExchangeRates",
                    headers=headers
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        if data.get('ok'):
                            rates = {}
                            for rate in data['result']:
                                if rate['target'] == 'USD':
                                    rates[rate['source']] = float(rate['rate'])
                            return rates
                    
                    return None
                    
        except Exception as e:
            logger.error(f"CryptoBot exchange rates error: {e}")
            return None
    
    async def verify_webhook(self, token: str, data: dict) -> bool:
        """Проверка подписи вебхука от CryptoBot"""
        try:
            expected_token = await self._get_token()
            if not expected_token:
                return False
            return token == expected_token
        except Exception as e:
            logger.error(f"CryptoBot webhook verification error: {e}")
            return False


# Глобальные экземпляры сервисов
aaio_service = AAIOService()
crypto_service = CryptoBotService()