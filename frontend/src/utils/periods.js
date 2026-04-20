import { localDateIso } from './formatters'

export function getPeriodRange(quick, customFrom, customTo, options = {}) {
  const baseDate = options.baseDate || new Date()
  const year = baseDate.getFullYear()
  const month = baseDate.getMonth() + 1

  if (quick === 'month') {
    const lastDay = new Date(year, month, 0).getDate()
    return {
      from: `${year}-${String(month).padStart(2, '0')}-01`,
      to: `${year}-${String(month).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
    }
  }

  if (quick === 'quarter') {
    const quarter = Math.ceil(month / 3)
    const startMonth = (quarter - 1) * 3 + 1
    const endMonth = quarter * 3
    const lastDay = new Date(year, endMonth, 0).getDate()
    return {
      from: `${year}-${String(startMonth).padStart(2, '0')}-01`,
      to: `${year}-${String(endMonth).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
    }
  }

  if (quick === 'year') {
    return { from: `${year}-01-01`, to: `${year}-12-31` }
  }

  return {
    from: customFrom || options.fallbackFrom || localDateIso(baseDate),
    to: customTo || options.fallbackTo || localDateIso(baseDate),
  }
}
