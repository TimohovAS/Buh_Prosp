// Привязка уже записанного расхода к работнику и правка этой привязки.
// Одна форма на кассу и на расходы: наличная выдача, покупка работнику с карты
// или по чеку учитываются в его доходе одинаково, а деньги самой записи при
// этом не меняются.
import { useEffect, useState } from 'react'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from './DatePicker'
import Modal from './Modal'
import { UI_DASH, formatInteger as fmtAmount } from '../utils/formatters'

const emptyForm = {
  worker_id: '',
  payout_type: 'regular',
  period_start: '',
  period_end: '',
}

const PAYOUT_TYPE_OPTIONS = [
  ['regular', 'workerPayoutRegular'],
  ['weekly', 'workerPayoutWeekly'],
  ['monthly', 'workerPayoutMonthly'],
  ['purchase', 'workerPayoutPurchase'],
  ['trip_advance', 'workerPayoutTripAdvance'],
  ['trip_final', 'workerPayoutTripFinal'],
]

const toFormValue = (value) => (value === null || value === undefined ? '' : String(value))

// В старых записях работник указан только в описании: подставляем его, если
// имя совпало точно.
const matchWorkerIdByName = (list, description) => {
  const value = String(description || '')
    .trim()
    .toLowerCase()
  if (!value) return ''
  const match = (list || []).find(
    (worker) =>
      String(worker.name || '')
        .trim()
        .toLowerCase() === value
  )
  return match ? String(match.id) : ''
}

export default function WorkerPayoutLinkModal({ isOpen, target, onClose, onSaved }) {
  const [workers, setWorkers] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const payoutId = target?.payoutId || null

  useEffect(() => {
    if (!isOpen) return undefined
    let cancelled = false
    setError('')
    setLoading(true)
    const load = async () => {
      // Архивных тоже берём: покупка или выплата могла быть тому, кто уже не работает.
      const [list, payout] = await Promise.all([
        api.workers.list(),
        payoutId ? api.workers.getPayout(payoutId) : Promise.resolve(null),
      ])
      if (cancelled) return
      setWorkers(list)
      setForm(
        payout
          ? {
              worker_id: toFormValue(payout.worker_id),
              payout_type: payout.payout_type || 'regular',
              period_start: payout.period_start || '',
              period_end: payout.period_end || '',
            }
          : {
              ...emptyForm,
              payout_type: target?.defaultPayoutType || emptyForm.payout_type,
              worker_id: matchWorkerIdByName(list, target?.description),
            }
      )
    }
    load()
      .catch((loadError) => {
        if (!cancelled) setError(loadError.message || tr('loadError'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, payoutId, target?.cashEntryId, target?.expenseId])

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!form.worker_id) return
    setSaving(true)
    setError('')
    try {
      const payload = {
        worker_id: parseInt(form.worker_id, 10),
        payout_type: form.payout_type,
        period_start: form.period_start || null,
        period_end: form.period_end || null,
      }
      if (payoutId) {
        await api.workers.updatePayoutLink(payoutId, payload)
      } else if (target?.cashEntryId) {
        await api.workers.attachPayout({ ...payload, cash_entry_id: target.cashEntryId })
      } else {
        await api.workers.attachPayout({ ...payload, expense_id: target.expenseId })
      }
      onSaved()
    } catch (saveError) {
      setError(saveError.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const handleUnlink = async () => {
    if (!payoutId || !confirm(tr('workerPayoutUnlinkConfirm'))) return
    setSaving(true)
    setError('')
    try {
      await api.workers.unlinkPayout(payoutId)
      onSaved()
    } catch (unlinkError) {
      setError(unlinkError.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const summary = target
    ? `${target.date || UI_DASH} ${UI_DASH} ${fmtAmount(target.amount)} ${target.currency || 'RSD'} ${UI_DASH} ${
        target.description || ''
      }`.trim()
    : UI_DASH

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={payoutId ? tr('workerPayoutRetype') : tr('workerPayoutAttachTitle')}
    >
      <form onSubmit={handleSubmit} className="card" style={{ padding: '1rem' }}>
        {error ? <div className="alert alert-danger">{error}</div> : null}
        <p className="text-muted" style={{ marginTop: 0 }}>
          {payoutId ? tr('workerPayoutRetypeHint') : tr('workerPayoutAttachHint')}
        </p>
        <div className="form-group">
          <label className="form-label">{tr('workerPayoutAttachEntry')}</label>
          <div className="record-field-text">{summary}</div>
        </div>
        <div className="form-group">
          <label className="form-label">{tr('worker')}</label>
          <select
            className="form-input"
            value={form.worker_id}
            onChange={(event) => setForm((previous) => ({ ...previous, worker_id: event.target.value }))}
            disabled={loading}
            required
          >
            <option value="">{UI_DASH}</option>
            {workers.map((worker) => (
              <option key={worker.id} value={worker.id}>
                {worker.is_active ? worker.name : `${worker.name} (${tr('archive')})`}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">{tr('workerPayoutType')}</label>
          <select
            className="form-input"
            value={form.payout_type}
            onChange={(event) => setForm((previous) => ({ ...previous, payout_type: event.target.value }))}
            disabled={loading}
          >
            {PAYOUT_TYPE_OPTIONS.map(([value, labelKey]) => (
              <option key={value} value={value}>
                {tr(labelKey)}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">{tr('workerPayoutPeriodStart')}</label>
          <DatePicker
            value={form.period_start}
            onChange={(value) => setForm((previous) => ({ ...previous, period_start: value }))}
          />
        </div>
        <div className="form-group">
          <label className="form-label">{tr('workerPayoutPeriodEnd')}</label>
          <DatePicker
            value={form.period_end}
            onChange={(value) => setForm((previous) => ({ ...previous, period_end: value }))}
          />
        </div>
        <div className="modal-actions">
          {payoutId ? (
            <button
              type="button"
              className="btn btn-danger"
              style={{ marginRight: 'auto' }}
              disabled={saving || loading}
              onClick={handleUnlink}
            >
              {tr('workerPayoutUnlink')}
            </button>
          ) : null}
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            {tr('cancel')}
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving || loading || !form.worker_id}>
            {saving || loading ? tr('loading') : payoutId ? tr('save') : tr('workerPayoutAttachSubmit')}
          </button>
        </div>
      </form>
    </Modal>
  )
}
