export const UI_DASH = '\u2014'
export const UI_CLOSE = '\u00D7'
export const UI_SORT_BOTH = '\u2195'
export const UI_SORT_ASC = '\u2191'
export const UI_SORT_DESC = '\u2193'

export function formatNumber(value, options = {}) {
  return Number(value ?? 0).toLocaleString('sr-RS', options)
}

export function formatInteger(value) {
  return formatNumber(value)
}

export function formatMoney(value, currency = 'RSD', options = {}) {
  return `${formatNumber(value, options)} ${currency}`
}

export function formatDateOnly(value, emptyLabel = UI_DASH) {
  if (!value) return emptyLabel
  return String(value).slice(0, 10)
}

// Принятый формат даты — ДД.ММ.ГГГГ, как в поле выбора даты (dd.MM.yyyy).
// Локаль sr-RS даёт «2. 9. 2026.», поэтому собираем строку сами.
export function formatDateSr(value, emptyLabel = UI_DASH) {
  if (!value) return emptyLabel
  const isoDate = typeof value === 'string' ? value.slice(0, 10) : ''
  if (/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) {
    const [year, month, day] = isoDate.split('-')
    return `${day}.${month}.${year}`
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return emptyLabel
  return formatDateParts(parsed)
}

export function formatDateTimeSr(value, emptyLabel = UI_DASH) {
  if (!value) return emptyLabel
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return String(value)
  const time = `${String(parsed.getHours()).padStart(2, '0')}:${String(parsed.getMinutes()).padStart(2, '0')}`
  return `${formatDateParts(parsed)} ${time}`
}

function formatDateParts(date) {
  const day = String(date.getDate()).padStart(2, '0')
  const month = String(date.getMonth() + 1).padStart(2, '0')
  return `${day}.${month}.${date.getFullYear()}`
}

export function formatMoney2(value) {
  return formatNumber(value, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatMoney2OrDash(value, emptyLabel = UI_DASH) {
  return value != null ? formatMoney2(value) : emptyLabel
}

export function localDateIso(value = new Date()) {
  const tzOffsetMs = value.getTimezoneOffset() * 60000
  return new Date(value.getTime() - tzOffsetMs).toISOString().slice(0, 10)
}

export function todayIso() {
  return localDateIso()
}
