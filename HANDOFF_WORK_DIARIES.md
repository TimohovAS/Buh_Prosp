# Handoff: Work Diaries Module

Дата handoff: 2026-07-10

## Что сделано

Добавлен раздел `Дневники работ` (`/work-diaries`) для учета выполненных работ и печатных отчетов:

- учет записей по проекту, работнику и датам;
- расчет часов по `start_time` / `end_time` или ручному количеству часов;
- обычные часы до 8 часов в день, сверхурочные после 8;
- фиксация ставки работника на момент записи;
- дневница, питание, проживание;
- материалы и оборудование по строкам;
- метаданные объекта для печатных форм;
- печатный `Грађевински дневник`;
- печатный отчет `Евиденција радних сати и утрошеног материјала`.

## Основные файлы

- `backend/models.py` - модели `WorkDiaryEntry`, `WorkDiaryMaterial`, `WorkDiaryProjectMeta`.
- `backend/schemas.py` - Pydantic-схемы для API.
- `backend/routers/work_diaries_router.py` - API `/api/work-diaries`.
- `backend/main.py` - подключение роутера.
- `alembic/versions/20260710_0003_work_diaries.py` - миграция БД.
- `frontend/src/pages/WorkDiaries.jsx` - страница раздела.
- `frontend/src/api.js` - API-клиент.
- `frontend/src/App.jsx` - маршрут `/work-diaries`.
- `frontend/src/components/Layout.jsx` - пункт меню.
- `frontend/src/index.css` - стили формы и печати.
- `frontend/src/i18n/ru.js`, `frontend/src/i18n/sr.js` - переводы.

## Архив базы

Архив для переноса базы лежит здесь:

```text
handoff/prospel_db_work_diaries_2026-07-10.zip
```

Архив создан встроенным backup-сервисом через SQLite snapshot. Внутри:

- `prospel.db`
- `meta.json`

## Как восстановить базу на другом компьютере

Перед восстановлением остановить backend/dev-сервер, если он запущен.

Из корня проекта:

```powershell
New-Item -ItemType Directory -Path .codex_tmp\db_restore -Force | Out-Null
Expand-Archive -LiteralPath .\handoff\prospel_db_work_diaries_2026-07-10.zip -DestinationPath .\.codex_tmp\db_restore -Force
Copy-Item -LiteralPath .\.codex_tmp\db_restore\prospel.db -Destination .\prospel.db -Force
.\venv\Scripts\python.exe -m alembic upgrade head
```

После этого можно запускать:

```powershell
.\start_dev.cmd
```

## Проверки, которые уже прошли

```text
cmd /c .\venv\Scripts\python.exe -m compileall backend
cmd /c .\venv\Scripts\python.exe -m ruff check backend alembic run.py create_admin.py
cmd /c .\venv\Scripts\python.exe -m pytest -q
cmd /c npm --prefix frontend run lint
cmd /c npm --prefix frontend run i18n:check
cmd /c npm --prefix frontend run build
cmd /c .\venv\Scripts\python.exe -m alembic -x database_url=sqlite:///./.codex_tmp/work_diary_migration.db upgrade head
```

Результаты:

- backend tests: `108 passed`;
- frontend build: успешно;
- i18n: `ru`, `sr` совпадают;
- миграция проверена на временной SQLite-базе;
- локальная dev-база `prospel.db` уже обновлена через `alembic upgrade head`.

## Что сказать новому чату Codex на ноутбуке

```text
Продолжи работу с проектом Buh_Prosp. Прочитай HANDOFF_WORK_DIARIES.md.
Изменения по разделу "Дневники работ" уже добавлены в код.
Проверь текущий git status/diff, восстанови базу из handoff/prospel_db_work_diaries_2026-07-10.zip при необходимости, запусти проверки и продолжай оттуда.
```

## Следующие возможные задачи

- Добавить редактирование записи дневника в UI, сейчас есть создание и удаление.
- Добавить экспорт отчета в Excel/PDF без печати браузером.
- Привязать записи дневника к существующим расходам/зарплатным выплатам, если нужно вести финансовое закрытие работ из этого раздела.
- Улучшить официальный шаблон строительного дневника под конкретные требования надзора/CEOP.
