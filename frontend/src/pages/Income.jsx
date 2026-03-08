import { useState, useEffect, useRef, useMemo } from 'react'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import ProjectSelect from '../components/ProjectSelect'

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
const PAYMENT_TYPE_KEYS = { advance: 'contractPaymentAdvance', intermediate: 'contractPaymentIntermediate', closing: 'contractPaymentClosing' }
const UI_DASH = '\u2014'
const UI_CLOSE = '\u00D7'
const UI_SORT_BOTH = '\u2195'
const UI_SORT_ASC = '\u2191'
const UI_SORT_DESC = '\u2193'

export default function Income() {
  const efakturaInputRef = useRef(null)
  const [items, setItems] = useState([])
  const [clients, setClients] = useState([])
  const [contracts, setContracts] = useState([])
  const [year, setYear] = useState(new Date().getFullYear())
  const [month, setMonth] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [sortCol, setSortCol] = useState('date')
  const [sortAsc, setSortAsc] = useState(false)
  const [selectedIds, setSelectedIds] = useState([])
  const [modal, setModal] = useState(null)
  const [modalAssign, setModalAssign] = useState(false)
  const [projects, setProjects] = useState([])
  const [assignProjectId, setAssignProjectId] = useState('')
  const [efakturaImporting, setEfakturaImporting] = useState(false)
  const [efakturaLastResult, setEfakturaLastResult] = useState(null)
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    due_date: '',
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
  const getDefaultIncomeDate = () => {
    const today = new Date()
    const targetYear = Number.isInteger(year) ? year : today.getFullYear()
    const targetMonth = month ? Number(month) : (today.getMonth() + 1)
    const lastDay = new Date(targetYear, targetMonth, 0).getDate()
    const targetDay = Math.min(today.getDate(), lastDay)
    return targetYear + '-' + String(targetMonth).padStart(2, '0') + '-' + String(targetDay).padStart(2, '0')
  }
  const closeModal = () => {
    setModal(null)
    setNextInvoiceHint('')
    setSubmitError('')
  }

  useEffect(() => {
    if (modal !== 'add') {
      setNextInvoiceHint('')
      return
    }
    const hintYear = /^\d{4}-\d{2}-\d{2}$/.test(form.date || '')
      ? parseInt(form.date.slice(0, 4), 10)
      : year
    api.income.nextInvoice(hintYear).then((response) => setNextInvoiceHint(response.invoice_number)).catch(() => setNextInvoiceHint(''))
  }, [modal, form.date, year])

  const openAdd = () => {
    const defaultForm = {
      date: getDefaultIncomeDate(),
      due_date: '',
      invoice_number: '',
      client_id: '',
      client_name: '',
      contract_id: '',
      contract_payment_type: '',
      project_id: unassignedProject ? String(unassignedProject.id) : '',
      description: '',
      amount_rsd: '',
      note: '',
    }
    setForm(defaultForm)
    setSubmitError('')
    setModal('add')
  }

  const openEdit = (item) => {
    setForm({
      date: item.date,
      due_date: item.due_date || '',
      invoice_number: item.invoice_number,
      client_id: item.client_id || '',
      client_name: item.client_name || '',
      contract_id: item.contract_id || '',
      contract_payment_type: item.contract_payment_type || '',
      project_id: item.project_id ?? (unassignedProject ? String(unassignedProject.id) : ''),
      description: item.description || '',
      amount_rsd: item.amount_rsd,
      note: item.note || '',
    })
    setSubmitError('')
    setModal({ type: 'edit', id: item.id })
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSubmitError('')
    setSubmitting(true)
    try {
      const toInt = (value) => {
        if (value === '' || value == null) return null
        const parsed = parseInt(String(value), 10)
        return Number.isNaN(parsed) ? null : parsed
      }
      const invoiceValue = form.invoice_number?.trim() || null
      const payload = {
        date: form.date,
        due_date: form.due_date || null,
        invoice_number: modal === 'add' ? invoiceValue : (invoiceValue || undefined),
        invoice_year: new Date(form.date).getFullYear(),
        client_id: toInt(form.client_id),
        client_name: form.client_name || null,
        contract_id: toInt(form.contract_id),
        contract_payment_type: form.contract_payment_type || null,
        project_id: toInt(form.project_id) ?? (unassignedProject ? unassignedProject.id : null),
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
      closeModal()
      load()
    } catch (err) {
      if (err.status === 409) {
        const yearValue = new Date(form.date).getFullYear()
        const response = await api.income.nextInvoice(yearValue).catch(() => ({}))
        if (response.invoice_number) setForm((prev) => ({ ...prev, invoice_number: response.invoice_number }))
        setSubmitError(err.message || tr('invoiceExistsWarning'))
        return
      }
      setSubmitError(err.message || tr('loadError'))
      console.error(err)
    } finally {
      setSubmitting(false)
    }
  }

  const toggleSelect = (id) => {
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }

  const toggleSelectAll = () => {
    if (selectedIds.length >= filtered.length) setSelectedIds([])
    else setSelectedIds(filtered.map((item) => item.id))
  }

  const handleBulkAssign = async () => {
    if (selectedIds.length === 0) return
    const pid = assignProjectId === '' || assignProjectId === '_none'
      ? (unassignedProject ? unassignedProject.id : null)
      : parseInt(assignProjectId, 10)
    try {
      await api.income.bulkAssignProject({ ids: selectedIds, project_id: pid })
      setModalAssign(false)
      setAssignProjectId('')
      setSelectedIds([])
      load()
    } catch (err) {
      setSubmitError(err.message || tr('loadError'))
      console.error(err)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm(tr('deleteIncome'))) return
    try {
      await api.income.delete(id)
      load()
    } catch (err) {
      setSubmitError(err.message || tr('loadError'))
      console.error(err)
    }
  }

  const openEfakturaPicker = () => {
    if (efakturaImporting) return
    efakturaInputRef.current?.click()
  }

  const handleEfakturaFiles = async (event) => {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    if (files.length === 0) return
    setEfakturaImporting(true)
    try {
      const result = await api.income.importEfaktura(files)
      setEfakturaLastResult(result)
      load()
      if ((result.error_count || 0) > 0) {
        const firstError = result.errors?.[0]?.error || tr('loadError')
        alert(`${tr('efakturaImportCompleted')}. ${tr('efakturaErrors')}: ${result.error_count}. ${firstError}`)
      }
    } catch (err) {
      setSubmitError(err.message || tr('loadError'))
      console.error(err)
    } finally {
      setEfakturaImporting(false)
    }
  }

  const invoiceDuplicate = modal === 'add' && form.invoice_number?.trim() &&
    items.some((item) => item.invoice_number === form.invoice_number.trim())

  const exportCsv = () => api.reports.downloadCsv(year, month || undefined).catch((error) => console.error(error))
  const exportPdf = () => api.reports.downloadPdf(year, month || undefined).catch((error) => console.error(error))

  const unassignedProject = projects.find((project) => project.code === 'INT-UNASSIGNED') || null
  const commercialProjects = projects.filter((project) => !project.is_internal && project.status !== 'archived')
  const internalProjects = projects.filter((project) => project.is_internal && project.status !== 'archived')
  const getProjectName = (projectId) => projects.find((project) => project.id === projectId)?.name || ''

  const filtered = useMemo(() => {
    const normalizedSearch = (search || '').trim().toLowerCase()
    let rows = items
    if (normalizedSearch) {
      rows = items.filter((item) =>
        (item.client_name || '').toLowerCase().includes(normalizedSearch) ||
        (item.invoice_number || '').toLowerCase().includes(normalizedSearch) ||
        (item.description || '').toLowerCase().includes(normalizedSearch) ||
        String(item.amount_rsd || '').includes(normalizedSearch) ||
        getProjectName(item.project_id).toLowerCase().includes(normalizedSearch)
      )
    }
    return [...rows].sort((left, right) => {
      const leftValue = sortCol === 'project_id' ? getProjectName(left.project_id) : (left[sortCol] ?? '')
      const rightValue = sortCol === 'project_id' ? getProjectName(right.project_id) : (right[sortCol] ?? '')
      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
  }, [items, search, sortCol, sortAsc, projects])

  const toggleSort = (col) => {
    if (sortCol === col) setSortAsc((value) => !value)
    else {
      setSortCol(col)
      setSortAsc(true)
    }
  }

  const SortIcon = ({ col }) => {
    if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 4 }}>{UI_SORT_BOTH}</span>
    return <span style={{ marginLeft: 4 }}>{sortAsc ? UI_SORT_ASC : UI_SORT_DESC}</span>
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('income')}</h1>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <input
            ref={efakturaInputRef}
            type="file"
            accept=".xml,text/xml,application/xml"
            multiple
            style={{ display: 'none' }}
            onChange={handleEfakturaFiles}
          />
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={year}
            onChange={(event) => setYear(parseInt(event.target.value, 10))}
          >
            {[year - 2, year - 1, year, year + 1].map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={month}
            onChange={(event) => setMonth(event.target.value ? parseInt(event.target.value, 10) : '')}
          >
            <option value="">{tr('allMonths')}</option>
            {MONTHS.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <input
            type="text"
            className="form-input"
            placeholder={tr('search')}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
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
            onClick={() => {
              setAssignProjectId(unassignedProject ? String(unassignedProject.id) : '')
              setModalAssign(true)
            }}
          >
            {tr('assignProject')} {selectedIds.length > 0 ? `(${selectedIds.length})` : ''}
          </button>
          <button className="btn btn-secondary" onClick={openEfakturaPicker} disabled={efakturaImporting}>
            {efakturaImporting ? tr('efakturaImporting') : tr('efakturaImport')}
          </button>
          <button className="btn btn-primary" onClick={openAdd}>
            {tr('add')}
          </button>
          {efakturaLastResult && (
            <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)', alignSelf: 'center' }}>
              {`${tr('efakturaCreated')}: ${efakturaLastResult.created_count || 0}, ${tr('efakturaSkipped')}: ${efakturaLastResult.skipped_count || 0}, ${tr('efakturaErrors')}: ${efakturaLastResult.error_count || 0}`}
            </div>
          )}
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
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIcon col="date" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('due_date')}>{tr('valuta')} <SortIcon col="due_date" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('invoice_number')}>{tr('invoiceNumber')} <SortIcon col="invoice_number" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('client_name')}>{tr('client')} <SortIcon col="client_name" /></th>
                  <th>{tr('contracts')}</th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('project_id')}>{tr('project')} <SortIcon col="project_id" /></th>
                  <th>{tr('description')}</th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('amount_rsd')}>{tr('amount')} <SortIcon col="amount_rsd" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('is_paid')}>{tr('status')} <SortIcon col="is_paid" /></th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={10}>{tr('loading')}</td></tr>
                ) : filtered.length === 0 ? (
                  <tr><td colSpan={10} style={{ color: 'var(--color-text-muted)' }}>{tr('noRecords')}</td></tr>
                ) : (
                  filtered.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(item.id)}
                          onChange={() => toggleSelect(item.id)}
                        />
                      </td>
                      <td>{item.date}</td>
                      <td>{item.due_date || UI_DASH}</td>
                      <td>{item.invoice_number}</td>
                      <td>{item.client_name || '-'}</td>
                      <td>{item.contract_number || '-'}</td>
                      <td title={projects.find((project) => project.id === item.project_id)?.name || ''}>
                        {item.project_id ? (
                          <span title={projects.find((project) => project.id === item.project_id)?.code || ''}>
                            {projects.find((project) => project.id === item.project_id)?.name || UI_DASH}
                          </span>
                        ) : UI_DASH}
                      </td>
                      <td>
                        {(item.description || '').slice(0, 40)}
                        {item.contract_payment_type && (
                          <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginLeft: '0.25rem' }}>
                            ({tr(PAYMENT_TYPE_KEYS[item.contract_payment_type] || item.contract_payment_type)})
                          </span>
                        )}
                      </td>
                      <td>{item.amount_rsd.toLocaleString('sr-RS')}</td>
                      <td>
                        {item.status === 'paid' ? (
                          <span className="badge badge-success" title={`${tr('paid')}: ${item.paid_date}`}>{tr('paid')}</span>
                        ) : item.status === 'partial' ? (
                          <span
                            className="badge"
                            style={{ background: 'var(--color-info, #0ea5e9)', color: '#fff' }}
                            title={`${tr('partial')}: ${(item.paid_amount || 0).toLocaleString('sr-RS')} / ${item.amount_rsd.toLocaleString('sr-RS')} RSD`}
                          >
                            {tr('partial')}
                            <span style={{ display: 'block', fontSize: '0.75em', opacity: 0.9 }}>
                              +{(item.paid_amount || 0).toLocaleString('sr-RS')} / {item.amount_rsd.toLocaleString('sr-RS')}
                            </span>
                          </span>
                        ) : (
                          <span className="badge badge-warning">{tr('unpaid')}</span>
                        )}
                      </td>
                      <td>
                        <button className="btn btn-sm btn-secondary" onClick={() => openEdit(item)}>{tr('edit')}</button>
                        <button className="btn btn-sm btn-danger" style={{ marginLeft: '0.5rem' }} onClick={() => handleDelete(item.id)}>
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
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">{modal === 'add' ? tr('add') : tr('edit')}</h2>
              <button className="modal-close" onClick={closeModal}>{UI_CLOSE}</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('date')}</label>
                <DatePicker
                  value={form.date}
                  onChange={(value) => setForm({ ...form, date: value })}
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
                  onChange={(event) => setForm({ ...form, invoice_number: event.target.value })}
                  placeholder={modal === 'add' && nextInvoiceHint ? nextInvoiceHint : ''}
                  required={modal !== 'add'}
                />
                {invoiceDuplicate && (
                  <div style={{ fontSize: '0.875rem', color: 'var(--color-warning)', marginTop: '0.25rem' }}>
                    {tr('invoiceExistsWarning')}
                  </div>
                )}
              </div>
              <div className="form-group">
                <label className="form-label">{tr('valuta')}</label>
                <DatePicker
                  value={form.due_date}
                  onChange={(value) => setForm({ ...form, due_date: value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('client')}</label>
                <select
                  className="form-input"
                  value={form.client_id}
                  onChange={(event) => {
                    const id = event.target.value ? parseInt(event.target.value, 10) : ''
                    const client = clients.find((item) => item.id === id)
                    setForm({ ...form, client_id: id, client_name: client ? client.name : '', contract_id: '' })
                  }}
                >
                  <option value="">{`${UI_DASH} ${tr('incomeManual')} ${UI_DASH}`}</option>
                  {clients.map((client) => (
                    <option key={client.id} value={client.id}>{client.name}</option>
                  ))}
                </select>
              </div>
              {contracts.length > 0 && (
                <div className="form-group">
                  <label className="form-label">{tr('contracts')}</label>
                  <select
                    className="form-input"
                    value={form.contract_id}
                    onChange={(event) => setForm({ ...form, contract_id: event.target.value, contract_payment_type: '' })}
                  >
                    <option value="">{`${UI_DASH} ${tr('incomeNoContract')} ${UI_DASH}`}</option>
                    {contracts.map((contract) => (
                      <option key={contract.id} value={contract.id}>{contract.number} {UI_DASH} {contract.client_name} ({contract.amount?.toLocaleString?.('sr-RS')} RSD)</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="form-group">
                <label className="form-label">{tr('project')}</label>
                <ProjectSelect
                  projects={projects}
                  value={form.project_id}
                  onChange={(nextValue) => setForm({ ...form, project_id: nextValue })}
                  required
                />
              </div>
              {form.contract_id && (
                <div className="form-group">
                  <label className="form-label">{tr('incomeType')}</label>
                  <select
                    className="form-input"
                    value={form.contract_payment_type}
                    onChange={(event) => setForm({ ...form, contract_payment_type: event.target.value })}
                  >
                    <option value="">{`${UI_DASH} ${tr('incomeNotSpecified')} ${UI_DASH}`}</option>
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
                    onChange={(event) => setForm({ ...form, client_name: event.target.value })}
                  />
                </div>
              )}
              <div className="form-group">
                <label className="form-label">{tr('description')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.description}
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
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
                  onChange={(event) => setForm({ ...form, amount_rsd: event.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('note')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.note}
                  onChange={(event) => setForm({ ...form, note: event.target.value })}
                />
              </div>
              {submitError && (
                <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
                  {submitError}
                </div>
              )}
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={closeModal} disabled={submitting}>
                  {tr('cancel')}
                </button>
                <button type="submit" className="btn btn-primary" style={{ display: 'flex', alignItems: 'center' }} disabled={submitting}>
                  {tr('save')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {modalAssign && (
        <div className="modal-overlay">
          <div className="modal" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 400 }}>
            <div className="modal-header">
              <h2 className="modal-title">{tr('assignProject')}</h2>
              <button className="modal-close" onClick={() => { setModalAssign(false); setAssignProjectId('') }}>{UI_CLOSE}</button>
            </div>
            <div className="form-group" style={{ margin: '1rem' }}>
              <label className="form-label">{tr('project')}</label>
              <ProjectSelect
                projects={projects}
                value={assignProjectId}
                onChange={setAssignProjectId}
                allowEmpty
                emptyLabel={UI_DASH}
              />
            </div>
            <div className="modal-actions" style={{ padding: '0 1rem 1rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => { setModalAssign(false); setAssignProjectId('') }}>
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
