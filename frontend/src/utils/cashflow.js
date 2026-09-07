import { localDateIso } from './formatters.js'

export function cashflowRange(period, anchor, customFrom, customTo) {
  if (period === 'custom') return { from: customFrom, to: customTo }
  const date = new Date(`${anchor}T12:00:00`)
  const year = date.getFullYear()
  const month = date.getMonth()
  const startMonth = period === 'year' ? 0 : period === 'quarter' ? Math.floor(month / 3) * 3 : month
  const months = period === 'year' ? 12 : period === 'quarter' ? 3 : 1
  return {
    from: localDateIso(new Date(year, startMonth, 1, 12)),
    to: localDateIso(new Date(year, startMonth + months, 0, 12)),
  }
}

export function shiftCashflowPeriod(anchor, period, direction) {
  const date = new Date(`${anchor}T12:00:00`)
  const months = period === 'year' ? 12 : period === 'quarter' ? 3 : 1
  return localDateIso(new Date(date.getFullYear(), date.getMonth() + months * direction, 1, 12))
}

export function cashflowDayCount(from, to) {
  if (!from || !to || from > to) return 0
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86400000) + 1
}

export function cashflowGrouping(from, to, selected = 'auto') {
  const days = cashflowDayCount(from, to)
  if (selected === 'auto') return days <= 31 ? 'day' : days <= 1096 ? 'month' : 'year'
  return selected === 'day' && days > 366 ? 'month' : selected
}
