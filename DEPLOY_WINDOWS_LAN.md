# ProspEl: запуск на Windows 11 в локальной сети

Сервер: `192.168.10.20`  
URL для клиентов: `http://192.168.10.20:5173`

## 1) Установить зависимости на сервере

- Python 3.10+
- Node.js 18+

Проверка:

```powershell
python --version
node --version
npm --version
```

## 2) Первичная настройка проекта

```powershell
cd D:\Program\ProspEl
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm install
cd ..
```

## 3) Настроить `.env`

1. Скопируйте `.env.example` в `.env`
2. Сгенерируйте секрет:

```powershell
.\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
```

3. Вставьте значение в `SECRET_KEY` в `.env`.

Минимальный пример:

```env
DATABASE_URL=sqlite+aiosqlite:///./prospel.db
SECRET_KEY=ваш_случайный_длинный_секрет
```

## 4) Открыть firewall

Запустите от имени администратора:

```powershell
.\setup_firewall_server.bat
```

## 5) Запустить приложение для работы по сети

```powershell
.\start_all_server.bat
```

Или вручную в двух окнах:

```powershell
.\start_backend_server.bat
.\start_frontend_server.bat
```

## 6) Проверки

На сервере:

- `http://127.0.0.1:8000/api/prospel` -> должен вернуться JSON со `status: ok`

На любом ПК в сети:

- `http://192.168.10.20:5173`

## 7) Вход и безопасность

- Первый вход: `admin / admin`
- Сразу смените пароль администратора
- Не храните реальный `SECRET_KEY` в git

## 8) Бэкап БД

Ручной запуск:

```powershell
powershell -ExecutionPolicy Bypass -File .\backup_db.ps1
```

Папка бэкапов по умолчанию: `D:\Program\ProspEl\backups`.

## 9) Обновления и доработки

Рекомендуемый процесс:

1. Сделать бэкап: `backup_db.ps1`
2. Обновить код
3. Перезапустить оба процесса (`backend` и `frontend`)
4. Проверить вход и ключевые разделы (доходы/расходы/отчеты)
