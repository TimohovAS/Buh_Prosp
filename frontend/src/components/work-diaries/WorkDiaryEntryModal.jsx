import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, ChevronDown, ChevronRight, Plus, RotateCcw, Save } from 'lucide-react'
import { api } from '../../api'
import { tr } from '../../i18n'
import DatePicker from '../DatePicker'
import FieldTooltip from '../FieldTooltip'
import Modal from '../Modal'
import ItemDragHandle from '../ItemDragHandle'
import ItemRemoveButton from '../ItemRemoveButton'
import useReorderableItems from '../../hooks/useReorderableItems'
import { createEditorRowKey } from '../../utils/reorderItems'
import MultiSelect from '../MultiSelect'
import ProjectSelect from '../ProjectSelect'
import WorkDiaryTripSection from './WorkDiaryTripSection'
import WorkDiaryWorkerPaySection from './WorkDiaryWorkerPaySection'
import {
  DAY_PAY_MODES,
  DEFAULT_MATERIAL_BILLING_MULTIPLIER,
  MATERIAL_UNITS,
  WEATHER_CODES,
  computeEntryTotals,
  dateLabel,
  defaultWorkerHourlyRate,
  hours,
  money,
  num,
  payModeLabel,
  resolveWorkerPay,
  teamAutoRate,
  teamBillingAutoRate,
  unitLabel,
  weatherLabel,
} from './workDiaryUtils'

const todayIso = () => new Date().toISOString().slice(0, 10)

const emptyForm = {
  date: todayIso(),
  project_id: '',
  worker_ids: [],
  description: '',
  start_time: '07:00',
  end_time: '15:00',
  duration_hours: '',
  team_hourly_rate_snapshot: '',
  team_billing_hourly_rate_snapshot: '',
  material_billing_multiplier: String(DEFAULT_MATERIAL_BILLING_MULTIPLIER),
  billable_amount_override: '',
  per_diem: false,
  per_diem_amount: '',
  lodging_amount: '',
  food_allowance: false,
  food_amount: '',
  is_trip: false,
  travel_hours: '',
  travel_km: '',
  weather: '',
  temperature: '',
  note: '',
}

// touchedDate — дата, для которой человек менял строку: режим оплаты действует на дату,
// поэтому правки одного дня не переносятся на другой при смене даты записи.
const emptyPay = {
  pay_mode: 'hourly',
  day_rate: '',
  per_diem: '',
  food: '',
  lodging: '',
  touched: false,
  touchedDate: '',
}

// Сохранённое начисление работника за дату -> состояние строки формы. Пустые поля —
// «как сохранено / по карточке»: сервер их так и разрешит.
function payFromSaved(saved) {
  if (!saved) return { ...emptyPay }
  return {
    ...emptyPay,
    pay_mode: saved.pay_mode || 'hourly',
    day_rate: saved.day_rate_manual ? String(saved.day_rate) : '',
  }
}

// Вкладки формы: что сделано (ежедневный минимум) и деньги — ставки и оплата работникам.
const ENTRY_TABS = ['work', 'pay']
const ENTRY_TAB_LABEL_KEYS = {
  work: 'workDiariesEntryTabWork',
  pay: 'workDiariesEntryTabPay',
}

function hasLegacyAllowances(form) {
  return Boolean(form.per_diem || form.food_allowance || num(form.lodging_amount) > 0)
}

function sameIds(left, right) {
  const a = [...(left || [])].map(Number).sort((x, y) => x - y)
  const b = [...(right || [])].map(Number).sort((x, y) => x - y)
  return a.length === b.length && a.every((value, index) => value === b[index])
}

const emptyMaterial = {
  description: '',
  quantity: '',
  unit: '',
  source: 'stock',
  expense_id: '',
  amount: '',
  source_item_type: '',
  source_item_id: '',
  unit_price: '',
  unit_price_derived: false,
  legacy_whole_expense: false,
}

function materialAmount(quantity, unitPrice) {
  if (quantity === '' || unitPrice === '') return ''
  return String(Math.round((num(quantity) * num(unitPrice) + Number.EPSILON) * 100) / 100)
}

function formatDuration(value) {
  const totalMinutes = Math.max(0, Math.round(num(value) * 60))
  const durationHours = Math.floor(totalMinutes / 60)
  const durationMinutes = totalMinutes % 60
  const parts = []
  if (durationHours > 0) {
    parts.push(tr('workDiariesDurationHoursShort', { value: durationHours }))
  }
  if (durationMinutes > 0) {
    parts.push(tr('workDiariesDurationMinutesShort', { value: durationMinutes }))
  }
  return parts.join(' ')
}

function formFromEntry(entry, defaultProjectId, materialBillingMultiplier) {
  if (!entry) {
    return {
      ...emptyForm,
      date: todayIso(),
      project_id: defaultProjectId || '',
      material_billing_multiplier: String(materialBillingMultiplier),
    }
  }
  const hasTimeRange = Boolean(entry.start_time && entry.end_time)
  return {
    date: entry.date,
    project_id: String(entry.project_id),
    worker_ids: [...(entry.worker_ids || [])],
    description: entry.description || '',
    start_time: entry.start_time || '',
    end_time: entry.end_time || '',
    duration_hours: hasTimeRange ? '' : String(entry.duration_hours ?? ''),
    team_hourly_rate_snapshot:
      entry.team_hourly_rate_snapshot == null ? '' : String(entry.team_hourly_rate_snapshot),
    team_billing_hourly_rate_snapshot:
      entry.team_billing_hourly_rate_snapshot == null ? '' : String(entry.team_billing_hourly_rate_snapshot),
    material_billing_multiplier:
      entry.material_billing_multiplier == null
        ? String(materialBillingMultiplier)
        : String(entry.material_billing_multiplier),
    billable_amount_override:
      entry.billable_amount_override == null ? '' : String(entry.billable_amount_override),
    per_diem: Boolean(entry.per_diem),
    per_diem_amount: entry.per_diem_amount ? String(entry.per_diem_amount) : '',
    lodging_amount: entry.lodging_amount ? String(entry.lodging_amount) : '',
    food_allowance: Boolean(entry.food_allowance),
    food_amount: entry.food_amount ? String(entry.food_amount) : '',
    is_trip: Boolean(entry.is_trip),
    travel_hours: entry.travel_hours == null ? '' : String(entry.travel_hours),
    travel_km: entry.travel_km == null ? '' : String(entry.travel_km),
    weather: entry.weather || '',
    temperature: entry.temperature || '',
    note: entry.note || '',
  }
}

function materialsFromEntry(entry) {
  return (entry?.materials || []).map((material) => ({
    rowKey: createEditorRowKey(),
    description: material.description || '',
    quantity: material.quantity == null ? '' : String(material.quantity),
    unit: material.unit || '',
    source: material.source || 'stock',
    expense_id: material.expense_id ? String(material.expense_id) : '',
    amount: material.amount ? String(material.amount) : '',
    source_item_type: material.source_item_type || '',
    source_item_id: material.source_item_id ? String(material.source_item_id) : '',
    unit_price:
      material.unit_price_snapshot != null
        ? String(material.unit_price_snapshot)
        : material.quantity && material.amount
          ? String(Math.round((material.amount / material.quantity) * 100) / 100)
          : '',
    unit_price_derived: material.unit_price_snapshot == null && Boolean(material.quantity && material.amount),
    expense_description: material.expense_description || '',
    expense_date: material.expense_date || '',
    legacy_whole_expense:
      material.source === 'expense' &&
      Boolean(material.expense_id) &&
      !material.source_item_type &&
      !material.source_item_id,
  }))
}

export default function WorkDiaryEntryModal({
  isOpen,
  onClose,
  onSaved,
  entry,
  projects,
  workers,
  defaultProjectId,
  overtimeMultiplier,
  materialBillingMultiplier = DEFAULT_MATERIAL_BILLING_MULTIPLIER,
  readOnly = false,
}) {
  const [form, setForm] = useState(emptyForm)
  const [materials, setMaterials] = useState([])
  const [saving, setSaving] = useState(false)
  const [expenseOptions, setExpenseOptions] = useState([])
  const [showAllowances, setShowAllowances] = useState(false)
  const [showDiaryDetails, setShowDiaryDetails] = useState(false)
  const [activeTab, setActiveTab] = useState('work')
  const formRef = useRef(null)
  // Режим оплаты по работникам (форма) и сохранённые начисления за дату (сервер).
  const [payState, setPayState] = useState({})
  const [savedDays, setSavedDays] = useState({})
  // Загрузка начислений за дату: для какого ключа (дата|работники) и чем закончилась —
  // loading, ready или error. Сохранять можно только при ready для текущего ключа.
  const [payLoad, setPayLoad] = useState({ key: '', status: 'idle' })
  const [payReload, setPayReload] = useState(0)
  // После смены даты правки прежнего дня отброшены — показать это, а не молча.
  const [payDateNotice, setPayDateNotice] = useState(false)
  const payStateRef = useRef(payState)
  const materialEditor = useReorderableItems({
    items: materials,
    onChange: setMaterials,
    getKey: (material) => material.rowKey,
    disabled: !isOpen || readOnly || saving,
  })

  const addMaterial = (source = 'stock') => {
    const material = {
      ...emptyMaterial,
      rowKey: createEditorRowKey(),
      source,
      quantity: source === 'service' ? '1' : '',
      unit: source === 'service' ? 'usl' : '',
    }
    materialEditor.focusNewItem(material.rowKey)
    setMaterials((previous) => [...previous, material])
  }

  useEffect(() => {
    if (!isOpen) return
    setForm(formFromEntry(entry, defaultProjectId, materialBillingMultiplier))
    setMaterials(materialsFromEntry(entry))
    setShowAllowances(
      Boolean(entry && (entry.per_diem || entry.food_allowance || num(entry.lodging_amount) > 0))
    )
    setShowDiaryDetails(Boolean(entry && (entry.weather || entry.temperature || entry.note)))
    const workerPay = entry?.worker_pay || []
    setPayState(
      Object.fromEntries(workerPay.map((item) => [item.worker_id, payFromSaved({ ...item, exists: true })]))
    )
    setSavedDays({})
    setPayLoad({ key: '', status: 'idle' })
    setPayDateNotice(false)
    setActiveTab('work')
  }, [isOpen, entry, defaultProjectId, materialBillingMultiplier])

  useEffect(() => {
    payStateRef.current = payState
  }, [payState])

  // Браузер не может показать ошибку поля на скрытой вкладке и молча не сохраняет форму.
  // Первое неверное поле открывает свою вкладку и показывает подсказку уже на ней.
  useEffect(() => {
    const formElement = formRef.current
    if (!isOpen || !formElement) return undefined
    let handled = false
    const revealInvalidField = (event) => {
      if (handled) return
      handled = true
      window.setTimeout(() => {
        handled = false
      }, 0)
      const panel = event.target.closest?.('[data-entry-tab]')
      if (!panel?.hidden) return
      setActiveTab(panel.dataset.entryTab)
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => event.target.reportValidity?.()))
    }
    formElement.addEventListener('invalid', revealInvalidField, true)
    return () => formElement.removeEventListener('invalid', revealInvalidField, true)
  }, [isOpen])

  // Начисления за дату общие для всех записей работника в этот день: при смене даты
  // или состава подгружаем, что уже сохранено, и сколько часов у других записей.
  const workerIdsKey = form.worker_ids.join(',')
  const payKey = `${form.date}|${workerIdsKey}`
  useEffect(() => {
    if (!isOpen) return undefined
    const day = form.date
    const key = `${day}|${workerIdsKey}`
    const ids = workerIdsKey ? workerIdsKey.split(',').map(Number) : []
    if (!day || ids.length === 0) {
      setSavedDays({})
      setPayLoad({ key, status: 'ready' })
      return undefined
    }
    let cancelled = false
    // Каждый запрос, в том числе «Повторить загрузку», заново блокирует сохранение:
    // оно откроется только после успешного ответа на этот запрос.
    setPayLoad({ key, status: 'loading' })
    api.workDiaries
      .workerDays({
        date: day,
        worker_ids: workerIdsKey,
        ...(entry?.id ? { entry_id: entry.id } : {}),
      })
      .then((states) => {
        if (cancelled) return
        const byWorker = Object.fromEntries(states.map((state) => [state.worker_id, state]))
        // Правки человека держим только для той даты, где они сделаны: на другой дате у
        // работника своё начисление, общее с его записями того дня, — перенести туда
        // режим прежнего дня значило бы переписать чужой день.
        const previous = payStateRef.current
        let discarded = false
        const next = Object.fromEntries(
          ids.map((id) => {
            const current = previous[id]
            if (current?.touched && current.touchedDate === day) return [id, current]
            if (current?.touched) discarded = true
            return [id, payFromSaved(byWorker[id])]
          })
        )
        setSavedDays(byWorker)
        setPayState(next)
        if (discarded) setPayDateNotice(true)
        setPayLoad({ key, status: 'ready' })
      })
      .catch(() => {
        if (cancelled) return
        // Не зная, что уже сохранено за этот день, форму сохранять нельзя: режимы молча
        // потерялись бы или затёрли начисления других записей работника.
        setSavedDays({})
        setPayLoad({ key, status: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [isOpen, form.date, workerIdsKey, entry?.id, payReload])

  useEffect(() => {
    if (!isOpen || !form.project_id || readOnly) {
      setExpenseOptions([])
      return
    }
    api.workDiaries
      .expenseOptions({
        project_id: form.project_id,
        ...(entry?.id ? { entry_id: entry.id } : {}),
      })
      .then(setExpenseOptions)
  }, [isOpen, form.project_id, entry?.id, readOnly])

  const workerOptions = useMemo(
    () => workers.map((worker) => ({ value: worker.id, label: worker.name })),
    [workers]
  )
  const selectableProjects = useMemo(
    () =>
      projects.filter(
        (project) => project.status === 'active' || (entry && String(project.id) === String(entry.project_id))
      ),
    [entry, projects]
  )

  const autoRate = useMemo(() => teamAutoRate(workers, form.worker_ids), [workers, form.worker_ids])
  const autoBillingRate = useMemo(
    () => teamBillingAutoRate(workers, form.worker_ids),
    [workers, form.worker_ids]
  )
  const hasZeroRateWorker = useMemo(() => {
    const selected = new Set(form.worker_ids.map(Number))
    return workers.some((worker) => selected.has(worker.id) && defaultWorkerHourlyRate(worker) === 0)
  }, [workers, form.worker_ids])

  const manualRate = form.team_hourly_rate_snapshot
  const effectiveRate = manualRate === '' ? autoRate : num(manualRate)
  const manualBillingRate = form.team_billing_hourly_rate_snapshot
  const teamBillingRate = manualBillingRate === '' ? autoBillingRate : num(manualBillingRate)
  const effectiveMultiplier = entry ? num(entry.overtime_multiplier) : num(overtimeMultiplier)

  // Для расчета материалов пустая сумма привязанной строки означает всю сумму расхода
  const materialsForCalc = useMemo(
    () =>
      materials.map((item) => {
        if (
          item.source === 'expense' &&
          item.amount === '' &&
          item.expense_id &&
          !item.source_item_id &&
          item.quantity === '' &&
          item.unit_price === ''
        ) {
          const option = expenseOptions.find((o) => String(o.id) === String(item.expense_id))
          if (!item.legacy_whole_expense && option?.items?.length) return { amount: 0 }
          return {
            source: item.source,
            amount: option
              ? option.remaining_amount
              : num(item.expense_remaining_amount ?? item.expense_amount),
          }
        }
        return { source: item.source, amount: num(item.amount) }
      }),
    [materials, expenseOptions]
  )

  // Выбранные работники: карточки из справочника, а архивные — по данным записи.
  const selectedWorkers = useMemo(
    () =>
      form.worker_ids.map((id) => {
        const card = workers.find((worker) => worker.id === Number(id))
        if (card) return card
        const saved = entry?.worker_pay?.find((item) => item.worker_id === Number(id))
        return { id: Number(id), name: saved?.worker_name || String(id) }
      }),
    [form.worker_ids, workers, entry]
  )
  const resolvedPay = useMemo(
    () =>
      Object.fromEntries(
        selectedWorkers.map((worker) => [
          worker.id,
          resolveWorkerPay(worker, payState[worker.id] || emptyPay, savedDays[worker.id]),
        ])
      ),
    [selectedWorkers, payState, savedDays]
  )
  // Ставка часа работника: снимок записи, пока состав и ставка бригады те же, иначе
  // сервер перечитает карточки — так же делает и предпросмотр.
  const keepRateSnapshots = Boolean(entry) && sameIds(form.worker_ids, entry.worker_ids) && manualRate !== ''
  const workerPay = selectedWorkers.map((worker) => {
    const pay = resolvedPay[worker.id]
    const snapshot = entry?.worker_pay?.find((item) => item.worker_id === worker.id)?.hourly_rate_snapshot
    return {
      worker_id: worker.id,
      mode: pay.mode,
      fixedTrip: pay.fixedTrip,
      dayRate: pay.dayRate,
      perDiem: pay.perDiem,
      food: pay.food,
      lodging: pay.lodging,
      otherEntries: (savedDays[worker.id]?.other_entries || []).map((other) => ({
        id: other.id,
        hours: other.duration_hours,
      })),
      hourlyRate: keepRateSnapshots && snapshot != null ? num(snapshot) : defaultWorkerHourlyRate(worker),
    }
  })

  const totals = computeEntryTotals({
    form,
    materials: materialsForCalc,
    teamRate: effectiveRate,
    teamBillingRate,
    overtimeMultiplier: effectiveMultiplier,
    workerPay,
    entryId: entry?.id ?? null,
  })
  const shareByWorker = Object.fromEntries(totals.workerShares.map((item) => [item.worker_id, item]))
  const payModes = new Set(Object.values(resolvedPay).map((pay) => pay.mode))
  const showPayAllowances =
    form.is_trip ||
    payModes.has('trip_day') ||
    Object.values(resolvedPay).some((pay) => pay.perDiem > 0 || pay.food > 0 || pay.lodging > 0)
  const paySummary =
    payModes.size === 0
      ? ''
      : payModes.size === 1
        ? payModeLabel([...payModes][0])
        : [...payModes].map(payModeLabel).join(' / ')
  // Пока неизвестно, что уже сохранено за этот день, сохранять запись нельзя: только
  // успешный ответ на запрос для текущих даты и работников снимает блокировку.
  const payReady = payLoad.key === payKey && payLoad.status === 'ready'
  const payError = payLoad.key === payKey && payLoad.status === 'error'
  const payLoading = !payReady && !payError
  const payBlocked = !payReady
  const legacyAllowances = hasLegacyAllowances(form)
  // На вкладке «Оплата и цены» есть что проверить: ошибка загрузки, сброс режимов после
  // смены даты или ставка дня, которой нет в карточке работника.
  const payAttention = payError || payDateNotice || Object.values(resolvedPay).some((pay) => pay.rateMissing)

  const setWorkerPay = (workerId, patch) => {
    setPayDateNotice(false)
    setPayState((previous) => ({
      ...previous,
      [workerId]: { ...(previous[workerId] || emptyPay), ...patch, touched: true, touchedDate: form.date },
    }))
  }
  const applyPayModeToAll = (mode) => {
    setPayDateNotice(false)
    setPayState((previous) =>
      Object.fromEntries(
        form.worker_ids.map((id) => [
          id,
          {
            ...(previous[id] || emptyPay),
            pay_mode: mode,
            day_rate: '',
            per_diem: '',
            food: '',
            touched: true,
            touchedDate: form.date,
          },
        ])
      )
    )
  }
  const addServiceLine = ({ description, quantity, unit, unit_price }) => {
    const material = {
      ...emptyMaterial,
      rowKey: createEditorRowKey(),
      source: 'service',
      description,
      quantity,
      unit,
      unit_price,
      amount: materialAmount(quantity, unit_price),
    }
    materialEditor.focusNewItem(material.rowKey)
    setMaterials((previous) => [...previous, material])
  }
  const durationText = formatDuration(totals.duration)
  const timeRangeLabel = durationText
    ? tr('workDiariesTimeRangeWithDuration', { duration: durationText })
    : tr('workDiariesTimeRange')

  const setFormField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }))

  const updateMaterial = (index, patch) => {
    setMaterials((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }

  const materialItemKey = (item) =>
    item?.source_item_type && item?.source_item_id ? `${item.source_item_type}:${item.source_item_id}` : ''

  const materialRowFromItem = (option, item) => ({
    ...emptyMaterial,
    rowKey: createEditorRowKey(),
    source: 'expense',
    expense_id: String(option.id),
    source_item_type: item.source_item_type,
    source_item_id: String(item.source_item_id),
    description: item.name,
    quantity:
      item.remaining_quantity == null
        ? item.quantity == null
          ? ''
          : String(item.quantity)
        : String(item.remaining_quantity),
    unit: item.unit || '',
    unit_price:
      item.unit_price != null
        ? String(item.unit_price)
        : item.quantity && item.total_amount
          ? String(Math.round((item.total_amount / item.quantity) * 100) / 100)
          : '',
    amount:
      item.remaining_amount == null
        ? item.total_amount
          ? String(item.total_amount)
          : ''
        : String(item.remaining_amount),
  })

  // Выбор позиции чека/фактуры автозаполняет строку; пустой выбор — весь расход целиком
  const applyExpenseItem = (index, option, itemKey) => {
    if (itemKey === '') {
      updateMaterial(index, {
        source_item_type: '',
        source_item_id: '',
        unit_price: '',
        quantity: '',
        unit: '',
        amount: '',
        description: option?.description || '',
      })
      return
    }
    const item = (option?.items || []).find((candidate) => materialItemKey(candidate) === itemKey)
    if (!item || item.is_used) return
    setMaterials((prev) => {
      const alreadySelected = prev.some(
        (material, materialIndex) => materialIndex !== index && materialItemKey(material) === itemKey
      )
      if (alreadySelected) return prev
      const updated = prev.map((material, materialIndex) =>
        materialIndex === index
          ? { ...material, ...materialRowFromItem(option, item), rowKey: material.rowKey }
          : material
      )
      const expenseId = String(option.id)
      const selectedKeys = new Set(
        updated
          .filter((material) => material.source === 'expense' && String(material.expense_id) === expenseId)
          .map(materialItemKey)
          .filter(Boolean)
      )
      const allItemsSelected = (option.items || [])
        .filter((candidate) => !candidate.is_used)
        .every((candidate) => selectedKeys.has(materialItemKey(candidate)))
      return allItemsSelected
        ? updated.filter(
            (material) =>
              material.source !== 'expense' ||
              String(material.expense_id) !== expenseId ||
              Boolean(materialItemKey(material))
          )
        : updated
    })
  }

  const addAllExpenseItems = (index, option) => {
    const items = (option?.items || []).filter((item) => !item.is_used)
    if (items.length === 0) return
    const expenseId = String(option.id)
    setMaterials((prev) => {
      const firstExpenseIndex = prev.findIndex(
        (material) => material.source === 'expense' && String(material.expense_id) === expenseId
      )
      const retained = prev.filter(
        (material) => material.source !== 'expense' || String(material.expense_id) !== expenseId
      )
      const insertionIndex = Math.min(firstExpenseIndex >= 0 ? firstExpenseIndex : index, retained.length)
      return [
        ...retained.slice(0, insertionIndex),
        ...items.map((item) => materialRowFromItem(option, item)),
        ...retained.slice(insertionIndex),
      ]
    })
  }

  const materialExpenseOptions = useMemo(() => {
    // Привязанный расход отредактированной записи может выпасть из списка — добавляем его вручную
    const known = new Set(expenseOptions.map((option) => String(option.id)))
    const extras = materials
      .filter((item) => item.expense_id && !known.has(String(item.expense_id)))
      .map((item) => ({
        id: Number(item.expense_id),
        date: item.expense_date,
        description: item.expense_description || item.description,
        amount: num(item.amount),
        used_amount: 0,
        remaining_amount: num(item.expense_remaining_amount ?? item.amount),
        items: [],
      }))
    return [...extras, ...expenseOptions]
  }, [expenseOptions, materials])

  const sourceItemForMaterial = (material) => {
    if (material.source !== 'expense' || !material.expense_id) return null
    const option = materialExpenseOptions.find(
      (candidate) => String(candidate.id) === String(material.expense_id)
    )
    return (option?.items || []).find((candidate) => materialItemKey(candidate) === materialItemKey(material))
  }

  const shouldShowExpensePicker = (material) => {
    if (material.source !== 'expense' || material.legacy_whole_expense) return false
    if (!material.expense_id) return true
    if (materialItemKey(material)) return false
    const option = materialExpenseOptions.find(
      (candidate) => String(candidate.id) === String(material.expense_id)
    )
    return (option?.items || []).length > 0
  }

  const close = () => {
    if (saving) return
    onClose()
  }

  const submit = async (event) => {
    event.preventDefault()
    if (readOnly) {
      close()
      return
    }
    if (payBlocked) return
    setSaving(true)
    try {
      const payload = {
        ...form,
        project_id: Number(form.project_id),
        worker_ids: form.worker_ids.map(Number),
        start_time: form.start_time || null,
        end_time: form.end_time || null,
        duration_hours: form.duration_hours === '' ? null : num(form.duration_hours),
        team_hourly_rate_snapshot: manualRate === '' ? null : num(manualRate),
        team_billing_hourly_rate_snapshot: manualBillingRate === '' ? null : num(manualBillingRate),
        material_billing_multiplier: num(form.material_billing_multiplier) || materialBillingMultiplier,
        billable_amount_override:
          form.billable_amount_override === '' ? null : num(form.billable_amount_override),
        per_diem_amount: num(form.per_diem_amount),
        lodging_amount: num(form.lodging_amount),
        food_amount: num(form.food_amount),
        is_trip: Boolean(form.is_trip),
        travel_hours: form.travel_hours === '' ? null : num(form.travel_hours),
        travel_km: form.travel_km === '' ? null : num(form.travel_km),
        // Пустое поле — «как сохранено / по карточке работника», решает сервер. Сохранение
        // возможно, только когда начисления этой даты загружены (payBlocked).
        worker_days: form.worker_ids.map((id) => {
          const state = payState[id] || emptyPay
          const value = (field) => (state[field] === '' || state[field] == null ? null : num(state[field]))
          return {
            worker_id: Number(id),
            pay_mode: state.pay_mode,
            day_rate: DAY_PAY_MODES.includes(state.pay_mode) ? value('day_rate') : null,
            per_diem_amount: value('per_diem'),
            food_amount: value('food'),
            lodging_amount: value('lodging'),
          }
        }),
        materials: materials
          .filter(
            (item) =>
              ((item.source === 'stock' || item.source === 'service') && item.description.trim()) ||
              (item.source === 'expense' && item.expense_id)
          )
          .map((item) => ({
            description: item.description.trim(),
            quantity: item.quantity === '' ? null : num(item.quantity),
            unit: item.unit || null,
            source: item.source,
            expense_id: item.source === 'expense' ? Number(item.expense_id) : null,
            source_item_type:
              item.source === 'expense' && item.source_item_type ? item.source_item_type : null,
            source_item_id:
              item.source === 'expense' && item.source_item_id ? Number(item.source_item_id) : null,
            unit_price_snapshot:
              item.unit_price === '' || item.unit_price_derived ? null : num(item.unit_price),
            amount: num(item.amount),
          })),
      }
      if (entry) {
        await api.workDiaries.updateEntry(entry.id, payload)
      } else {
        await api.workDiaries.createEntry(payload)
      }
      await onSaved()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={tr(readOnly ? 'workDiariesViewEntry' : entry ? 'workDiariesEditEntry' : 'workDiariesNewEntry')}
      maxWidth="1120px"
      bodyClassName="work-diaries-entry-modal-body"
    >
      <form
        ref={formRef}
        className={`work-diaries-entry-form${readOnly ? ' is-readonly' : ''}`}
        onSubmit={submit}
        inert={readOnly ? '' : undefined}
        aria-readonly={readOnly || undefined}
      >
        <div className="work-diaries-form-grid">
          <label className="form-group">
            <span className="form-label">{tr('date')}</span>
            <DatePicker value={form.date} required onChange={(value) => setFormField('date', value)} />
          </label>
          <label className="form-group">
            <span className="form-label">{tr('project')}</span>
            <ProjectSelect
              projects={selectableProjects}
              value={form.project_id}
              required
              onChange={(value) => setFormField('project_id', value)}
            />
          </label>
          <div className="form-group">
            <span className="form-label">{tr('workDiariesWorkersLabel')} *</span>
            <MultiSelect
              options={workerOptions}
              value={form.worker_ids}
              onChange={(value) => setFormField('worker_ids', value)}
              placeholder={tr('workDiariesWorkersPlaceholder')}
              emptyText={tr('workersEmpty')}
              clearLabel={tr('workDiariesClearWorkers')}
              ariaLabel={tr('workDiariesWorkersLabel')}
            />
          </div>
          <div className="form-group work-diaries-time-range-group">
            <span className="form-label">{timeRangeLabel}</span>
            <div className="work-diaries-time-range-control">
              <label className="work-diaries-time-range-endpoint">
                <span>{tr('workDiariesStart')}</span>
                <input
                  type="time"
                  value={form.start_time}
                  aria-label={tr('workDiariesStart')}
                  onClick={(event) => event.currentTarget.showPicker?.()}
                  onChange={(event) => {
                    const value = event.target.value
                    setForm((prev) => ({
                      ...prev,
                      start_time: value,
                      duration_hours: value ? '' : prev.duration_hours,
                    }))
                  }}
                />
              </label>
              <ArrowRight className="work-diaries-time-range-arrow" size={18} aria-hidden="true" />
              <label className="work-diaries-time-range-endpoint">
                <span>{tr('workDiariesEnd')}</span>
                <input
                  type="time"
                  value={form.end_time}
                  aria-label={tr('workDiariesEnd')}
                  onClick={(event) => event.currentTarget.showPicker?.()}
                  onChange={(event) => {
                    const value = event.target.value
                    setForm((prev) => ({
                      ...prev,
                      end_time: value,
                      duration_hours: value ? '' : prev.duration_hours,
                    }))
                  }}
                />
              </label>
            </div>
          </div>
        </div>

        <div className="work-diaries-tabs work-diaries-entry-tabs" role="tablist">
          {ENTRY_TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              id={`work-diary-entry-tab-${tab}`}
              aria-selected={activeTab === tab}
              aria-controls={`work-diary-entry-panel-${tab}`}
              className={`work-diaries-tab${activeTab === tab ? ' active' : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tr(ENTRY_TAB_LABEL_KEYS[tab])}
              {tab === 'pay' && payAttention ? (
                <span className="work-diaries-entry-tab-badge" title={tr('workDiariesEntryTabAttention')}>
                  !
                </span>
              ) : null}
            </button>
          ))}
        </div>

        <div
          className="work-diaries-entry-panel"
          data-entry-tab="work"
          id="work-diary-entry-panel-work"
          role="tabpanel"
          aria-labelledby="work-diary-entry-tab-work"
          hidden={activeTab !== 'work'}
        >
          <label className="form-group work-diaries-wide">
            <span className="form-label">{tr('workDiariesDescription')}</span>
            <textarea
              className="form-input"
              rows={3}
              value={form.description}
              required
              onChange={(event) => setFormField('description', event.target.value)}
            />
          </label>

          <div className="work-diaries-materials">
            <div className="work-diaries-section-row">
              <strong>{tr('workDiariesMaterialsAndServices')}</strong>
            </div>
            {materials.length > 0 ? (
              <div className="work-diaries-material-row work-diaries-material-header" aria-hidden="true">
                <span>{tr('workDiariesMaterialSource')}</span>
                <span>{tr('description')}</span>
                <span>{tr('quantity')}</span>
                <span>{tr('unit')}</span>
                <span>{tr('workDiariesMaterialUnitPrice')}</span>
                <span>{tr('workDiariesMaterialTotal')}</span>
                <span />
              </div>
            ) : null}
            {materials.map((material, index) => (
              <div
                key={material.rowKey}
                {...materialEditor.getRowProps(
                  material,
                  `work-diaries-material-block${readOnly ? '' : ' is-reorderable'}`
                )}
              >
                {!readOnly ? (
                  <div className="work-diaries-material-drag">
                    <ItemDragHandle number={index + 1} {...materialEditor.getHandleProps(material)} />
                  </div>
                ) : null}
                <div className="work-diaries-material-row">
                  <select
                    className="form-input"
                    value={material.source}
                    onChange={(event) =>
                      updateMaterial(index, {
                        source: event.target.value,
                        expense_id: '',
                        amount: '',
                        quantity: event.target.value === 'service' ? '1' : '',
                        unit: event.target.value === 'service' ? 'usl' : '',
                        source_item_type: '',
                        source_item_id: '',
                        unit_price: '',
                        unit_price_derived: false,
                        legacy_whole_expense: false,
                      })
                    }
                  >
                    <option value="stock">{tr('workDiariesMaterialSourceStock')}</option>
                    <option value="expense">{tr('workDiariesMaterialSourceExpense')}</option>
                    <option value="service">{tr('workDiariesMaterialSourceService')}</option>
                  </select>
                  <input
                    ref={materialEditor.getInputRef(material)}
                    className="form-input"
                    value={material.description}
                    placeholder={tr('description')}
                    onChange={(event) => updateMaterial(index, { description: event.target.value })}
                  />
                  <input
                    className="form-input"
                    type="number"
                    min="0"
                    max={sourceItemForMaterial(material)?.remaining_quantity ?? undefined}
                    step={['m', 'm2', 'm3', 'kg', 't', 'l', 'h'].includes(material.unit) ? '0.1' : '1'}
                    value={material.quantity}
                    placeholder={tr('quantity')}
                    aria-label={tr('quantity')}
                    required={Boolean(
                      material.unit_price !== '' ||
                      sourceItemForMaterial(material)?.remaining_quantity != null
                    )}
                    onChange={(event) => {
                      const value = event.target.value
                      const patch = { quantity: value, unit_price_derived: false }
                      if (material.unit_price !== '') {
                        const sourceItem = sourceItemForMaterial(material)
                        patch.amount =
                          sourceItem &&
                          sourceItem.remaining_quantity != null &&
                          value !== '' &&
                          num(value) >= num(sourceItem.remaining_quantity)
                            ? String(sourceItem.remaining_amount)
                            : materialAmount(value, material.unit_price)
                      }
                      updateMaterial(index, patch)
                    }}
                  />
                  <select
                    className="form-input"
                    value={material.unit}
                    onChange={(event) => updateMaterial(index, { unit: event.target.value })}
                  >
                    <option value="">{tr('unit')}</option>
                    {MATERIAL_UNITS.map((code) => (
                      <option key={code} value={code}>
                        {unitLabel(code)}
                      </option>
                    ))}
                  </select>
                  <label className="work-diaries-material-value-field">
                    <span>{tr('workDiariesMaterialUnitPrice')}</span>
                    <input
                      className="form-input"
                      type="number"
                      min="0"
                      step="0.01"
                      value={material.unit_price}
                      placeholder={tr('workDiariesMaterialUnitPrice')}
                      title={tr('workDiariesMaterialUnitPrice')}
                      required={Boolean(material.quantity !== '' && !materialItemKey(material))}
                      readOnly={Boolean(materialItemKey(material))}
                      onChange={(event) =>
                        updateMaterial(index, {
                          unit_price: event.target.value,
                          unit_price_derived: false,
                          amount: materialAmount(material.quantity, event.target.value),
                        })
                      }
                    />
                  </label>
                  <label className="work-diaries-material-value-field">
                    <span>{tr('workDiariesMaterialTotal')}</span>
                    <input
                      className="form-input"
                      type="text"
                      value={material.amount}
                      placeholder={tr('workDiariesMaterialTotal')}
                      title={tr('workDiariesMaterialTotal')}
                      readOnly
                    />
                  </label>
                  {!readOnly ? (
                    <ItemRemoveButton
                      number={index + 1}
                      onClick={() => setMaterials((prev) => prev.filter((_, i) => i !== index))}
                    />
                  ) : null}
                </div>
                {shouldShowExpensePicker(material) ? (
                  <div className="work-diaries-material-expense-row">
                    {materialExpenseOptions.length === 0 ? (
                      <span className="work-diaries-material-empty">
                        {tr('workDiariesMaterialNoExpenses')}
                      </span>
                    ) : (
                      (() => {
                        const selectedOption = materialExpenseOptions.find(
                          (o) => String(o.id) === String(material.expense_id)
                        )
                        const selectableExpenseOptions = materialExpenseOptions.filter((option) => {
                          if (String(option.id) === String(material.expense_id)) return true
                          if (num(option.remaining_amount) <= 0) return false
                          const optionMaterials = materials.filter(
                            (item) =>
                              item.source === 'expense' && String(item.expense_id) === String(option.id)
                          )
                          const optionItems = option.items || []
                          if (optionItems.length > 0) {
                            const selectedKeys = new Set(optionMaterials.map(materialItemKey).filter(Boolean))
                            return optionItems.some(
                              (item) => !item.is_used && !selectedKeys.has(materialItemKey(item))
                            )
                          }
                          return optionMaterials.length === 0
                        })
                        const expenseItems = selectedOption?.items || []
                        const requiresExpenseItem = expenseItems.length > 0 && !material.legacy_whole_expense
                        const availableExpenseItems = expenseItems.filter((item) => !item.is_used)
                        const selectedExpenseItemKeys = new Set(
                          materials
                            .filter(
                              (item) =>
                                item.source === 'expense' &&
                                String(item.expense_id) === String(material.expense_id)
                            )
                            .map(materialItemKey)
                            .filter(Boolean)
                        )
                        const allExpenseItemsAdded =
                          availableExpenseItems.length > 0 &&
                          availableExpenseItems.every((item) =>
                            selectedExpenseItemKeys.has(materialItemKey(item))
                          )
                        return (
                          <>
                            <select
                              className="form-input"
                              value={material.expense_id}
                              required
                              onChange={(event) => {
                                const option = materialExpenseOptions.find(
                                  (o) => String(o.id) === event.target.value
                                )
                                updateMaterial(index, {
                                  expense_id: event.target.value,
                                  description: option?.description || '',
                                  quantity: option && !(option.items || []).length ? '1' : '',
                                  unit: '',
                                  amount:
                                    option && !(option.items || []).length
                                      ? String(option.remaining_amount)
                                      : '',
                                  source_item_type: '',
                                  source_item_id: '',
                                  unit_price:
                                    option && !(option.items || []).length
                                      ? String(option.remaining_amount)
                                      : '',
                                  unit_price_derived: false,
                                  legacy_whole_expense: false,
                                })
                              }}
                            >
                              <option value="">{tr('workDiariesMaterialExpensePick')}</option>
                              {selectableExpenseOptions.map((option) => (
                                <option key={option.id} value={option.id}>
                                  {dateLabel(option.date)} — {option.description} — {money(option.amount)};{' '}
                                  {tr('workDiariesMaterialAvailable')}: {money(option.remaining_amount)}
                                </option>
                              ))}
                            </select>
                            {expenseItems.length > 0 ? (
                              <>
                                <select
                                  className="form-input"
                                  value={materialItemKey(material)}
                                  required={requiresExpenseItem}
                                  onChange={(event) =>
                                    applyExpenseItem(index, selectedOption, event.target.value)
                                  }
                                >
                                  <option value="" disabled={requiresExpenseItem}>
                                    {material.legacy_whole_expense
                                      ? tr('workDiariesMaterialLegacyWholeExpense')
                                      : tr('workDiariesMaterialItemPick')}
                                  </option>
                                  {expenseItems.map((item) => {
                                    const itemKey = materialItemKey(item)
                                    const availableQuantity = item.remaining_quantity ?? item.quantity
                                    const availableAmount = item.remaining_amount ?? item.total_amount
                                    const selectedElsewhere =
                                      selectedExpenseItemKeys.has(itemKey) &&
                                      itemKey !== materialItemKey(material)
                                    const unavailable = item.is_used || selectedElsewhere
                                    return (
                                      <option key={itemKey} value={itemKey} disabled={unavailable}>
                                        {item.name}
                                        {availableQuantity != null
                                          ? ` — ${tr('workDiariesMaterialAvailable')}: ${availableQuantity}${
                                              item.unit ? ` ${unitLabel(item.unit)}` : ''
                                            }`
                                          : ''}{' '}
                                        — {money(availableAmount)}
                                        {unavailable ? ` — ${tr('workDiariesMaterialItemUsed')}` : ''}
                                      </option>
                                    )
                                  })}
                                </select>
                                {availableExpenseItems.length > 1 && !allExpenseItemsAdded ? (
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-secondary"
                                    title={tr('workDiariesMaterialAddAllItemsHint')}
                                    onClick={() => addAllExpenseItems(index, selectedOption)}
                                  >
                                    <Plus size={14} /> {tr('workDiariesMaterialAddAllItems')}
                                  </button>
                                ) : null}
                              </>
                            ) : null}
                          </>
                        )
                      })()
                    )}
                  </div>
                ) : null}
              </div>
            ))}
            {!readOnly ? (
              <div className="work-diaries-material-add-row">
                <button
                  type="button"
                  className="btn btn-secondary item-editor-add"
                  onClick={() => addMaterial('stock')}
                  disabled={saving}
                >
                  <Plus size={16} /> {tr('workDiariesAddMaterial')}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary item-editor-add"
                  onClick={() => addMaterial('service')}
                  disabled={saving}
                >
                  <Plus size={16} /> {tr('workDiariesAddService')}
                </button>
              </div>
            ) : null}
          </div>

          <div className="work-diaries-collapse">
            <label className="work-diaries-trip-toggle">
              <input
                type="checkbox"
                checked={form.is_trip}
                onChange={(event) => setFormField('is_trip', event.target.checked)}
              />
              <span>{tr('workDiariesTripToggle')}</span>
            </label>
            {form.is_trip ? (
              <WorkDiaryTripSection
                form={form}
                totals={totals}
                teamBillingRate={teamBillingRate}
                readOnly={readOnly}
                setFormField={setFormField}
                onAddService={addServiceLine}
              />
            ) : null}
          </div>

          <div className="work-diaries-collapse">
            <button
              type="button"
              className="work-diaries-collapse-toggle"
              onClick={() => setShowDiaryDetails((prev) => !prev)}
            >
              {showDiaryDetails ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              {tr('workDiariesSectionDiary')}
            </button>
            {showDiaryDetails ? (
              <div className="work-diaries-form-grid">
                <label className="form-group">
                  <span className="form-label">{tr('workDiariesWeather')}</span>
                  <select
                    className="form-input"
                    value={form.weather}
                    onChange={(event) => setFormField('weather', event.target.value)}
                  >
                    <option value="">{tr('select')}</option>
                    {WEATHER_CODES.map((code) => (
                      <option key={code} value={code}>
                        {weatherLabel(code)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-group">
                  <span className="form-label">{tr('workDiariesTemperature')}</span>
                  <input
                    className="form-input"
                    value={form.temperature}
                    onChange={(event) => setFormField('temperature', event.target.value)}
                  />
                </label>
                <label className="form-group work-diaries-wide">
                  <span className="form-label">{tr('note')}</span>
                  <textarea
                    className="form-input"
                    rows={2}
                    value={form.note}
                    onChange={(event) => setFormField('note', event.target.value)}
                  />
                </label>
              </div>
            ) : null}
          </div>
        </div>

        <div
          className="work-diaries-entry-panel"
          data-entry-tab="pay"
          id="work-diary-entry-panel-pay"
          role="tabpanel"
          aria-labelledby="work-diary-entry-tab-pay"
          hidden={activeTab !== 'pay'}
        >
          <div className="work-diaries-form-grid">
            <div className="form-group">
              <span className="form-label field-label-with-tooltip">
                {tr('workDiariesHourlyRate')}
                <FieldTooltip text={tr('workDiariesCostRateTooltip')} />
              </span>
              <input
                className="form-input"
                type="number"
                min="0"
                step="0.01"
                value={manualRate}
                placeholder={autoRate > 0 ? String(Math.round(autoRate * 100) / 100) : ''}
                onChange={(event) => setFormField('team_hourly_rate_snapshot', event.target.value)}
              />
              <small className="work-diaries-rate-hint">
                {tr('workDiariesAutoRate')}: {money(autoRate)}
                {!readOnly && manualRate !== '' && num(manualRate) !== autoRate ? (
                  <button
                    type="button"
                    className="btn-link"
                    onClick={() => setFormField('team_hourly_rate_snapshot', '')}
                  >
                    {tr('workDiariesApplyAutoRate')}
                  </button>
                ) : null}
              </small>
              {hasZeroRateWorker ? (
                <small className="work-diaries-rate-warning">{tr('workDiariesRateZeroWarning')}</small>
              ) : null}
            </div>
            <div className="form-group">
              <span className="form-label field-label-with-tooltip">
                {tr('workDiariesTeamBillingRate')}
                <FieldTooltip text={tr('workDiariesTeamBillingRateTooltip')} align="right" />
              </span>
              <input
                className="form-input"
                type="number"
                min="0"
                step="0.01"
                value={manualBillingRate}
                placeholder={autoBillingRate > 0 ? String(Math.round(autoBillingRate * 100) / 100) : ''}
                onChange={(event) => setFormField('team_billing_hourly_rate_snapshot', event.target.value)}
              />
              <small className="work-diaries-rate-hint">
                {tr('workDiariesTeamBillingRateHint')}: {money(autoBillingRate)}
                {!readOnly && manualBillingRate !== '' && num(manualBillingRate) !== autoBillingRate ? (
                  <button
                    type="button"
                    className="btn-link"
                    onClick={() => setFormField('team_billing_hourly_rate_snapshot', '')}
                  >
                    {tr('workDiariesApplyAutoRate')}
                  </button>
                ) : null}
              </small>
              {teamBillingRate === 0 ? (
                <small className="work-diaries-rate-warning">{tr('workDiariesBillingRateZeroWarning')}</small>
              ) : null}
            </div>
            <label className="form-group">
              <span className="form-label field-label-with-tooltip">
                {tr('workDiariesMaterialBillingMultiplier')}
                <FieldTooltip text={tr('workDiariesMaterialBillingMultiplierTooltip')} />
              </span>
              <input
                className="form-input"
                type="number"
                min="0.01"
                step="0.01"
                value={form.material_billing_multiplier}
                required
                onChange={(event) => setFormField('material_billing_multiplier', event.target.value)}
              />
              <small className="work-diaries-rate-hint">
                {tr('workDiariesBillableMaterials')}: {money(totals.billableMaterials)}
              </small>
            </label>
            <div className="form-group work-diaries-billable-override">
              <span className="form-label field-label-with-tooltip">
                {tr('workDiariesBillableOverride')}
                <FieldTooltip text={tr('workDiariesBillableOverrideTooltip')} align="right" />
              </span>
              <div className="work-diaries-billable-override-control">
                <input
                  className="form-input"
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.billable_amount_override}
                  placeholder={String(Math.round(totals.calculatedBillable * 100) / 100)}
                  onChange={(event) => setFormField('billable_amount_override', event.target.value)}
                />
                {!readOnly && totals.billableAdjusted ? (
                  <button
                    type="button"
                    className="btn btn-secondary work-diaries-billable-reset"
                    onClick={() => setFormField('billable_amount_override', '')}
                    title={tr('workDiariesBillableReset')}
                    aria-label={tr('workDiariesBillableReset')}
                  >
                    <RotateCcw size={16} />
                  </button>
                ) : null}
              </div>
              <small className="work-diaries-rate-hint">
                {tr('workDiariesBillableAuto')}: {money(totals.calculatedBillable)}
              </small>
            </div>
          </div>

          <div className="work-diaries-pay-block">
            <div className="work-diaries-section-row">
              <strong>{tr('workDiariesPaySection')}</strong>
            </div>
            {payError ? (
              <div className="work-diaries-pay-alert is-error" role="alert">
                <span>{tr('workDiariesPayLoadError')}</span>
                {!readOnly ? (
                  <button
                    type="button"
                    className="btn btn-sm btn-secondary"
                    onClick={() => setPayReload((value) => value + 1)}
                  >
                    <RotateCcw size={14} /> {tr('workDiariesPayRetry')}
                  </button>
                ) : null}
              </div>
            ) : null}
            {payDateNotice && !payError ? (
              <div className="work-diaries-pay-alert" role="status">
                {tr('workDiariesPayDateNotice')}
              </div>
            ) : null}
            {/* Пока начисления даты не загружены (или не загрузились), поля не редактируются. */}
            <fieldset className="work-diaries-pay-fieldset" disabled={payBlocked}>
              <WorkDiaryWorkerPaySection
                workers={selectedWorkers}
                payState={payState}
                savedDays={savedDays}
                resolved={resolvedPay}
                shares={shareByWorker}
                duration={totals.duration}
                showAllowances={showPayAllowances}
                readOnly={readOnly}
                onChange={setWorkerPay}
                onApplyAll={applyPayModeToAll}
              />
            </fieldset>
          </div>

          {legacyAllowances ? (
            <div className="work-diaries-collapse">
              <button
                type="button"
                className="work-diaries-collapse-toggle"
                onClick={() => setShowAllowances((prev) => !prev)}
              >
                {showAllowances ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                {tr('workDiariesLegacyAllowances')}
                {!showAllowances && totals.legacyAllowances > 0 ? (
                  <span> — {money(totals.legacyAllowances)}</span>
                ) : null}
              </button>
              {showAllowances ? (
                <p className="work-diaries-pay-hint">{tr('workDiariesLegacyAllowancesHint')}</p>
              ) : null}
              {showAllowances ? (
                <div className="work-diaries-allowances">
                  <label>
                    <input
                      type="checkbox"
                      checked={form.per_diem}
                      onChange={(event) => setFormField('per_diem', event.target.checked)}
                    />{' '}
                    {tr('workDiariesPerDiemPerWorker')}
                  </label>
                  <input
                    className="form-input"
                    type="number"
                    min="0"
                    step="0.01"
                    value={form.per_diem_amount}
                    placeholder={tr('amount')}
                    onChange={(event) => setFormField('per_diem_amount', event.target.value)}
                  />
                  <label>
                    <input
                      type="checkbox"
                      checked={form.food_allowance}
                      onChange={(event) => setFormField('food_allowance', event.target.checked)}
                    />{' '}
                    {tr('workDiariesFoodPerWorker')}
                  </label>
                  <input
                    className="form-input"
                    type="number"
                    min="0"
                    step="0.01"
                    value={form.food_amount}
                    placeholder={tr('amount')}
                    onChange={(event) => setFormField('food_amount', event.target.value)}
                  />
                  <span className="work-diaries-allowance-label">{tr('workDiariesLodgingTotal')}</span>
                  <input
                    className="form-input"
                    type="number"
                    min="0"
                    step="0.01"
                    value={form.lodging_amount}
                    placeholder={tr('amount')}
                    onChange={(event) => setFormField('lodging_amount', event.target.value)}
                  />
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="work-diaries-live-calc">
          <div className="work-diaries-live-calc-line">
            <strong>{tr('workDiariesCalcSummary')}:</strong>
            <span>
              {tr('workDiariesCalcHoursOnSite')}: <b>{hours(totals.duration)}</b>
            </span>
            <span>
              {tr('workDiariesPersonHours')}: <b>{hours(totals.personHours)}</b>
              {totals.overtimePersonHours > 0
                ? ` (${tr('workDiariesCalcOvertime')}: ${hours(totals.overtimePersonHours)})`
                : ''}
            </span>
            {paySummary ? (
              <span>
                {tr('workDiariesPayMode')}: <b>{paySummary}</b>
              </span>
            ) : null}
          </div>
          <div className="work-diaries-live-calc-line">
            <strong>{tr('workDiariesCalcAccrued')}:</strong>
            <span>
              {tr('workDiariesCalcLabor')}: <b>{money(totals.labor)}</b>
              {totals.dayLabor > 0 && totals.hourlyLabor > 0
                ? ` (${tr('workDiariesCalcLaborDay')}: ${money(totals.dayLabor)})`
                : ''}
            </span>
            {totals.allowances > 0 ? (
              <span>
                {tr('workDiariesCalcTripAllowances')}: <b>{money(totals.allowances)}</b>
              </span>
            ) : null}
            {totals.materials > 0 ? (
              <span>
                {tr('workDiariesMaterials')}: <b>{money(totals.materials)}</b>
              </span>
            ) : null}
            <span>
              {tr('workDiariesTotalCostShort')}: <b>{money(totals.totalCost)}</b>
            </span>
          </div>
          <div className="work-diaries-live-calc-line">
            <strong>{tr('workDiariesCalcCustomer')}:</strong>
            <span>
              {tr('workDiariesCustomerLabor')}: <b>{money(totals.billableLabor)}</b>
            </span>
            {totals.materials > 0 ? (
              <span>
                {tr('workDiariesBillableMaterials')}: <b>{money(totals.billableMaterials)}</b>
              </span>
            ) : null}
            {totals.services > 0 ? (
              <span>
                {tr('workDiariesServices')}: <b>{money(totals.services)}</b>
              </span>
            ) : null}
            {totals.billableAdjusted ? (
              <span>
                {tr('workDiariesBillableAdjustment')}: <b>{money(totals.billableAdjustment)}</b>
              </span>
            ) : null}
            <span>
              {tr('workDiariesBillable')}: <b>{money(totals.billable)}</b>
            </span>
            {totals.billableAdjusted ? <span>{tr('workDiariesBillableAdjusted')}</span> : null}
            <span className={totals.margin < 0 ? 'work-diaries-margin-negative' : undefined}>
              {tr('workDiariesCalcMargin')}: <b>{money(totals.margin)}</b>
            </span>
          </div>
        </div>
        {!readOnly ? (
          <div className="modal-actions">
            {payError ? (
              <span className="work-diaries-save-blocked">{tr('workDiariesPaySaveBlocked')}</span>
            ) : null}
            <button type="button" className="btn btn-secondary" onClick={close}>
              {tr('cancel')}
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={saving || form.worker_ids.length === 0 || payBlocked}
              title={
                payError
                  ? tr('workDiariesPaySaveBlocked')
                  : payLoading
                    ? tr('workDiariesPayLoading')
                    : undefined
              }
            >
              <Save size={16} /> {saving ? tr('saving') : tr('save')}
            </button>
          </div>
        ) : null}
      </form>
      {readOnly ? (
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={close}>
            {tr('close')}
          </button>
        </div>
      ) : null}
    </Modal>
  )
}
