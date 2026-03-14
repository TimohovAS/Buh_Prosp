import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { getLang, tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import Modal from '../components/Modal'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
const UI_DASH = '\u2014'
const UI_SORT_BOTH = '\u2195'
const UI_SORT_ASC = '\u2191'
const UI_SORT_DESC = '\u2193'
const CASH_CATEGORY_VALUE = '__cash__'

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

function buildContractLabel(contract) {
  if (!contract) return ''
  const parts = []
  if (contract.number) parts.push(contract.number)
  if (contract.subject) parts.push(contract.subject)
  return parts.join(` ${UI_DASH} `) || contract.number || contract.subject || ''
}

export default function BankTransactions() {
  const pageBodyRef = useRef(null)
  const pendingScrollTopRef = useRef(null)
  const [data, setData] = useState([])
  const [projects, setProjects] = useState([])
  const [contracts, setContracts] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)

  const lang = getLang()
  const currentYear = new Date().getFullYear()

  const [year, setYear] = useState('')
  const [availableYears, setAvailableYears] = useState([currentYear])
  const [month, setMonth] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [directionFilter, setDirectionFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [queryInitialized, setQueryInitialized] = useState(false)

  const [sortCol, setSortCol] = useState('date')
  const [sortAsc, setSortAsc] = useState(false)

  const [selectedIds, setSelectedIds] = useState([])
  const [modalAssign, setModalAssign] = useState(false)
  const [assignProjectId, setAssignProjectId] = useState('')

  const [matchTx, setMatchTx] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const [suggestLoading, setSuggestLoading] = useState(false)
  const [matchError, setMatchError] = useState('')
  const [matchTab, setMatchTab] = useState('link')
  const [allInvoiceSearch, setAllInvoiceSearch] = useState('')
  const [expenseSaving, setExpenseSaving] = useState(false)
  const [expenseForm, setExpenseForm] = useState({
    date: todayIso(),
    description: '',
    category_id: '',
    project_id: '',
    contract_id: '',
    note: '',
  })


  const unassignedProject = projects.find((project) => project.code === 'INT-UNASSIGNED') || null
  const cashProject = projects.find((project) => project.code === 'INT-CASH') || null
  const commercialProjects = projects.filter((project) => !project.is_internal && project.status !== 'archived')
  const internalProjects = projects.filter((project) => project.is_internal && project.status !== 'archived')

  const getProjectName = (projectId) => projects.find((project) => project.id === projectId)?.name || UI_DASH
  const getCategoryName = (categoryId) => {
    const category = categories.find((item) => item.id === categoryId)
    if (!category) return UI_DASH
    return lang === 'ru' ? category.name_ru : category.name_sr
  }
  const getContractLabel = (contractId) => buildContractLabel(contracts.find((contract) => contract.id === contractId))
  const getContractsForProject = (projectId) => contracts
    .filter((contract) => contract.project_id === projectId || contract.project_id == null)
    .sort((left, right) => {
      const leftRank = left.project_id === projectId ? 0 : 1
      const rightRank = right.project_id === projectId ? 0 : 1
      if (leftRank !== rightRank) return leftRank - rightRank
      return buildContractLabel(left).localeCompare(buildContractLabel(right), 'sr')
    })

  const loadData = async ({ preserveScroll = false } = {}) => {
    if (preserveScroll && pageBodyRef.current) {
      pendingScrollTopRef.current = pageBodyRef.current.scrollTop
    }

    setLoading(true)
    try {
      const params = {}
      if (year) params.year = year
      if (year && month) params.month = month
      if (statusFilter !== 'all') params.status = statusFilter
      if (directionFilter !== 'all') params.direction = directionFilter

      const [transactions, projectList, contractList, categoryList, years] = await Promise.all([
        api.bankTransactions.list(params),
        api.projects.list({ show_archived: true }),
        api.contracts.list({ limit: 500 }),
        api.categories.list({ category_type: 'expense' }),
        api.bankTransactions.years(),
      ])
      setData(transactions)
      setProjects(projectList)
      setContracts(contractList)
      setCategories(categoryList)
      setAvailableYears(years?.length ? years : [currentYear])
    } catch (error) {
      console.error(error)
    } finally {
      setLoading(false)
      if (preserveScroll && pendingScrollTopRef.current != null) {
        const scrollTop = pendingScrollTopRef.current
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (pageBodyRef.current) {
              pageBodyRef.current.scrollTop = scrollTop
            }
            pendingScrollTopRef.current = null
          })
        })
      }
    }
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const nextYear = params.get('year')
    const nextMonth = params.get('month')
    const nextStatus = params.get('status')
    const nextDirection = params.get('direction')
    const nextSearch = params.get('search')

    if (nextYear) setYear(Number(nextYear))
    if (nextMonth) setMonth(nextMonth)
    if (nextStatus) setStatusFilter(nextStatus)
    if (nextDirection) setDirectionFilter(nextDirection)
    if (nextSearch) setSearch(nextSearch)
    setQueryInitialized(true)
  }, [])

  useEffect(() => {
    if (!queryInitialized) return
    loadData()
  }, [statusFilter, directionFilter, year, month, queryInitialized])

  useEffect(() => {
    if (availableYears.length === 0) return
    if (year !== '' && !availableYears.includes(year)) {
      setYear(availableYears[0])
    }
  }, [availableYears, year])

  const displayed = useMemo(() => {
    const query = search.trim().toLowerCase()
    let rows = data

    if (query) {
      rows = data.filter((transaction) =>
        (transaction.date || '').toLowerCase().includes(query) ||
        (transaction.counterparty_name || '').toLowerCase().includes(query) ||
        (transaction.purpose || '').toLowerCase().includes(query) ||
        (transaction.bank_reference || '').toLowerCase().includes(query) ||
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
  }, [data, search, sortAsc, sortCol, projects])

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
    contract_id: '',
    note: '',
  })

  const toggleSelect = (id) => {
    setSelectedIds((previous) => previous.includes(id) ? previous.filter((value) => value !== id) : [...previous, id])
  }

  const toggleSelectAll = () => {
    if (selectedIds.length >= displayed.length) setSelectedIds([])
    else setSelectedIds(displayed.map((item) => item.id))
  }


  const handleBulkAssign = async () => {
    if (selectedIds.length === 0) return
    const projectId = assignProjectId === '' || assignProjectId === '_none'
      ? null
      : parseInt(assignProjectId, 10)
    try {
      await api.bankTransactions.bulkAssignProject({ ids: selectedIds, project_id: projectId })
      setModalAssign(false)
      setAssignProjectId('')
      setSelectedIds([])
      await loadData({ preserveScroll: true })
    } catch (error) {
      console.error(error)
    }
  }

  const handleUnmatch = async (id) => {
    if (!confirm(tr('bankTxUnmatchBtn'))) return
    try {
      await api.bankTransactions.unmatch(id)
      await loadData({ preserveScroll: true })
    } catch (error) {
      console.error(error)
    }
  }

  const getMatchedTypeLabel = (type) => {
    if (type === 'cash') return tr('bankTxMatchedCash')
    if (type === 'income') return tr('income')
    if (type === 'expense') return tr('expenses')
    if (type === 'obligation') return tr('payments')
    return type || ''
  }

  const openMatchModal = async (transaction) => {
    setMatchTx(transaction)
    setMatchError('')
    setMatchTab(transaction.direction === 'out' ? 'link' : 'link')
    setAllInvoiceSearch('')
    setSuggestions([])
    setExpenseForm(buildExpenseForm(transaction))

    setSuggestLoading(true)
    try {
      const response = await api.bankTransactions.suggest(transaction.id)
      setSuggestions(response)
      if (transaction.direction === 'out') {
        const hasLinkOptions = response.some((item) => item.type === 'obligation' && item.section === 'suggested')
        setMatchTab(hasLinkOptions ? 'link' : 'create')
      }
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
    setMatchTab('link')
    setAllInvoiceSearch('')
    setExpenseSaving(false)
    setExpenseForm({
      date: todayIso(),
      description: '',
      category_id: '',
      project_id: '',
      contract_id: '',
      note: '',
    })
  }

  const performMatch = async (targetId, targetType) => {
    if (!matchTx) return
    try {
      await api.bankTransactions.match(matchTx.id, { type: targetType, id: targetId })
      closeMatchModal()
      await loadData({ preserveScroll: true })
    } catch (error) {
      setMatchError(error.message)
    }
  }

  const updateExpenseProject = (projectId) => {
    setExpenseForm((previous) => {
      const selectedContract = previous.contract_id ? contracts.find((contract) => String(contract.id) === String(previous.contract_id)) : null
      const keepContract = selectedContract && String(selectedContract.project_id) === String(projectId)
      return {
        ...previous,
        project_id: projectId,
        contract_id: keepContract ? previous.contract_id : '',
      }
    })
  }

  const updateExpenseContract = (contractId) => {
    setExpenseForm((previous) => {
      if (!contractId) {
        return { ...previous, contract_id: '' }
      }
      const selectedContract = contracts.find((contract) => String(contract.id) === String(contractId))
      return {
        ...previous,
        contract_id: contractId,
        project_id: selectedContract?.project_id ? String(selectedContract.project_id) : previous.project_id,
      }
    })
  }

  const updateExpenseCategory = (categoryId) => {
    setExpenseForm((previous) => {
      const isCashCategory = categoryId === CASH_CATEGORY_VALUE
      if (isCashCategory) {
        return {
          ...previous,
          category_id: categoryId,
          project_id: cashProject ? String(cashProject.id) : previous.project_id,
          contract_id: '',
        }
      }

      const wasCashCategory = previous.category_id === CASH_CATEGORY_VALUE
      const fallbackProjectId = matchTx?.project_id ? String(matchTx.project_id) : (unassignedProject ? String(unassignedProject.id) : '')
      return {
        ...previous,
        category_id: categoryId,
        project_id: wasCashCategory ? fallbackProjectId : previous.project_id,
      }
    })
  }

  const handleCreateExpense = async (event) => {
    event.preventDefault()
    if (!matchTx) return

    setExpenseSaving(true)
    try {
      const isCashCategorySelected = expenseForm.category_id === CASH_CATEGORY_VALUE
      await api.bankTransactions.createExpense(matchTx.id, {
        date: expenseForm.date,
        description: expenseForm.description.trim(),
        category: isCashCategorySelected ? 'cash' : null,
        category_id: expenseForm.category_id && !isCashCategorySelected ? parseInt(expenseForm.category_id, 10) : null,
        project_id: isCashCategorySelected
          ? (cashProject ? cashProject.id : null)
          : (expenseForm.project_id ? parseInt(expenseForm.project_id, 10) : (unassignedProject ? unassignedProject.id : null)),
        contract_id: isCashCategorySelected ? null : (expenseForm.contract_id ? parseInt(expenseForm.contract_id, 10) : null),
        note: expenseForm.note?.trim() || null,
      })
      closeMatchModal()
      await loadData({ preserveScroll: true })
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
      <div key={`${item.type}-${item.id}`} className="bank-match-item">
        <div style={{ minWidth: 0 }}>
          <div className="bank-match-item-title">
            <span>{label}</span>
            {item.date ? <span className="bank-match-item-subtle">{item.date}</span> : null}
            {item.score != null ? <span className="bank-match-item-subtle">{item.score}%</span> : null}
          </div>
          {item.client_name ? <div style={{ fontSize: '0.85rem', fontWeight: 600, marginTop: '0.2rem' }}>{item.client_name}</div> : null}
          {item.description ? <div className="bank-match-item-body">{item.description}</div> : null}
          <div className="bank-match-item-amount">
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

  const renderMatchSummary = (transaction) => {
    if (!transaction) return null
    const amount = Number(transaction.amount || 0)
    const amountClassName = transaction.direction === 'in' ? 'positive' : 'negative'

    return (
      <div className="card bank-match-summary">
        <div>
          <div className="bank-match-summary-title">{transaction.counterparty_name || UI_DASH}</div>
          <div className="bank-match-summary-purpose">{transaction.purpose || UI_DASH}</div>
          <div className="bank-match-summary-meta">
            <span>{tr('date')}: {transaction.date || UI_DASH}</span>
            <span>{tr('bankTxReference')}: {transaction.bank_reference || UI_DASH}</span>
          </div>
        </div>
        <div>
          <div className={`bank-match-summary-amount ${amountClassName}`}>
            {transaction.direction === 'in' ? '+' : '-'}{amount.toLocaleString('sr-RS')} {transaction.currency || 'RSD'}
          </div>
          <div className="bank-match-summary-project">
            {tr('project')}: {getProjectName(transaction.project_id)}
          </div>
        </div>
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
            <SearchInput
              placeholder={tr('bankTxSearchInvoices')}
              value={allInvoiceSearch}
              onChange={setAllInvoiceSearch}
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
    const isCashCategorySelected = expenseForm.category_id === CASH_CATEGORY_VALUE
    const selectedProjectId = expenseForm.project_id ? parseInt(expenseForm.project_id, 10) : null
    const filteredContracts = selectedProjectId ? getContractsForProject(selectedProjectId) : []
    const suggested = suggestions.filter((item) => item.section === 'suggested')
    const allObligations = suggestions.filter((item) => item.type === 'obligation' && (item.section === 'all' || !item.section))
    const query = allInvoiceSearch.trim().toLowerCase()
    const filteredObligations = allObligations.filter((item) =>
      !query ||
      String(item.description || '').toLowerCase().includes(query) ||
      String(item.client_name || '').toLowerCase().includes(query) ||
      String(item.date || '').toLowerCase().includes(query) ||
      String(item.amount || '').includes(query)
    )

    const renderLinkPanel = () => (
      <div className="bank-match-columns bank-match-link-panel">
        {suggested.length > 0 ? (
          <div className="bank-match-panel">
            <div className="bank-match-panel-title">{tr('bankTxAutoFound')}</div>
            <div className="bank-match-list">
              {suggested.map(renderSuggestionCard)}
            </div>
          </div>
        ) : null}

        <div className="bank-match-panel">
          <div className="bank-match-panel-title">{tr('bankTxOpenObligations')}</div>
          <SearchInput
            placeholder={tr('bankTxSearchObligations')}
            value={allInvoiceSearch}
            onChange={setAllInvoiceSearch}
            style={{ width: '100%', marginBottom: '0.75rem' }}
          />
          <div className="bank-match-list">
            {allObligations.length === 0 && (
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', textAlign: 'center' }}>{tr('bankTxNoOpenObligations')}</p>
            )}
            {filteredObligations.length === 0 && allObligations.length > 0 && (
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', textAlign: 'center' }}>{tr('bankTxNoInvoicesFound')}</p>
            )}
            {filteredObligations.map(renderSuggestionCard)}
          </div>
        </div>
      </div>
    )

    const renderCreatePanel = () => (
      <form onSubmit={handleCreateExpense} className="bank-match-panel bank-match-form">
        <p className="bank-match-form-note">{tr('bankTxCreateExpenseHint')}</p>
        <p className="bank-match-form-note">{tr('bankTxCreateExpenseFallbackHint')}</p>

        <div className="bank-match-form-grid">
          <div className="form-group">
            <label className="form-label">{tr('category')}</label>
            <select className="form-input" value={expenseForm.category_id} onChange={(event) => updateExpenseCategory(event.target.value)}>
              <option value="">{UI_DASH}</option>
              <option value={CASH_CATEGORY_VALUE}>{tr('cashCategoryOption')}</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>{getCategoryName(category.id)}</option>
              ))}
            </select>
          </div>

          {!isCashCategorySelected ? (
            <div className="form-group">
              <label className="form-label">{tr('project')}</label>
              <ProjectSelect
                projects={projects}
                value={expenseForm.project_id}
                onChange={updateExpenseProject}
                required
              />
            </div>
          ) : null}

          {!isCashCategorySelected ? (
            <div className="form-group full">
              <label className="form-label">{tr('contract')}</label>
              <select className="form-input" value={expenseForm.contract_id} onChange={(event) => updateExpenseContract(event.target.value)}>
                <option value="">{`${UI_DASH} ${tr('withoutContract')} ${UI_DASH}`}</option>
                {filteredContracts.map((contract) => (
                  <option key={contract.id} value={contract.id}>{getContractLabel(contract.id)}</option>
                ))}
              </select>
            </div>
          ) : null}

          <div className="form-group">
            <label className="form-label">{tr('date')}</label>
            <DatePicker value={expenseForm.date} onChange={(value) => setExpenseForm((previous) => ({ ...previous, date: value }))} required />
          </div>

          <div className="form-group">
            <label className="form-label">{tr('amount')}</label>
            <input className="form-input" value={matchTx?.amount?.toLocaleString('sr-RS') || ''} disabled />
          </div>

          <div className="form-group full">
            <label className="form-label">{tr('description')}</label>
            <input
              className="form-input"
              value={expenseForm.description}
              onChange={(event) => setExpenseForm((previous) => ({ ...previous, description: event.target.value }))}
              required
            />
          </div>

          <div className="form-group full">
            <label className="form-label">{tr('note')}</label>
            <input className="form-input" value={expenseForm.note} onChange={(event) => setExpenseForm((previous) => ({ ...previous, note: event.target.value }))} />
          </div>
        </div>

        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={closeMatchModal}>{tr('cancel')}</button>
          <button type="submit" className="btn btn-primary" disabled={expenseSaving}>{expenseSaving ? tr('loading') : tr('bankTxCreateAndMatch')}</button>
        </div>
      </form>
    )

    return (
      <div className="bank-match-layout">
        <div className="bank-match-tabs">
          <button
            type="button"
            className={`bank-match-tab ${matchTab === 'link' ? 'active' : ''}`}
            onClick={() => setMatchTab('link')}
          >
            {tr('bankTxMatchBtn')}
          </button>
          <button
            type="button"
            className={`bank-match-tab ${matchTab === 'create' ? 'active' : ''}`}
            onClick={() => setMatchTab('create')}
          >
            {tr('bankTxCreateExpense')}
          </button>
        </div>

        <div className="bank-match-content">
          {matchTab === 'link' ? renderLinkPanel() : renderCreatePanel()}
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">{tr('bankTransactions')}</h1>
        </div>
        <div className="page-header-actions">
          <select className="form-input" style={{ width: 'auto' }} value={year} onChange={(event) => { setYear(event.target.value ? Number(event.target.value) : ''); setMonth('') }}>
            <option value="">{tr('allTime')}</option>
            {availableYears.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <select className="form-input" style={{ width: 'auto' }} value={month} onChange={(event) => setMonth(event.target.value)} disabled={!year}>
            <option value="">{tr('allMonths')}</option>
            {MONTHS.map((value) => (
              <option key={value} value={value}>{String(value).padStart(2, '0')}</option>
            ))}
          </select>
          <select className="form-input" style={{ width: 'auto' }} value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">{tr('filterAll')}</option>
            <option value="unmatched">{tr('bankTxUnmatched')}</option>
            <option value="matched">{tr('bankTxMatched')}</option>
          </select>
          <select className="form-input" style={{ width: 'auto' }} value={directionFilter} onChange={(event) => setDirectionFilter(event.target.value)}>
            <option value="all">{tr('filterAll')}</option>
            <option value="in">{tr('bankTxDirectionIn')}</option>
            <option value="out">{tr('bankTxDirectionOut')}</option>
          </select>
          <SearchInput
            placeholder={tr('search')}
            value={search}
            onChange={setSearch}
            style={{ minWidth: 180 }}
          />
          {selectedIds.length > 0 && (
            <button className="btn btn-secondary" onClick={() => { setAssignProjectId(unassignedProject ? String(unassignedProject.id) : ''); setModalAssign(true) }}>
              {tr('assignProject')} ({selectedIds.length})
            </button>
          )}
        </div>
      </div>

      <div className="page-body" ref={pageBodyRef}>
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
                        {transaction.status === 'matched'
                          ? <span className="badge badge-success">{tr('bankTxMatched')} ({getMatchedTypeLabel(transaction.matched_type)})</span>
                          : <span className="badge badge-warning">{tr('bankTxUnmatched')}</span>}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {transaction.status !== 'matched' && (
                          <div style={{ display: 'flex', gap: '0.35rem', justifyContent: 'flex-end' }}>
                            <button className="btn btn-sm btn-primary" onClick={() => openMatchModal(transaction)}>
                              {transaction.direction === 'out' ? tr('bankTxCreateExpense') : tr('bankTxMatchBtn')}
                            </button>
                          </div>
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

      <Modal
        isOpen={!!matchTx}
        onClose={closeMatchModal}
        title={matchTx?.direction === 'out' ? tr('bankTxCreateExpense') : tr('bankTxMatchTitle')}
        className={matchTx?.direction === 'out' ? 'bank-match-modal' : ''}
        maxWidth={matchTx?.direction === 'out' ? '980px' : '700px'}
      >
        {matchTx && (
          <div className="bank-match-layout">
            {renderMatchSummary(matchTx)}

            {suggestLoading ? (
              <p>{tr('loading')}</p>
            ) : matchTx.direction === 'out' ? (
              renderOutgoingModalContent()
            ) : (
              renderIncomingModalContent()
            )}

            {matchError ? <div style={{ color: 'var(--color-danger)' }}>{matchError}</div> : null}
          </div>
        )}
      </Modal>

      <Modal isOpen={modalAssign} onClose={() => { setModalAssign(false); setAssignProjectId('') }} title={tr('assignProject')}>
        <div className="form-group">
          <label className="form-label">{tr('project')}</label>
          <ProjectSelect
            projects={projects}
            value={assignProjectId}
            onChange={setAssignProjectId}
            allowEmpty
            emptyLabel={UI_DASH}
          />
        </div>
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={() => { setModalAssign(false); setAssignProjectId('') }}>{tr('cancel')}</button>
          <button className="btn btn-primary" onClick={handleBulkAssign}>{tr('save')}</button>
        </div>
      </Modal>
    </>
  )
}
