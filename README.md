# Бот-конвертер валют

Этот Telegram бот позволяет конвертировать валюты и криптовалюты. Он поддерживает как личные чаты, так и групповые.

## Возможности

- Конвертация валют и криптовалют
- Поддержка групповых чатов
- Inline режим для быстрой конвертации
- Настраиваемый список валют и криптовалют
- Многоязычный интерфейс (русский и английский)

## Установка

1. Клонируйте репозиторий:
   ```
   git clone https://github.com/onlive1337/OTC.git
   cd OTC
   ```

2. Установите зависимости:
   ```
   pip install -r requirements.txt
   ```

3. Создайте файл `.env` и добавьте следующие переменные:
   ```python
   BOT_TOKEN = 'your_bot_token_here'
   ```

## Запуск бота

Запустите бота с помощью команды:
```
python bot.py
```

## Использование

1. Начните чат с ботом в Telegram, отправив команду `/start`.
2. Для конвертации валюты, просто отправьте сумму и код валюты, например: `100 USD` или `5000 RUB`.
3. Используйте команду `/settings` для настройки списка валют и языка интерфейса.
4. В групповых чатах, добавьте бота и используйте команду `/settings` для настройки валют для группы.

## Дополнительные команды

- `/start` - Начать взаимодействие с ботом
- `/settings` - Открыть меню настроек
- `/stats` - Показать статистику (только для администраторов)

## Поддержка

Если у вас возникли проблемы или есть предложения по улучшению бота, пожалуйста, создайте issue в этом репозитории.

---

# Currency Converter Bot

This Telegram bot allows you to convert currencies and cryptocurrencies. It supports both private chats and group chats.

## Features

- Currency and cryptocurrency conversion
- Group chat support
- Inline mode for quick conversion
- Customizable list of currencies and cryptocurrencies
- Multilingual interface (Russian and English)

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/onlive1337/OTC.git
   cd OTC
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file and add the following variables:
   ```python
   BOT_TOKEN = 'your_bot_token_here'
   ```

## Running the Bot

Start the bot using the command:
```
python bot.py
```

## Usage

1. Start a chat with the bot on Telegram by sending the `/start` command.
2. To convert currency, simply send an amount and currency code, for example: `100 USD` or `5000 RUB`.
3. Use the `/settings` command to customize the list of currencies and interface language.
4. In group chats, add the bot and use the `/settings` command to set up currencies for the group.

## Additional Commands

- `/start` - Start interacting with the bot
- `/settings` - Open the settings menu
- `/stats` - Show statistics (admin only)

## Support

If you encounter any issues or have suggestions for improving the bot, please create an issue in this repository.
