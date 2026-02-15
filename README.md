# ProspEl v2.0 — Бухгалтерская программа для ИП-паушальщика (Сербия)

Система учёта для индивидуального предпринимателя на паушальном режиме налогообложения в Сербии.

## Функционал

- **Книга доходов (КПО)** — ведение учёта доходов с датой, клиентом, основанием и суммой
- **Договоры** — управление договорами по образцу 1С «Моя фирма»: виды (услуги, поставка, аренда, комиссия), позиции, сроки действия, связь с доходами
- **Счета-фактуры** — нумерация и учёт выданных счетов
- **Лимиты дохода** — мониторинг лимитов 6 млн RSD (год) и 8 млн RSD (12 мес.)
- **Налоги и взносы** — учёт фиксированных платежей (налог, PIO, здоровье, безработица)
- **Экспорт отчётов** — выгрузка КПО в CSV и PDF
- **Справочник клиентов** — хранение данных клиентов
- **Мультиязычность** — интерфейс на сербском и русском

## Требования

- Python 3.10+
- Node.js 18+

## Установка и запуск

### 1. Backend

```bash
cd c:\Programming\Buh_Prosp
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Сервер будет доступен по адресу: http://127.0.0.1:8000

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Интерфейс: http://localhost:5173

### Учётные данные по умолчанию

- **Логин:** admin  
- **Пароль:** admin  

## Структура проекта

```
Buh_Prosp/
├── backend/
│   ├── main.py          # Точка входа FastAPI
│   ├── config.py        # Конфигурация
│   ├── database.py      # Подключение к БД
│   ├── models.py        # Модели SQLAlchemy
│   ├── schemas.py       # Pydantic-схемы
│   ├── auth.py          # Аутентификация
│   ├── services.py      # Бизнес-логика
│   └── routers/         # API-роутеры
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── api.js       # API-клиент
│       ├── i18n.js      # Переводы SR/RU
│       └── pages/        # Страницы интерфейса
├── requirements.txt
└── run.py
```

## База данных

По умолчанию используется SQLite (`prospel.db`). Для PostgreSQL укажите `DATABASE_URL` в `.env`:

```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/prospel
```

## API

- `POST /api/auth/login` — вход
- `GET /api/dashboard` — дашборд
- `GET/POST /api/income` — доходы (КПО)
- `GET/POST /api/clients` — клиенты
- `GET /api/payments` — платежи
- `GET /api/reports/kpo/csv` — экспорт КПО CSV
- `GET /api/reports/kpo/pdf` — экспорт КПО PDF
