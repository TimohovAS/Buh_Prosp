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
