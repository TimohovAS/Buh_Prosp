import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { getLang, tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import Modal from '../components/Modal'

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
const UI_DASH = '\u2014'
const UI_SORT_BOTH = '\u2195'
const UI_SORT_ASC = '\u2191'
const UI_SORT_DESC = '\u2193'

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

export default function BankTransactions() {
  const [data, setData] = useState([])
  const [projects, setProjects] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)

  const [year, setYear] = useState('')
  const [month, setMonth] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [directionFilter, setDirectionFilter] = useState('all')
  const [search, setSearch] = useState('')

  const [sortCol, setSortCol] = useState('date')
  const [sortAsc, setSortAsc] = useState(false)

  const [selectedIds, setSelectedIds] = useState([])
  const [modalAssign, setModalAssign] = useState(false)
  const [assignProjectId, setAssignProjectId] = useState('')

  const [matchTx, setMatchTx] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const [suggestLoading, setSuggestLoading] = useState(false)
  const [matchError, setMatchError] = useState('')
  const [allInvoiceSearch, setAllInvoiceSearch] = useState('')
  const [expenseSaving, setExpenseSaving] = useState(false)
  const [expenseForm, setExpenseForm] = useState({
    date: todayIso(),
    description: '',
    category_id: '',
    project_id: '',
    note: '',
  })

  const lang = getLang()
  const currentYear = new Date().getFullYear()
  const years = Array.from({ length: 5 }, (_, index) => currentYear - index)

  const unassignedProject = projects.find((project) => project.code === 'INT-UNASSIGNED') || null
  const commercialProjects = projects.filter((project) => !project.is_internal && project.status !== 'archived')
  const internalProjects = projects.filter((project) => project.is_internal && project.status !== 'archived')

  const getProjectName = (projectId) => projects.find((project) => project.id === projectId)?.name || UI_DASH
  const getCategoryName = (categoryId) => {
    const category = categories.find((item) => item.id === categoryId)
    if (!category) return UI_DASH
    return lang === 'ru' ? category.name_ru : category.name_sr
  }

  const loadData = async () => {
    setLoading(true)
    try {
      const params = {}
      if (year) params.year = year
      if (year && month) params.month = month
      if (statusFilter !== 'all') params.status = statusFilter
      if (directionFilter !== 'all') params.direction = directionFilter

      const [transactions, projectList, categoryList] = await Promise.all([
        api.bankTransactions.list(params),
        api.projects.list({ show_archived: true }),
        api.categories.list({ category_type: 'expense' }),
      ])
      setData(transactions)
      setProjects(projectList)
      setCategories(categoryList)
    } catch (error) {
      console.error(error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [statusFilter, directionFilter, year, month])

  const displayed = useMemo(() => {
    const query = search.trim().toLowerCase()
    let rows = data

    if (query) {
      rows = data.filter((transaction) =>
        (transaction.date || '').toLowerCase().includes(query) ||
        (transaction.counterparty_name || '').toLowerCase().includes(query) ||
        (transaction.purpose || '').toLowerCase().includes(query) ||
        String(transaction.amount || '').includes(query) ||
        (transaction.status || '').toLowerCase().includes(query) ||
        getProjectName(transaction.project_id).toLowerCase().includes(query)
      )
    }

    return [...rows].sort((left, right) => {
      const leftValue = sortCol === 'project_id' ? getProjectName(left.project_id) : (left[sortCol] ?? '')
      const rightValue = sortCol === 'project_id' ? getProjectName(right.project_id) : (right[sortCol] ?? '')
      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
  }, [data, getProjectName, search, sortAsc, sortCol])

  const toggleSort = (column) => {
    if (sortCol === column) setSortAsc((value) => !value)
    else {
      setSortCol(column)
      setSortAsc(true)
    }
  }

  const SortIcon = ({ col }) => {
    if (sortCol !== col) return <span style={{ opacity: 0.35, marginLeft: 4 }}>{UI_SORT_BOTH}</span>
    return <span style={{ marginLeft: 4 }}>{sortAsc ? UI_SORT_ASC : UI_SORT_DESC}</span>
  }

  const buildExpenseForm = (transaction) => ({
    date: transaction?.date || todayIso(),
    description: transaction?.purpose || transaction?.counterparty_name || '',
    category_id: '',
    project_id: transaction?.project_id ? String(transaction.project_id) : (unassignedProject ? String(unassignedProject.id) : ''),
    note: '',
  })

  const toggleSelect = (id) => {
    setSelectedIds((previous) => previous.includes(id) ? previous.filter((value) => value !== id) : [...previous, id])
  }

  const toggleSelectAll = () => {
    if (selectedIds.length >= displayed.length) setSelectedIds([])
    else setSelectedIds(displayed.map((item) => item.id))
  }

  const handleUpdateStatus = async (id, newStatus) => {
    try {
      await api.bankTransactions.update(id, { status: newStatus })
      loadData()
    } catch (error) {
      console.error(error)
    }
  }

  const handleBulkAssign = async () => {
    if (selectedIds.length === 0) return
    const projectId = assignProjectId === '' || assignProjectId === '_none' ? null : parseInt(assignProjectId, 10)
    try {
      await api.bankTransactions.bulkAssignProject({ ids: selectedIds, project_id: projectId })
      setModalAssign(false)
      setAssignProjectId('')
      setSelectedIds([])
      loadData()
    } catch (error) {
      console.error(error)
    }
  }

  const handleUnmatch = async (id) => {
    if (!confirm(tr('bankTxUnmatchBtn'))) return
    try {
      await api.bankTransactions.unmatch(id)
      loadData()
    } catch (error) {
      console.error(error)
    }
  }

  const openMatchModal = async (transaction) => {
    setMatchTx(transaction)
    setMatchError('')
    setAllInvoiceSearch('')
    setSuggestions([])
    setExpenseForm(buildExpenseForm(transaction))
    setSuggestLoading(true)
    try {
      const response = await api.bankTransactions.suggest(transaction.id)
      setSuggestions(response)
    } catch (error) {
      setMatchError(error.message)
    } finally {
      setSuggestLoading(false)
    }
  }

  const closeMatchModal = () => {
    setMatchTx(null)
    setSuggestions([])
    setSuggestLoading(false)
    setMatchError('')
    setAllInvoiceSearch('')
    setExpenseSaving(false)
    setExpenseForm({
      date: todayIso(),
      description: '',
      category_id: '',
      project_id: '',
      note: '',
    })
  }

  const performMatch = async (targetId, targetType) => {
    if (!matchTx) return
    try {
      await api.bankTransactions.match(matchTx.id, { type: targetType, id: targetId })
      closeMatchModal()
      loadData()
    } catch (error) {
      setMatchError(error.message)
    }
  }

  const handleCreateExpense = async (event) => {
    event.preventDefault()
    if (!matchTx) return

    setExpenseSaving(true)
    try {
      await api.bankTransactions.createExpense(matchTx.id, {
        date: expenseForm.date,
        description: expenseForm.description.trim(),
        category_id: expenseForm.category_id ? parseInt(expenseForm.category_id, 10) : null,
        project_id: expenseForm.project_id ? parseInt(expenseForm.project_id, 10) : (unassignedProject ? unassignedProject.id : null),
        note: expenseForm.note?.trim() || null,
      })
      closeMatchModal()
      loadData()
    } catch (error) {
      setMatchError(error.message)
    } finally {
      setExpenseSaving(false)
    }
  }

  const renderSuggestionCard = (item) => {
    const amount = Number(item.amount || 0)
    const fullAmount = item.amount_full != null ? Number(item.amount_full) : amount
    const isPartial = item.type === 'income' && fullAmount > amount
    const label = item.invoice_number || item.description || `#${item.id}`

    return (
      <div key={`${item.type}-${item.id}`} className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', padding: '0.75rem' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'baseline', flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 700 }}>{label}</span>
            {item.date ? <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>{item.date}</span> : null}
            {item.score != null ? <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>{item.score}%</span> : null}
          </div>
          {item.client_name ? <div style={{ fontSize: '0.85rem', fontWeight: 600, marginTop: '0.2rem' }}>{item.client_name}</div> : null}
          {item.description ? <div style={{ fontSize: '0.82rem', color: 'var(--color-text-muted)', marginTop: '0.2rem' }}>{item.description}</div> : null}
          <div style={{ fontSize: '0.86rem', marginTop: '0.25rem', fontWeight: 600 }}>
            {isPartial ? (
              <>
                <span>{tr('partial')}: {amount.toLocaleString('sr-RS')} RSD</span>
                <span style={{ fontWeight: 400, color: 'var(--color-text-muted)' }}> / {fullAmount.toLocaleString('sr-RS')} RSD</span>
              </>
            ) : (
              <span>{amount.toLocaleString('sr-RS')} RSD</span>
            )}
          </div>
        </div>
        <button className="btn btn-sm btn-primary" style={{ whiteSpace: 'nowrap' }} onClick={() => performMatch(item.id, item.type)}>
          {tr('bankTxMatchBtn')}
        </button>
      </div>
    )
  }

  const renderIncomingModalContent = () => {
    const suggested = suggestions.filter((item) => item.section === 'suggested')
    const byCounterparty = suggestions.filter((item) => item.section === 'counterparty')
    const allInvoices = suggestions.filter((item) => item.section === 'all' || !item.section)
    const query = allInvoiceSearch.trim().toLowerCase()
    const filteredAll = allInvoices.filter((item) =>
      !query ||
      String(item.description || '').toLowerCase().includes(query) ||
      String(item.client_name || '').toLowerCase().includes(query) ||
      String(item.invoice_number || '').toLowerCase().includes(query) ||
      String(item.amount || '').includes(query)
    )

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {suggested.length > 0 && (
          <div>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--color-text-muted)', marginBottom: '0.4rem', textTransform: 'uppercase' }}>
              {tr('bankTxAutoFound')}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              {suggested.map(renderSuggestionCard)}
            </div>
          </div>
        )}

        {byCounterparty.length > 0 && (
          <div>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--color-text-muted)', marginBottom: '0.4rem', textTransform: 'uppercase' }}>
              {tr('bankTxCounterpartyInvoices')}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              {byCounterparty.map(renderSuggestionCard)}
            </div>
          </div>
        )}

        <div>
          <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--color-text-muted)', marginBottom: '0.4rem', textTransform: 'uppercase' }}>
            {tr('bankTxAllOpenInvoices')}
          </div>
          <input
            className="form-input"
            placeholder={tr('bankTxSearchInvoices')}
            value={allInvoiceSearch}
            onChange={(event) => setAllInvoiceSearch(event.target.value)}
            style={{ width: '100%', marginBottom: '0.5rem' }}
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', maxHeight: 260, overflowY: 'auto' }}>
            {filteredAll.length === 0 && allInvoices.length === 0 && (
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', textAlign: 'center' }}>{tr('bankTxNoOpenInvoices')}</p>
            )}
            {filteredAll.length === 0 && allInvoices.length > 0 && (
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', textAlign: 'center' }}>{tr('bankTxNoInvoicesFound')}</p>
            )}
            {filteredAll.map(renderSuggestionCard)}
          </div>
        </div>
      </div>
    )
  }

  const renderOutgoingModalContent = () => {
    const existingExpenses = suggestions.filter((item) => item.type === 'expense')

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {existingExpenses.length > 0 && (
          <div>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--color-text-muted)', marginBottom: '0.4rem', textTransform: 'uppercase' }}>
              {tr('bankTxExistingExpenses')}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              {existingExpenses.map(renderSuggestionCard)}
            </div>
          </div>
        )}

        <form onSubmit={handleCreateExpense} className="card" style={{ padding: '1rem' }}>
          <div style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '0.75rem' }}>
            {tr('bankTxCreateExpenseHint')}
          </div>
          <div className="form-group">
            <label className="form-label">{tr('date')}</label>
            <DatePicker value={expenseForm.date} onChange={(value) => setExpenseForm((previous) => ({ ...previous, date: value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('description')}</label>
            <input
              className="form-input"
              value={expenseForm.description}
              onChange={(event) => setExpenseForm((previous) => ({ ...previous, description: event.target.value }))}
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('category')}</label>
            <select
              className="form-input"
              value={expenseForm.category_id}
              onChange={(event) => setExpenseForm((previous) => ({ ...previous, category_id: event.target.value }))}
            >
              <option value="">{UI_DASH}</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {lang === 'ru' ? category.name_ru : category.name_sr}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">{tr('project')}</label>
            <select
              className="form-input"
              value={expenseForm.project_id}
              onChange={(event) => setExpenseForm((previous) => ({ ...previous, project_id: event.target.value }))}
              required
            >
              {commercialProjects.length > 0 && (
                <optgroup label={tr('commercialProject')}>
                  {commercialProjects.map((project) => (
                    <option key={project.id} value={project.id}>{project.name}{project.code ? ` ${UI_DASH} ${project.code}` : ''}</option>
                  ))}
                </optgroup>
              )}
              {internalProjects.length > 0 && (
                <optgroup label={tr('internalProject')}>
                  {internalProjects.map((project) => (
                    <option key={project.id} value={project.id}>{project.name}{project.code ? ` ${UI_DASH} ${project.code}` : ''}</option>
                  ))}
                </optgroup>
              )}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">{tr('amount')}</label>
            <input className="form-input" value={matchTx?.amount?.toLocaleString('sr-RS') || ''} disabled />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('note')}</label>
            <input
              className="form-input"
              value={expenseForm.note}
              onChange={(event) => setExpenseForm((previous) => ({ ...previous, note: event.target.value }))}
            />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={closeMatchModal}>{tr('cancel')}</button>
            <button type="submit" className="btn btn-primary" disabled={expenseSaving}>{expenseSaving ? tr('loading') : tr('bankTxCreateAndMatch')}</button>
          </div>
        </form>
      </div>
    )
  }

  return (
    <>
      <div className="page-header">
        <h1>{tr('bankTransactions')}</h1>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <select className="form-input" style={{ width: 'auto' }} value={year} onChange={(event) => { setYear(event.target.value ? Number(event.target.value) : ''); setMonth('') }}>
            <option value="">{tr('allYears')}</option>
            {years.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <select className="form-input" style={{ width: 'auto' }} value={month} onChange={(event) => setMonth(event.target.value)}>
            <option value="">{tr('allMonths')}</option>
            {MONTHS.map((value) => (
              <option key={value} value={value}>{String(value).padStart(2, '0')}</option>
            ))}
          </select>
          <select className="form-input" style={{ width: 'auto' }} value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">{tr('filterAll')}</option>
            <option value="unmatched">{tr('bankTxUnmatched')}</option>
            <option value="matched">{tr('bankTxMatched')}</option>
            <option value="ignored">{tr('bankTxIgnored')}</option>
          </select>
          <select className="form-input" style={{ width: 'auto' }} value={directionFilter} onChange={(event) => setDirectionFilter(event.target.value)}>
            <option value="all">{tr('filterAll')}</option>
            <option value="in">{tr('bankTxDirectionIn')}</option>
            <option value="out">{tr('bankTxDirectionOut')}</option>
          </select>
          <input
            className="form-input"
            placeholder={tr('search')}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            style={{ minWidth: 180 }}
          />
          {selectedIds.length > 0 && (
            <button
              className="btn btn-secondary"
              onClick={() => { setAssignProjectId(unassignedProject ? String(unassignedProject.id) : ''); setModalAssign(true) }}
            >
              {tr('assignProject')} ({selectedIds.length})
            </button>
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
                    <input type="checkbox" checked={displayed.length > 0 && selectedIds.length === displayed.length} onChange={toggleSelectAll} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIcon col="date" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('counterparty_name')}>{tr('bankTxCounterparty')} <SortIcon col="counterparty_name" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('purpose')}>{tr('bankTxPurpose')} / {tr('bankTxReference')} <SortIcon col="purpose" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('project_id')}>{tr('project')} <SortIcon col="project_id" /></th>
                  <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')} <SortIcon col="amount" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('status')}>{tr('status')} <SortIcon col="status" /></th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={8}>{tr('loading')}</td></tr>
                ) : displayed.length === 0 ? (
                  <tr><td colSpan={8} style={{ color: 'var(--color-text-muted)' }}>{tr('noRecords')}</td></tr>
                ) : (
                  displayed.map((transaction) => (
                    <tr key={transaction.id}>
                      <td>
                        <input type="checkbox" checked={selectedIds.includes(transaction.id)} onChange={() => toggleSelect(transaction.id)} />
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}>{transaction.date}</td>
                      <td>{transaction.counterparty_name || UI_DASH}</td>
                      <td style={{ maxWidth: 320 }}>
                        <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={transaction.purpose || ''}>
                          {transaction.purpose || UI_DASH}
                        </div>
                        {transaction.bank_reference ? <div style={{ fontSize: '0.78rem', color: 'var(--color-text-muted)' }}>Ref: {transaction.bank_reference}</div> : null}
                      </td>
                      <td title={getProjectName(transaction.project_id)}>{getProjectName(transaction.project_id)}</td>
                      <td style={{ textAlign: 'right', fontWeight: 700, color: transaction.direction === 'in' ? 'var(--color-success)' : 'var(--color-text)' }}>
                        {transaction.direction === 'in' ? '+' : '-'}{Number(transaction.amount || 0).toLocaleString('sr-RS')} {transaction.currency || 'RSD'}
                      </td>
                      <td>
                        {transaction.status === 'unmatched' && <span className="badge badge-warning">{tr('bankTxUnmatched')}</span>}
                        {transaction.status === 'matched' && <span className="badge badge-success">{tr('bankTxMatched')} ({transaction.matched_type})</span>}
                        {transaction.status === 'ignored' && <span className="badge badge-secondary">{tr('bankTxIgnored')}</span>}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {transaction.status === 'unmatched' && (
                          <div style={{ display: 'flex', gap: '0.35rem', justifyContent: 'flex-end' }}>
                            <button className="btn btn-sm btn-primary" onClick={() => openMatchModal(transaction)}>
                              {transaction.direction === 'out' ? tr('bankTxCreateExpense') : tr('bankTxMatchBtn')}
                            </button>
                            <button className="btn btn-sm btn-secondary" onClick={() => handleUpdateStatus(transaction.id, 'ignored')}>
                              {tr('bankTxIgnore')}
                            </button>
                          </div>
                        )}
                        {transaction.status === 'ignored' && (
                          <button className="btn btn-sm btn-secondary" onClick={() => handleUpdateStatus(transaction.id, 'unmatched')}>
                            {tr('restore')}
                          </button>
                        )}
                        {transaction.status === 'matched' && (
                          <button className="btn btn-sm btn-danger" onClick={() => handleUnmatch(transaction.id)}>
                            {tr('bankTxUnmatchBtn')}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <Modal isOpen={!!matchTx} onClose={closeMatchModal} title={matchTx?.direction === 'out' ? tr('bankTxCreateExpense') : tr('bankTxMatchTitle')}>
        {matchTx && (
          <div>
            <div className="card" style={{ marginBottom: '1rem', padding: '0.75rem 1rem' }}>
              <div style={{ fontWeight: 700 }}>{matchTx.counterparty_name || UI_DASH}</div>
              <div style={{ color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>{matchTx.purpose || UI_DASH}</div>
              <div style={{ marginTop: '0.5rem', fontWeight: 700 }}>
                {matchTx.direction === 'in' ? '+' : '-'}{Number(matchTx.amount || 0).toLocaleString('sr-RS')} {matchTx.currency || 'RSD'}
              </div>
              <div style={{ marginTop: '0.25rem', fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                {tr('project')}: {getProjectName(matchTx.project_id)}
              </div>
            </div>

            {suggestLoading ? (
              <p>{tr('loading')}</p>
            ) : matchTx.direction === 'out' ? (
              renderOutgoingModalContent()
            ) : (
              renderIncomingModalContent()
            )}

            {matchError ? <div style={{ color: 'var(--color-danger)', marginTop: '1rem' }}>{matchError}</div> : null}
          </div>
        )}
      </Modal>

      <Modal isOpen={modalAssign} onClose={() => { setModalAssign(false); setAssignProjectId('') }} title={tr('assignProject')}>
        <div className="form-group">
          <label className="form-label">{tr('project')}</label>
          <select className="form-input" value={assignProjectId} onChange={(event) => setAssignProjectId(event.target.value)}>
            <option value="">{UI_DASH}</option>
            <option value="_none">{UI_DASH}</option>
            {commercialProjects.length > 0 && (
              <optgroup label={tr('commercialProject')}>
                {commercialProjects.map((project) => (
                  <option key={project.id} value={project.id}>{project.name}{project.code ? ` ${UI_DASH} ${project.code}` : ''}</option>
                ))}
              </optgroup>
            )}
            {internalProjects.length > 0 && (
              <optgroup label={tr('internalProject')}>
                {internalProjects.map((project) => (
                  <option key={project.id} value={project.id}>{project.name}{project.code ? ` ${UI_DASH} ${project.code}` : ''}</option>
                ))}
              </optgroup>
            )}
          </select>
        </div>
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={() => { setModalAssign(false); setAssignProjectId('') }}>{tr('cancel')}</button>
          <button className="btn btn-primary" onClick={handleBulkAssign}>{tr('save')}</button>
        </div>
      </Modal>
    </>
  )
}
