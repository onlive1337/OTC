from aiogram.fsm.state import State, StatesGroup

class UserStates(StatesGroup):
    selecting_crypto = State()
    selecting_settings = State()

class AdminStates(StatesGroup):
    waiting_broadcast = State()
