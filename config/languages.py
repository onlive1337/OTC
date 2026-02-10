LANGUAGES = {
    'ru': {
        'welcome': """Добро пожаловать в OTC!

Введите сумму и валюту для конвертации (например, 100 USD).

Инлайн-режим: @onlive_twilight_bot в любом чате.
Настройки: /settings
Помощь: /help
Канал: @OTC_InfoHub""",

        'help': """Руководство OTC

Использование:
- Введите сумму и код валюты: 100 USD, 50 EUR
- Бот ответит конвертацией в выбранные валюты

Инлайн-режим: @onlive_twilight_bot 100 USD в любом чате

Команды:
/start — запуск бота
/settings — настройки валют
/help — справка

Сокращения:
- к — тысячи: 5к USD = 5000 USD
- м — миллионы: 1м EUR = 1000000 EUR

Связь: @onswix""",

        'feedback': "Обратная связь:\n\nПредложения и замечания — @onswix",
        'settings': "Выберите раздел настроек:",
        'currencies': "Выберите валюты:",
        'cryptocurrencies': "Выберите криптовалюты:",
        'language': "Выберите язык:",
        'save_settings': "Настройки сохранены!",
        'invalid_input': "Неверный ввод. Введите сумму и код валюты, например: 100 USD.",
        'error': "Произошла ошибка. Попробуйте снова.",
        'fiat_currencies': "Фиатные валюты:",
        'cryptocurrencies_output': "Криптовалюты:",
        'back': "Назад",
        'help_button': "Помощь",
        'news_button': "Новости",
        'feedback_button': "Обратная связь",
        'settings_button': "Настройки",
        'save_button': "Сохранить настройки",
        'back_to_settings': "Назад к настройкам",
        'forward': "Вперёд",
        'stats_title': "Статистика бота:",
        'total_users': "Всего пользователей:",
        'active_users': "Активных сегодня:",
        'new_users': "Новых сегодня:",
        'no_currencies_selected': "Валюты не выбраны",
        'select_currencies_message': "Выберите валюты в настройках",
        'select_currencies_full_message': "Вы не выбрали ни одной валюты. Перейдите в настройки для выбора.",
        'conversion_result': "Результат конвертации",
        'number_too_large': "Число слишком большое.",
        'about_button': "О боте",
        'about_message': "Onlive Twilight Convert",
        'current_version': "Версия:",
        'view_changelog': "Список изменений",
        'invalid_currency': "Не удалось распознать валюту '{currency}'. Используйте коды: USD, EUR, RUB.",
        'delete_button': "Удалить",
        'quote_format': "Формат цитаты",
        'quote_format_status': "Статус формата цитаты",
        'on': "Вкл",
        'off': "Выкл",
        'chat_settings': "Настройки чата",
        'admin_only': "Только администраторы могут изменять настройки чата.",
        'support_button': "Поддержать",
        'support_message': "Если вы хотите поддержать разработку проекта, вы можете сделать это, нажав на кнопку ниже. Из Узбекистана или России — напишите @onswix лично.",
        'donate_button': "Поддержать",
        'empty_input_title': "Введите сумму и валюту",
        'empty_input_description': "Например: 100 USD или 10 982 RUB",
        'empty_input_message': "Введите сумму и код валюты: 100 USD или 10 982 RUB.",
        'invalid_input_description': "Проверьте формат ввода",
        'not_admin_message': 'Для изменения настроек нужны права администратора.',
        'welcome_group_message': """OTC добавлен в группу!

Введите сумму и валюту для конвертации (например, 500 EUR).
Администраторы: /settings для настройки валют группы.
Помощь: /help""",
   'setting_updated': "Настройка обновлена",
   'language_changed': "Язык изменён",
   'negative_or_zero_amount': "Сумма должна быть положительной.",
   'conversion_help_message': """Не удалось распознать сумму и валюту.

Формат: 100 USD, 50 евро, 1000 рублей, 10к долларов""",
    },
    'en': {
        'welcome': """Welcome to OTC!

Type an amount and currency to convert (e.g., 100 USD).

Inline mode: @onlive_twilight_bot in any chat.
Settings: /settings
Help: /help
Channel: @OTC_InfoHub""",

        'help': """OTC Help Guide

Usage:
- Type amount and currency code: 100 USD, 50 EUR
- Bot will reply with conversions to your selected currencies

Inline mode: @onlive_twilight_bot 100 USD in any chat

Commands:
/start — restart bot
/settings — currency preferences
/help — this guide

Shortcuts:
- k — thousands: 5k USD = 5000 USD
- m — millions: 1m EUR = 1000000 EUR

Contact: @onswix""",

        'feedback': "Feedback:\n\nSuggestions and comments — @onswix",
        'settings': "Choose a settings section:",
        'currencies': "Select currencies:",
        'cryptocurrencies': "Select cryptocurrencies:",
        'language': "Select language:",
        'save_settings': "Settings saved!",
        'invalid_input': "Invalid input. Enter amount and currency code, e.g.: 100 USD.",
        'error': "An error occurred. Please try again.",
        'fiat_currencies': "Fiat currencies:",
        'cryptocurrencies_output': "Cryptocurrencies:",
        'back': "Back",
        'help_button': "Help",
        'news_button': "News",
        'feedback_button': "Feedback",
        'settings_button': "Settings",
        'save_button': "Save settings",
        'back_to_settings': "Back to settings",
        'forward': "Next",
        'stats_title': "Bot Statistics:",
        'total_users': "Total users:",
        'active_users': "Active today:",
        'new_users': "New today:",
        'no_currencies_selected': "No currencies selected",
        'select_currencies_message': "Select currencies in settings",
        'select_currencies_full_message': "No currencies selected. Go to settings to choose.",
        'conversion_result': "Conversion Result",
        'number_too_large': "Number is too large.",
        'about_button': "About",
        'about_message': "Onlive Twilight Convert",
        'current_version': "Version:",
        'view_changelog': "View changelog",
        'invalid_currency': "Can't recognize currency '{currency}'. Use codes: USD, EUR, RUB.",
        'delete_button': "Delete",
        'quote_format': "Quote format",
        'quote_format_status': "Quote format status",
        'on': "On",
        'off': "Off",
        'chat_settings': "Chat settings",
        'admin_only': "Only admins can change chat settings.",
        'support_button': "Support",
        'support_message': "If you'd like to support the project, click the button below. From Uzbekistan or Russia — contact @onswix directly.",
        'donate_button': "Support",
        'empty_input_title': "Enter amount and currency",
        'empty_input_description': "For example: 100 USD or 10,982 KZT",
        'empty_input_message': "Enter amount and currency code: 100 USD or 10,982 KZT.",
        'invalid_input_description': "Check your input format",
        'not_admin_message': 'Admin rights required to change settings.',
        'welcome_group_message': """OTC added to group!

Type amount and currency to convert (e.g., 500 EUR).
Admins: /settings to customize group currencies.
Help: /help""",
   'setting_updated': "Settings updated",
   'language_changed': "Language changed",
   'negative_or_zero_amount': "Amount must be positive.",
   'conversion_help_message': """Could not recognize amount and currency.

Format: 100 USD, 50 euro, 1000 rubles, 10k dollars""",
    }
}