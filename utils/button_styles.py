from enum import Enum
from aiogram.types import InlineKeyboardButton


class ButtonStyle(str, Enum):
    PRIMARY = "primary"
    SUCCESS = "success"
    DANGER = "danger"


EMOJI = {
    'news': '6021536113108196448',
    'feedback': '6030863729808120196',
    'help': '5807800879553715710',
    'settings': '6021582331251268218',
    'about': '5879813604068298387',
    'support': '5769403330761593044',
    'delete': '5879896690210639947',
    'back': '5877629862306385808',
    'forward': '5807453545548487345',
    'save': '5825794181183836432',
    'currencies': '5985598781712767394',
    'crypto': '5778546023349621090',
    'language': '5879585266426973039',
    'quote_format': '5886437972647088483',
    'changelog': '5960551395730919906',
}


def styled_button(
    text: str,
    callback_data: str = None,
    style: ButtonStyle = None,
    url: str = None,
    emoji: str = None
) -> InlineKeyboardButton:
    kwargs = {"text": text}

    if style:
        kwargs["style"] = style.value
    if emoji:
        kwargs["icon_custom_emoji_id"] = emoji
    if url:
        kwargs["url"] = url
    elif callback_data:
        kwargs["callback_data"] = callback_data

    return InlineKeyboardButton(**kwargs)


def primary_button(text: str, callback_data: str = None, url: str = None, emoji: str = None) -> InlineKeyboardButton:
    return styled_button(text, callback_data, ButtonStyle.PRIMARY, url, emoji)


def success_button(text: str, callback_data: str = None, url: str = None, emoji: str = None) -> InlineKeyboardButton:
    return styled_button(text, callback_data, ButtonStyle.SUCCESS, url, emoji)


def danger_button(text: str, callback_data: str = None, url: str = None, emoji: str = None) -> InlineKeyboardButton:
    return styled_button(text, callback_data, ButtonStyle.DANGER, url, emoji)
