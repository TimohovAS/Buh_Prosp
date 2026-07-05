export function getCurrentYear() {
  return new Date().getFullYear()
}

export function normalizeAvailableYears(years, fallbackYear = getCurrentYear()) {
  const normalized = Array.from(
    new Set(
      (Array.isArray(years) ? years : [])
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value))
    )
  ).sort((left, right) => right - left)

  return normalized.length ? normalized : [fallbackYear]
}

export function getValidYearSelection(year, availableYears, { includeAllTime = true } = {}) {
  if (includeAllTime && year === '') return ''
  if (availableYears.includes(year)) return year
  return availableYears[0] ?? (includeAllTime ? '' : getCurrentYear())
}
