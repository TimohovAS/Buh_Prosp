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

export const MATERIAL_UNITS = ['kom', 'm', 'm2', 'm3', 'kg', 't', 'l', 'pak', 'h', 'km', 'usl']

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
  km: 'unitCodeKm',
  usl: 'unitCodeUsl',
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

export const PAY_MODES = ['hourly', 'full_day', 'trip_day']
export const DAY_PAY_MODES = ['full_day', 'trip_day']
const TRIP_PRICING_FIXED = 'fixed_plus_lodging'

const PAY_MODE_LABEL_KEYS = {
  hourly: 'workDiariesPayModeHourly',
  full_day: 'workDiariesPayModeFullDay',
  trip_day: 'workDiariesPayModeTripDay',
}

export function payModeLabel(mode) {
  return PAY_MODE_LABEL_KEYS[mode] ? tr(PAY_MODE_LABEL_KEYS[mode]) : mode || ''
}

export function cardDayRate(worker, mode) {
  if (mode === 'full_day') return num(worker?.regular_day_rate)
  if (mode === 'trip_day') return num(worker?.trip_work_day_rate)
  return 0
}

// Что сервер сохранит для работника за дату — та же логика, что в
// work_diary_costing.apply_worker_day_inputs. Пустые поля формы — «по карточке»,
// но уже сохранённый снимок того же режима не перечитывается.
export function resolveWorkerPay(worker, state, saved) {
  const mode = state?.pay_mode || 'hourly'
  const sameMode = Boolean(saved?.exists) && saved.pay_mode === mode
  let dayRate = 0
  let dayRateSource = ''
  if (DAY_PAY_MODES.includes(mode)) {
    if (state.day_rate !== '' && state.day_rate != null) {
      dayRate = num(state.day_rate)
      dayRateSource = 'manual'
    } else if (sameMode && !saved.day_rate_manual && num(saved.day_rate) > 0) {
      dayRate = num(saved.day_rate)
      dayRateSource = 'saved'
    } else {
      dayRate = cardDayRate(worker, mode)
      dayRateSource = 'card'
    }
  }
  const tripPricing =
    mode === 'trip_day'
      ? (sameMode && saved.trip_pricing_mode) || worker?.trip_pricing_mode || 'allowances'
      : null
  const fixedTrip = mode === 'trip_day' && tripPricing === TRIP_PRICING_FIXED
  const allowance = (value, savedValue, cardValue) => {
    if (fixedTrip) return 0
    if (value !== '' && value != null) return num(value)
    if (sameMode) return num(savedValue)
    return mode === 'trip_day' ? num(cardValue) : 0
  }
  const lodging =
    state?.lodging !== '' && state?.lodging != null
      ? num(state.lodging)
      : saved?.exists
        ? num(saved.lodging_amount)
        : 0
  return {
    mode,
    dayRate,
    dayRateSource,
    tripPricing,
    fixedTrip,
    perDiem: allowance(state?.per_diem, saved?.per_diem_amount, worker?.trip_per_diem_rate),
    food: allowance(state?.food, saved?.food_amount, worker?.trip_food_rate),
    lodging,
    rateMissing: DAY_PAY_MODES.includes(mode) && dayRate <= 0 && dayRateSource !== 'manual',
  }
}

// Раскладка суммы по весам в парах — как work_diary_costing.allocate: доли вниз до пары,
// остаток — последней доле. Веса — часы, в сотых; деление целочисленное, чтобы совпасть
// с сервером до пары.
export function allocateParas(total, weights) {
  if (!weights.length) return []
  const totalParas = Math.round(num(total) * 100)
  let scaled = weights.map((weight) => Math.max(Math.round(num(weight) * 100), 0))
  let weightSum = scaled.reduce((sum, weight) => sum + weight, 0)
  if (weightSum <= 0) {
    scaled = weights.map(() => 1)
    weightSum = scaled.length
  }
  const parts = scaled
    .slice(0, -1)
    .map((weight) => Number((BigInt(totalParas) * BigInt(weight)) / BigInt(weightSum)))
  parts.push(totalParas - parts.reduce((sum, part) => sum + part, 0))
  return parts.map((part) => part / 100)
}

// Часть дневной суммы для записи: записи дня по возрастанию id, остаток — последней.
function dayPart(amount, rows, entryKey) {
  if (!num(amount)) return 0
  const parts = allocateParas(
    amount,
    rows.map((row) => row.hours)
  )
  return parts[rows.findIndex((row) => row.id === entryKey)] || 0
}

// Живой расчет в форме: та же логика, что и на бэкенде (см. work_diary_costing.entry_cost
// и work_diaries_router._entry_amounts). workerPay — по работнику: режим, дневная ставка,
// командировочные за день, другие записи этого дня ({ id, hours }) и ставка часа работника.
// entryId — id редактируемой записи; новая получит наибольший id и остаток от раскладки.
export function computeEntryTotals({
  form,
  materials,
  teamRate,
  teamBillingRate,
  overtimeMultiplier,
  workerPay = [],
  entryId = null,
}) {
  const entryKey = entryId == null ? Number.MAX_SAFE_INTEGER : Number(entryId)
  const workerCount = form.worker_ids.length
  const duration = computeDurationHours(form)
  const regular = Math.min(duration, REGULAR_DAY_HOURS)
  const overtime = Math.max(duration - REGULAR_DAY_HOURS, 0)
  const teamHourlyLabor = regular * teamRate + overtime * teamRate * overtimeMultiplier
  const payByWorker = new Map(workerPay.map((item) => [Number(item.worker_id), item]))
  const pays = form.worker_ids.map(
    (workerId) => payByWorker.get(Number(workerId)) || { worker_id: Number(workerId), mode: 'hourly' }
  )
  const totalRate = pays.reduce((sum, pay) => sum + num(pay.hourlyRate), 0)
  let hourlyRateSum = 0
  let hourlyCount = 0
  let dayLabor = 0
  let tripAllowances = 0
  const workerShares = pays.map((pay) => {
    const rows = [
      ...(pay.otherEntries || [])
        .filter((other) => Number(other.id) !== entryKey)
        .map((other) => ({ id: Number(other.id), hours: num(other.hours) })),
      { id: entryKey, hours: duration },
    ].sort((left, right) => left.id - right.id)
    const dayHours = rows.reduce((sum, row) => sum + row.hours, 0)
    const share = dayHours > 0 ? duration / dayHours : 1 / rows.length
    const weight = totalRate > 0 ? num(pay.hourlyRate) / totalRate : workerCount ? 1 / workerCount : 0
    let labor
    let hourlyEquivalent = 0
    if (DAY_PAY_MODES.includes(pay.mode)) {
      labor = dayPart(pay.dayRate, rows, entryKey)
      dayLabor += labor
      hourlyEquivalent = teamHourlyLabor * weight
    } else {
      labor = teamHourlyLabor * weight
      hourlyRateSum += num(pay.hourlyRate)
      hourlyCount += 1
    }
    const allowances = dayPart(num(pay.perDiem) + num(pay.food) + num(pay.lodging), rows, entryKey)
    tripAllowances += allowances
    return {
      worker_id: pay.worker_id,
      mode: pay.mode,
      fixedTrip: Boolean(pay.fixedTrip),
      isDay: DAY_PAY_MODES.includes(pay.mode),
      share,
      dayHours,
      labor,
      allowances,
      hourlyEquivalent,
    }
  })
  const hourlyFraction =
    totalRate > 0 ? hourlyRateSum / totalRate : workerCount ? hourlyCount / workerCount : 1
  const hourlyLabor = teamHourlyLabor * hourlyFraction
  const labor = hourlyLabor + dayLabor
  // Сколько ставка за день добавила к оплате тех же часов по часам. У полного дня это
  // доплата до полного дня; у дня командировки — надбавка командировочной ставки, в
  // которую при фиксированной ставке уже входят дневница и питание.
  const extraOverHours = (mode) =>
    Math.max(
      workerShares.reduce(
        (sum, item) => sum + (item.mode === mode ? item.labor - item.hourlyEquivalent : 0),
        0
      ),
      0
    )
  const fullDayTopUp = extraOverHours('full_day')
  const tripDayExtra = extraOverHours('trip_day')
  const tripDayIncludesMeals = workerShares.some((item) => item.mode === 'trip_day' && item.fixedTrip)
  const dayTopUp = fullDayTopUp + tripDayExtra
  let legacyAllowances = num(form.lodging_amount)
  if (form.per_diem) legacyAllowances += num(form.per_diem_amount) * workerCount
  if (form.food_allowance) legacyAllowances += num(form.food_amount) * workerCount
  const allowances = legacyAllowances + tripAllowances
  const materialsTotal = materials.reduce(
    (sum, item) => sum + (item.source === 'service' ? 0 : num(item.amount)),
    0
  )
  const servicesTotal = materials.reduce(
    (sum, item) => sum + (item.source === 'service' ? num(item.amount) : 0),
    0
  )
  const materialBillingMultiplier =
    num(form.material_billing_multiplier) || DEFAULT_MATERIAL_BILLING_MULTIPLIER
  const billableMaterials = materialsTotal * materialBillingMultiplier
  const personHours = duration * workerCount
  const calculatedBillable = duration * teamBillingRate + billableMaterials + servicesTotal
  const billableAdjusted = form.billable_amount_override !== '' && form.billable_amount_override != null
  const billable = billableAdjusted ? num(form.billable_amount_override) : calculatedBillable
  const billableLabor = duration * teamBillingRate
  const totalCost = labor + allowances + materialsTotal
  return {
    duration,
    personHours,
    overtimePersonHours: overtime * workerCount,
    labor,
    hourlyLabor,
    dayLabor,
    dayTopUp,
    fullDayTopUp,
    tripDayExtra,
    tripDayIncludesMeals,
    allowances,
    tripAllowances,
    legacyAllowances,
    workerShares,
    materials: materialsTotal,
    services: servicesTotal,
    payout: labor + allowances,
    totalCost,
    calculatedBillable,
    billableMaterials,
    billableLabor,
    billableAdjustment: billable - calculatedBillable,
    billableAdjusted,
    billable,
    margin: billable - totalCost,
  }
}
