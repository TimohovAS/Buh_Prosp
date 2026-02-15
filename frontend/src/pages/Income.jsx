import { useState, useEffect } from 'react'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'

const MONTHS = [1,2,3,4,5,6,7,8,9,10,11,12];
const PAYMENT_TYPE_KEYS = { advance: 'contractPaymentAdvance', intermediate: 'contractPaymentIntermediate', closing: 'contractPaymentClosing' };

export default function Income() {
  const [items, setItems] = useState([])
  const [clients, setClients] = useState([])
  const [contracts, setContracts] = useState([])
  const [year, setYear] = useState(new Date().getFullYear())
  const [month, setMonth] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [selectedIds, setSelectedIds] = useState([])
  const [modal, setModal] = useState(null)
  const [modalAssign, setModalAssign] = useState(false)
  const [projects, setProjects] = useState([])
  const [assignProjectId, setAssignProjectId] = useState('')
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    invoice_number: '',
    client_id: '',
    client_name: '',
    contract_id: '',
    contract_payment_type: '',
    project_id: '',
    description: '',
    amount_rsd: '',
    note: '',
  })

  const load = () => {
    setLoading(true)
    const params = { year }
    if (month) params.month = month
    api.income.list(params).then(setItems).finally(() => setLoading(false))
  }

  useEffect(load, [year, month])
  useEffect(() => { api.clients.listBrief().then(setClients) }, [])
  useEffect(() => {
    api.projects.list({ show_archived: true }).then(setProjects)
  }, [])
  useEffect(() => {
    if (!modal) return setContracts([])
    const params = form.client_id ? { client_id: form.client_id } : {}
    if (modal === 'add' || !modal?.id) params.status = 'active'
    api.contracts.list(params).then(setContracts)
  }, [modal, form.client_id])

  const [nextInvoiceHint, setNextInvoiceHint] = useState('')
  const openAdd = () => {
    const y = new Date().getFullYear()
    const defaultForm = {
      date: new Date().toISOString().slice(0, 10),
      invoice_number: '', // сервер присвоит автоматически (блокировка конкуренции)
      client_id: '',
      client_name: '',
      contract_id: '',
      contract_payment_type: '',
      project_id: '',
      description: '',
      amount_rsd: '',
      note: '',
    }
    setForm(defaultForm)
    setModal('add')
    api.income.nextInvoice(y).then((r) => setNextInvoiceHint(r.invoice_number)).catch(() => setNextInvoiceHint(''))
  }

  const openEdit = (item) => {
    setForm({
      date: item.date,
      invoice_number: item.invoice_number,
      client_id: item.client_id || '',
      client_name: item.client_name || '',
      contract_id: item.contract_id || '',
      contract_payment_type: item.contract_payment_type || '',
      project_id: item.project_id ?? '',
      description: item.description || '',
      amount_rsd: item.amount_rsd,
      note: item.note || '',
    })
    setModal({ type: 'edit', id: item.id })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      const num = (v) => {
        if (v === '' || v == null) return null
        const n = parseInt(String(v), 10)
        return Number.isNaN(n) ? null : n
      }
      const invoiceVal = form.invoice_number?.trim() || null
      const payload = {
        date: form.date,
        invoice_number: modal === 'add' ? invoiceVal : (invoiceVal || undefined),
        invoice_year: new Date(form.date).getFullYear(),
        client_id: num(form.client_id),
        client_name: form.client_name || null,
        contract_id: num(form.contract_id),
        contract_payment_type: form.contract_payment_type || null,
        project_id: num(form.project_id),
        description: form.description || null,
        amount_rsd: parseFloat(form.amount_rsd) || 0,
        note: form.note || null,
      }
      if (modal === 'add') {
        if (payload.invoice_number) {
          const check = await api.income.checkInvoice(payload.invoice_number, payload.invoice_year)
          if (check.exists && !confirm(tr('invoiceExistsConfirm'))) return
        }
        await api.income.create(payload)
      } else {
        await api.income.update(modal.id, payload)
      }
      setModal(null)
      setNextInvoiceHint('')
      load()
    } catch (err) {
      if (err.status === 409 || (err.message && (err.message.includes('уже существует') || err.message.includes('већ постоји')))) {
        const y = new Date(form.date).getFullYear()
        const r = await api.income.nextInvoice(y).catch(() => ({}))
        if (r.invoice_number) setForm((f) => ({ ...f, invoice_number: r.invoice_number }))
        alert(tr('invoiceExistsConfirm'))
        return
      }
      alert(err.message)
    }
  }

  const toggleSelect = (id) => {
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }
  const toggleSelectAll = () => {
    if (selectedIds.length >= filtered.length) setSelectedIds([])
    else setSelectedIds(filtered.map((i) => i.id))
  }
  const handleBulkAssign = async () => {
    if (selectedIds.length === 0) return
    const pid = assignProjectId === '' || assignProjectId === '_none' ? null : parseInt(assignProjectId, 10)
    try {
      await api.income.bulkAssignProject({ ids: selectedIds, project_id: pid })
      setModalAssign(false)
      setAssignProjectId('')
      setSelectedIds([])
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm(tr('deleteIncome'))) return
    try {
      await api.income.delete(id)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const invoiceDuplicate = modal === 'add' && form.invoice_number?.trim() &&
    items.some((i) => i.invoice_number === form.invoice_number.trim())

  const exportCsv = () => api.reports.downloadCsv(year, month || undefined).catch((e) => alert(e.message))
  const exportPdf = () => api.reports.downloadPdf(year, month || undefined).catch((e) => alert(e.message))

  const filtered = items.filter((i) => {
    if (!search) return true
    const s = search.toLowerCase()
    return (i.client_name || '').toLowerCase().includes(s) ||
           (i.invoice_number || '').toLowerCase().includes(s) ||
           (i.description || '').toLowerCase().includes(s)
  })

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('income')}</h1>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value))}
          >
            {[year-2, year-1, year, year+1].map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={month}
            onChange={(e) => setMonth(e.target.value ? parseInt(e.target.value) : '')}
          >
            <option value="">{tr('allMonths')}</option>
            {MONTHS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <input
            type="text"
            className="form-input"
            placeholder={tr('search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 180 }}
          />
          <button className="btn btn-secondary" onClick={exportCsv}>
            {tr('exportKpo')} CSV
          </button>
          <button className="btn btn-secondary" onClick={exportPdf}>
            {tr('exportKpo')} PDF
          </button>
          <button
            className="btn btn-secondary"
            disabled={selectedIds.length === 0}
            onClick={() => setModalAssign(true)}
          >
            {tr('assignProject')} {selectedIds.length > 0 ? `(${selectedIds.length})` : ''}
          </button>
          <button className="btn btn-primary" onClick={openAdd}>
            {tr('add')}
          </button>
        </div>
      </div>

      <div className="page-body">
      <div className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 40 }}>
                  <input
                    type="checkbox"
                    checked={filtered.length > 0 && selectedIds.length >= filtered.length}
                    onChange={toggleSelectAll}
                  />
                </th>
                <th>{tr('date')}</th>
                <th>{tr('invoiceNumber')}</th>
                <th>{tr('client')}</th>
                <th>{tr('contracts')}</th>
                <th>{tr('project')}</th>
                <th>{tr('description')}</th>
                <th>{tr('amount')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={9}>{tr('loading')}</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={9} style={{ color: 'var(--color-text-muted)' }}>{tr('noRecords')}</td></tr>
              ) : (
                filtered.map((i) => (
                  <tr key={i.id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(i.id)}
                        onChange={() => toggleSelect(i.id)}
                      />
                    </td>
                    <td>{i.date}</td>
                    <td>{i.invoice_number}</td>
                    <td>{i.client_name || '-'}</td>
                    <td>{i.contract_number || '-'}</td>
                    <td title={projects.find((p) => p.id === i.project_id)?.name || ''}>
                      {i.project_id ? (projects.find((p) => p.id === i.project_id)?.code || '—') : '—'}
                    </td>
                    <td>
                      {(i.description || '').slice(0, 40)}
                      {i.contract_payment_type && (
                        <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginLeft: '0.25rem' }}>
                          ({tr(PAYMENT_TYPE_KEYS[i.contract_payment_type] || i.contract_payment_type)})
                        </span>
                      )}
                    </td>
                    <td>{i.amount_rsd.toLocaleString('sr-RS')}</td>
                    <td>
                      <button className="btn btn-sm btn-secondary" onClick={() => openEdit(i)}>{tr('edit')}</button>
                      <button className="btn btn-sm btn-danger" style={{ marginLeft: '0.5rem' }} onClick={() => handleDelete(i.id)}>
                        {tr('delete')}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      </div>

      {modal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">{modal === 'add' ? tr('add') : tr('edit')}</h2>
              <button className="modal-close" onClick={() => { setModal(null); setNextInvoiceHint(''); }}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('date')}</label>
                <DatePicker
                  value={form.date}
                  onChange={(v) => setForm({ ...form, date: v })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('invoiceNumber')}</label>
                {modal === 'add' && (
                  <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>
                    {nextInvoiceHint ? `${tr('suggestedNext')}: ${nextInvoiceHint}. ${tr('invoiceYearHint')}` : tr('invoiceYearHint')}
                  </div>
                )}
                <input
                  type="text"
                  className="form-input"
                  value={form.invoice_number}
                  onChange={(e) => setForm({ ...form, invoice_number: e.target.value })}
                  placeholder={modal === 'add' && nextInvoiceHint ? nextInvoiceHint : (modal === 'add' ? '' : '')}
                  required={modal !== 'add'}
                />
                {invoiceDuplicate && (
                  <div style={{ fontSize: '0.875rem', color: 'var(--color-warning)', marginTop: '0.25rem' }}>
                    {tr('invoiceExistsWarning')}
                  </div>
                )}
              </div>
              <div className="form-group">
                <label className="form-label">{tr('client')}</label>
                <select
                  className="form-input"
                  value={form.client_id}
                  onChange={(e) => {
                    const id = e.target.value ? parseInt(e.target.value) : ''
                    const c = clients.find((x) => x.id === id)
                    setForm({ ...form, client_id: id, client_name: c ? c.name : '', contract_id: '' })
                  }}
                >
                  <option value="">— {tr('incomeManual')} —</option>
                  {clients.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              {contracts.length > 0 && (
                <div className="form-group">
                  <label className="form-label">{tr('contracts')}</label>
                  <select
                    className="form-input"
                    value={form.contract_id}
                    onChange={(e) => setForm({ ...form, contract_id: e.target.value, contract_payment_type: '' })}
                  >
                    <option value="">— {tr('incomeNoContract')} —</option>
                    {contracts.map((c) => (
                      <option key={c.id} value={c.id}>{c.number} — {c.client_name} ({c.amount?.toLocaleString?.('sr-RS')} RSD)</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="form-group">
                <label className="form-label">{tr('project')}</label>
                <select
                  className="form-input"
                  value={form.project_id}
                  onChange={(e) => setForm({ ...form, project_id: e.target.value })}
                >
                  <option value="">— {tr('unassignProject')} —</option>
                  {projects.filter((p) => p.status !== 'archived').map((p) => (
                    <option key={p.id} value={p.id}>{p.code || p.name} — {p.name}</option>
                  ))}
                </select>
              </div>
              {form.contract_id && (
                <div className="form-group">
                  <label className="form-label">{tr('incomeType')}</label>
                  <select
                    className="form-input"
                    value={form.contract_payment_type}
                    onChange={(e) => setForm({ ...form, contract_payment_type: e.target.value })}
                  >
                    <option value="">— {tr('incomeNotSpecified')} —</option>
                    <option value="advance">{tr('contractPaymentAdvance')}</option>
                    <option value="intermediate">{tr('contractPaymentIntermediate')}</option>
                    <option value="closing">{tr('contractPaymentClosing')}</option>
                  </select>
                </div>
              )}
              {!form.client_id && (
                <div className="form-group">
                  <label className="form-label">{tr('incomeClientName')}</label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.client_name}
                    onChange={(e) => setForm({ ...form, client_name: e.target.value })}
                  />
                </div>
              )}
              <div className="form-group">
                <label className="form-label">{tr('description')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder={tr('incomeDescriptionPlaceholder')}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('amount')}</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  value={form.amount_rsd}
                  onChange={(e) => setForm({ ...form, amount_rsd: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('note')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.note}
                  onChange={(e) => setForm({ ...form, note: e.target.value })}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>
                  {tr('cancel')}
                </button>
                <button type="submit" className="btn btn-primary" style={{ display: 'flex', alignItems: 'center' }}>
                  {tr('save')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {modalAssign && (
        <div className="modal-overlay" onClick={() => { setModalAssign(false); setAssignProjectId(''); }}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 400 }}>
            <div className="modal-header">
              <h2 className="modal-title">{tr('assignProject')}</h2>
              <button className="modal-close" onClick={() => { setModalAssign(false); setAssignProjectId(''); }}>×</button>
            </div>
            <div className="form-group" style={{ margin: '1rem' }}>
              <label className="form-label">{tr('project')}</label>
              <select
                className="form-input"
                value={assignProjectId}
                onChange={(e) => setAssignProjectId(e.target.value)}
              >
                <option value="_none">— {tr('unassignProject')} —</option>
                {projects.filter((p) => p.status !== 'archived').map((p) => (
                  <option key={p.id} value={p.id}>{p.code || p.name} — {p.name}</option>
                ))}
              </select>
            </div>
            <div className="modal-actions" style={{ padding: '0 1rem 1rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => { setModalAssign(false); setAssignProjectId(''); }}>
                {tr('cancel')}
              </button>
              <button type="button" className="btn btn-primary" onClick={handleBulkAssign}>
                {tr('save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
