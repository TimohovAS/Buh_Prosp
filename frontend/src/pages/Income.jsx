import { useState, useEffect, useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
const PAYMENT_TYPE_KEYS = { advance: 'contractPaymentAdvance', intermediate: 'contractPaymentIntermediate', closing: 'contractPaymentClosing' }
const UI_DASH = '\u2014'
const UI_CLOSE = '\u00D7'
const UI_SORT_BOTH = '\u2195'
const UI_SORT_ASC = '\u2191'
const UI_SORT_DESC = '\u2193'

function buildContractLabel(contract) {
  if (!contract) return ''
  const parts = []
  if (contract.number) parts.push(contract.number)
  if (contract.subject) parts.push(contract.subject)
  return parts.join(` ${UI_DASH} `) || contract.number || contract.subject || ''
}

export default function Income() {
  const location = useLocation()
  const isActivePage = location.pathname === '/income'
  const [items, setItems] = useState([])
  const [clients, setClients] = useState([])
  const [contracts, setContracts] = useState([])
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  const [availableYears, setAvailableYears] = useState([currentYear])
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
  const [pageError, setPageError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [paymentModal, setPaymentModal] = useState(null)
  const [paymentDetails, setPaymentDetails] = useState(null)
  const [paymentLoading, setPaymentLoading] = useState(false)
  const [paymentActionLoading, setPaymentActionLoading] = useState(false)
  const [paymentError, setPaymentError] = useState('')
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
    setPageError('')
    const params = {}
    if (year) params.year = year
    if (month && year) params.month = month
    return Promise.all([api.income.list(params), api.income.years()])
      .then(([incomeItems, years]) => {
        setItems(incomeItems)
        setAvailableYears(years?.length ? years : [currentYear])
      })
      .catch((error) => {
        setItems([])
        setPageError(error.message || tr('loadError'))
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return
    load()
  }, [year, month, isActivePage])
  useEffect(() => {
    if (!isActivePage) return
    api.clients.listBrief().then(setClients)
  }, [isActivePage])
  useEffect(() => {
    if (!isActivePage) return
    api.projects.list({ show_archived: true }).then(setProjects)
  }, [isActivePage])
  useEffect(() => {
    if (availableYears.length === 0) return
    if (year !== '' && !availableYears.includes(year)) {
      setYear(availableYears[0])
    }
  }, [availableYears, year])
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
    setPageError('')
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
    setPageError('')
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
        if (modal === 'add') {
          const yearValue = new Date(form.date).getFullYear()
          const response = await api.income.nextInvoice(yearValue).catch(() => ({}))
          if (response.invoice_number) setNextInvoiceHint(response.invoice_number)
        }
        setSubmitError(tr('invoiceExistsWarning'))
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
      setPageError('')
      setModalAssign(false)
      setAssignProjectId('')
      setSelectedIds([])
      load()
    } catch (err) {
      setPageError(err.message || tr('loadError'))
      console.error(err)
    }
  }

  const handleDelete = async (item) => {
    const confirmKey = item.status === 'cancelled' ? 'confirmDeleteCancelledIncome' : 'confirmCancelIncome'
    if (!confirm(tr(confirmKey))) return
    try {
      await api.income.delete(item.id)
      setPageError('')
      load()
    } catch (err) {
      setPageError(err.message || tr('loadError'))
      console.error(err)
    }
  }

  const loadPaymentDetails = async (incomeId) => {
    setPaymentLoading(true)
    setPaymentError('' )
    try {
      const details = await api.income.payments(incomeId)
      setPaymentDetails(details)
      return details
    } catch (err) {
      const message = err.message || tr('loadError')
      setPaymentError(message)
      throw err
    } finally {
      setPaymentLoading(false)
    }
  }

  const openPaymentModal = async (item) => {
    setPaymentModal(item)
    setPaymentDetails(null)
    setPaymentActionLoading(false)
    try {
      await loadPaymentDetails(item.id)
    } catch (err) {
      console.error(err)
    }
  }

  const closePaymentModal = () => {
    setPaymentModal(null)
    setPaymentDetails(null)
    setPaymentLoading(false)
    setPaymentActionLoading(false)
    setPaymentError('' )
  }

  const handleUnlinkIncomePayment = async (transactionId) => {
    if (!paymentModal) return
    if (!confirm(tr('incomeUnlinkPaymentConfirm'))) return
    setPaymentActionLoading(true)
    try {
      await api.bankTransactions.unmatch(transactionId)
      await load()
      await loadPaymentDetails(paymentModal.id)
    } catch (err) {
      setPaymentError(err.message || tr('loadError'))
      console.error(err)
    } finally {
      setPaymentActionLoading(false)
    }
  }

  const handleClearManualPayment = async () => {
    if (!paymentModal) return
    if (!confirm(tr('incomeClearPaymentConfirm'))) return
    setPaymentActionLoading(true)
    try {
      await api.income.clearManualPayment(paymentModal.id)
      await load()
      await loadPaymentDetails(paymentModal.id)
    } catch (err) {
      setPaymentError(err.message || tr('loadError'))
      console.error(err)
    } finally {
      setPaymentActionLoading(false)
    }
  }

  const renderPaymentStatus = (item) => {
    let badge = null
    if (item.status === 'cancelled') {
      return <span className="badge" style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#fda4af' }}>{tr('cancelled')}</span>
    }
    if (item.status === 'paid') {
      badge = <span className="badge badge-success" title={`${tr('paid')}: ${item.paid_date || UI_DASH}`}>{tr('paid')}</span>
    } else if (item.status === 'partial') {
      badge = (
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
      )
    } else {
      return <span className="badge badge-warning">{tr('unpaid')}</span>
    }

    return (
      <button
        type="button"
        onClick={() => openPaymentModal(item)}
        title={tr('incomePaymentDetails')}
        style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left' }}
      >
        {badge}
      </button>
    )
  }

  const invoiceDuplicate = modal === 'add' && form.invoice_number?.trim() &&
    items.some((item) => item.invoice_number === form.invoice_number.trim())

  const exportCsv = () => api.reports.downloadCsv(year, month || undefined).catch((error) => console.error(error))
  const exportPdf = () => api.reports.downloadPdf(year, month || undefined).catch((error) => console.error(error))

  const unassignedProject = projects.find((project) => project.code === 'INT-UNASSIGNED') || null
  const commercialProjects = projects.filter((project) => !project.is_internal && project.status !== 'archived')
  const internalProjects = projects.filter((project) => project.is_internal && project.status !== 'archived')
  const getProjectName = (projectId) => projects.find((project) => project.id === projectId)?.name || ''
  const getContractsForProject = (projectId) => contracts
    .filter((contract) => contract.project_id === projectId || contract.project_id == null)
    .sort((left, right) => {
      const leftRank = left.project_id === projectId ? 0 : 1
      const rightRank = right.project_id === projectId ? 0 : 1
      if (leftRank !== rightRank) return leftRank - rightRank
      return buildContractLabel(left).localeCompare(buildContractLabel(right), 'sr')
    })

  const updateProject = (projectId) => {
    setForm((previous) => {
      const selectedContract = previous.contract_id ? contracts.find((contract) => String(contract.id) === String(previous.contract_id)) : null
      const keepContract = selectedContract && String(selectedContract.project_id) === String(projectId)
      return {
        ...previous,
        project_id: projectId,
        contract_id: keepContract ? previous.contract_id : '',
        contract_payment_type: keepContract ? previous.contract_payment_type : '',
      }
    })
  }

  const updateContract = (contractId) => {
    setForm((previous) => {
      if (!contractId) {
        return { ...previous, contract_id: '', contract_payment_type: '' }
      }
      const selectedContract = contracts.find((contract) => String(contract.id) === String(contractId))
      const keepPaymentType = String(previous.contract_id) === String(contractId)
      return {
        ...previous,
        contract_id: contractId,
        project_id: selectedContract?.project_id ? String(selectedContract.project_id) : previous.project_id,
        contract_payment_type: keepPaymentType ? previous.contract_payment_type : '',
      }
    })
  }

  const filteredContracts = useMemo(() => {
    const selectedProjectId = form.project_id ? parseInt(form.project_id, 10) : null
    return selectedProjectId ? getContractsForProject(selectedProjectId) : []
  }, [contracts, form.project_id])

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
        <div className="page-header-main">
          <h1 className="page-title">{tr('income')}</h1>
        </div>
        <div className="page-header-actions">
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={year}
            onChange={(event) => {
              const nextYear = event.target.value ? parseInt(event.target.value, 10) : ''
              setYear(nextYear)
              if (!event.target.value) setMonth('')
            }}
          >
            <option value="">{tr('allTime')}</option>
            {availableYears.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={month}
            onChange={(event) => setMonth(event.target.value ? parseInt(event.target.value, 10) : '')}
            disabled={!year}
          >
            <option value="">{tr('allMonths')}</option>
            {MONTHS.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
            <SearchInput
              placeholder={tr('search')}
              value={search}
              onChange={setSearch}
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
          <button className="btn btn-primary" onClick={openAdd}>
            {tr('add')}
          </button>
        </div>
      </div>

      <div className="page-body">
        {pageError && (
          <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
            {pageError}
          </div>
        )}
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
                    <tr key={item.id} className={item.status === 'cancelled' ? 'row-reversal' : ''}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(item.id)}
                          onChange={() => toggleSelect(item.id)}
                        />
                      </td>
                      <td className="date-cell">{item.date}</td>
                      <td className="date-cell">{item.due_date || UI_DASH}</td>
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
                      <td>{renderPaymentStatus(item)}</td>
                      <td>
                        <button className="btn btn-sm btn-secondary" disabled={item.status === 'cancelled'} onClick={() => openEdit(item)}>{tr('edit')}</button>
                        <button className="btn btn-sm btn-danger" style={{ marginLeft: '0.5rem' }} onClick={() => handleDelete(item)}>
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

      {paymentModal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 760 }}>
            <div className="modal-header">
              <h2 className="modal-title">{tr('incomePaymentDetails')} {UI_DASH} {paymentModal.invoice_number}</h2>
              <button className="modal-close" onClick={closePaymentModal}>{UI_CLOSE}</button>
            </div>
            <div className="card" style={{ marginBottom: '1rem', padding: '0.75rem 1rem' }}>
              <div style={{ fontWeight: 700 }}>{paymentModal.client_name || UI_DASH}</div>
              <div style={{ color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>{paymentModal.description || UI_DASH}</div>
              <div style={{ marginTop: '0.5rem', fontWeight: 700 }}>{paymentModal.amount_rsd.toLocaleString('sr-RS')} RSD</div>
            </div>
            {paymentError && (
              <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
                {paymentError}
              </div>
            )}
            {paymentLoading ? (
              <p>{tr('loading')}</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div className="card" style={{ padding: '1rem' }}>
                  <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--color-text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase' }}>
                    {tr('incomeLinkedBankPayments')}
                  </div>
                  {paymentDetails?.linked_transactions?.length ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                      {paymentDetails.linked_transactions.map((transaction) => (
                        <div key={transaction.id} className="card" style={{ padding: '0.75rem', display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontWeight: 700 }}>{transaction.amount.toLocaleString('sr-RS')} {transaction.currency || 'RSD'}</div>
                            <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>{transaction.date}</div>
                            <div style={{ marginTop: '0.35rem' }}>{transaction.counterparty_name || UI_DASH}</div>
                            <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>{transaction.purpose || UI_DASH}</div>
                            {transaction.bank_reference ? (
                              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
                                {tr('bankTxReference')}: {transaction.bank_reference}
                              </div>
                            ) : null}
                          </div>
                          <button
                            type="button"
                            className="btn btn-sm btn-danger"
                            onClick={() => handleUnlinkIncomePayment(transaction.id)}
                            disabled={paymentActionLoading}
                          >
                            {paymentActionLoading ? tr('loading') : tr('bankTxUnmatchBtn')}
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>{tr('incomeNoLinkedPayments')}</div>
                  )}
                </div>
                {paymentDetails?.has_manual_payment && (
                  <div className="card" style={{ padding: '1rem', borderColor: 'var(--color-warning)' }}>
                    <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--color-text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase' }}>
                      {tr('incomeManualPaymentMark')}
                    </div>
                    <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem', marginBottom: '0.75rem' }}>
                      {tr('incomeManualPaymentHint')}
                    </div>
                    <div>{tr('amount')}: {Number(paymentDetails.manual_paid_amount || 0).toLocaleString('sr-RS')} RSD</div>
                    <div style={{ marginTop: '0.25rem' }}>{tr('dateOfPayment')}: {paymentDetails.manual_paid_date || UI_DASH}</div>
                    <div className="modal-actions" style={{ marginTop: '1rem' }}>
                      <button
                        type="button"
                        className="btn btn-danger"
                        onClick={handleClearManualPayment}
                        disabled={paymentActionLoading}
                      >
                        {paymentActionLoading ? tr('loading') : tr('incomeClearPaymentMark')}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

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
                    setForm({ ...form, client_id: id, client_name: client ? client.name : '', contract_id: '', contract_payment_type: '' })
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
                    onChange={(event) => updateContract(event.target.value)}
                  >
                    <option value="">{`${UI_DASH} ${tr('incomeNoContract')} ${UI_DASH}`}</option>
                    {filteredContracts.map((contract) => (
                      <option key={contract.id} value={contract.id}>{buildContractLabel(contract)} {UI_DASH} {contract.client_name} ({contract.amount?.toLocaleString?.('sr-RS')} RSD)</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="form-group">
                <label className="form-label">{tr('project')}</label>
                <ProjectSelect
                  projects={projects}
                  value={form.project_id}
                  onChange={updateProject}
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
