from aiogram.fsm.state import State, StatesGroup


class SettingsStates(StatesGroup):
    waiting_for_channel_id = State()
    waiting_for_topic = State()
    waiting_for_system_instruction = State()


class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_subscription_days = State()
    waiting_for_week_number = State()
    waiting_for_broadcast_message = State()
    waiting_for_broadcast_buttons = State()
    # Autopilot pricing management states
    waiting_for_autopilot_rate_name = State()
    waiting_for_autopilot_rate_desc = State()
    waiting_for_autopilot_rate_price_rub = State()
    waiting_for_autopilot_rate_price_usd = State()
    waiting_for_autopilot_rate_price_stars = State()
    waiting_for_autopilot_edit_value = State()
    # Instruction URL management state
    waiting_for_instruction_url = State()


class APIConfigStates(StatesGroup):
    waiting_for_groq_key = State()
    waiting_for_crypto_token = State()
    waiting_for_aaio_api_key = State()
    waiting_for_aaio_shop_id = State()
    waiting_for_aaio_secret_key = State()


class AutopilotStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_topic = State()
    waiting_for_tone = State()
    waiting_for_frequency = State()
    waiting_for_keywords = State()