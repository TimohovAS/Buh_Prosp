# План реализации: позиции расходов и улучшение интерфейса расходов

## Цель

Сделать страницу `Расходы` такой же информативной и удобной, как `Кассовые чеки`:

- расход может состоять из нескольких позиций;
- позиции можно добавлять, редактировать и удалять;
- сумма расхода считается по позициям;
- кассовый чек является документом-источником расхода;
- в модалке расхода не нужно дублировать таблицу `Позиции чека`;
- вместо дублирования нужна кнопка перехода к связанному чеку;
- старые расходы без позиций должны продолжать работать.

## Важное состояние перед стартом

Перед выполнением этого плана нужно начать из чистой ветки от актуального `main`.

Если в рабочем дереве уже есть незавершённые изменения в:

- `backend/models.py`
- `backend/routers/expenses_router.py`
- `backend/schemas.py`

то их нельзя автоматически считать правильной реализацией. Нужно либо аккуратно перенести нужные идеи вручную, либо начать заново из чистого состояния.

Рекомендуемая ветка:

```powershell
git switch main
git pull
git switch -c feature/expense-items-ui
```

## Архитектурное решение

Добавляем отдельную таблицу `expense_items`.

Почему не использовать напрямую `purchase_receipt_items`:

- не каждый расход создаётся из кассового чека;
- расход должен иметь собственную редактируемую структуру строк;
- чек остаётся первичным документом, а расход остаётся бухгалтерской операцией;
- при создании расхода из чека позиции чека копируются в позиции расхода;
- после этого расход можно редактировать независимо от исходного чека, если нужно.

## Модель данных

Добавить модель `ExpenseItem`.

Файл:

- `backend/models.py`

Сущность:

```python
class ExpenseItem(Base):
    __tablename__ = "expense_items"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True)
    line_no = Column(Integer, nullable=False, default=1)
    name = Column(String(500), nullable=False)
    quantity = Column(Numeric(14, 3), nullable=True)
    unit_price = Column(Numeric(14, 2), nullable=True)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    expense = relationship("Expense", back_populates="items", foreign_keys=[expense_id])
```

В `Expense` добавить:

```python
items = relationship(
    "ExpenseItem",
    back_populates="expense",
    cascade="all, delete-orphan",
    order_by="ExpenseItem.line_no.asc()",
)
```

## Ручная миграция

Миграции базы в этом проекте выполняются только вручную через `manual_migrations`.

Добавить:

- `backend/scripts/migrate_v18_expense_items.py`
- `manual_migrations/v18_expense_items.cmd`

Миграция должна:

1. Создать таблицу `expense_items`, если её нет.
2. Создать индекс `ix_expense_items_expense_id`.
3. Перенести позиции из кассовых чеков в расходы, если:
   - `purchase_receipts.expense_id IS NOT NULL`;
   - у расхода ещё нет строк в `expense_items`.

SQL-логика переноса:

```sql
INSERT INTO expense_items (
    expense_id,
    line_no,
    name,
    quantity,
    unit_price,
    total_amount,
    note,
    created_at
)
SELECT
    pr.expense_id,
    pri.line_no,
    pri.name,
    pri.quantity,
    pri.unit_price,
    pri.total_amount,
    NULL,
    CURRENT_TIMESTAMP
FROM purchase_receipts pr
JOIN purchase_receipt_items pri ON pri.receipt_id = pr.id
WHERE pr.expense_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM expense_items ei
      WHERE ei.expense_id = pr.expense_id
  )
ORDER BY pr.expense_id, pri.line_no;
```

Миграция должна иметь `--dry-run`.

После деплоя на сервере выполнить вручную:

```powershell
manual_migrations\v18_expense_items.cmd
```

## Backend API

### Схемы

Файл:

- `backend/schemas.py`

Добавить:

```python
class ExpenseItemCreate(BaseModel):
    name: str
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    total_amount: Decimal = Decimal("0.00")
    note: Optional[str] = None


class ExpenseItemResponse(ExpenseItemCreate):
    id: int
    line_no: int

    class Config:
        from_attributes = True
```

В `ExpenseCreate` добавить:

```python
items: list[ExpenseItemCreate] = Field(default_factory=list)
```

В `ExpenseUpdate` добавить:

```python
items: Optional[list[ExpenseItemCreate]] = None
```

В `ExpenseDetailResponse` добавить:

```python
items: list[ExpenseItemResponse] = Field(default_factory=list)
```

Важно: если Pydantic ругается на forward refs, объявить `ExpenseItemCreate` до `ExpenseCreate`.

### Роутер расходов

Файл:

- `backend/routers/expenses_router.py`

Добавить helper-функции:

- нормализация строк расхода;
- пересчёт суммы по строкам;
- автосборка описания из строк;
- создание `ExpenseItem` ORM-объектов.

Правила:

- если `items` переданы и не пустые, `amount = sum(items.total_amount)`;
- если `description` пустой, собрать его из названий строк через `; `;
- если строка полностью пустая, игнорировать;
- если строка содержит сумму/количество/цену, но нет названия, вернуть `HTTP 400`;
- при `PATCH` список `items` полностью заменяет старые строки;
- если `items` не передан в `PATCH`, старые строки не трогать.

В `GET /expenses/{id}` нужно загрузить:

```python
selectinload(Expense.items)
selectinload(Expense.purchase_receipt).selectinload(PurchaseReceipt.items)
```

При `admin delete` расхода строки `ExpenseItem` должны удаляться каскадом. Если каскад в SQLite не гарантирован, добавить явное удаление:

```python
await db.execute(delete(ExpenseItem).where(ExpenseItem.expense_id.in_(expense_ids)))
```

### Создание расхода из кассового чека

Файл:

- `backend/receipt_service.py`

В `create_expense_from_receipt` после создания `Expense` скопировать строки из `PurchaseReceipt.items`:

```python
expense.items = [
    ExpenseItem(
        line_no=item.line_no,
        name=item.name,
        quantity=item.quantity,
        unit_price=item.unit_price,
        total_amount=item.total_amount,
        note=None,
    )
    for item in (receipt.items or [])
]
```

Если чек создаёт расход, то расход должен появляться в `Расходы` сразу.

Статус чека:

- `matched` / `waiting_bank` должен быть производным от связанного расхода и банка;
- нельзя создавать чек без расхода, если это обычный кассовый чек продажи.

## Frontend

### Страница расходов

Файл:

- `frontend/src/pages/Expenses.jsx`

Добавить state:

```javascript
const [expenseLines, setExpenseLines] = useState([makeExpenseLine()])
```

Строка расхода:

```javascript
{
  key,
  name,
  quantity,
  unit_price,
  total_amount,
  note,
}
```

Добавить функции:

- `makeExpenseLine(overrides)`
- `normalizeExpenseLine(line)`
- `buildExpenseDescriptionFromLines(lines)`
- `getExpenseDisplayLines(expense)`
- `updateExpenseLine(key, field, value)`
- `addExpenseLine()`
- `removeExpenseLine(key)`
- `hydrateExpenseLines(expense)`

### Добавление расхода

В модалке добавления расхода:

- оставить основные поля: дата, категория, проект, договор, примечание;
- добавить таблицу позиций;
- кнопку `Добавить позицию`;
- кнопку удаления строки;
- сумма расхода считается по позициям;
- поле `Сумма` сделать readonly, если есть позиции;
- если позиций нет, сумма вводится вручную;
- если описание пустое, оно собирается из строк.

### Редактирование расхода

В модалке редактирования:

- загрузить полный расход через `api.expenses.get(id)`;
- показать таблицу позиций;
- разрешить добавлять/удалять/редактировать строки;
- при сохранении отправлять `items`;
- если `items` отправлены, backend полностью заменяет строки.

### Просмотр расхода

Текущую модалку сделать более информативной:

Левая часть:

- дата;
- сумма;
- статус;
- проект;
- категория;
- договор;
- описание;
- номер платёжного поручения;
- примечание.

Правая часть:

- `Изменить`;
- `Удалить`;
- `Админ: удалить запись`;
- если есть связанный чек: `Открыть чек`;
- если есть связанный банк: `Открыть банк`;
- если есть связанная входящая фактура: `Открыть фактуру`.

Нижняя часть:

- таблица `Строки расхода`;
- если есть `expense.items`, показывать их;
- если нет `expense.items`, показать одну fallback-строку из старых полей расхода.

Важно: не показывать отдельный блок `Позиции чека`. Это дублирует данные. Для чека должна быть только ссылка/кнопка открытия.

### Переход к связанному чеку

Файлы:

- `frontend/src/pages/Expenses.jsx`
- `frontend/src/pages/Receipts.jsx`

В `Expenses.jsx`:

```javascript
navigate('/receipts', { state: { openReceiptId: receipt.id } })
```

В `Receipts.jsx` добавить обработку `location.state.openReceiptId`:

- перейти на страницу `Кассовые чеки`;
- открыть модалку нужного чека;
- очистить `location.state`, чтобы модалка не открывалась повторно после обновления состояния.

### Локализация

Файл:

- `frontend/src/i18n.js`

Добавить ключи:

- `expensePositions`
- `addExpensePosition`
- `removeExpensePosition`
- `expenseLineName`
- `expenseLinesTotal`
- `openReceipt`

Русские значения:

- `Строки расхода`
- `Добавить позицию`
- `Удалить позицию`
- `Название позиции`
- `Итого по строкам`
- `Открыть чек`

## CSS

Файл:

- `frontend/src/index.css`

Добавить стили:

- таблица строк расхода;
- редактор строк расхода;
- responsive-режим для узких экранов;
- кнопки связанных документов в правом блоке.

Ориентир:

- визуально использовать стиль `Кассовые чеки`;
- таблица должна быть широкой и читабельной;
- в мобильном/узком окне поля не должны обрезаться.

## Проверки

Backend:

```powershell
.\venv\Scripts\python.exe -m compileall backend
```

Frontend:

```powershell
npm --prefix frontend run build
```

Ручные сценарии:

1. Создать расход без позиций.
2. Создать расход с 2-3 позициями.
3. Проверить автосумму.
4. Проверить автосборку описания.
5. Открыть расход и увидеть строки.
6. Отредактировать строки расхода.
7. Удалить одну строку.
8. Создать расход из кассового чека.
9. Проверить, что позиции чека скопировались в расход.
10. Открыть расход, связанный с чеком.
11. Проверить, что отдельный блок `Позиции чека` не дублируется.
12. Нажать `Открыть чек` из расхода.
13. Проверить связь чек → расход → банк.
14. Проверить старые расходы без строк.

## Критерии готовности

Реализация готова, если:

- база мигрируется вручную через `manual_migrations`;
- старые данные не ломаются;
- расходы из чеков сразу имеют строки;
- ручные расходы могут иметь строки;
- сумма по строкам считается корректно;
- UI расхода понятный и не дублирует чек;
- `npm build` проходит;
- `compileall backend` проходит;
- изменения закоммичены и запушены в `main`.

## Коммит

Рекомендуемый коммит:

```powershell
git add backend/models.py backend/schemas.py backend/routers/expenses_router.py backend/receipt_service.py backend/scripts/migrate_v18_expense_items.py manual_migrations/v18_expense_items.cmd frontend/src/pages/Expenses.jsx frontend/src/pages/Receipts.jsx frontend/src/i18n.js frontend/src/index.css EXPENSE_ITEMS_IMPLEMENTATION_PLAN.md
git commit -m "Add editable expense line items"
git push origin main
```
