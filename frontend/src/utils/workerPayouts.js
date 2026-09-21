// Общее для вкладки «Выплаты» и карточки статистики работника: цвета рядов,
// подписи типов выплат и сборка истории. Держим в одном месте, чтобы страница
// и модалка не разъезжались по оформлению и терминологии.
import { tr } from '../i18n'
import { formatMoney2 } from './formatters'

// Тройка проверена на различимость при дальтонизме на тёмной подложке карточки;
// порядок сегментов и подписи рядом несут то же самое и без цвета.
export const PAYOUT_SERIES_COLORS = { regular: '#3b82f6', purchase: '#a855f7', trip: '#d97706' }

export const TRIP_PAYOUT_TYPES = new Set(['trip_advance', 'trip_final'])

const PAYOUT_LABELS = {
  regular: 'workerPayoutRegular',
  weekly: 'workerPayoutWeekly',
  monthly: 'workerPayoutMonthly',
  purchase: 'workerPayoutPurchase',
  trip_advance: 'workerPayoutTripAdvance',
  trip_final: 'workerPayoutTripFinal',
}

// Командировочные подписаны коротко: цвет метки и период работ рядом уже
// говорят, что это командировка, а полное название разрывает строку на три.
const PAYOUT_CHIP_LABELS = {
  purchase: 'workerPayoutPurchaseShort',
  trip_advance: 'workerPayoutTripAdvanceShort',
  trip_final: 'workerPayoutTripFinalShort',
}

export const payoutMoney = (value) => `${formatMoney2(value)} RSD`

export const sumPayoutMoney = (items, field) =>
  items.reduce((sum, item) => sum + Math.round(Number(item[field]) * 100), 0) / 100

const cents = (value) => Math.round(Number(value || 0) * 100)

// Доход работника вне командировок: обычная выплата плюс купленное ему в счёт
// зарплаты — деньгами оно не выдавалось, но получено им же.
export const payoutNonTrip = (item) => (cents(item.regular_paid) + cents(item.purchase_paid)) / 100

// Заработок работника — доход без командировок и командировочные без стоимости
// жилья: гостиницу оплачивают отелю, и в заработке она не участвует.
export const payoutEarned = (item) =>
  (cents(item.regular_paid) + cents(item.purchase_paid) + cents(item.trip_paid)) / 100

export const sumPayoutEarned = (items) => items.reduce((sum, item) => sum + payoutEarned(item), 0)

export const payoutTypeLabel = (type) => (PAYOUT_LABELS[type] ? tr(PAYOUT_LABELS[type]) : type)

export const payoutTypeChipLabel = (type) =>
  PAYOUT_CHIP_LABELS[type] ? tr(PAYOUT_CHIP_LABELS[type]) : payoutTypeLabel(type)

// Служебные пометки вида days=3 в примечание не попадают.
export const visiblePayoutNote = (note) => (note && !/^days=\d/.test(note.trim()) ? note : '')

// История приходит по убыванию даты, поэтому записи одного дня идут подряд
// и собираются в группы одним проходом.
export const groupPayoutsByDate = (items) => {
  const groups = []
  for (const payout of items || []) {
    const group = groups[groups.length - 1]
    if (group && group.date === payout.date) group.items.push(payout)
    else groups.push({ date: payout.date, items: [payout] })
  }
  return groups
}

export const payoutChartSeries = () => [
  {
    key: 'regular',
    name: tr('workerPayoutsRegular'),
    color: PAYOUT_SERIES_COLORS.regular,
    stack: 'paid',
  },
  {
    key: 'purchase',
    name: tr('workerPayoutsPurchases'),
    color: PAYOUT_SERIES_COLORS.purchase,
    stack: 'paid',
  },
  {
    key: 'trip',
    name: tr('workerPayoutsTrips'),
    color: PAYOUT_SERIES_COLORS.trip,
    stack: 'paid',
  },
]
