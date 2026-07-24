import { tr } from '../../i18n'
import { formatInteger as fmtAmount } from '../../utils/formatters'

export const REGULAR_DAY_HOURS = 8
export const DEFAULT_OVERTIME_MULTIPLIER = 1.26
export const DEFAULT_MATERIAL_BILLING_MULTIPLIER = 1.2

export const WEATHER_CODES = ['sunny', 'cloudy', 'rain', 'snow', 'wind', 'fog']

const WEATHER_LABEL_KEYS = {
  sunny: 'workDiariesWeatherSunny',
  cloudy: 'workDiariesWeatherCloudy',
  rain: 'workDiariesWeatherRain',
  snow: 'workDiariesWeatherSnow',
  wind: 'workDiariesWeatherWind',
  fog: 'workDiariesWeatherFog',
}

// Печатные формы всегда на сербском независимо от языка интерфейса
const WEATHER_PRINT_LABELS = {
  sunny: 'Сунчано',
  cloudy: 'Облачно',
  rain: 'Киша',
  snow: 'Снег',
  wind: 'Ветар',
  fog: 'Магла',
}

export const MATERIAL_UNITS = ['kom', 'm', 'm2', 'm3', 'kg', 't', 'l', 'pak', 'h']

const UNIT_LABEL_KEYS = {
  kom: 'unitCodeKom',
  m: 'unitCodeM',
  m2: 'unitCodeM2',
  m3: 'unitCodeM3',
  kg: 'unitCodeKg',
  t: 'unitCodeT',
  l: 'unitCodeL',
  pak: 'unitCodePak',
  h: 'unitCodeH',
}

export function weatherLabel(code) {
  return WEATHER_LABEL_KEYS[code] ? tr(WEATHER_LABEL_KEYS[code]) : code || ''
}

export function weatherPrintLabel(code) {
  return WEATHER_PRINT_LABELS[code] || code || ''
}

export function unitLabel(code) {
  return UNIT_LABEL_KEYS[code] ? tr(UNIT_LABEL_KEYS[code]) : code || ''
}

export function num(value) {
  return Number(value || 0)
}

export function money(value) {
  return `${fmtAmount(value || 0)} RSD`
}

export function hours(value) {
  return Number(value || 0).toFixed(2)
}

export function dateLabel(value) {
  if (!value) return ''
  const [year, month, day] = value.split('-')
  return day && month && year ? `${day}.${month}.${year}.` : value
}

export function dayName(value) {
  if (!value) return ''
  return ['Недеља', 'Понедељак', 'Уторак', 'Среда', 'Четвртак', 'Петак', 'Субота'][new Date(value).getDay()]
}

export function defaultWorkerHourlyRate(worker) {
  const dayRate = num(worker?.regular_day_rate)
  return dayRate > 0 ? dayRate / REGULAR_DAY_HOURS : 0
}

export function teamAutoRate(workers, workerIds) {
  const selected = new Set(workerIds.map(Number))
  return workers
    .filter((worker) => selected.has(worker.id))
    .reduce((sum, worker) => sum + defaultWorkerHourlyRate(worker), 0)
}

export function teamBillingAutoRate(workers, workerIds) {
  const selected = new Set(workerIds.map(Number))
  return workers
    .filter((worker) => selected.has(worker.id))
    .reduce((sum, worker) => sum + num(worker.billing_hourly_rate), 0)
}

function parseTimeToHours(value) {
  if (!value) return null
  const [h, m] = value.split(':').map(Number)
  if (Number.isNaN(h) || Number.isNaN(m)) return null
  return h + m / 60
}

export function computeDurationHours(form) {
  const start = parseTimeToHours(form.start_time)
  const end = parseTimeToHours(form.end_time)
  if (start != null && end != null && end > start) return end - start
  if (form.duration_hours !== '' && num(form.duration_hours) > 0) return num(form.duration_hours)
  return 0
}

// Живой расчет в форме: та же логика, что и на бэкенде (см. work_diaries_router._entry_amounts)
export function computeEntryTotals({ form, materials, teamRate, teamBillingRate, overtimeMultiplier }) {
  const workerCount = form.worker_ids.length
  const duration = computeDurationHours(form)
  const regular = Math.min(duration, REGULAR_DAY_HOURS)
  const overtime = Math.max(duration - REGULAR_DAY_HOURS, 0)
  const labor = regular * teamRate + overtime * teamRate * overtimeMultiplier
  let allowances = num(form.lodging_amount)
  if (form.per_diem) allowances += num(form.per_diem_amount) * workerCount
  if (form.food_allowance) allowances += num(form.food_amount) * workerCount
  const materialsTotal = materials.reduce((sum, item) => sum + num(item.amount), 0)
  const materialBillingMultiplier =
    num(form.material_billing_multiplier) || DEFAULT_MATERIAL_BILLING_MULTIPLIER
  const billableMaterials = materialsTotal * materialBillingMultiplier
  const personHours = duration * workerCount
  const calculatedBillable = duration * teamBillingRate + billableMaterials
  const billableAdjusted = form.billable_amount_override !== '' && form.billable_amount_override != null
  const billable = billableAdjusted ? num(form.billable_amount_override) : calculatedBillable
  const billableLabor = duration * teamBillingRate
  return {
    duration,
    personHours,
    overtimePersonHours: overtime * workerCount,
    labor,
    allowances,
    materials: materialsTotal,
    payout: labor + allowances,
    totalCost: labor + allowances + materialsTotal,
    calculatedBillable,
    billableMaterials,
    billableLabor,
    billableAdjustment: billable - calculatedBillable,
    billableAdjusted,
    billable,
  }
}
