# ProspEl: запуск на Windows 11 в локальной сети

Сервер: `192.168.10.20`  
URL для клиентов: `http://192.168.10.20:5173`

Рекомендуемый режим: запуск как службы Windows (`ProspEl-Backend` и `ProspEl-Web`).

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

## 5) Установить службы (один раз, от администратора)

```powershell
.\install_services.cmd
```

Проверка:

```powershell
Get-Service ProspEl-Backend,ProspEl-Web
```

Обе службы должны быть в состоянии `Running`.

> В PowerShell используйте `sc.exe`, а не `sc` (в PowerShell `sc` — это алиас `Set-Content`).

## 6) Запуск/остановка служб

Запуск:

```powershell
Start-Service ProspEl-Backend
Start-Service ProspEl-Web
```

Остановка:

```powershell
Stop-Service ProspEl-Web
Stop-Service ProspEl-Backend
```

## 7) Проверки

На сервере:

- `http://127.0.0.1:8000/api/prospel` -> должен вернуться JSON со `status: ok`

На любом ПК в сети:

- `http://192.168.10.20:5173`

## 8) Вход и безопасность

- Первый вход: `admin / admin`
- Сразу смените пароль администратора
- Не храните реальный `SECRET_KEY` в git

## 9) Бэкап БД

Ручной запуск:

```powershell
powershell -ExecutionPolicy Bypass -File .\backup_db.ps1
```

Папка бэкапов по умолчанию: `D:\Program\ProspEl\backups`.

## 10) Обновления и доработки

После `git push` с рабочего ПК:

```powershell
.\update_prod.cmd
```

Скрипт делает:

1. Бэкап БД (если есть `backup_db.ps1`)
2. `git pull --ff-only origin main`
3. Установку backend/frontend зависимостей
4. Сборку frontend
5. Перезапуск служб и health-check

## 11) Если службы пока не используете

Ручной запуск (2 окна):

```powershell
.\start_backend_server.bat
.\start_frontend_server.bat
```

Удаление служб:

```powershell
.\remove_services.cmd
```
