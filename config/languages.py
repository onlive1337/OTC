LANGUAGES = {
    'ru': {
'welcome': """Привет! Я бот для конвертации валют. 🌍💱

Вот что я умею:
- Конвертировать валюты: просто напишите сумму и код валюты (например, 100 USD, 5000 RUB, 750 EUR)
- Работаю с фиатными валютами и криптовалютами
- Работаю в инлайн-режиме: просто упомяните меня в любом чате @onlive_twilight_bot
- Поддерживаю групповые чаты: добавьте меня в группу для быстрой конвертации (нужно выдать права администратора)
- Настройка валют: выберите валюты, которые вы хотите видеть в результатах
- Мультиязычность: поддержка русского и английского языков

Используйте кнопки ниже для дополнительной информации и настройки.""",

'help': """Как пользоваться ботом:

1. Конвертация валют:
   • Напишите сумму и код валюты, например: 100 USD, 5000 RUB, 750 EUR

2. Поддерживаемые валюты:
   • Фиатные валюты: USD, EUR, RUB, GBP, JPY, CNY, и другие
   • Криптовалюты: BTC, ETH, USDT, BNB, XRP, и другие

3. Инлайн-режим:
   • Упомяните бота в любом чате: @onlive_twilight_bot 100 USD

4. Групповые чаты:
   • Добавьте бота в группу для быстрой конвертации (нужно выдать права администратора)
   • Настройте валюты для группы с помощью команды /settings (только администратор может менять)

5. Настройки:
   • Используйте /settings или кнопку "Настройки" в главном меню
   • Выберите предпочитаемые валюты для отображения
   • Измените язык интерфейса

6. Дополнительно:
   • Новости и обновления: подпишитесь на наш канал
   • Обратная связь: используйте кнопку "Обратная связь"
   • Информация о боте: кнопка "О боте" в главном меню

Если у вас остались вопросы, не стесняйтесь обращаться к нам через обратную связь!""",

        'feedback': "📬 Обратная связь:\n\nМы всегда рады вашим предложениям и замечаниям!\nCвяжитесь со мной в Telegram: @onswix",
        'settings': "Выберите раздел настроек:",
        'currencies': "Выберите валюты:",
        'cryptocurrencies': "Выберите криптовалюты:",
        'language': "Выберите язык:",
        'save_settings': "Настройки сохранены!",
        'invalid_input': "Неверный ввод. Пожалуйста, введите сумму и код валюты, например, '100 USD' или '100 USD EUR'.",
        'error': "Произошла ошибка. Пожалуйста, попробуйте снова.",
        'fiat_currencies': "Фиатные валюты:",
        'cryptocurrencies_output': "Криптовалюты:",
        'back': "Назад",
        'help_button': "❓ Помощь",
        'news_button': "🗞 Новости",
        'feedback_button': "💭 Обратная связь",
        'settings_button': "⚙️ Настройки",
        'save_button': "Сохранить настройки",
        'back_to_settings': "Назад к настройкам",
        'forward': "Вперёд",
        'stats_title': "📊 Статистика бота:",
        'total_users': "👥 Общее количество пользователей:",
        'active_users': "🔵 Активных пользователей сегодня:",
        'new_users': "🆕 Новых пользователей сегодня:",
        'no_currencies_selected': "Валюты не выбраны",
        'select_currencies_message': "Пожалуйста, выберите валюты в настройках",
        'select_currencies_full_message': "Вы не выбрали ни одной валюты. Пожалуйста, перейдите в настройки бота, чтобы выбрать валюты для конвертации.",
        'conversion_result': "Результат конвертации",
        'number_too_large': "Число слишком большое для обработки.",
        'about_button': "ℹ️ О боте",
        'about_message': "Информация о боте Onlive Twilight Convert",
        'current_version': "Текущая версия:",
        'view_changelog': "Посмотреть список изменений",
        'invalid_currency': "Извините, я не могу распознать валюту '{currency}'. Пожалуйста, используйте стандартные коды валют, например: USD, EUR, RUB.",
        'delete_button': "Удалить",
        'quote_format': "Формат цитаты",
        'quote_format_status': "Статус формата цитаты",
        'on': "Включен",
        'off': "Выключен",
        'chat_settings': "Настройки чата",
        'admin_only': "Только администраторы могут изменять настройки чата.",
        'support_button': "❤️ Поддержать",
        'support_message': "✨ Спасибо за использование моего бота! Если вы хотите поддержать разработчика и помочь в дальнейшем развитии проекта, вы можете сделать это, отправив добровольный взнос, нажав на кнопку. Если вы с Узбекистана или с России обратитесь в ко мне лично пожалуйста. Ваша поддержка очень ценна! ❤️",
        'donate_button': "❤️ Поддержать",
        'welcome_group_message': (
    "Привет! Я бот для конвертации валют. 🌍💱\n\n"
    "Чтобы конвертировать валюту, просто напишите сумму и код валюты. Например:\n"
    "100 USD\n5000 RUB\n750 EUR\n\n"
    "Я автоматически конвертирую в другие валюты.\n\n"
    "Используйте /settings, чтобы настроить валюты для конвертации."
)
    },
    'en': {
'welcome': """Hello! I'm a currency conversion bot. 🌍💱

Here's what I can do:
- Convert currencies: just type an amount and currency code (e.g., 100 USD, 5000 RUB, 750 EUR)
- Work with fiat currencies and cryptocurrencies
- Work in inline mode: just mention me in any chat @onlive_twilight_bot
- Support group chats: add me to a group for quick conversions (need to give admin rights)
- Currency settings: choose which currencies you want to see in results
- Multilingual: support for Russian and English languages

Use the buttons below for more information and settings.""",

'help': """How to use the bot:

1. Currency conversion:
   • Type an amount and currency code, e.g.: 100 USD, 5000 RUB, 750 EUR

2. Supported currencies:
   • Fiat currencies: USD, EUR, RUB, GBP, JPY, CNY, and others
   • Cryptocurrencies: BTC, ETH, USDT, BNB, XRP, and others

3. Inline mode:
   • Mention the bot in any chat: @onlive_twilight_bot 100 USD

4. Group chats:
   • Add the bot to a group for quick conversions and give admin rights (need to give admin rights)
   • Configure currencies for the group using the /settings command (only administrator can do this)

5. Settings:
   • Use /settings or the "Settings" button in the main menu
   • Select preferred currencies to display
   • Change the interface language

6. Additional features:
   • News and updates: subscribe to our channel
   • Feedback: use the "Feedback" button
   • Bot information: "About" button in the main menu

If you have any questions, feel free to contact us via feedback!""",

        'feedback': "📬 Feedback:\n\nWe always appreciate your suggestions and comments!\nContact me on Telegram: @onswix",
        'settings': "Choose a settings section:",
        'currencies': "Select currencies:",
        'cryptocurrencies': "Select cryptocurrencies:",
        'language': "Select language:",
        'save_settings': "Settings saved!",
        'invalid_input': "Invalid input. Please enter an amount and currency code, e.g., '100 USD' or '100 USD EUR'.",
        'error': "An error occurred. Please try again.",
        'fiat_currencies': "Fiat currencies:",
        'cryptocurrencies_output': "Cryptocurrencies:",
        'back': "Back",
        'help_button': "❓ Help",
        'news_button': "🗞 News",
        'feedback_button': "💭 Feedback",
        'settings_button': "⚙️ Settings",
        'save_button': "Save settings",
        'back_to_settings': "Back to settings",
        'forward': "Next",
        'stats_title': "📊 Bot Statistics:",
        'total_users': "👥 Total number of users:",
        'active_users': "🔵 Active users today:",
        'new_users': "🆕 New users today:",
        'no_currencies_selected': "No currencies selected",
        'select_currencies_message': "Please select currencies in settings",
        'select_currencies_full_message': "You haven't selected any currencies. Please go to bot settings to select currencies for conversion.",
        'conversion_result': "Conversion Result",
        'number_too_large': "The number is too large to process.",
        'about_button': "ℹ️ About",
        'about_message': "About Onlive Twilight Convert bot",
        'current_version': "Current version:",
        'view_changelog': "View changelog",
        'invalid_currency': "Sorry, I can't recognize the currency '{currency}'. Please use standard currency codes, for example: USD, EUR, RUB.",
        'delete_button': "Delete",
        'quote_format': "Quote format",
        'quote_format_status': "Quote format status",
        'on': "On",
        'off': "Off",
        'chat_settings': "Chat settings",
        'admin_only': "Only administrators can change chat settings.",
        'support_button': "❤️ Support",
        'support_message': "✨ Thank you for using my bot! If you would like to support the developer and help with the further development of the project, you can do so by making a voluntary donation by clicking the button. If you are from Uzbekistan or Russia, please contact me personally. Your support is greatly appreciated! ❤️",
        'donate_button': "❤️ Support",
        'welcome_group_message': (
    "Hello! I'm a currency conversion bot. 🌍💱\n\n"
    "To convert currency, simply type an amount and currency code. For example:\n"
    "100 USD\n5000 RUB\n750 EUR\n\n"
    "I will automatically convert to other currencies.\n\n"
    "Use /settings to configure currencies for conversion."
)
    }
}