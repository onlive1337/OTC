from aiogram.filters.callback_data import CallbackData


class UserCurrenciesCB(CallbackData, prefix="ucur"):
    page: int


class UserToggleCurrencyCB(CallbackData, prefix="utcur"):
    currency: str
    page: int


class UserToggleCryptoCB(CallbackData, prefix="utcry"):
    symbol: str


class UserLangCB(CallbackData, prefix="ulang"):
    lang: str


class UserFormatCB(CallbackData, prefix="ufmt"):
    fmt: str


class ChatSettingsActionCB(CallbackData, prefix="cact"):
    chat_id: int
    action: str


class ChatCurrenciesCB(CallbackData, prefix="ccur"):
    chat_id: int
    page: int


class ChatToggleCurrencyCB(CallbackData, prefix="ctcur"):
    chat_id: int
    currency: str
    page: int


class ChatToggleCryptoCB(CallbackData, prefix="ctcry"):
    chat_id: int
    symbol: str


class ChatLangCB(CallbackData, prefix="clang"):
    chat_id: int
    lang: str


class ChatFormatCB(CallbackData, prefix="cfmt"):
    chat_id: int
    fmt: str
