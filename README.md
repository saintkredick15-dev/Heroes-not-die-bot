<div align="center">
  <h1>Heroes Not Die — Discord Bot</h1>
  <p align="center">
    <a href="https://github.com/Kredickoa/disco-bot/stargazers">
      <img src="https://img.shields.io/github/stars/Kredickoa/disco-bot?colorA=363a4f&colorB=b7bdf8&style=for-the-badge" alt="Stars"/>
    </a>
    <a href="https://github.com/Kredickoa/disco-bot/issues">
      <img src="https://img.shields.io/github/issues/Kredickoa/disco-bot?colorA=363a4f&colorB=f5a97f&style=for-the-badge" alt="Issues"/>
    </a>
    <a href="https://github.com/Kredickoa/disco-bot/contributors">
      <img src="https://img.shields.io/github/contributors/Kredickoa/disco-bot?colorA=363a4f&colorB=a6da95&style=for-the-badge" alt="Contributors"/>
    </a>
  </p>
</div>

---

Приватний бот сервера **Heroes Not Die**, розроблений **Kredick**.
Ви можете вільно використовувати його у власних цілях та додати на свій сервер.

---

## Функціонал

| Модуль | Опис |
|--------|------|
| XP & Рівні | Нарахування за повідомлення, войс та реакції |
| Лідерборд | Пагінований з підтримкою кастомних емодзі |
| Профіль | Картка з графіком активності |
| Tickets | Система тікетів з UI-панеллю адміністратора |
| Авто-роль | Автоматична видача ролі новим учасникам |
| Войс-кімнати | Приватні голосові кімнати |
| Адмін | Управління XP, mute, kick, ban, purge |
| Меми | Випадкові меми з Reddit |

---

## Встановлення

### ✅ Вимоги

- **Python 3.11+**
- **MongoDB** (локально або [MongoDB Atlas](https://www.mongodb.com/atlas) — безкоштовний)

### 📦 Встановлення залежностей

```bash
git clone https://github.com/Kredickoa/disco-bot.git
cd disco-bot
pip install -r requirements.txt
```

| Бібліотека | Призначення |
|---|---|
| `discord.py` | Основний фреймворк |
| `motor` | Асинхронний драйвер MongoDB |
| `python-dotenv` | Завантаження змінних з `.env` |
| `Pillow` | Генерація зображення профілю |
| `matplotlib` | Графік активності у профілі |
| `rich` | Прогрес-бар у консолі при старті |
| `aiohttp` | HTTP-запити (меми) |
| `yt-dlp` + `PyNaCl` | Підтримка голосових каналів |

### ⚙️ Конфігурація

Створіть файл `.env` у корені проєкту:

```env
TOKEN=ваш_токен_бота
MONGO_DB=mongodb+srv://...
```

- **TOKEN** — токен з [Discord Developer Portal](https://discord.com/developers/applications)
- **MONGO_DB** — рядок підключення до MongoDB

Відредагуйте `config.json`:

```json
{
    "prefix": "!",
    "guild": ID_ВАШОГО_СЕРВЕРА,
    "dev": [ВАШ_USER_ID],
    "channels": {
        "complaints": ID_КАНАЛУ_ДЛЯ_СКАРГ,
        "support": ID_КАНАЛУ_ПІДТРИМКИ
    }
}
```

### 🚀 Запуск

```bash
python run.py
```

### 🔐 Привілеї бота

У [Discord Developer Portal](https://discord.com/developers/applications) → **Bot** → Privileged Gateway Intents увімкніть:

- `Server Members Intent`
- `Message Content Intent`

---

## Структура проєкту

```
bot1/
├── run.py
├── config.json
├── requirements.txt
├── .env
└── src/
    ├── bot.py
    ├── commands/
    │   └── activity/
    ├── events/
    ├── modules/
    └── repositories/
```

---

<div align="center">
  <sub>Made with ❤️ by <b>Kredick</b> for <b>Heroes Not Die</b></sub>
</div>