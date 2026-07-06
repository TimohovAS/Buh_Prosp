# План: распил страниц-гигантов и общий компонент сортируемых заголовков

Цель: убрать дублирование табличных заголовков и раздробить страницы-гиганты
(CashRegister 2223 строк, BankTransactions 2180, IncomingInvoices 1774,
Settings 1761, Income 1641, Expenses 1580, Receipts 1554) на компоненты.
Ориентир: страница ≤ 500 строк.

## Правила (для каждого шага)

- Только перестановка кода, ноль изменений поведения. Никаких «заодно улучшу».
- Один коммит = одна страница или один компонент. Никогда не смешивать
  создание общего компонента и его внедрение на >2 страницах в одном коммите.
- Перед коммитом: `npm run lint` (zero-warnings), `npm run format:check`,
  `npm run i18n:check`, `npm run build`.
- После каждой страницы — ручная проверка в браузере: страница рендерится,
  клик по заголовку сортирует (повторный — меняет направление), ресайз
  колонок за край заголовка работает, поиск и фильтры живы, модалки
  открываются. Хук ресайза (`useResizableTableColumns`) работает по DOM
  (`.table-wrap table th`) — разметка th/thead должна остаться эквивалентной.
- Не трогать: `useResizableTableColumns`, CSS `.table-wrap`, `useListPageState`.

## Фаза 1 — `components/SortableTh.jsx` + пилот на двух малых страницах

Сейчас на каждой странице повторяется:

```jsx
<th className="col-date" style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>
  {tr('date')} <SortIndicator active={sortCol === 'date'} asc={sortAsc} />
</th>
```

Сделать компонент:

```jsx
<SortableTh col="date" sortCol={sortCol} sortAsc={sortAsc} onSort={toggleSort} className="col-date">
  {tr('date')}
</SortableTh>
```

- Рендерит ровно тот же `<th>` (className, cursor, onClick, SortIndicator,
  поддержка `style` для `textAlign: 'right'`). DOM-эквивалентность обязательна
  (ресайз и sticky-CSS завязаны на th).
- Пилот: перевести Clients и Workers (самые маленькие списки). Один коммит —
  компонент + пилот.

## Фаза 2 — SortableTh на остальные списки

По одному коммиту на 1–2 страницы: Contracts, Projects, PlannedExpenses,
Obligations, CounterpartyLoans, Receipts, IncomingInvoices, Income, Expenses,
BankTransactions, CashRegister. Механическая замена th → SortableTh, ничего
больше. После каждой — браузерная проверка сортировки/ресайза.

## Фаза 3 — распил гигантов (по одной странице за сессию)

Порядок: Income → Expenses → IncomingInvoices → Receipts → BankTransactions →
CashRegister → Settings. (Income/Expenses первыми: самые «денежные», но их
бэкенд уже под тестами, а фронт проверяется руками по чек-листу выше.)

Для каждой страницы одинаковый рецепт, маленькими коммитами:

1. Вынести модалки в `src/components/<domain>/` (например
   `income/IncomeFormModal.jsx`, `income/PaymentDetailsModal.jsx`).
   Пропсы — явные (данные + колбэки), без проброса всего состояния страницы.
2. Вынести чистые вычисления (фильтрация/суммы/лейблы) в
   `src/utils/<domain>.js`, если они не завязаны на состояние.
3. Формы с логикой — в хук `use<Domain>Form.js`, если форма > ~100 строк.
4. Страница остаётся: состояние списка, загрузка, фильтры, таблица, монтаж
   модалок.

Settings пилить по вкладкам (Enterprise/Users/Categories/Backup/eFaktura —
каждая вкладка в свой компонент) — это самый безопасный из гигантов, можно
взять первым, если хочется потренироваться перед денежными.

## Фаза 4 (опционально, потом) — полноценный `<DataTable>`

Только после фаз 1–3 и только если останется желание: колоночная конфигурация
(key/label/render/align), встроенные sticky+sort. Новый компонент для НОВЫХ
страниц; массовую миграцию существующих не делать — SortableTh уже убирает
основное дублирование при нулевом риске.

## Definition of done (фазы 1–3)

- Ни одной страницы > 800 строк (жёсткая цель — 500, для CashRegister и
  BankTransactions допустимо приближение).
- Заголовки таблиц — только через SortableTh.
- Все проверки CI зелёные, поведение таблиц не изменилось (сортировка,
  ресайз, поиск, липкие заголовки, модалки).

## Находки (заполнять по ходу)

- (пусто)
