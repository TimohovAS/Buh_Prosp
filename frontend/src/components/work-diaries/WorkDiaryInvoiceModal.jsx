import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { FileText } from 'lucide-react'
import { api } from '../../api'
import { tr, trFor } from '../../i18n'
import DatePicker from '../DatePicker'
import Modal from '../Modal'
import { dateLabel, money } from './workDiaryUtils'

function todayIso() {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function defaultLineName(entry) {
  return entry.description.slice(0, 500)
}

function invoicePeriod(entries) {
  if (!entries.length) return ''
  const dates = entries.map((entry) => entry.date).sort()
  const first = dateLabel(dates[0])
  const last = dateLabel(dates[dates.length - 1])
  return first === last ? first : `${first} - ${last}`
}

function InvoiceLineTextarea({ value, onChange }) {
  const inputRef = useRef(null)

  useLayoutEffect(() => {
    const input = inputRef.current
    if (!input) return

    const resize = () => {
      input.style.height = 'auto'
      const borderHeight = input.offsetHeight - input.clientHeight
      input.style.height = `${input.scrollHeight + borderHeight}px`
    }

    resize()
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [value])

  return (
    <textarea
      ref={inputRef}
      className="form-input work-diaries-invoice-line-input"
      rows={1}
      value={value}
      maxLength={500}
      onChange={onChange}
    />
  )
}

export default function WorkDiaryInvoiceModal({ isOpen, onClose, onCreated, entries, project }) {
  const [form, setForm] = useState({
    issued_date: todayIso(),
    due_date: '',
    invoice_number: '',
    contract_id: '',
    contract_payment_type: 'intermediate',
    description: '',
    note: '',
  })
  const [lines, setLines] = useState([])
  const [contracts, setContracts] = useState([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isOpen) return
    const period = invoicePeriod(entries)
    setForm({
      issued_date: todayIso(),
      due_date: '',
      invoice_number: '',
      contract_id: '',
      contract_payment_type: 'intermediate',
      description: trFor('sr', 'workDiariesInvoiceDescription', {
        project: project?.name || '',
        period,
      }),
      note: '',
    })
    setLines(
      [...entries]
        .sort((left, right) => left.date.localeCompare(right.date))
        .map((entry) => ({
          entry_id: entry.id,
          name: defaultLineName(entry),
          amount: String(entry.remaining_billable_amount),
          available: Number(entry.remaining_billable_amount) || 0,
          date: entry.date,
        }))
    )
    setError('')
  }, [isOpen, entries, project])

  useEffect(() => {
    if (!isOpen || !project?.client_id) {
      setContracts([])
      return
    }
    api.contracts
      .list({ client_id: project.client_id, status: 'active' })
      .then((items) => {
        const available = items.filter(
          (contract) => !contract.project_id || String(contract.project_id) === String(project.id)
        )
        setContracts(available)
        const projectContract = available.find(
          (contract) => String(contract.project_id) === String(project.id)
        )
        if (projectContract) {
          setForm((current) => ({ ...current, contract_id: String(projectContract.id) }))
        }
      })
      .catch(() => setContracts([]))
  }, [isOpen, project])

  const total = useMemo(() => lines.reduce((sum, line) => sum + (Number(line.amount) || 0), 0), [lines])

  const updateLine = (entryId, field, value) => {
    setLines((current) =>
      current.map((line) => (line.entry_id === entryId ? { ...line, [field]: value } : line))
    )
  }

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    const invalidLine = lines.find((line) => {
      const amount = Number(line.amount)
      return !line.name.trim() || !Number.isFinite(amount) || amount <= 0 || amount > line.available
    })
    if (invalidLine) {
      setError(tr('workDiariesInvoiceInvalidAmount'))
      return
    }
    setSaving(true)
    try {
      const created = await api.workDiaries.createInvoice({
        issued_date: form.issued_date,
        due_date: form.due_date || null,
        invoice_number: form.invoice_number.trim() || null,
        contract_id: form.contract_id ? Number(form.contract_id) : null,
        contract_payment_type: form.contract_id ? form.contract_payment_type : null,
        description: form.description.trim() || null,
        note: form.note.trim() || null,
        lines: lines.map((line) => ({
          entry_id: line.entry_id,
          name: line.name.trim(),
          amount: Number(line.amount),
        })),
      })
      await onCreated(created)
    } catch (requestError) {
      setError(requestError.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={saving ? () => {} : onClose}
      title={tr('workDiariesCreateInvoice')}
      maxWidth="1100px"
      className="work-diaries-invoice-modal"
      resizable={false}
      bodyClassName="work-diaries-invoice-modal-body"
    >
      <form className="work-diaries-invoice-form" onSubmit={submit}>
        <div className="work-diaries-invoice-context">
          <span>
            {tr('project')}: <strong>{project?.name || '-'}</strong>
          </span>
          <span>
            {tr('client')}: <strong>{project?.client_name || '-'}</strong>
          </span>
          <span>
            {tr('workDiariesInvoiceEntriesCount')}: <strong>{lines.length}</strong>
          </span>
        </div>

        <div className="work-diaries-invoice-grid">
          <label className="form-group">
            <span className="form-label">{tr('workDiariesInvoiceDate')}</span>
            <DatePicker
              value={form.issued_date}
              onChange={(value) => setForm((current) => ({ ...current, issued_date: value }))}
            />
          </label>
          <label className="form-group">
            <span className="form-label">{tr('workDiariesInvoiceDueDate')}</span>
            <DatePicker
              value={form.due_date}
              onChange={(value) => setForm((current) => ({ ...current, due_date: value }))}
              placeholder={tr('workDiariesInvoiceDueDate')}
            />
          </label>
          <label className="form-group">
            <span className="form-label">{tr('invoiceNumber')}</span>
            <input
              className="form-input"
              value={form.invoice_number}
              onChange={(event) => setForm((current) => ({ ...current, invoice_number: event.target.value }))}
              placeholder={tr('workDiariesInvoiceNumberAuto')}
            />
          </label>
          <label className="form-group">
            <span className="form-label">{tr('contract')}</span>
            <select
              className="form-input"
              value={form.contract_id}
              onChange={(event) => setForm((current) => ({ ...current, contract_id: event.target.value }))}
            >
              <option value="">{tr('workDiariesInvoiceNoContract')}</option>
              {contracts.map((contract) => (
                <option key={contract.id} value={contract.id}>
                  {contract.number}
                  {contract.subject ? ` - ${contract.subject}` : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="form-group">
            <span className="form-label">{tr('workDiariesInvoicePaymentType')}</span>
            <select
              className="form-input"
              value={form.contract_payment_type}
              disabled={!form.contract_id}
              onChange={(event) =>
                setForm((current) => ({ ...current, contract_payment_type: event.target.value }))
              }
            >
              <option value="advance">{tr('contractPaymentAdvance')}</option>
              <option value="intermediate">{tr('contractPaymentIntermediate')}</option>
              <option value="closing">{tr('contractPaymentClosing')}</option>
            </select>
          </label>
          <label className="form-group work-diaries-invoice-description">
            <span className="form-label">{tr('description')}</span>
            <input
              className="form-input"
              value={form.description}
              maxLength={500}
              onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
            />
          </label>
        </div>

        <div className="work-diaries-invoice-lines">
          <div className="table-wrap work-diaries-invoice-lines-scroll">
            <table>
              <thead>
                <tr>
                  <th>{tr('date')}</th>
                  <th>{tr('workDiariesInvoiceLine')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('workDiariesInvoiceAvailable')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('workDiariesInvoiceThisAmount')}</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line) => (
                  <tr key={line.entry_id}>
                    <td className="date-cell">{dateLabel(line.date)}</td>
                    <td className="work-diaries-invoice-line-cell">
                      <InvoiceLineTextarea
                        value={line.name}
                        onChange={(event) => updateLine(line.entry_id, 'name', event.target.value)}
                      />
                    </td>
                    <td className="work-diaries-invoice-amount">{money(line.available)}</td>
                    <td className="work-diaries-invoice-amount-cell">
                      <input
                        className="form-input work-diaries-invoice-amount-input"
                        type="number"
                        min="0.01"
                        max={line.available}
                        step="0.01"
                        value={line.amount}
                        onChange={(event) => updateLine(line.entry_id, 'amount', event.target.value)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="work-diaries-invoice-total-row">
            <strong>{tr('total')}</strong>
            <strong>{money(total)}</strong>
          </div>
        </div>

        <label className="form-group">
          <span className="form-label">{tr('note')}</span>
          <textarea
            className="form-input"
            rows={2}
            value={form.note}
            onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))}
          />
        </label>

        {error ? <div className="form-error">{error}</div> : null}
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>
            {tr('cancel')}
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving || !lines.length || total <= 0}>
            <FileText size={16} /> {saving ? tr('saving') : tr('workDiariesCreateInvoice')}
          </button>
        </div>
      </form>
    </Modal>
  )
}
