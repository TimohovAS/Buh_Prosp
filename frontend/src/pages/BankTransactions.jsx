import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { getLang, tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import YearFilterSelect from '../components/YearFilterSelect'
import useAvailableYears from '../hooks/useAvailableYears'
import useCategoryProjectResolver from '../hooks/useCategoryProjectResolver'
import useListPageState from '../hooks/useListPageState'
import { buildContractLabel, contractMatchesProject, filterContractsForProject, findUnassignedProject, getContractLabelById, getProjectName as resolveProjectName } from '../utils/entityLabels'
import { UI_DASH, todayIso, formatMoney2 as formatMoney } from '../utils/formatters'
import { MONTHS } from '../utils/constants'

const CASH_CATEGORY_VALUE = '__cash__'

function parseMoneyInput(value) {
  if (value == null) return 0
  const normalized = String(value).replace(/\s+/g, '').replace(',', '.')
  const parsed = Number.parseFloat(normalized)
  return Number.isFinite(parsed) ? parsed : 0
}

export default function BankTransactions() {
  const location = useLocation()
  const navigate = useNavigate()
  const pageBodyRef = useRef(null)
  const pendingScrollTopRef = useRef(null)
  const isActivePage = location.pathname === '/bank'
  const [data, setData] = useState([])
  const [projects, setProjects] = useState([])
  const [contracts, setContracts] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)

  const lang = getLang()
  const { currentYear, year, setYear, availableYears, applyAvailableYears } = useAvailableYears({ initialYear: '' })
  const [month, setMonth] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [directionFilter, setDirectionFilter] = useState('all')
  const [pendingBankReferenceOpen, setPendingBankReferenceOpen] = useState(null)
  const {
    search,
    setSearch,
    sortCol,
    sortAsc,
    toggleSort,
  } = useListPageState({ initialSortCol: 'date', initialSortAsc: false })

  const [selectedIds, setSelectedIds] = useState([])
  const [modalAssign, setModalAssign] = useState(false)
  const [assignProjectId, setAssignProjectId] = useState('')

  const [matchTx, setMatchTx] = useState(null)
  const [transactionModalMode, setTransactionModalMode] = useState('overview')
  const [suggestions, setSuggestions] = useState([])
  const [suggestLoading, setSuggestLoading] = useState(false)
  const [matchError, setMatchError] = useState('')
  const [matchTab, setMatchTab] = useState('link')
  const [allInvoiceSearch, setAllInvoiceSearch] = useState('')
  const [allocationLines, setAllocationLines] = useState([])
  const [allocationSaving, setAllocationSaving] = useState(false)
  const [expenseSaving, setExpenseSaving] = useState(false)
  const [expenseForm, setExpenseForm] = useState({
    date: todayIso(),
    description: '',
    category_id: '',
    project_id: '',
    contract_id: '',
    note: '',
  })
  const [loanModal, setLoanModal] = useState(null)
  const [loanClients, setLoanClients] = useState([])
  const [loanCandidates, setLoanCandidates] = useState([])
  const [loanSaving, setLoanSaving] = useState(false)
  const [loanError, setLoanError] = useState('')
  const [loanForm, setLoanForm] = useState({
    client_id: '',
    counterparty_name: '',
    agreement_number: '',
    agreement_date: '',
    due_date: '',
    note: '',
    loan_id: '',
  })


  const unassignedProject = findUnassignedProject(projects)
  const cashProject = projects.find((project) => project.code === 'INT-CASH') || null
  const commercialProjects = projects.filter((project) => !project.is_internal && project.status !== 'archived')
  const internalProjects = projects.filter((project) => project.is_internal && project.status !== 'archived')
  const {
    getCategoryById: getExpenseCategoryById,
    getCategoryDefaultProjectId: getExpenseCategoryDefaultProjectId,
    usesCategoryProject: expenseUsesDefaultProject,
    getCategoryLabel: getResolvedCategoryLabel,
  } = useCategoryProjectResolver(categories, lang)

  const getProjectName = (projectId) => resolveProjectName(projects, projectId, UI_DASH)
  const getCategoryName = (categoryId) => getResolvedCategoryLabel(categoryId, UI_DASH)
  const getContractLabel = (contractId) => getContractLabelById(contracts, contractId, '')
  const getContractsForProject = (projectId) => filterContractsForProject(contracts, projectId)

  const loadReferenceData = async () => {
    const [projectList, contractList, categoryList] = await Promise.all([
      api.projects.list({ show_archived: true }),
      api.contracts.list({ limit: 500 }),
      api.categories.list({ category_type: 'expense' }),
    ])
    setProjects(projectList)
    setContracts(contractList)
    setCategories(categoryList)
    return { projectList, contractList, categoryList }
  }

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

      const [transactions, years] = await Promise.all([
        api.bankTransactions.list(params),
        api.bankTransactions.years(),
        loadReferenceData(),
      ])
      setData(transactions)
      applyAvailableYears(years)
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
    if (!isActivePage) return

    const params = new URLSearchParams(location.search || '')
    const hasExplicitQuery = params.toString().length > 0
    if (hasExplicitQuery) {
      const nextYear = params.get('year') ? Number(params.get('year')) : ''
      const nextMonth = params.get('month') || ''
      const nextStatus = params.get('status') || 'all'
      const nextDirection = params.get('direction') || 'all'
      const nextSearch = params.get('search') || ''
      if (
        year !== nextYear ||
        month !== nextMonth ||
        statusFilter !== nextStatus ||
        directionFilter !== nextDirection ||
        search !== nextSearch
      ) {
        setYear(nextYear)
        setMonth(nextMonth)
        setStatusFilter(nextStatus)
        setDirectionFilter(nextDirection)
        setSearch(nextSearch)
        return
      }
    }

    loadData()
  }, [statusFilter, directionFilter, year, month, search, isActivePage, location.search])

  useEffect(() => {
    if (!isActivePage) return

    const deepLink = location.state && typeof location.state === 'object'
      ? {
          bankReference: location.state.openBankReference || '',
          year: location.state.openBankYear ? Number(location.state.openBankYear) : '',
          month: location.state.openBankMonth || '',
          direction: location.state.openBankDirection || 'all',
          status: location.state.openBankStatus || 'all',
        }
      : null

    if (!deepLink?.bankReference) return

    setPendingBankReferenceOpen(deepLink)

    if (year !== deepLink.year) setYear(deepLink.year)
    if (month !== deepLink.month) setMonth(deepLink.month)
    if (directionFilter !== deepLink.direction) setDirectionFilter(deepLink.direction)
    if (statusFilter !== deepLink.status) setStatusFilter(deepLink.status)
    if (search !== '') setSearch('')

    navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
  }, [directionFilter, isActivePage, location.pathname, location.search, location.state, month, navigate, search, statusFilter, year])

  useEffect(() => {
    if (!isActivePage || loading || !pendingBankReferenceOpen?.bankReference) return

    const filtersAligned = (
      year === pendingBankReferenceOpen.year &&
      month === pendingBankReferenceOpen.month &&
      directionFilter === pendingBankReferenceOpen.direction &&
      statusFilter === pendingBankReferenceOpen.status &&
      search === ''
    )
    const matchedTransaction = data.find((transaction) => transaction.bank_reference === pendingBankReferenceOpen.bankReference)
    if (!matchedTransaction) {
      if (filtersAligned) setPendingBankReferenceOpen(null)
      return
    }

    openTransactionModal(matchedTransaction)
    setPendingBankReferenceOpen(null)
  }, [data, directionFilter, isActivePage, loading, month, pendingBankReferenceOpen, search, statusFilter, year])

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

  const buildExpenseForm = (transaction) => ({
    date: transaction?.date || todayIso(),
    description: transaction?.purpose || transaction?.counterparty_name || '',
    category_id: '',
    project_id: transaction?.project_id ? String(transaction.project_id) : (unassignedProject ? String(unassignedProject.id) : ''),
    contract_id: '',
    note: '',
  })

  const resetTransactionWorkflow = (transaction = null) => {
    setSuggestLoading(false)
    setMatchError('')
    setMatchTab(transaction?.direction === 'out' ? 'link' : (transaction?.status === 'matched' ? 'allocate' : 'link'))
    setAllInvoiceSearch('')
    setSuggestions([])
    setAllocationLines([])
    setAllocationSaving(false)
    setExpenseSaving(false)
    setExpenseForm(buildExpenseForm(transaction))
  }

  const openTransactionModal = (transaction) => {
    setMatchTx(transaction)
    setTransactionModalMode('overview')
    resetTransactionWorkflow(transaction)
  }

  const refreshSelectedTransaction = async (txId = matchTx?.id, nextMode = 'overview') => {
    if (!txId) return null
    await loadData({ preserveScroll: true })
    try {
      const fresh = await api.bankTransactions.get(txId)
      setMatchTx(fresh)
      setTransactionModalMode(nextMode)
      resetTransactionWorkflow(fresh)
      return fresh
    } catch (error) {
      console.error(error)
      setMatchTx(null)
      setTransactionModalMode('overview')
      resetTransactionWorkflow()
      return null
    }
  }

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
      await refreshSelectedTransaction(id, 'overview')
    } catch (error) {
      console.error(error)
    }
  }

  const handleClassifyOwnerFunds = async (transaction) => {
    const confirmMessage = transaction?.status === 'matched' && transaction?.matched_type === 'expense'
      ? tr('bankTxOwnerFundsConvertConfirm')
      : (transaction?.direction === 'in' ? tr('bankTxOwnerFundsConfirmIn') : tr('bankTxOwnerFundsConfirmOut'))
    if (!confirm(confirmMessage)) return
    try {
      await api.bankTransactions.classifyOwnerFunds(transaction.id)
      await refreshSelectedTransaction(transaction.id, 'overview')
    } catch (error) {
      console.error(error)
    }
  }

  const handleDownloadOwnerFundsDocument = async (transactionId) => {
    try {
      await api.reports.downloadOwnerFundsPdf(transactionId)
    } catch (error) {
      console.error(error)
    }
  }

  const openLoanOperation = async (transaction, operation) => {
    const isRepayment = operation === 'repayBorrowed' || operation === 'repayIssued'
    const loanType = operation === 'receiveBorrowed' || operation === 'repayBorrowed' ? 'borrowed' : 'issued'
    setLoanModal({ transaction, operation, loanType, isRepayment })
    setLoanError('')
    setLoanForm({
      client_id: '',
      counterparty_name: transaction.counterparty_name || '',
      agreement_number: '',
      agreement_date: '',
      due_date: '',
      note: '',
      loan_id: '',
    })
    setLoanCandidates([])
    try {
      const [clients, loans] = await Promise.all([
        api.clients.list({ archived: false }),
        api.counterpartyLoans.list({ loan_type: loanType, status: 'open' }),
      ])
      setLoanClients(clients.filter((client) => !client.is_archived))
      const matchingLoans = loans.filter((loan) => (loan.currency || 'RSD') === (transaction.currency || 'RSD'))
      setLoanCandidates(matchingLoans)
      if (isRepayment && matchingLoans.length === 1) setLoanForm((current) => ({ ...current, loan_id: String(matchingLoans[0].id) }))
    } catch (error) {
      setLoanError(error.message)
    }
  }

  const closeLoanModal = () => {
    if (loanSaving) return
    setLoanModal(null)
    setLoanError('')
  }

  const handleSaveLoanMovement = async (event) => {
    event.preventDefault()
    if (!loanModal) return
    setLoanSaving(true)
    setLoanError('')
    try {
      if (loanModal.isRepayment || loanForm.loan_id) {
        if (loanModal.isRepayment && !loanForm.loan_id) throw new Error(tr('loanSelectOpen'))
        await api.counterpartyLoans.addMovementFromBank(Number(loanForm.loan_id), loanModal.transaction.id, {
          movement_type: loanModal.isRepayment ? 'repayment' : 'disbursement',
          note: loanForm.note || null,
        })
      } else {
        await api.counterpartyLoans.createFromBank(loanModal.transaction.id, {
          loan_type: loanModal.loanType,
          client_id: loanForm.client_id || null,
          counterparty_name: loanForm.counterparty_name,
          agreement_number: loanForm.agreement_number || null,
          agreement_date: loanForm.agreement_date || null,
          due_date: loanForm.due_date || null,
          note: loanForm.note || null,
        })
      }
      const txId = loanModal.transaction.id
      setLoanModal(null)
      await refreshSelectedTransaction(txId, 'overview')
    } catch (error) {
      setLoanError(error.message)
    } finally {
      setLoanSaving(false)
    }
  }

  const getLoanMovementStatusLabel = (transaction) => {
    if (transaction.loan_movement_type === 'disbursement') {
      return transaction.loan_type === 'borrowed' ? tr('loanReceivedStatus') : tr('loanIssuedStatus')
    }
    return transaction.loan_type === 'borrowed' ? tr('loanRepaidStatus') : tr('loanReturnedStatus')
  }

  const getMatchedTypeLabel = (type) => {
    if (type === 'cash') return tr('bankTxMatchedCash')
    if (type === 'income') return tr('income')
    if (type === 'income_allocation') return tr('bankTxDistributedLabel')
    if (type === 'owner_funds') return tr('bankTxOwnerFundsLabel')
    if (type === 'loan_movement') return tr('loanMovementLabel')
    if (type === 'expense') return tr('expenses')
    if (type === 'obligation') return tr('payments')
    return type || ''
  }

  const isEditableIncomeTransaction = (transaction) => (
    transaction?.direction === 'in' &&
    transaction?.status === 'matched' &&
    ['income', 'income_allocation'].includes(transaction?.matched_type)
  )

  const isOwnerFundsTransaction = (transaction) => (
    transaction?.status === 'matched' && transaction?.matched_type === 'owner_funds'
  )

  const isLoanTransaction = (transaction) => (
    transaction?.status === 'matched' && transaction?.matched_type === 'loan_movement'
  )

  const canConvertExpenseToOwnerFunds = (transaction) => (
    transaction?.status === 'matched' && transaction?.matched_type === 'expense'
  )

  const getOwnerFundsStatusLabel = (transaction) => (
    transaction?.direction === 'in' ? tr('bankTxOwnerFundsInStatus') : tr('bankTxOwnerFundsOutStatus')
  )

  const getAllocationTotals = (lines = allocationLines) => {
    const allocated = lines.reduce((sum, line) => sum + parseMoneyInput(line.amount), 0)
    const total = parseMoneyInput(matchTx?.amount)
    const remaining = total - allocated
    return {
      total,
      allocated,
      remaining: remaining > 0 ? remaining : 0,
      overAllocated: remaining < -0.009 ? Math.abs(remaining) : 0,
    }
  }

  const openAssignModal = async () => {
    try {
      const { projectList } = await loadReferenceData()
      const nextUnassignedProject = findUnassignedProject(projectList)
      setAssignProjectId(nextUnassignedProject ? String(nextUnassignedProject.id) : '')
    } catch (error) {
      console.error(error)
      setAssignProjectId(unassignedProject ? String(unassignedProject.id) : '')
    }
    setModalAssign(true)
  }

  const openMatchModal = async (transaction, requestedTab = null) => {
    const activeTransaction = transaction || matchTx
    if (!activeTransaction) return
    setMatchTx(activeTransaction)
    setTransactionModalMode('workflow')
    resetTransactionWorkflow(activeTransaction)
    setSuggestLoading(true)
    try {
      const referenceDataPromise = loadReferenceData()
      if (activeTransaction.direction === 'out') {
        const [response] = await Promise.all([
          api.bankTransactions.suggest(activeTransaction.id),
          referenceDataPromise,
        ])
        setSuggestions(response)
        const hasLinkOptions = response.some((item) => item.type === 'obligation' && item.section === 'suggested')
        setMatchTab(requestedTab || (hasLinkOptions ? 'link' : 'create'))
      } else {
        const [response] = await Promise.all([
          api.bankTransactions.incomeAllocation(activeTransaction.id),
          referenceDataPromise,
        ])
        setSuggestions(response.candidates || [])
        setAllocationLines((response.allocations || []).map((item) => ({
          income_id: item.income_id,
          invoice_number: item.invoice_number,
          client_name: item.client_name,
          description: item.description,
          date: item.date,
          status: item.status,
          amount_full: item.amount_full,
          amount_paid: item.amount_paid,
          available_amount: item.available_amount,
          allocated_amount: item.allocated_amount,
          project_name: item.project_name,
          project_code: item.project_code,
          amount: String(item.allocated_amount ?? ''),
        })))
        setMatchTab(requestedTab || (activeTransaction.status === 'matched' ? 'allocate' : 'link'))
      }
    } catch (error) {
      setMatchError(error.message)
    } finally {
      setSuggestLoading(false)
    }
  }

  const closeMatchModal = () => {
    setMatchTx(null)
    setTransactionModalMode('overview')
    resetTransactionWorkflow()
  }

  const performMatch = async (targetId, targetType) => {
    if (!matchTx) return
    try {
      await api.bankTransactions.match(matchTx.id, { type: targetType, id: targetId })
      await loadData({ preserveScroll: true })
      closeMatchModal()
    } catch (error) {
      setMatchError(error.message)
    }
  }

  const addAllocationLine = (item) => {
    setAllocationLines((previous) => {
      if (previous.some((line) => String(line.income_id) === String(item.id))) return previous
      const totals = getAllocationTotals(previous)
      const defaultAmount = Math.max(0, Math.min(parseMoneyInput(item.amount), totals.remaining))
      return [
        ...previous,
        {
          income_id: item.id,
          invoice_number: item.invoice_number,
          client_name: item.client_name,
          description: item.description,
          date: item.date,
          status: item.status,
          amount_full: item.amount_full,
          amount_paid: item.amount_paid,
          available_amount: item.amount,
          allocated_amount: 0,
          project_name: item.project_name,
          project_code: item.project_code,
          amount: defaultAmount > 0 ? String(defaultAmount) : '',
        },
      ]
    })
  }

  const updateAllocationAmount = (incomeId, value) => {
    setAllocationLines((previous) => previous.map((line) => (
      String(line.income_id) !== String(incomeId)
        ? line
        : { ...line, amount: value }
    )))
  }

  const removeAllocationLine = (incomeId) => {
    setAllocationLines((previous) => previous.filter((line) => String(line.income_id) !== String(incomeId)))
  }

  const saveAllocation = async () => {
    if (!matchTx) return
    setAllocationSaving(true)
    setMatchError('')
    try {
      const payload = {
        allocations: allocationLines
          .map((line) => ({
            income_id: line.income_id,
            amount: parseMoneyInput(line.amount),
          }))
          .filter((line) => line.amount > 0),
      }
      await api.bankTransactions.saveIncomeAllocation(matchTx.id, payload)
      await loadData({ preserveScroll: true })
      closeMatchModal()
    } catch (error) {
      setMatchError(error.message)
    } finally {
      setAllocationSaving(false)
    }
  }

  const updateExpenseProject = (projectId) => {
    setExpenseForm((previous) => {
      const selectedContract = previous.contract_id ? contracts.find((contract) => String(contract.id) === String(previous.contract_id)) : null
      const keepContract = contractMatchesProject(selectedContract, projectId)
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
      const defaultProjectId = getExpenseCategoryDefaultProjectId(categoryId)
      const selectedContract = previous.contract_id ? contracts.find((contract) => String(contract.id) === String(previous.contract_id)) : null
      const nextProjectId = defaultProjectId || (wasCashCategory ? fallbackProjectId : previous.project_id)
      const keepContract = selectedContract && (!nextProjectId || String(selectedContract.project_id) === String(nextProjectId) || selectedContract.project_id == null)
      return {
        ...previous,
        category_id: categoryId,
        project_id: nextProjectId,
        contract_id: keepContract ? previous.contract_id : '',
      }
    })
  }

  const handleCreateExpense = async (event) => {
    event.preventDefault()
    if (!matchTx) return

    setExpenseSaving(true)
    try {
      const isCashCategorySelected = expenseForm.category_id === CASH_CATEGORY_VALUE
      const categoryDefaultProjectId = getExpenseCategoryDefaultProjectId(expenseForm.category_id)
      await api.bankTransactions.createExpense(matchTx.id, {
        date: expenseForm.date,
        description: expenseForm.description.trim(),
        category: isCashCategorySelected ? 'cash' : null,
        category_id: expenseForm.category_id && !isCashCategorySelected ? parseInt(expenseForm.category_id, 10) : null,
        project_id: isCashCategorySelected
          ? (cashProject ? cashProject.id : null)
          : (categoryDefaultProjectId
            ? parseInt(categoryDefaultProjectId, 10)
            : (expenseForm.project_id ? parseInt(expenseForm.project_id, 10) : (unassignedProject ? unassignedProject.id : null))),
        contract_id: isCashCategorySelected ? null : (expenseForm.contract_id ? parseInt(expenseForm.contract_id, 10) : null),
        note: expenseForm.note?.trim() || null,
      })
      await loadData({ preserveScroll: true })
      closeMatchModal()
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

  const renderAllocationCandidateCard = (item) => {
    const isSelected = allocationLines.some((line) => String(line.income_id) === String(item.id))
    const amount = parseMoneyInput(item.amount)
    const fullAmount = item.amount_full != null ? parseMoneyInput(item.amount_full) : amount
    const isPartial = item.type === 'income' && fullAmount > amount
    const label = item.invoice_number || item.description || `#${item.id}`

    return (
      <div key={`allocation-${item.id}`} className={`bank-match-item ${isSelected ? 'selected' : ''}`}>
        <div style={{ minWidth: 0 }}>
          <div className="bank-match-item-title">
            <span>{label}</span>
            {item.date ? <span className="bank-match-item-subtle">{item.date}</span> : null}
          </div>
          {item.client_name ? <div style={{ fontSize: '0.85rem', fontWeight: 600, marginTop: '0.2rem' }}>{item.client_name}</div> : null}
          {item.description ? <div className="bank-match-item-body">{item.description}</div> : null}
          <div className="bank-match-item-amount">
            {isPartial ? (
              <>
                <span>{tr('bankTxAvailableAmount')}: {formatMoney(amount)} RSD</span>
                <span style={{ fontWeight: 400, color: 'var(--color-text-muted)' }}> / {formatMoney(fullAmount)} RSD</span>
              </>
            ) : (
              <span>{formatMoney(amount)} RSD</span>
            )}
          </div>
        </div>
        <button
          className="btn btn-sm btn-primary"
          style={{ whiteSpace: 'nowrap' }}
          onClick={() => addAllocationLine(item)}
          disabled={isSelected}
        >
          {isSelected ? tr('bankTxAllocatedSelected') : tr('bankTxAllocateAdd')}
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

  const renderTransactionStatusBadge = (transaction) => {
    if (!transaction) return null
    if (transaction.status === 'matched') {
      if (transaction.matched_type === 'income_allocation') {
        return (
          <span className={`badge ${transaction.allocation_remaining > 0 ? 'badge-warning' : 'badge-success'}`}>
            {transaction.allocation_remaining > 0 ? tr('bankTxAllocationPartialStatus') : tr('bankTxAllocationFullStatus')}
            {transaction.allocation_count ? ` (${transaction.allocation_count})` : ''}
            {transaction.allocation_remaining > 0 ? ` • ${tr('bankTxAllocationRemainingShort')} ${formatMoney(transaction.allocation_remaining)}` : ''}
          </span>
        )
      }
      if (transaction.matched_type === 'owner_funds') {
        return <span className="badge badge-success">{getOwnerFundsStatusLabel(transaction)}</span>
      }
      if (transaction.matched_type === 'loan_movement') {
        return <span className="badge badge-success">{getLoanMovementStatusLabel(transaction)}</span>
      }
      return <span className="badge badge-success">{tr('bankTxMatched')} ({getMatchedTypeLabel(transaction.matched_type)})</span>
    }
    return <span className="badge badge-warning">{tr('bankTxUnmatched')}</span>
  }

  const renderTransactionDetails = (transaction) => {
    if (!transaction) return null

    const actions = []
    if (transaction.status !== 'matched') {
      if (transaction.direction === 'in') {
        actions.push(
          { key: 'link', label: tr('bankTxMatchBtn'), className: 'btn btn-primary', onClick: () => openMatchModal(transaction, 'link') },
          { key: 'allocate', label: tr('bankTxAllocateMode'), className: 'btn btn-secondary', onClick: () => openMatchModal(transaction, 'allocate') },
          { key: 'loan-receive', label: tr('loanReceive'), className: 'btn btn-secondary', onClick: () => openLoanOperation(transaction, 'receiveBorrowed') },
          { key: 'loan-repayment-in', label: tr('loanReceiveRepayment'), className: 'btn btn-secondary', onClick: () => openLoanOperation(transaction, 'repayIssued') },
          { key: 'owner-funds-in', label: tr('bankTxOwnerFundsMarkIn'), className: 'btn btn-secondary', onClick: () => handleClassifyOwnerFunds(transaction) },
        )
      } else {
        actions.push(
          { key: 'link', label: tr('bankTxMatchBtn'), className: 'btn btn-primary', onClick: () => openMatchModal(transaction, 'link') },
          { key: 'create', label: tr('bankTxCreateExpense'), className: 'btn btn-secondary', onClick: () => openMatchModal(transaction, 'create') },
          { key: 'loan-issue', label: tr('loanIssue'), className: 'btn btn-secondary', onClick: () => openLoanOperation(transaction, 'issueLoan') },
          { key: 'loan-repayment-out', label: tr('loanRepayBorrowed'), className: 'btn btn-secondary', onClick: () => openLoanOperation(transaction, 'repayBorrowed') },
          { key: 'owner-funds-out', label: tr('bankTxOwnerFundsMarkOut'), className: 'btn btn-secondary', onClick: () => handleClassifyOwnerFunds(transaction) },
        )
      }
    } else {
      if (isEditableIncomeTransaction(transaction)) {
        actions.push({ key: 'edit', label: tr('edit'), className: 'btn btn-primary', onClick: () => openMatchModal(transaction, 'allocate') })
      }
      if (canConvertExpenseToOwnerFunds(transaction)) {
        actions.push({ key: 'convert-owner-funds', label: tr('bankTxOwnerFundsConvert'), className: 'btn btn-secondary', onClick: () => handleClassifyOwnerFunds(transaction) })
      }
      if (isOwnerFundsTransaction(transaction)) {
        actions.push({ key: 'document', label: tr('bankTxOwnerFundsDocument'), className: 'btn btn-secondary', onClick: () => handleDownloadOwnerFundsDocument(transaction.id) })
      }
      if (isLoanTransaction(transaction) && transaction.loan_id) {
        actions.push({ key: 'open-loan', label: tr('openLoan'), className: 'btn btn-secondary', onClick: () => navigate(`/counterparty-loans?open=${transaction.loan_id}`) })
      }
      actions.push({ key: 'unmatch', label: tr('bankTxUnmatchBtn'), className: 'btn btn-danger', onClick: () => handleUnmatch(transaction.id) })
    }

    return (
      <div className="bank-transaction-details">
        <div className="bank-transaction-detail-grid">
          <section className="card bank-transaction-detail-card">
            <div className="bank-transaction-field-grid">
              <div className="bank-transaction-field">
                <span className="bank-transaction-field-label">{tr('status')}</span>
                <div>{renderTransactionStatusBadge(transaction)}</div>
              </div>
              <div className="bank-transaction-field">
                <span className="bank-transaction-field-label">{tr('amount')}</span>
                <strong className={`bank-transaction-field-value ${transaction.direction === 'in' ? 'positive' : 'negative'}`}>
                  {transaction.direction === 'in' ? '+' : '-'}{formatMoney(transaction.amount)} {transaction.currency || 'RSD'}
                </strong>
              </div>
              <div className="bank-transaction-field">
                <span className="bank-transaction-field-label">{tr('date')}</span>
                <span className="bank-transaction-field-value">{transaction.date || UI_DASH}</span>
              </div>
              <div className="bank-transaction-field">
                <span className="bank-transaction-field-label">{tr('project')}</span>
                <span className="bank-transaction-field-value">{getProjectName(transaction.project_id)}</span>
              </div>
              <div className="bank-transaction-field full">
                <span className="bank-transaction-field-label">{tr('bankTxCounterparty')}</span>
                <span className="bank-transaction-field-value">{transaction.counterparty_name || UI_DASH}</span>
              </div>
              <div className="bank-transaction-field full">
                <span className="bank-transaction-field-label">{tr('bankTxPurpose')}</span>
                <div className="bank-transaction-field-text">{transaction.purpose || UI_DASH}</div>
              </div>
              <div className="bank-transaction-field full">
                <span className="bank-transaction-field-label">{tr('bankTxReference')}</span>
                <span className="bank-transaction-field-value">{transaction.bank_reference || UI_DASH}</span>
              </div>
              {transaction.status === 'matched' ? (
                <div className="bank-transaction-field full">
                  <span className="bank-transaction-field-label">{tr('bankTxMatched')}</span>
                  <span className="bank-transaction-field-value">
                    {transaction.matched_type === 'owner_funds'
                      ? getOwnerFundsStatusLabel(transaction)
                      : transaction.matched_type === 'loan_movement'
                        ? getLoanMovementStatusLabel(transaction)
                        : getMatchedTypeLabel(transaction.matched_type)}
                  </span>
                </div>
              ) : null}
            </div>
          </section>

          <section className="card bank-transaction-detail-card">
            <div className="bank-transaction-action-grid">
              {actions.map((action) => (
                <button key={action.key} type="button" className={action.className} onClick={action.onClick}>
                  {action.label}
                </button>
              ))}
            </div>
          </section>
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
    const filteredAllocationCandidates = suggestions.filter((item) =>
      !query ||
      String(item.description || '').toLowerCase().includes(query) ||
      String(item.client_name || '').toLowerCase().includes(query) ||
      String(item.invoice_number || '').toLowerCase().includes(query) ||
      String(item.amount || '').includes(query)
    )
    const totals = getAllocationTotals()
    const hasInvalidAllocation = allocationLines.some((line) => parseMoneyInput(line.amount) <= 0)

    const renderLinkPanel = () => (
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

    const renderAllocationPanel = () => (
      <div className="bank-match-columns bank-match-link-panel">
        <div className="bank-match-panel">
          <div className="bank-match-panel-title">{tr('bankTxAllocationSelected')}</div>
          <div className="bank-allocation-summary">
            <div className="bank-allocation-summary-item">
              <span>{tr('bankTxAllocationPayment')}</span>
              <strong>{formatMoney(totals.total)} RSD</strong>
            </div>
            <div className="bank-allocation-summary-item">
              <span>{tr('bankTxAllocationAllocated')}</span>
              <strong>{formatMoney(totals.allocated)} RSD</strong>
            </div>
            <div className="bank-allocation-summary-item">
              <span>{tr('bankTxAllocationRemaining')}</span>
              <strong className={totals.remaining > 0 ? 'warning' : 'success'}>{formatMoney(totals.remaining)} RSD</strong>
            </div>
          </div>

          {totals.overAllocated > 0 && (
            <div className="alert alert-danger" style={{ marginBottom: '0.75rem' }}>
              {tr('bankTxAllocationOverAllocated')} {formatMoney(totals.overAllocated)} RSD
            </div>
          )}
          {totals.remaining > 0.009 && (
            <div className="alert alert-warning" style={{ marginBottom: '0.75rem' }}>
              {tr('bankTxAllocationRemainingHint')} {formatMoney(totals.remaining)} RSD
            </div>
          )}

          <div className="bank-match-list">
            {allocationLines.length === 0 ? (
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem', textAlign: 'center' }}>{tr('bankTxAllocationEmpty')}</p>
            ) : allocationLines.map((line) => (
              <div key={`selected-${line.income_id}`} className="bank-match-item selected">
                <div style={{ minWidth: 0 }}>
                  <div className="bank-match-item-title">
                    <span>{line.invoice_number}</span>
                    {line.date ? <span className="bank-match-item-subtle">{line.date}</span> : null}
                  </div>
                  {line.client_name ? <div style={{ fontSize: '0.85rem', fontWeight: 600, marginTop: '0.2rem' }}>{line.client_name}</div> : null}
                  {line.description ? <div className="bank-match-item-body">{line.description}</div> : null}
                  <div className="bank-match-item-body">
                    {tr('bankTxAvailableAmount')}: {formatMoney(line.available_amount)} RSD
                  </div>
                  {(line.project_name || line.project_code) ? (
                    <div className="bank-match-item-subtle" style={{ marginTop: '0.25rem' }}>
                      {tr('project')}: {line.project_name || UI_DASH}{line.project_code ? ` (${line.project_code})` : ''}
                    </div>
                  ) : null}
                </div>
                <div className="bank-allocation-line-actions">
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    className="form-input bank-allocation-amount-input"
                    value={line.amount}
                    onChange={(event) => updateAllocationAmount(line.income_id, event.target.value)}
                  />
                  <button className="btn btn-sm btn-secondary" type="button" onClick={() => removeAllocationLine(line.income_id)}>
                    {tr('delete')}
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={closeMatchModal}>{tr('cancel')}</button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={saveAllocation}
              disabled={allocationSaving || allocationLines.length === 0 || hasInvalidAllocation || totals.overAllocated > 0}
            >
              {allocationSaving ? tr('loading') : tr('save')}
            </button>
          </div>
        </div>

        <div className="bank-match-panel">
          <div className="bank-match-panel-title">{tr('bankTxAllocationCandidates')}</div>
          <SearchInput
            placeholder={tr('bankTxSearchInvoices')}
            value={allInvoiceSearch}
            onChange={setAllInvoiceSearch}
            style={{ width: '100%', marginBottom: '0.75rem' }}
          />
          <div className="bank-match-list">
            {filteredAllocationCandidates.length === 0 && (
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', textAlign: 'center' }}>{tr('bankTxNoInvoicesFound')}</p>
            )}
            {filteredAllocationCandidates.map(renderAllocationCandidateCard)}
          </div>
        </div>
      </div>
    )

    if (matchTx?.status === 'matched') {
      return renderAllocationPanel()
    }

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
            className={`bank-match-tab ${matchTab === 'allocate' ? 'active' : ''}`}
            onClick={() => setMatchTab('allocate')}
          >
            {tr('bankTxAllocateMode')}
          </button>
        </div>

        <div className="bank-match-content">
          {matchTab === 'allocate' ? renderAllocationPanel() : renderLinkPanel()}
        </div>
      </div>
    )
  }

  const renderOutgoingModalContent = () => {
    const isCashCategorySelected = expenseForm.category_id === CASH_CATEGORY_VALUE
    const categoryDefaultProjectId = getExpenseCategoryDefaultProjectId(expenseForm.category_id)
    const usesDefaultProject = expenseUsesDefaultProject(expenseForm.category_id)
    const effectiveProjectId = categoryDefaultProjectId || expenseForm.project_id || ''
    const selectedProjectId = effectiveProjectId ? parseInt(effectiveProjectId, 10) : null
    const filteredContracts = getContractsForProject(selectedProjectId)
    const suggested = suggestions.filter((item) => item.section === 'suggested')
    const allLinkCandidates = suggestions.filter((item) => item.section === 'all' || !item.section)
    const query = allInvoiceSearch.trim().toLowerCase()
    const filteredLinkCandidates = allLinkCandidates.filter((item) =>
      !query ||
      String(item.description || '').toLowerCase().includes(query) ||
      String(item.client_name || '').toLowerCase().includes(query) ||
      String(item.invoice_number || '').toLowerCase().includes(query) ||
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
          <div className="bank-match-panel-title">{tr('bankTxExistingExpenses')} / {tr('bankTxOpenObligations')}</div>
          <SearchInput
            placeholder={tr('bankTxSearchInvoices')}
            value={allInvoiceSearch}
            onChange={setAllInvoiceSearch}
            style={{ width: '100%', marginBottom: '0.75rem' }}
          />
          <div className="bank-match-list">
            {allLinkCandidates.length === 0 && (
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', textAlign: 'center' }}>{tr('bankTxNoInvoicesFound')}</p>
            )}
            {filteredLinkCandidates.length === 0 && allLinkCandidates.length > 0 && (
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', textAlign: 'center' }}>{tr('bankTxNoInvoicesFound')}</p>
            )}
            {filteredLinkCandidates.map(renderSuggestionCard)}
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

          {!isCashCategorySelected && !usesDefaultProject ? (
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

          {!isCashCategorySelected && filteredContracts.length > 0 ? (
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

  const selectedLoanCandidate = loanCandidates.find((loan) => String(loan.id) === String(loanForm.loan_id))
  const loanOperationAmount = Number(loanModal?.transaction?.amount || 0)
  const loanBalanceAfter = selectedLoanCandidate
    ? Number(selectedLoanCandidate.outstanding_amount || 0) + (loanModal?.isRepayment ? -loanOperationAmount : loanOperationAmount)
    : null
  const loanRepaymentExceeds = !!loanModal?.isRepayment && loanBalanceAfter != null && loanBalanceAfter < 0

  return (
    <>
      <PageHeader
        title={tr('bankTransactions')}
        subtitle={tr('bankTxOpenHint')}
        actions={(
          <>
          <YearFilterSelect
            value={year}
            availableYears={availableYears}
            onChange={(nextYear) => {
              setYear(nextYear)
              setMonth('')
            }}
          />
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
            <button className="btn btn-secondary" onClick={openAssignModal}>
              {tr('assignProject')} ({selectedIds.length})
            </button>
          )}
          </>
        )}
      />

      <div className="page-body" ref={pageBodyRef}>
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 40 }}>
                    <input type="checkbox" checked={displayed.length > 0 && selectedIds.length === displayed.length} onChange={toggleSelectAll} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIndicator active={sortCol === 'date'} asc={sortAsc} /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('counterparty_name')}>{tr('bankTxCounterparty')} <SortIndicator active={sortCol === 'counterparty_name'} asc={sortAsc} /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('purpose')}>{tr('bankTxPurpose')} / {tr('bankTxReference')} <SortIndicator active={sortCol === 'purpose'} asc={sortAsc} /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('project_id')}>{tr('project')} <SortIndicator active={sortCol === 'project_id'} asc={sortAsc} /></th>
                  <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')} <SortIndicator active={sortCol === 'amount'} asc={sortAsc} /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('status')}>{tr('status')} <SortIndicator active={sortCol === 'status'} asc={sortAsc} /></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={7}>{tr('loading')}</td></tr>
                ) : displayed.length === 0 ? (
                  <tr><td colSpan={7} style={{ color: 'var(--color-text-muted)' }}>{tr('noRecords')}</td></tr>
                ) : (
                  displayed.map((transaction) => (
                    <tr
                      key={transaction.id}
                      className="record-row"
                      onClick={() => openTransactionModal(transaction)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          openTransactionModal(transaction)
                        }
                      }}
                      tabIndex={0}
                    >
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(transaction.id)}
                          onChange={() => toggleSelect(transaction.id)}
                          onClick={(event) => event.stopPropagation()}
                        />
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}>{transaction.date}</td>
                      <td>{transaction.counterparty_name || UI_DASH}</td>
                      <td style={{ maxWidth: 320 }}>
                        <div className="bank-transaction-open">
                          <span className="bank-transaction-open-title">{transaction.purpose || UI_DASH}</span>
                          {transaction.bank_reference ? <span className="bank-transaction-open-meta">Ref: {transaction.bank_reference}</span> : null}
                        </div>
                      </td>
                      <td title={getProjectName(transaction.project_id)}>{getProjectName(transaction.project_id)}</td>
                      <td style={{ textAlign: 'right', fontWeight: 700, color: transaction.direction === 'in' ? 'var(--color-success)' : 'var(--color-text)' }}>
                        {transaction.direction === 'in' ? '+' : '-'}{Number(transaction.amount || 0).toLocaleString('sr-RS')} {transaction.currency || 'RSD'}
                      </td>
                      <td>
                        {transaction.status === 'matched' ? (
                          transaction.matched_type === 'income_allocation' ? (
                            <span className={`badge ${transaction.allocation_remaining > 0 ? 'badge-warning' : 'badge-success'}`}>
                              {transaction.allocation_remaining > 0 ? tr('bankTxAllocationPartialStatus') : tr('bankTxAllocationFullStatus')}
                              {transaction.allocation_count ? ` (${transaction.allocation_count})` : ''}
                              {transaction.allocation_remaining > 0 ? ` • ${tr('bankTxAllocationRemainingShort')} ${formatMoney(transaction.allocation_remaining)}` : ''}
                            </span>
                          ) : transaction.matched_type === 'owner_funds' ? (
                            <span className="badge badge-success">{getOwnerFundsStatusLabel(transaction)}</span>
                          ) : transaction.matched_type === 'loan_movement' ? (
                            <span className="badge badge-success">{getLoanMovementStatusLabel(transaction)}</span>
                          ) : (
                            <span className="badge badge-success">{tr('bankTxMatched')} ({getMatchedTypeLabel(transaction.matched_type)})</span>
                          )
                        ) : (
                          <span className="badge badge-warning">{tr('bankTxUnmatched')}</span>
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
          title={transactionModalMode === 'workflow' ? tr('bankTxMatchTitle') : tr('bankTxDetailsTitle')}
          className={matchTx ? 'bank-match-modal' : ''}
          maxWidth={matchTx ? '980px' : '700px'}
        >
        {matchTx && (
          <div className="bank-match-layout">
            {renderMatchSummary(matchTx)}

            {transactionModalMode === 'overview' ? (
              renderTransactionDetails(matchTx)
            ) : (
              <>
                <div className="bank-transaction-workflow-toolbar">
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => setTransactionModalMode('overview')}>
                    {tr('bankTxBackToDetails')}
                  </button>
                </div>
                {suggestLoading ? (
                  <p>{tr('loading')}</p>
                ) : matchTx.direction === 'out' ? (
                  renderOutgoingModalContent()
                ) : (
                  renderIncomingModalContent()
                )}
              </>
            )}

            {matchError ? <div style={{ color: 'var(--color-danger)' }}>{matchError}</div> : null}
          </div>
        )}
      </Modal>

      <Modal
        isOpen={!!loanModal}
        onClose={closeLoanModal}
        title={loanModal?.isRepayment
          ? (loanModal.loanType === 'borrowed' ? tr('loanRepayBorrowed') : tr('loanReceiveRepayment'))
          : (loanModal?.loanType === 'borrowed' ? tr('loanReceive') : tr('loanIssue'))}
        className="loan-operation-modal"
        maxWidth="760px"
      >
        {loanModal ? (
          <form className="loan-operation-form" onSubmit={handleSaveLoanMovement}>
            <div className="loan-operation-summary">
              <div>
                <span>{tr('amount')}</span>
                <strong>{formatMoney(loanOperationAmount)} {loanModal.transaction.currency || 'RSD'}</strong>
              </div>
              {selectedLoanCandidate ? (
                <>
                  <div>
                    <span>{tr('loanOutstanding')}</span>
                    <strong>{formatMoney(selectedLoanCandidate.outstanding_amount)} {selectedLoanCandidate.currency}</strong>
                  </div>
                  <div>
                    <span>{tr('loanAfterMovement')}</span>
                    <strong className={loanRepaymentExceeds ? 'negative' : ''}>{formatMoney(loanBalanceAfter)} {selectedLoanCandidate.currency}</strong>
                  </div>
                </>
              ) : null}
            </div>
            {loanModal.isRepayment ? (
              <div className="form-group">
                <label className="form-label">{tr('loanSelectOpen')}</label>
                <select className="form-input" value={loanForm.loan_id} onChange={(event) => setLoanForm({ ...loanForm, loan_id: event.target.value })} required>
                  <option value="">{UI_DASH}</option>
                  {loanCandidates.map((loan) => (
                    <option key={loan.id} value={loan.id}>
                      {loan.counterparty_name} / {loan.agreement_number || `#${loan.id}`} / {formatMoney(loan.outstanding_amount)} {loan.currency}
                    </option>
                  ))}
                </select>
                {loanCandidates.length === 0 ? <p className="bank-match-form-note">{tr('loanNoOpen')}</p> : null}
              </div>
            ) : (
              <>
              {loanCandidates.length > 0 ? (
                <div className="form-group">
                  <label className="form-label">{tr('loanSelectExisting')}</label>
                  <select className="form-input" value={loanForm.loan_id} onChange={(event) => setLoanForm({ ...loanForm, loan_id: event.target.value })}>
                    <option value="">{tr('loanNew')}</option>
                    {loanCandidates.map((loan) => (
                      <option key={loan.id} value={loan.id}>
                        {loan.counterparty_name} / {loan.agreement_number || `#${loan.id}`} / {formatMoney(loan.outstanding_amount)} {loan.currency}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}
              {!loanForm.loan_id ? <div className="loan-operation-fields">
                <div className="form-group">
                  <label className="form-label">{tr('counterpartyName')}</label>
                  <input className="form-input" value={loanForm.counterparty_name} onChange={(event) => setLoanForm({ ...loanForm, counterparty_name: event.target.value })} required />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('client')}</label>
                  <select
                    className="form-input"
                    value={loanForm.client_id}
                    onChange={(event) => {
                      const client = loanClients.find((item) => String(item.id) === event.target.value)
                      setLoanForm({ ...loanForm, client_id: event.target.value, counterparty_name: client?.name || loanForm.counterparty_name })
                    }}
                  >
                    <option value="">{UI_DASH}</option>
                    {loanClients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('loanAgreementNumber')}</label>
                  <input className="form-input" value={loanForm.agreement_number} onChange={(event) => setLoanForm({ ...loanForm, agreement_number: event.target.value })} />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('loanAgreementDate')}</label>
                  <DatePicker value={loanForm.agreement_date} onChange={(value) => setLoanForm({ ...loanForm, agreement_date: value })} />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('loanDueDate')}</label>
                  <DatePicker value={loanForm.due_date} onChange={(value) => setLoanForm({ ...loanForm, due_date: value })} />
                </div>
              </div> : null}
              </>
            )}
            <div className="form-group">
              <label className="form-label">{tr('note')}</label>
              <textarea className="form-input" value={loanForm.note} onChange={(event) => setLoanForm({ ...loanForm, note: event.target.value })} />
            </div>
            {loanRepaymentExceeds ? <div style={{ color: 'var(--color-danger)' }}>{tr('loanRepaymentExceeds')}</div> : null}
            {loanError ? <div style={{ color: 'var(--color-danger)' }}>{loanError}</div> : null}
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={closeLoanModal}>{tr('cancel')}</button>
              <button type="submit" className="btn btn-primary" disabled={loanSaving || loanRepaymentExceeds || (loanModal.isRepayment && !loanForm.loan_id)}>
                {loanSaving ? tr('loading') : tr('save')}
              </button>
            </div>
          </form>
        ) : null}
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
