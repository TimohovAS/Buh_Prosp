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

export function formatDateSr(value, emptyLabel = UI_DASH) {
  if (!value) return emptyLabel
  const normalizedValue =
    typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
      ? `${value}T12:00:00`
      : value
  const parsed = new Date(normalizedValue)
  if (Number.isNaN(parsed.getTime())) return emptyLabel
  return parsed.toLocaleDateString('sr-RS')
}

export function formatDateTimeSr(value, emptyLabel = UI_DASH) {
  if (!value) return emptyLabel
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return String(value)
  return parsed.toLocaleString('sr-RS')
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
