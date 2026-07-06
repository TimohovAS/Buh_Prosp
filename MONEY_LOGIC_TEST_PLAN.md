# План: тесты на денежную логику (bank_matching, state_machine, allocations)

Цель: характеризационные тесты на самые опасные участки перед дальнейшим выносом
сервисов. Тесты фиксируют **текущее** поведение, а не желаемое: если тест вскрыл
странность — записать её в секцию «Находки» внизу этого файла и зафиксировать
текущее поведение в тесте с комментарием, НЕ менять продакшен-код в том же коммите.

## Правила для всех фаз

- Один коммит = одна фаза (или меньше). Никаких рефакторингов продакшен-кода в
  коммитах с тестами.
- Перед каждым коммитом: `pytest -q -W default` (без warnings), `ruff check backend
  alembic run.py create_admin.py`, `ruff format --check backend alembic run.py create_admin.py`.
- Паттерн фикстуры уже есть в `backend/tests/test_incoming_invoice_service.py`:
  in-memory `sqlite+aiosqlite`, `Base.metadata.create_all`, `async_sessionmaker(expire_on_commit=False)`.
- Даты в тестах фиксированные (никаких `date.today()` в ассертах).

## Фаза 0 — общий conftest (15 минут)

Фикстура `db_session` сейчас продублирована в `test_incoming_invoice_service.py` и
`test_expense_service.py`. Вынести в `backend/tests/conftest.py`, убрать дубли.
Туда же — фабрики-помощники, которые понадобятся дальше:

- `make_project(db, code="PR-1", status="active")`
- `make_unassigned_project(db)` — код `INT-UNASSIGNED` (нужен потокам матчинга,
  они зовут `get_unassigned_project_id`)
- `make_income(db, amount, status="issued", ...)`
- `make_expense(db, amount, status="planned", ...)`
- `make_bank_tx(db, amount, direction, status="unmatched", ...)`

## Фаза 1 — state_machine.py (чистые функции, без БД; самая дешёвая и ценная)

Файл: `backend/tests/test_state_machine.py`. Объекты — обычные модели без сессии
(функции принимают `Any`). Сценарии:

**Income:**
- `initialize_income_status`: issued без paid_date; paid требует paid_date
  (`_require_date` кидает без даты); неизвестный статус — ошибка.
- `transition_income_status`: разрешённые переходы issued→partial→paid,
  issued/partial→cancelled; запрещённые (paid→issued, cancelled→*) кидают
  `InvalidStatusTransition`.
- `reconcile_income_payment_state`: paid_amount=0 → issued; 0 < paid < total →
  partial (paid_date сбрасывается в None); paid ≥ total (и > 0) → paid, причём
  БЕЗ paid_date кидает (проверено в коде: `_require_date`); на cancelled income —
  `InvalidStatusTransition` (терминальный статус); повторный вызов с теми же
  данными идемпотентен; уменьшение paid_amount возвращает paid → partial.
- `cancel_income`: из issued и partial — ок; из paid — поведение зафиксировать
  (что бы оно ни было).

**Expense:**
- `mark_expense_paid`: planned→paid с датой; `allow_same=True` повторно — не
  падает; без даты — ошибка.
- `reopen_expense_for_unmatch`: paid→? (зафиксировать целевой статус и что
  происходит с paid_date).
- `ensure_expense_can_reverse`: paid — ок; planned/reversed/уже сторнированный
  (`reversed_expense_id` установлен) — ошибка.

**MonthlyObligation:** `mark_obligation_paid_status`, `refresh_obligation_due_status`
(до/после дедлайна с фиксированным `today=`), `restore_obligation_after_payment_reset`.

**IncomingInvoice:** `reconcile_incoming_invoice_status`: settled_amount 0 / частично /
полностью / больше total; `cancel_incoming_invoice` из paid — зафиксировать.

Ориентир: 20–25 мелких тестов.

## Фаза 2 — чистые хелперы bank_matching_service (без БД)

Файл: `backend/tests/test_bank_matching_helpers.py`.

- `_matches_counterparty_name`: точное совпадение; ≥2 общих слова из первых 4;
  подстрока в обе стороны; пустые имена → False; регистр/пробелы.
- `_matches_receipt_seller`: seller в purpose/bank_reference; слова короче 3 букв
  игнорируются.
- `_normalize_digits`: `"265-0000001234-38" → "265000000123438"`, None → "".
- `_get_income_available_amount` и `_merge_income_payment_summary`: остаток к
  оплате при частичных аллокациях (это сердце частичных оплат — не пропускать).

## Фаза 3 — match_transaction / unmatch_transaction (с БД)

Файл: `backend/tests/test_bank_matching_flows.py`. Это главная фаза.

**match income:**
- unmatched tx + issued income → tx.status="matched", matched_type/id выставлены,
  вызван reconcile: income получает paid_amount/status по сумме tx.
- tx.amount < income.amount_rsd → income становится partial (частичная оплата).
- project: у income без проекта появляется проект (unassigned или из tx) —
  зафиксировать выбор из `tx.project_id or income.project_id or unassigned`.

**match expense:**
- planned expense → paid с paid_date=tx.date; bank_reference переносится, если у
  расхода пустой (и НЕ затирается, если уже был).
- перенос project_id + сброс contract_id при несовпадении проекта договора
  (`_clear_contract_if_project_mismatch`).

**match obligation:** unpaid obligation → mark_obligation_paid, tx остаётся со
статусом, который выставляет `mark_obligation_paid` (зафиксировать: tx.status
после — какой?).

**Ошибки:** несуществующий tx / income / expense / obligation → ValueError;
повторный матч уже matched tx → ValueError "already matched"; неизвестный
match_type → ValueError.

**unmatch_transaction:** после match expense → unmatch возвращает expense в
исходный статус (`reopen_expense_for_unmatch`), tx снова unmatched,
matched_type/id очищены; после match income → аллокации сняты, income
реконсилирован обратно (paid_amount уменьшился, статус пересчитан).

## Фаза 4 — save_income_allocation / detach / reconcile (частичные оплаты)

Файл: тот же `test_bank_matching_flows.py` или отдельный.

- `save_income_allocation`: одна tx на два income (разбивка суммы) — обе записи
  созданы, каждый income реконсилирован на свою долю; сумма аллокаций больше
  суммы tx — зафиксировать поведение (ошибка или кламп); нулевая/отрицательная
  аллокация — зафиксировать.
- `detach_income_transaction_link`: у income с двумя tx отвязали одну → paid_amount
  уменьшился ровно на её долю, статус paid→partial.
- `reconcile_income_payment_links` идемпотентен: два вызова подряд не меняют
  paid_amount повторно.
- `get_bank_transaction_allocation_stats`: остаток нераспределённой суммы tx.

## Фаза 5 — низкий приоритет (smoke)

- `classify_transaction_as_owner_funds`: happy-path + запрет реклассификации
  (`_ensure_expense_can_reclassify_to_owner_funds` кидает, когда нельзя).
- `suggest_matches`: один smoke-тест — на tx с очевидным кандидатом возвращает
  его в секции suggested (точный скоринг не фиксировать, он эвристический).

## Definition of done

- Фазы 0–4 закоммичены отдельными коммитами, CI зелёный после каждого.
- `pytest -q -W default` — без warnings.
- Ни одного изменения в backend/*.py вне tests/ (кроме согласованных находок).

## Находки (заполнять по ходу)

- (пусто)
