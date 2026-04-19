import { tr } from '../i18n'

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

export default function YearFilterSelect({
  value,
  availableYears,
  onChange,
  includeAllTime = true,
  className = 'form-input',
  style = { width: 'auto' },
  title,
  disabled = false,
}) {
  return (
    <select
      className={className}
      style={style}
      value={value === '' ? '' : String(value)}
      onChange={(event) => onChange(event.target.value ? Number(event.target.value) : '')}
      title={title}
      disabled={disabled}
    >
      {includeAllTime ? <option value="">{tr('allTime')}</option> : null}
      {availableYears.map((optionYear) => (
        <option key={optionYear} value={optionYear}>{optionYear}</option>
      ))}
    </select>
  )
}
