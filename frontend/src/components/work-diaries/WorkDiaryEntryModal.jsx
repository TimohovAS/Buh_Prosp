import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, ChevronDown, ChevronRight, Plus, RotateCcw, Save, Trash2 } from 'lucide-react'
import { api } from '../../api'
import { tr } from '../../i18n'
import DatePicker from '../DatePicker'
import FieldTooltip from '../FieldTooltip'
import Modal from '../Modal'
import MultiSelect from '../MultiSelect'
import {
  DEFAULT_MATERIAL_BILLING_MULTIPLIER,
  MATERIAL_UNITS,
  WEATHER_CODES,
  computeEntryTotals,
  dateLabel,
  defaultWorkerHourlyRate,
  hours,
  money,
  num,
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
  material_billing_multiplier: String(DEFAULT_MATERIAL_BILLING_MULTIPLIER),
  billable_amount_override: '',
  per_diem: false,
  per_diem_amount: '',
  lodging_amount: '',
  food_allowance: false,
  food_amount: '',
  weather: '',
  temperature: '',
  note: '',
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
  legacy_whole_expense: false,
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
    weather: entry.weather || '',
    temperature: entry.temperature || '',
    note: entry.note || '',
  }
}

function materialsFromEntry(entry) {
  return (entry?.materials || []).map((material) => ({
    description: material.description || '',
    quantity: material.quantity == null ? '' : String(material.quantity),
    unit: material.unit || '',
    source: material.source || 'stock',
    expense_id: material.expense_id ? String(material.expense_id) : '',
    amount: material.amount ? String(material.amount) : '',
    source_item_type: material.source_item_type || '',
    source_item_id: material.source_item_id ? String(material.source_item_id) : '',
    unit_price: material.unit_price_snapshot == null ? '' : String(material.unit_price_snapshot),
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
}) {
  const [form, setForm] = useState(emptyForm)
  const [materials, setMaterials] = useState([])
  const [saving, setSaving] = useState(false)
  const [expenseOptions, setExpenseOptions] = useState([])
  const [showAllowances, setShowAllowances] = useState(false)
  const [showDiaryDetails, setShowDiaryDetails] = useState(false)

  useEffect(() => {
    if (!isOpen) return
    setForm(formFromEntry(entry, defaultProjectId, materialBillingMultiplier))
    setMaterials(materialsFromEntry(entry))
    setShowAllowances(
      Boolean(entry && (entry.per_diem || entry.food_allowance || num(entry.lodging_amount) > 0))
    )
    setShowDiaryDetails(Boolean(entry && (entry.weather || entry.temperature || entry.note)))
  }, [isOpen, entry, defaultProjectId, materialBillingMultiplier])

  useEffect(() => {
    if (!isOpen || !form.project_id) {
      setExpenseOptions([])
      return
    }
    api.workDiaries
      .expenseOptions({
        project_id: form.project_id,
        ...(entry?.id ? { entry_id: entry.id } : {}),
      })
      .then(setExpenseOptions)
  }, [isOpen, form.project_id, entry?.id])

  const workerOptions = useMemo(
    () => workers.map((worker) => ({ value: worker.id, label: worker.name })),
    [workers]
  )

  const autoRate = useMemo(() => teamAutoRate(workers, form.worker_ids), [workers, form.worker_ids])
  const teamBillingRate = useMemo(
    () => teamBillingAutoRate(workers, form.worker_ids),
    [workers, form.worker_ids]
  )
  const hasZeroRateWorker = useMemo(() => {
    const selected = new Set(form.worker_ids.map(Number))
    return workers.some((worker) => selected.has(worker.id) && defaultWorkerHourlyRate(worker) === 0)
  }, [workers, form.worker_ids])

  const manualRate = form.team_hourly_rate_snapshot
  const effectiveRate = manualRate === '' ? autoRate : num(manualRate)
  const effectiveMultiplier = entry ? num(entry.overtime_multiplier) : num(overtimeMultiplier)

  // Для расчета материалов пустая сумма привязанной строки означает всю сумму расхода
  const materialsForCalc = useMemo(
    () =>
      materials.map((item) => {
        if (item.source === 'expense' && item.amount === '' && item.expense_id) {
          const option = expenseOptions.find((o) => String(o.id) === String(item.expense_id))
          return {
            amount: option
              ? option.remaining_amount
              : num(item.expense_remaining_amount ?? item.expense_amount),
          }
        }
        return { amount: num(item.amount) }
      }),
    [materials, expenseOptions]
  )

  const totals = computeEntryTotals({
    form,
    materials: materialsForCalc,
    teamRate: effectiveRate,
    teamBillingRate,
    overtimeMultiplier: effectiveMultiplier,
  })
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
    source: 'expense',
    expense_id: String(option.id),
    source_item_type: item.source_item_type,
    source_item_id: String(item.source_item_id),
    description: item.name,
    quantity: item.quantity == null ? '' : String(item.quantity),
    unit: item.unit || '',
    unit_price: item.unit_price == null ? '' : String(item.unit_price),
    amount: item.total_amount ? String(item.total_amount) : '',
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
        materialIndex === index ? { ...material, ...materialRowFromItem(option, item) } : material
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

  const close = () => {
    if (saving) return
    onClose()
  }

  const submit = async (event) => {
    event.preventDefault()
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
        material_billing_multiplier: num(form.material_billing_multiplier) || materialBillingMultiplier,
        billable_amount_override:
          form.billable_amount_override === '' ? null : num(form.billable_amount_override),
        per_diem_amount: num(form.per_diem_amount),
        lodging_amount: num(form.lodging_amount),
        food_amount: num(form.food_amount),
        materials: materials
          .filter(
            (item) =>
              (item.source === 'stock' && item.description.trim()) ||
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
            unit_price_snapshot: item.unit_price === '' ? null : num(item.unit_price),
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
      title={tr(entry ? 'workDiariesEditEntry' : 'workDiariesNewEntry')}
      maxWidth="1120px"
      bodyClassName="work-diaries-entry-modal-body"
    >
      <form className="work-diaries-entry-form" onSubmit={submit}>
        <div className="work-diaries-form-grid">
          <label className="form-group">
            <span className="form-label">{tr('date')}</span>
            <DatePicker value={form.date} required onChange={(value) => setFormField('date', value)} />
          </label>
          <label className="form-group">
            <span className="form-label">{tr('project')}</span>
            <select
              className="form-input"
              value={form.project_id}
              required
              onChange={(event) => setFormField('project_id', event.target.value)}
            >
              <option value="">{tr('select')}</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
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
              {manualRate !== '' && num(manualRate) !== autoRate ? (
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
            <input className="form-input" type="number" value={teamBillingRate} readOnly />
            <small className="work-diaries-rate-hint">{tr('workDiariesTeamBillingRateHint')}</small>
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
              {totals.billableAdjusted ? (
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
        </div>

        <div className="work-diaries-materials">
          <div className="work-diaries-section-row">
            <strong>{tr('workDiariesMaterials')}</strong>
          </div>
          {materials.map((material, index) => (
            <div className="work-diaries-material-block" key={index}>
              <div className="work-diaries-material-row">
                <select
                  className="form-input"
                  value={material.source}
                  onChange={(event) =>
                    updateMaterial(index, {
                      source: event.target.value,
                      expense_id: '',
                      amount: '',
                      source_item_type: '',
                      source_item_id: '',
                      unit_price: '',
                      legacy_whole_expense: false,
                    })
                  }
                >
                  <option value="stock">{tr('workDiariesMaterialSourceStock')}</option>
                  <option value="expense">{tr('workDiariesMaterialSourceExpense')}</option>
                </select>
                <input
                  className="form-input"
                  value={material.description}
                  placeholder={tr('description')}
                  onChange={(event) => updateMaterial(index, { description: event.target.value })}
                />
                <input
                  className="form-input"
                  type="number"
                  min="0"
                  step="0.001"
                  value={material.quantity}
                  placeholder={tr('quantity')}
                  onChange={(event) => {
                    const value = event.target.value
                    const patch = { quantity: value }
                    // Строка из позиции чека: сумма пересчитывается по цене за единицу
                    const unitPrice = num(material.unit_price)
                    if (unitPrice > 0 && value !== '') {
                      patch.amount = String(Math.round(num(value) * unitPrice * 100) / 100)
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
                <input
                  className="form-input"
                  type="number"
                  min="0"
                  step="0.01"
                  value={material.amount}
                  placeholder={
                    material.source === 'expense' ? tr('workDiariesMaterialExpenseAmountHint') : tr('amount')
                  }
                  onChange={(event) => updateMaterial(index, { amount: event.target.value })}
                />
                <button
                  type="button"
                  className="btn btn-sm btn-danger"
                  onClick={() => setMaterials((prev) => prev.filter((_, i) => i !== index))}
                >
                  <Trash2 size={16} />
                </button>
              </div>
              {material.source === 'expense' ? (
                <div className="work-diaries-material-expense-row">
                  {materialExpenseOptions.length === 0 ? (
                    <span className="work-diaries-material-empty">{tr('workDiariesMaterialNoExpenses')}</span>
                  ) : (
                    (() => {
                      const selectedOption = materialExpenseOptions.find(
                        (o) => String(o.id) === String(material.expense_id)
                      )
                      const selectableExpenseOptions = materialExpenseOptions.filter((option) => {
                        if (String(option.id) === String(material.expense_id)) return true
                        if (num(option.remaining_amount) <= 0) return false
                        const optionMaterials = materials.filter(
                          (item) => item.source === 'expense' && String(item.expense_id) === String(option.id)
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
                                quantity: '',
                                unit: '',
                                amount: '',
                                source_item_type: '',
                                source_item_id: '',
                                unit_price: '',
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
                                  const selectedElsewhere =
                                    selectedExpenseItemKeys.has(itemKey) &&
                                    itemKey !== materialItemKey(material)
                                  const unavailable = item.is_used || selectedElsewhere
                                  return (
                                    <option key={itemKey} value={itemKey} disabled={unavailable}>
                                      {item.name}
                                      {item.quantity != null
                                        ? ` — ${item.quantity}${item.unit ? ` ${unitLabel(item.unit)}` : ''}`
                                        : ''}{' '}
                                      — {money(item.total_amount)}
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
          <div className="work-diaries-material-add-row">
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => setMaterials((prev) => [...prev, { ...emptyMaterial }])}
            >
              <Plus size={16} /> {tr('add')}
            </button>
          </div>
        </div>

        <div className="work-diaries-collapse">
          <button
            type="button"
            className="work-diaries-collapse-toggle"
            onClick={() => setShowAllowances((prev) => !prev)}
          >
            {showAllowances ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            {tr('workDiariesSectionAllowances')}
            {!showAllowances && totals.allowances > 0 ? <span> — {money(totals.allowances)}</span> : null}
          </button>
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

        <div className="work-diaries-live-calc">
          <strong>{tr('workDiariesCalcSummary')}:</strong>
          <span>
            {tr('workDiariesPersonHours')}: <b>{hours(totals.personHours)}</b>
            {totals.overtimePersonHours > 0
              ? ` (${tr('workDiariesCalcOvertime')}: ${hours(totals.overtimePersonHours)})`
              : ''}
          </span>
          <span>
            {tr('workDiariesLabor')}: <b>{money(totals.labor)}</b>
          </span>
          {totals.allowances > 0 ? (
            <span>
              {tr('workDiariesSectionAllowances')}: <b>{money(totals.allowances)}</b>
            </span>
          ) : null}
          {totals.materials > 0 ? (
            <span>
              {tr('workDiariesMaterials')}: <b>{money(totals.materials)}</b>
            </span>
          ) : null}
          {totals.materials > 0 ? (
            <span>
              {tr('workDiariesBillableMaterials')}: <b>{money(totals.billableMaterials)}</b>
            </span>
          ) : null}
          <span>
            {tr('workDiariesCustomerLabor')}: <b>{money(totals.billableLabor)}</b>
          </span>
          {totals.billableAdjusted ? (
            <span>
              {tr('workDiariesBillableAdjustment')}: <b>{money(totals.billableAdjustment)}</b>
            </span>
          ) : null}
          {totals.billable != null ? (
            <span>
              {tr('workDiariesBillable')}: <b>{money(totals.billable)}</b>
            </span>
          ) : null}
          {totals.billableAdjusted ? <span>{tr('workDiariesBillableAdjusted')}</span> : null}
        </div>

        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={close}>
            {tr('cancel')}
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving || form.worker_ids.length === 0}>
            <Save size={16} /> {saving ? tr('saving') : tr('save')}
          </button>
        </div>
      </form>
    </Modal>
  )
}
