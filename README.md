# OTC bot

[![Python](https://img.shields.io/badge/Python-3.7%2B-blue)](https://www.python.org/downloads/)
[![aiogram](https://img.shields.io/badge/aiogram-3.0%2B-green)](https://docs.aiogram.dev/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)

[English](#english) | [Русский](#русский)

---

## English

### Description

This Currency Converter Bot is a powerful Telegram bot that allows users to convert between various currencies and cryptocurrencies. It provides real-time exchange rates, supports group chats, and offers a user-friendly interface with customizable settings.

### Key Features

- Real-time currency and cryptocurrency conversion
- Support for multiple fiat currencies and cryptocurrencies
- Inline mode for quick conversions in any chat
- Customizable user settings (preferred currencies, language, quote format)
- Group chat support with separate settings for each group
- Caching system for efficient API usage

### Requirements

- Python 3.7+
- aiogram 3.0+
- aiohttp
- Other dependencies (see `requirements.txt`)

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/OTC.git
   cd OTC
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. Set up your configuration:
   - Create `.env` file 
   - Fill `TELEGRAM_BOT_TOKEN=TOKEN`

### Usage

To start the bot, run:

```
python main.py
```

### Commands

- `/start` - Initialize the bot and see the main menu
- `/settings` - Adjust your preferences
- `/stats` - View bot statistics (admin only)

### Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Русский

### Описание

Этот Бот-Конвертер Валют - мощный Telegram-бот, который позволяет пользователям конвертировать различные валюты и криптовалюты. Он предоставляет актуальные обменные курсы, поддерживает групповые чаты и предлагает удобный интерфейс с настраиваемыми параметрами.

### Основные функции

- Конвертация валют и криптовалют в реальном времени
- Поддержка множества фиатных валют и криптовалют
- Инлайн-режим для быстрой конвертации в любом чате
- Настраиваемые пользовательские настройки (предпочтительные валюты, язык, формат цитирования)
- Поддержка групповых чатов с отдельными настройками для каждой группы
- Система кэширования для эффективного использования API

### Требования

- Python 3.7+
- aiogram 3.0+
- aiohttp
- Другие зависимости (см. `requirements.txt`)

### Установка

1. Клонируйте репозиторий:
   ```
   git clone https://github.com/yourusername/OTC.git
   cd OTC
   ```

2. Установите необходимые пакеты:
   ```
   pip install -r requirements.txt
   ```

3. Настройте конфигурацию:
  - Создайте файл `.env`
  -  Заполните токен вот так: `TELEGRAM_BOT_TOKEN=TOKEN` 

### Использование

Чтобы запустить бота, выполните:

```
python main.py
```

### Команды

- `/start` - Инициализировать бота и увидеть главное меню
- `/settings` - Настроить ваши предпочтения
- `/stats` - Просмотреть статистику бота (только для админов)

### Вклад в проект

Мы приветствуем вклад в развитие проекта! Пожалуйста, не стесняйтесь отправлять Pull Request.

### Лицензия

Этот проект лицензирован под MIT License - подробности см. в файле [LICENSE](LICENSE).
