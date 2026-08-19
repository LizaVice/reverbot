# ⚖️ Как интегрировать условия в Telegram-бот

Инструкция для добавления Условий использования, Политики конфиденциальности и Copyright Disclaimer в бот.

---

## 1. Добавить команды в бот

### Обновить `bot.py`

Добавьте эти обработчики перед `main()`:

```python
@dp.message.command("terms")
async def cmd_terms(message: Message):
    """Показывает Terms of Service"""
    text = """
📋 <b>Условия использования</b>

Полные условия: https://github.com/ВАШ_USERNAME/reverbot/blob/main/TERMS_OF_SERVICE.md

<b>Краткий обзор:</b>
✅ Для личного использования музыки, на которую у вас есть права
✅ Premium подписка: $4.99/месяц
❌ Использование музыки с авторскими правами запрещено
❌ Запрещено распространение обработанной чужой музыки

<b>Вопросы?</b> /help или напишите нам
    """
    await message.answer(text, parse_mode="HTML")

@dp.message.command("privacy")
async def cmd_privacy(message: Message):
    """Показывает Privacy Policy"""
    text = """
🔒 <b>Политика конфиденциальности</b>

Полная политика: https://github.com/ВАШ_USERNAME/reverbot/blob/main/PRIVACY_POLICY.md

<b>Краткий обзор:</b>
✅ Мы не продаём ваши данные
✅ Ваши файлы удаляются через 24 часа
✅ Используем ваш ID только для работы сервиса
❌ Платежи обрабатывает Telegram, не мы

<b>Требования:</b>
/delete_my_data — удалить все ваши данные
/export_my_data — скачать копию своих данных
    """
    await message.answer(text, parse_mode="HTML")

@dp.message.command("copyright")
async def cmd_copyright(message: Message):
    """Показывает Copyright Disclaimer"""
    text = """
⚠️ <b>Дисклеймер об авторских правах</b>

Полный дисклеймер: https://github.com/ВАШ_USERNAME/reverbot/blob/main/COPYRIGHT_DISCLAIMER.md

<b>Важно:</b>
✅ Используйте только музыку, на которую у вас есть права
✅ Музыка CC0, CC-BY, и другие открытые лицензии OK
❌ Обработка музыки Spotify, YouTube (©) запрещена
❌ Даже если вы не делитесь — нарушение авторского права

<b>Где взять музыку?</b>
📎 YouTube Audio Library
📎 Pixabay Music
📎 Incompetech
📎 Epidemic Sound (подписка $4.99)
    """
    await message.answer(text, parse_mode="HTML")

@dp.message.command("delete_my_data")
async def cmd_delete_data(message: Message):
    """Запрос на удаление всех данных пользователя"""
    user_id = message.from_user.id
    text = f"""
❌ <b>Запрос на удаление данных</b>

Ваши данные (User ID: <code>{user_id}</code>) будут удалены за 30 дней.

<b>Что будет удалено:</b>
✗ История обработок
✗ Профиль пользователя
✗ Все файлы в облаке
✗ Записи о платежах (кроме бухгалтерии за 7 лет)

<b>Процесс:</b>
1️⃣ Запрос принят
2️⃣ 30 дней для отмены (/cancel_deletion)
3️⃣ Автоматическое удаление

Вы больше не сможете использовать бот после удаления.
    """
    
    # Логируйте это в БД
    logging.info(f"Delete request from user_id={user_id}")
    
    # Добавьте пользователя в очередь удаления
    # (реализуйте это в своей БД/хранилище)
    
    await message.answer(text, parse_mode="HTML")

@dp.message.command("export_my_data")
async def cmd_export_data(message: Message):
    """Экспортирует данные пользователя в JSON"""
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    
    # Соберите данные пользователя
    user_data = {
        "user_id": user_id,
        "username": username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
        "request_date": datetime.now().isoformat(),
        "history": [],  # Добавьте историю из БД
        "account_age_days": (datetime.now() - message.from_user.is_bot).days,
    }
    
    # Экспортируйте как JSON файл
    json_str = json.dumps(user_data, indent=2, ensure_ascii=False)
    
    file = FSInputFile(
        path=f"/tmp/{user_id}_export.json",
        filename=f"my_data_{user_id}.json"
    )
    
    await message.answer_document(
        file,
        caption="📄 Ваши данные в формате JSON (GDPR Article 20)"
    )

@dp.message.command("help")
async def cmd_help(message: Message):
    """Показывает справку с командами"""
    text = """
🎵 <b>Помощь по музыкальному боту</b>

<b>Основные команды:</b>
/start — начать использование
/history — ваша история обработок

<b>Управление аккаунтом:</b>
/terms — условия использования
/privacy — политика конфиденциальности
/copyright — дисклеймер об авторских правах
/delete_my_data — удалить все данные
/export_my_data — скачать свои данные

<b>Используйте музыку:</b>
✅ Свою (CC0, CC-BY, лицензионную)
❌ Spotify, YouTube, Apple Music (авторские права)

<b>Вопросы?</b>
📧 Email: support@[ваш домен]
🐛 GitHub Issues: [ваш github]
    """
    await message.answer(text, parse_mode="HTML")
```

---

## 2. Добавить уведомление при первом использовании

Обновьте `/start`:

```python
@dp.message.command("start")
async def cmd_start(message: Message):
    """Приветствие новых пользователей"""
    user_id = message.from_user.id
    
    # Проверьте, первый ли это раз
    is_new_user = True  # Получите из БД
    
    if is_new_user:
        text = f"""
👋 Добро пожаловать, {message.from_user.first_name}!

Я помогу вам обработать музыку эффектами:
🎸 Nightcore, Bass Boosted, 8D Audio
🎵 Реверберация (3 уровня)
⚡ Регулировка скорости 0.5x–1.5x

<b>⚠️ Важно перед началом:</b>
• /copyright — прочитайте о авторских правах
• Используйте только вашу музыку или с открытой лицензией
• Запрещено использовать Spotify/YouTube (© музыка)

<b>Начните:</b>
1. Отправьте голосовое сообщение или аудиофайл
2. Выберите эффекты
3. Выберите скорость
4. Получите результат!

Вопросы? /help
        """
    else:
        text = f"Добро пожаловать назад, {message.from_user.first_name}! 🎵"
    
    await message.answer(text, parse_mode="HTML")
```

---

## 3. Добавить ссылки в главное меню

```python
# В main():
async def setup_bot_commands():
    """Настройка команд в меню бота"""
    commands = [
        BotCommand(command="start", description="🎵 Начать"),
        BotCommand(command="history", description="📋 История обработок"),
        BotCommand(command="help", description="❓ Справка"),
        BotCommand(command="terms", description="⚖️ Условия использования"),
        BotCommand(command="privacy", description="🔒 Приватность"),
        BotCommand(command="copyright", description="⚠️ Авторские права"),
        BotCommand(command="delete_my_data", description="❌ Удалить мои данные"),
    ]
    await bot.set_my_commands(commands)

# Вызовите в main():
await setup_bot_commands()
```

---

## 4. Добавить кнопку "Условия" в начале

```python
@dp.message.command("start")
async def cmd_start(message: Message):
    """Приветствие с согласием на условия"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я согласен с условиями", callback_data="agree_terms")],
        [InlineKeyboardButton(text="📋 Прочитать условия", url="https://github.com/ВАШ_USERNAME/reverbot/blob/main/TERMS_OF_SERVICE.md")],
    ])
    
    text = """
🎵 Добро пожаловать!

Перед использованием, пожалуйста:
1. Прочитайте условия использования
2. Согласитесь с условиями

⚠️ <b>Важно:</b> Используйте только музыку, на которую у вас есть права!
    """
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "agree_terms")
async def cb_agree_terms(query: CallbackQuery):
    """Пользователь согласился с условиями"""
    user_id = query.from_user.id
    
    # Сохраните согласие в БД
    # db.users.update_one({"user_id": user_id}, {"$set": {"terms_agreed": True, "agreed_date": datetime.now()}})
    
    await query.message.edit_text("""
✅ Спасибо! Вы согласились с условиями использования.

Теперь вы можете:
• Отправить голосовое сообщение/аудиофайл
• Выбрать эффекты
• Получить результат

🎵 Начните!
    """, parse_mode="HTML")
    
    await query.answer("Условия приняты ✅")
```

---

## 5. README обновление

Добавьте в `README.md`:

```markdown
## 📋 Условия использования

Перед использованием бота прочитайте:

- **[Условия использования](TERMS_OF_SERVICE.md)** — ваши права и обязанности
- **[Политика конфиденциальности](PRIVACY_POLICY.md)** — как мы используем ваши данные
- **[Дисклеймер об авторских правах](COPYRIGHT_DISCLAIMER.md)** — какую музыку можно обрабатывать

### Краткий обзор:

✅ **Используйте**:
  - Вашу собственную музыку
  - Музыку с открытой лицензией (CC0, CC-BY)
  - Лицензионную музыку (Epidemic Sound, AudioJungle)

❌ **Не используйте**:
  - Spotify, Apple Music, YouTube (авторские права)
  - Музыку без разрешения правообладателя

## Команды в боте

```
/start           — начало
/terms           — условия использования
/privacy         — политика конфиденциальности
/copyright       — дисклеймер об авторских правах
/delete_my_data  — удалить все мои данные
/export_my_data  — скачать мои данные
/help            — справка
```
```

---

## 6. Лёгальная защита (опционально)

Добавьте в `.env`:

```env
# Контакты для жалоб
SUPPORT_EMAIL=support@[ваш домен]
DMCA_EMAIL=copyright@[ваш домен]
DPO_EMAIL=privacy@[ваш домен]

# Версия условий
TERMS_VERSION=1.0
TERMS_LAST_UPDATED=2026-08-19
```

---

## 7. Логирование согласий

```python
async def log_compliance(user_id: int, action: str, timestamp: datetime = None):
    """Логируйте все действия для compliance"""
    if timestamp is None:
        timestamp = datetime.now()
    
    log_entry = {
        "user_id": user_id,
        "action": action,  # "terms_accepted", "privacy_viewed", "data_deleted", и т.д.
        "timestamp": timestamp.isoformat(),
        "ip_address": None,  # Получите из Telegram, если нужно
    }
    
    # Сохраните в БД (обычно в audit log таблице)
    # db.compliance_log.insert_one(log_entry)
    
    logging.info(f"Compliance log: {log_entry}")
```

---

## 8. Проверка перед обработкой

```python
async def check_compliance(user_id: int) -> bool:
    """Проверьте, согласился ли пользователь с условиями"""
    # Получите из БД
    user = await db.users.find_one({"user_id": user_id})
    
    if not user or not user.get("terms_agreed"):
        return False
    
    return True

# В обработчике аудио:
@dp.message.audio()
async def handle_audio(message: Message):
    user_id = message.from_user.id
    
    if not await check_compliance(user_id):
        await message.answer(
            "⚠️ Пожалуйста, сначала согласитесь с условиями использования\n/start"
        )
        return
    
    # Процесс обработки...
```

---

## Чек-лист интеграции

- [ ] Скопировал `TERMS_OF_SERVICE.md`, `PRIVACY_POLICY.md`, `COPYRIGHT_DISCLAIMER.md`
- [ ] Обновил `/start` с кнопкой согласия
- [ ] Добавил команды `/terms`, `/privacy`, `/copyright`
- [ ] Добавил `/delete_my_data`, `/export_my_data`
- [ ] Обновил `bot.set_my_commands()`
- [ ] Добавил проверку согласия перед обработкой
- [ ] Логирую все действия compliance
- [ ] Обновил README с ссылками на условия
- [ ] Установил контакты для DMCA (`DMCA_EMAIL`)
- [ ] Протестировал все команды

---

**Готово!** Ваш бот теперь юридически защищён. 🛡️
