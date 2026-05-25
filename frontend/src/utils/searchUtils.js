/**
 * Build a search-friendly token string for a numeric value that covers
 * the common representations a user might type into a free-text search
 * box: dotted decimal ("477.60"), comma decimal ("477,60"), and the
 * integer truncation ("477"). Use the result by concatenating with the
 * rest of the haystack and matching with .includes().
 *
 * Returns an empty string for null/undefined/empty/non-numeric input so
 * it is safe to interpolate unconditionally.
 */
export function amountSearchHay(value) {
  if (value === null || value === undefined || value === '') return ''
  const num = Number(value)
  if (!Number.isFinite(num)) return ''
  const abs = Math.abs(num)
  const dotted = abs.toFixed(2)
  const comma = dotted.replace('.', ',')
  const intPart = String(Math.trunc(abs))
  return `${dotted} ${comma} ${intPart}`
}
