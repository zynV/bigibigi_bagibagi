# 💰 Сімейний бюджет — Telegram-бот

Готовий проєкт за ТЗ **«Сімейний бюджет» v1.0**. Приватна Telegram-група, **рівно два користувачі**, український інтерфейс, витрати в PLN, SQLite, Python 3.12+, aiogram 3, Docker Compose, Long Polling.

> **Стан:** код підготовлений для запуску на VPS. Бот не розгорнутий і не підключений до Telegram; для цього потрібні ваші приватні налаштування. Не передавайте токен бота в чат.

## Функції

- `/start`, `/menu`: спільне меню з inline-кнопками, яке оновлюється в одному повідомленні; запити суми й підтвердження прибираються після завершення або скасування вводу;
- `/add`: вибір однієї з 10 категорій, відповідь сумою (`125,50`) або сумою з коментарем (`125,50 Biedronka`), підтвердження;
- `/today`, `/week`, `/month`: підсумки за категоріями та двома учасниками;
- `/history`: 10 останніх витрат і кнопки видалення лише власних записів (адмін може видаляти будь-які);
- `/undo`: скасувати **останню власну** витрату;
- `/categories`, `/cancel`, `/help`, `/settings`;
- `/export`: **адмін** експортує всі невидалені витрати CSV із BOM для Excel;
- щоденний онлайн-backup SQLite (Backup API), збереження 14 останніх копій;
- SQLite WAL, транзакції, `request_id` від дублювання, м'яке видалення.

**Особливість групового чату:** сума вводиться відповіддю (**Reply**) на спеціальне повідомлення бота з `ForceReply`. Так працює Telegram Privacy Mode без відкриття доступу бота до всіх розмов у групі. Незавершений ввід у пам'яті: після перезапуску потрібно почати його заново, але всі *підтверджені* операції зберігаються.

## 1. Створіть бота та групу

1. В Telegram відкрийте офіційного [@BotFather](https://t.me/BotFather), виконайте `/newbot` і збережіть отриманий **токен** тільки у приватний `.env`.
2. Створіть **приватну** Telegram-групу та додайте туди бота й обох учасників. Для введення через `ForceReply` **вимикати Privacy Mode не потрібно**.
3. Дізнайтесь `GROUP_CHAT_ID` (від'ємний, часто починається з `-100`) і числові `USER_ID` обох учасників. Є helper `scripts/discover_ids.py` (опис нижче).
4. Виберіть одного користувача адміністратором.

### Знайти Telegram ID через власного бота

Створіть `.env` з реальним `BOT_TOKEN` (поки інші поля можуть залишатися шаблонними). На комп'ютері з Python 3.12+:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/discover_ids.py
```

У **приватній групі** кожен учасник окремо надсилає `/id`. Скрипт надрукує `GROUP_CHAT_ID` та його `USER_ID`. Натисніть Ctrl+C. **Не запускайте** helper одночасно з основним ботом: у Telegram для токена має бути лише один Long Polling consumer.

## 2. Підготувати VPS

На Debian/Ubuntu з Docker Engine і Docker Compose Plugin (команда `docker compose`):

```bash
git clone https://github.com/zynV/bigibigi_bagibagi.git family_budget_bot
cd family_budget_bot
cp .env.example .env
chmod 600 .env
nano .env
```

Заповніть приклад нижче **своїми** значеннями, не поширюйте файл:

```dotenv
BOT_TOKEN=<токен з BotFather>
GROUP_CHAT_ID=-1001234567890
ALLOWED_USER_IDS=111111111,222222222
ADMIN_USER_ID=111111111
FAMILY_NAME=Сімейний бюджет
DATABASE_PATH=/app/data/budget.sqlite3
BACKUP_DIR=/app/backups
LOG_LEVEL=INFO
```

Запустіть:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100 family-budget-bot
```

**Ніяких відкритих портів, домену або HTTPS для Telegram не потрібно.** VPS має мати вихідний доступ до Telegram API. Міграція БД автоматично виконується при старті контейнера. Docker перезапускає контейнер після reboot VPS.

У групі надішліть `/start` та перевірте додавання `12,50`, `/today`, `/history`, видалення та `/export`. Повідомлення меню можна закріпити у групі.

## 3. Безпека

- Бот реагує **лише** на два `ALLOWED_USER_IDS` у **точно визначеній** групі `GROUP_CHAT_ID`; middleware перевіряє кожне повідомлення і callback.
- Автор може видалити свою витрату, адміністратор — будь-яку. CSV експортує тільки адміністратор, **але цей файл надсилається у спільну групу**, де його бачать обидва учасники.
- Файл `.env` виключений з Git, у Docker бота запущено від непривілейованого користувача. SSH-доступ рекомендується лише по ключах.
- Дані зберігаються у Docker named volume `budget_data`, резервні копії — `budget_backups`.
- **Не використовуйте `docker compose down -v`**, якщо не хочете видалити обидва volumes разом з даними.

## 4. Backups і перевірка відновлення

При старті (якщо сьогоднішнього backup ще немає) та під час періодичних перевірок бот створює один snapshot на локальну дату Варшави і зберігає 14 останніх файлів. Snapshot створюється через **SQLite Backup API**, а не звичайним копіюванням працюючої БД.

Щоб скопіювати резервні копії з Docker на хост:

```bash
mkdir -p ./backups-export
docker compose cp family-budget-bot:/app/backups/. ./backups-export/
```

Зберігайте копії також **за межами VPS** (інший сервер/зашифроване сховище). Рекомендується періодично відновлювати *копію* у тестовій SQLite й перевіряти `PRAGMA integrity_check;`. Для перевірки без установленого локального sqlite3:

```bash
python3 - <<'PY'
import sqlite3
from pathlib import Path
p = sorted(Path('backups-export').glob('budget-*.sqlite3'))[-1]
with sqlite3.connect(p) as db:
    print('Backup:', p, db.execute('PRAGMA integrity_check').fetchone())
PY
```

Не перезаписуйте робочу базу, поки бот запущений.

## 5. Оновлення / діагностика

Перед оновленням контейнера завантажте зміни з GitHub командою `git pull --ff-only` у папці проєкту.

```bash
docker compose up -d --build
docker compose logs --tail=100 family-budget-bot
docker compose restart family-budget-bot
```

Після оновлення дані не втрачаються завдяки named volumes. Перед оновленням зберігайте offsite backup. В один момент має працювати лише **одна** копія цього бота з одним токеном.

## 6. Локальний запуск і тести

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# У .env вкажіть локальні шляхи DATABASE_PATH=data/budget.sqlite3 і BACKUP_DIR=backups
# та справжні Telegram IDs/token
alembic upgrade head
pytest -q
python -m app.main
```

Поточні unit-тести перевіряють парсинг сум, Warsaw DST, структуру SQLite та online backup. Для **повного** end-to-end тестування потрібні встановлені залежності, бот і приватна тестова група Telegram.

## Структура

```text
app/
  main.py                 # polling / lifecycle
  config.py               # перевірка налаштувань
  db/                     # models, session, seed
  services/               # money, dates, budget, reports, backup
  bot/
    handlers/             # меню, витрати, звіти, експорт
    keyboards/            # кнопки
    middlewares/          # перевірка доступу
    states/               # незалежний FSM кожного учасника
migrations/versions/      # Alembic schema v1
tests/                    # unit tests
scripts/discover_ids.py   # одноразове визначення ID
docker-compose.yml
Dockerfile
.env.example
```

## Обмеження MVP

- Лише облік витрат; **доходи, банківські баланси, бюджетні ліміти** не включені.
- Додавання витрат за минулу дату й редагування операцій не включені.
- Категорії наразі фіксовані; розширення — наступна версія.
- Незавершені форми скидаються після перезапуску.
- Автоматична **передача backup поза VPS** потребує вашого окремого offsite-процесу.
