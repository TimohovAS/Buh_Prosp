const CYRILLIC_TO_LATIN = {
  а: 'a',
  б: 'b',
  в: 'v',
  г: 'g',
  д: 'd',
  ђ: 'dj',
  е: 'e',
  ж: 'z',
  з: 'z',
  и: 'i',
  ј: 'j',
  к: 'k',
  л: 'l',
  љ: 'lj',
  м: 'm',
  н: 'n',
  њ: 'nj',
  о: 'o',
  п: 'p',
  р: 'r',
  с: 's',
  т: 't',
  ћ: 'c',
  у: 'u',
  ф: 'f',
  х: 'h',
  ц: 'c',
  ч: 'c',
  џ: 'dz',
  ш: 's',
}

/**
 * Reduce text to a form where search ignores script, diacritics and case:
 * "АИМА" matches "aima", "Vršac" matches "vrsac". đ is typed both as "dj"
 * and as "d", so both spellings fold to "d". Mirrors fold_search_text in
 * backend/text_utils.py — keep the rules in sync.
 */
export function foldSearchText(value) {
  if (value === null || value === undefined) return ''
  return String(value)
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[а-џ]/g, (char) => CYRILLIC_TO_LATIN[char] ?? char)
    .replaceAll('đ', 'd')
    .replaceAll('dj', 'd')
}

/**
 * True when every word of the query occurs in at least one of the values.
 * An empty query matches everything.
 */
export function matchesSearch(query, ...values) {
  const haystack = values.map(foldSearchText).join(' ')
  return foldSearchText(query)
    .split(/\s+/)
    .every((token) => haystack.includes(token))
}

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
