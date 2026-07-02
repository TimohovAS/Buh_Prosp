# Handoff Context - Buh_Prosp

Дата обновления: 2026-07-02
Текущая ветка: `main`
Последний известный коммит: `18d6abc Warn on non-production hosts`
Рабочая папка: `D:\Work\Programming\Buh_Prosp`

Этот файл нужен, чтобы быстро продолжить работу без потери договоренностей, технических ограничений и текущего состояния.

## 1. Жесткие правила проекта

- Все изменения схемы БД делать только отдельными ручными скриптами в `manual_migrations`.
- Не добавлять автоматические runtime-миграции в startup приложения.
- Боевой сервер: `192.168.10.20`.
- Боевая БД на сервере: `D:\Program\ProspEl\prospel.db`.
- `!update_prod.cmd` делает backup, pull, install/build/restart, но не запускает ручные миграции БД.
- Перед ручной миграцией на сервере должен быть backup.
- Не трогать чужие незакоммиченные изменения без проверки diff.
- Локальный `.claude/settings.local.json` часто бывает изменен и не должен попадать в коммиты.
- Если появляется `.git\index.lock`, сначала проверить, что нет активного git-процесса, потом можно удалить stale lock.
- Для UI-лейблов не хранить текст как бизнес-данные: backend хранит код/тип, frontend переводит.

## 2. Текущее состояние рабочего дерева

На момент обновления handoff:

```text
## main...origin/main
 M .claude/settings.local.json
 M HANDOFF_CONTEXT.md
?? .codex_tmp/
```

Смысл:

- `main` синхронизирован с `origin/main`.
- `.claude/settings.local.json` - локальные настройки, не коммитить.
- `.codex_tmp/` - локальные диагностические файлы, не коммитить без явной просьбы.
- Из проектных файлов незакоммичен только сам `HANDOFF_CONTEXT.md`.

Перед любой новой задачей проверять:

```powershell
git status --short --branch
git diff --stat
```

## 3. Последние коммиты в `main`

```text
18d6abc Warn on non-production hosts
aebbf5e Show trip advance payout totals in cash register
2ae086d Remove cash register table title
823f75f Add selection summaries to ledger tables
5f5ca23 Avoid ambiguous cash withdrawal auto matching
a393cf1 Add cash register Excel export
37fa9a2 Reuse pending cash withdrawals for bank cash transfers
4c0a0fd Disable bank import cash withdrawal auto-link
792a0d2 Link pending cash withdrawals from matched expenses
3b10b8f Harden income item backfill mismatches
d9e4d53 Improve income invoice item entry
651d21b Add income invoice items and eFaktura export
```

## 4. Последние важные решения и изменения

### 4.1. Non-production banner

- В UI добавлен заметный красный баннер, если приложение открыто не на боевом host.
- Боевой host по умолчанию: `192.168.10.20`.
- Можно переопределить список боевых адресов через `VITE_PRODUCTION_HOSTS` (через запятую).
- Ключевые файлы:
  - `frontend/src/components/Layout.jsx`
  - `frontend/src/index.css`
  - `frontend/src/i18n.js`

### 4.2. Доходы, позиции фактур и eFaktura

- В доходах есть таблица позиций фактуры (`income_items`).
- Create/update дохода пересобирают позиции и считают `amount_rsd` из строк.
- Подсказки позиций берутся из прошлых фактур, legacy-описаний и договоров.
- В UI подсказки разделены на:
  - ранее фактурисали текущему контрагенту;
  - все клиенты и проекты.
- Подсказки при вводе показываются в выпадающем списке, справа в модалке есть история по контрагенту.
- Ручной ввод контрагента в доходах убран: выбирать только из справочника.
- Проекты в форме дохода ограничены выбранным клиентом и `Razno`.
- Для строк фактуры добавлены номер позиции, выбор единиц, неinput-итог по строке и итоговая сумма справа под суммами позиций.
- Модалка дохода не должна закрываться по клику вне окна.

eFaktura export выбран как non-VAT для паушала:

- `CustomizationID`: `urn:cen.eu:en16931:2017#compliant#urn:mfin.gov.rs:srbdt:2021`.
- `ProfileID` Peppol нужно убирать, он не из сербского CIUS.
- `InvoiceTypeCode = 380`.
- `EndpointID schemeID = 9948`.
- Не копировать `TaxExemptionReasonCode = PDV-RS-11-1-4` из примера: это не основание для паушала. Если точный код "није у систему ПДВ-а" не подтвержден по шифарнику, лучше оставить TODO и свободный `TaxExemptionReason`, чем зашить неверный код.

Ключевые файлы:

- `backend/models.py`
- `backend/schemas.py`
- `backend/routers/income_router.py`
- `backend/income_efaktura_xml.py`
- `backend/scripts/migrate_v26_income_items.py`
- `backend/scripts/backfill_income_items_from_efaktura.py`
- `manual_migrations/v26_income_items.cmd`
- `manual_migrations/backfill_income_items_from_efaktura.cmd`
- `frontend/src/pages/Income.jsx`
- `frontend/src/i18n.js`

### 4.3. Backfill старых позиций доходов из eFaktura

Скрипт:

```powershell
manual_migrations\backfill_income_items_from_efaktura.cmd
```

Важные флаги:

```powershell
manual_migrations\backfill_income_items_from_efaktura.cmd --dry-run
manual_migrations\backfill_income_items_from_efaktura.cmd --income-id 24 --income-id 25
manual_migrations\backfill_income_items_from_efaktura.cmd --clear-line-total-mismatches --income-id 27 --income-id 35
```

Что уже было сделано по пользовательскому логу:

- Основной backfill нашел 21 candidate.
- 19 записей обновились сразу.
- #24 и #25 сначала были skipped из-за расхождения `0012` / `12` / `012`, затем обновились после hardened matching.
- #27 и #35 имели line total mismatch из-за удвоенных строк; их позиции были очищены через `--clear-line-total-mismatches`.

При повторном запуске сначала делать `--dry-run`.

### 4.4. Банк и наличка

- На странице `Банк` отключены автоматические matching-сценарии снятия налички.
- Снятие налички должно идти через временное пополнение/связку с реестром налички, а не автоматически как расход на странице банка.
- Важная причина: банковская выписка может показать снятие 26.06 как проведенное 30.06, и автоматическое закрытие может ошибочно убрать несколько временных пополнений.
- Для снятий налички используется проект `_Gotovina / Наличка`.
- В реестр налички добавлен Excel export.
- Кнопка `Добавить из банка` из реестра налички убрана.
- Заголовок строки `Операции по наличке` в карточке таблицы убран.
- В реестре налички дата расширена и не переносится.
- В реестре налички добавлены checkbox-выделение строк и сумма выделения.
- На страницах с массовым выделением добавлена общая сводка выделенных строк:
  - `Банк`: приход / расход / нетто;
  - `Наличка`: приход / расход / нетто;
  - `Доходы`: сумма;
  - `Расходы`: сумма;
  - `Импорт выписки`: сумма.
- Для строки `Аванс за командировку` в реестре налички под описанием показываются `Начислено` и `Остаток`.

Ключевые файлы:

- `backend/cash_service.py`
- `backend/routers/bank_transactions_router.py`
- `backend/routers/cash_router.py`
- `backend/routers/workers_router.py`
- `frontend/src/pages/BankTransactions.jsx`
- `frontend/src/pages/CashRegister.jsx`
- `frontend/src/components/SelectionSummary.jsx`
- `frontend/src/index.css`

### 4.5. Работники и выплаты

- Есть список работников: постоянные и временные.
- Схемы оплаты: за выход, еженедельно, раз в месяц.
- Командировки рассчитываются по датам: дни командировки и ночи выводятся автоматически.
- Гостиница считается как `стоимость ночи * количество ночей`.
- В выплатах есть типы: обычная, еженедельная, месячная, аванс за командировку, окончательный расчет командировки.
- Окончательный расчет командировки должен предзаполняться из ранее созданного аванса.
- Редактирование выплаты из реестра налички открывает форму выплаты, а не обычную форму наличного расхода.

Ключевые файлы:

- `backend/models.py`
- `backend/routers/workers_router.py`
- `backend/routers/cash_router.py`
- `frontend/src/pages/Workers.jsx`
- `frontend/src/pages/CashRegister.jsx`
- `frontend/src/i18n.js`

### 4.6. eFaktura sync

- eFaktura синхронизация поддерживает входящие и исходящие документы.
- PDF не сохраняются на сервере. Если включена галка сохранения PDF, frontend скачивает PDF на компьютер пользователя.
- Настройки eFaktura API вынесены в `Настройки / eFaktura API`.
- Исходящие фактуры со статусами `Storno`, `Cancelled`, `Mistake` не должны создаваться как обычный доход.
- Уже импортированный доход по сторнированной исходящей eFaktura отменяется при синхронизации, если по нему нет оплат.
- Для исходящих фактур текущий статус дополнительно читается через `GET /api/publicApi/sales-invoice?invoiceId=...`, а не только через `/sales-invoice/changes`.

Ключевые файлы:

- `backend/efaktura_service.py`
- `backend/routers/efaktura_router.py`
- `frontend/src/pages/Efaktura.jsx`

### 4.7. Входящие фактуры

- Детальная модалка входящей фактуры переработана под компактный layout без лишнего скроллинга.
- Блоки связанного расхода и банковской транзакции обернуты в единый визуальный стиль.
- Кнопки действий вынесены в правую колонку в верхнем summary-блоке.
- Входящая фактура может закрываться банком, наличкой и взаимозачетом.
- Settlement должен идти через сервис, не прямой записью в таблицу.

### 4.8. Кассовые чеки

- Импорт по QR URL с `suf.purs.gov.rs`.
- Сохранение ссылки на чек и открытие оригинала.
- Позиции чека сохраняются.
- Создание расхода из чека.
- Ручная привязка чека к расходу.
- Для наличного чека можно создать `Expense(source="cash", status="paid")` и `CashEntry(direction="out", entry_type="expense")`.
- Если чек ошибочно отмечен наличным, есть возврат в ожидание банка.
- Поиск чеков учитывает суммы, проект, продавца, ПИБ, адрес, номер, способ оплаты, статус, id связанных расхода/банка/налички.

### 4.9. Займы

- Займы вынесены в отдельные сущности `counterparty_loans` и `counterparty_loan_movements`.
- Тело займа не создает `Income`/`Expense` и не попадает в P&L.
- В cash flow займы отражаются как финансирование.
- Банковская строка связывается с движением займа через `matched_type = "loan_movement"`.
- Собственные средства показываются отдельной read-only секцией из `BankTransaction` с `matched_type = "owner_funds"`.

### 4.10. Android-приложение для QR

- Папка `android-app`.
- Приложение сканирует QR кассового чека и отправляет URL в backend.
- После успешного сканирования: vibration/beep, auto-submit, очистка URL.

## 5. Ручные миграции и скрипты

Из известных ручных миграций/скриптов:

- `manual_migrations\v18_expense_items.cmd`
- `manual_migrations\v19_counterparty_loans.cmd`
- `manual_migrations\v26_income_items.cmd`
- `manual_migrations\backfill_income_items_from_efaktura.cmd`

Проверка перед запуском:

```powershell
manual_migrations\v18_expense_items.cmd --dry-run
manual_migrations\v19_counterparty_loans.cmd --dry-run
manual_migrations\v26_income_items.cmd --dry-run
manual_migrations\backfill_income_items_from_efaktura.cmd --dry-run
```
Запуск на проде только после backup и dry-run.

## 6. Известные инварианты

- Кассовый чек сам по себе является документом подтверждения расхода.
- Если чек оплачен картой, связанный расход может быть `planned/waiting_bank` до появления банковской транзакции.
- Если чек оплачен наличкой, расход должен быть `Expense(source="cash", status="paid")`, а чек должен иметь `cash_entry_id`.
- Ошибочный cash-mark для чека должен удалять только связанную `CashEntry` и возвращать расход в `planned`.
- Банковские списания и расходы сравнивать по абсолютной сумме: `abs(bank.amount) == expense.amount`.
- Проект у чека и связанного расхода должен совпадать.
- Если пользователь меняет проект у расхода, связанный чек получает тот же проект.
- Если договор выбран в форме дохода/расхода, проект должен подставляться из договора.
- Тело займа не является доходом/расходом.
- Снятия налички не матчить автоматически на странице банка.
- Временные пополнения налички могут быть неоднозначными из-за даты проводки в банковской выписке; при сомнении проверять вручную.

## 7. Что проверить на проде

- После обновления сервера проверить, что non-production banner НЕ показывается на `192.168.10.20`.
- Проверить, что на локальном/тестовом адресе banner показывается.
- Запустить eFaktura sync и проверить, что сторнированные исходящие фактуры не остаются `issued`.
- Проверить, выполнены ли нужные ручные миграции на сервере.
- Проверить, что доходы с позициями корректно экспортируются в XML non-VAT.
- Проверить, что подсказки позиций в доходах работают по текущему контрагенту и глобально.
- Проверить временные пополнения налички: банковское снятие должно закрывать только соответствующее временное пополнение.
- Проверить Excel export реестра налички.
- Проверить строку `Аванс за командировку`: под описанием должны отображаться `Начислено` и `Остаток`.

## 8. Полезные команды

Backend:

```powershell
.\venv\Scripts\python.exe -m compileall backend
```

Frontend:

```powershell
cmd /c npm --prefix frontend run build
```

Git:

```powershell
git status --short --branch
git log --oneline -12
```

Manual scripts:

```powershell
manual_migrations\v26_income_items.cmd --dry-run
manual_migrations\backfill_income_items_from_efaktura.cmd --dry-run
```
