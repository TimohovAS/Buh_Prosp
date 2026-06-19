import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { getLang, tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import Modal from '../components/Modal'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import YearFilterSelect from '../components/YearFilterSelect'
import useAvailableYears from '../hooks/useAvailableYears'
import useCategoryProjectResolver from '../hooks/useCategoryProjectResolver'
import useProjectContractForm from '../hooks/useProjectContractForm'
import { buildContractLabel, filterContractsForProject, findUnassignedProject, getContractLabelById } from '../utils/entityLabels'
import { UI_DASH, formatInteger as fmtAmount, todayIso } from '../utils/formatters'
import { amountSearchHay } from '../utils/searchUtils'
import { MONTHS } from '../utils/constants'

function buildBankLabel(item) {
  const parts = [item.counterparty_name, item.purpose, item.bank_reference].filter(Boolean)
  return parts.join(` ${UI_DASH} `) || UI_DASH
}

function isSalaryCategory(category) {
  const sr = String(category?.name_sr || '').trim().toLowerCase()
  const ru = String(category?.name_ru || '').trim().toLowerCase()
  return sr === 'zarade' || sr.includes('zarad') || ru.includes('зарп')
}

const emptyWorkerPayoutForm = {
  worker_id: '',
  payout_type: 'regular',
  date: todayIso(),
  period_start: '',
  period_end: '',
  work_days: '1',
  trip_days: '1',
  lodging_nights: '',
  lodging_amount: '',
  advance_paid: '',
  cash_paid_amount: '',
  project_id: '',
  contract_id: '',
  category_id: '',
  description: '',
  note: '',
}

const toNumber = (value) => Number(value || 0)

export default function CashRegister() {
  const location = useLocation()
  const isActivePage = location.pathname === '/cash'
  const { currentYear, year, setYear, availableYears, applyAvailableYears } = useAvailableYears({ initialYear: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [pageError, setPageError] = useState('')
  const [month, setMonth] = useState('')
  const [search, setSearch] = useState('')
  const [sortCol, setSortCol] = useState('date')
  const [sortAsc, setSortAsc] = useState(false)
  const [summary, setSummary] = useState({ current_balance: 0, total_in: 0, total_out: 0, entries: [], available_withdrawals: [] })
  const [projects, setProjects] = useState([])
  const [contracts, setContracts] = useState([])
  const [categories, setCategories] = useState([])
  const [workers, setWorkers] = useState([])
  const [bankModalOpen, setBankModalOpen] = useState(false)
  const [expenseModal, setExpenseModal] = useState(null)
  const [workerPayoutModal, setWorkerPayoutModal] = useState(null)
  const [adjustmentModal, setAdjustmentModal] = useState(null)
  const [withdrawalModal, setWithdrawalModal] = useState(null)
  const [pendingWithdrawalModal, setPendingWithdrawalModal] = useState(null)
  const [pendingLinkModal, setPendingLinkModal] = useState(null)
  const [detailModal, setDetailModal] = useState(null)
  const [expenseForm, setExpenseForm] = useState({
    date: todayIso(),
    description: '',
    amount: '',
    category_id: '',
    project_id: '',
    contract_id: '',
    note: '',
  })
  const [adjustmentForm, setAdjustmentForm] = useState({
    date: todayIso(),
    direction: 'out',
    amount: '',
    description: '',
    note: '',
  })
  const [withdrawalForm, setWithdrawalForm] = useState({
    description: '',
    project_id: '',
    contract_id: '',
    note: '',
  })
  const [pendingWithdrawalForm, setPendingWithdrawalForm] = useState({
    date: todayIso(),
    amount: '',
    currency: 'RSD',
    description: '',
    note: '',
  })
  const [workerPayoutForm, setWorkerPayoutForm] = useState(emptyWorkerPayoutForm)

  const lang = getLang()
  const unassignedProject = findUnassignedProject(projects)
  const salaryProject = projects.find((project) => project.code === 'INT-SALARY') || null
  const {
    getCategoryById,
    getCategoryDefaultProjectId,
    getCategoryLabel: getResolvedCategoryLabel,
  } = useCategoryProjectResolver(categories, lang)
  const { updateProject: updateExpenseProjectBase, updateContract: updateExpenseContractBase } = useProjectContractForm({
    contracts,
    setForm: setExpenseForm,
  })
  const { updateProject: updateWithdrawalProjectBase, updateContract: updateWithdrawalContractBase } = useProjectContractForm({
    contracts,
    setForm: setWithdrawalForm,
  })
  const getProjectName = (projectId) => projects.find((project) => project.id === projectId)?.name || ''

  const loadData = () => {
    setLoading(true)
    setPageError('')
    const params = {}
    if (year) params.year = year
    if (year && month) params.month = month
    return Promise.all([
      api.cash.summary(params),
      api.cash.years(),
      api.projects.list({ show_archived: true }),
      api.categories.list({ category_type: 'expense' }),
      api.contracts.list({ limit: 500 }),
      api.workers.list({ active: true }),
    ])
      .then(([cashSummary, years, projectList, categoryList, contractList, workerList]) => {
        setSummary(cashSummary)
        applyAvailableYears(years)
        setProjects(projectList)
        setCategories(categoryList)
        setContracts(contractList)
        setWorkers(workerList)
      })
      .catch((error) => {
        setPageError(error.message || tr('loadError'))
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return

    const params = new URLSearchParams(location.search || '')
    const hasExplicitQuery = params.toString().length > 0
    if (hasExplicitQuery) {
      const nextYear = params.get('year')
      const nextMonth = params.get('month')
      const resolvedYear = nextYear ? Number(nextYear) : ''
      const resolvedMonth = nextMonth ? String(Number(nextMonth)) : ''
      const resolvedSearch = params.get('search') || ''
      if (year !== resolvedYear || month !== resolvedMonth || search !== resolvedSearch) {
        setYear(resolvedYear)
        setMonth(resolvedMonth)
        setSearch(resolvedSearch)
        return
      }
    }

    loadData()
  }, [year, month, search, isActivePage, location.search])

  const getCategoryLabel = (categoryId) => getResolvedCategoryLabel(categoryId, UI_DASH)
  const getForcedExpenseProjectId = (categoryId) => {
    const category = getCategoryById(categoryId)
    const defaultProjectId = category?.default_project_id ? String(category.default_project_id) : ''
    if (defaultProjectId) return defaultProjectId
    if (isSalaryCategory(category) && salaryProject) return String(salaryProject.id)
    return ''
  }

  const getEntryTypeLabel = (entry) => {
    if (entry.entry_type === 'withdrawal') return tr('cashEntryTypeWithdrawal')
    if (entry.entry_type === 'pending_withdrawal') return tr('cashEntryTypePendingWithdrawal')
    if (entry.entry_type === 'expense') return tr('cashEntryTypeExpense')
    return tr('cashEntryTypeAdjustment')
  }

  const getEntrySourceLabel = (entry) => {
    if (entry.bank_transaction_id) {
      return `${tr('cashSourceBank')}: ${entry.bank_reference || entry.counterparty_name || `#${entry.bank_transaction_id}`}`
    }
    if (entry.expense_id) {
      return `${tr('cashSourceExpense')}: #${entry.expense_id}`
    }
    return UI_DASH
  }

  const getContractsForProject = (projectId) => filterContractsForProject(contracts, projectId)

  const expenseContracts = useMemo(() => {
    const effectiveProjectId = getForcedExpenseProjectId(expenseForm.category_id) || expenseForm.project_id || ''
    const selectedProjectId = effectiveProjectId ? parseInt(effectiveProjectId, 10) : null
    return getContractsForProject(selectedProjectId)
  }, [contracts, expenseForm.project_id, expenseForm.category_id, categories, salaryProject])

  const selectedExpenseCategory = useMemo(
    () => getCategoryById(expenseForm.category_id),
    [categories, expenseForm.category_id]
  )
  const expenseUsesForcedProject = Boolean(getForcedExpenseProjectId(expenseForm.category_id))

  useEffect(() => {
    const forcedProjectId = getForcedExpenseProjectId(expenseForm.category_id)
    if (!forcedProjectId) return
    if (String(expenseForm.project_id || '') === forcedProjectId && !expenseForm.contract_id) return
    setExpenseForm((previous) => ({
      ...previous,
      project_id: forcedProjectId,
      contract_id: '',
    }))
  }, [expenseForm.category_id, expenseForm.project_id, expenseForm.contract_id, categories, salaryProject])

  const withdrawalContracts = useMemo(() => {
    const selectedProjectId = withdrawalForm.project_id ? parseInt(withdrawalForm.project_id, 10) : null
    return getContractsForProject(selectedProjectId)
  }, [contracts, withdrawalForm.project_id])

  const pendingWithdrawalTotal = useMemo(
    () => (summary.entries || [])
      .filter((entry) => entry.entry_type === 'pending_withdrawal')
      .reduce((total, entry) => total + Number(entry.amount || 0), 0),
    [summary.entries]
  )

  const pendingLinkCandidates = useMemo(() => {
    if (!pendingLinkModal?.entry) return []
    const entryAmount = Number(pendingLinkModal.entry.amount || 0)
    const entryCurrency = pendingLinkModal.entry.currency || 'RSD'
    return (summary.available_withdrawals || []).filter((transaction) => {
      const txAmount = Number(transaction.amount || 0)
      const txCurrency = transaction.currency || 'RSD'
      return Math.abs(txAmount - entryAmount) < 0.005 && txCurrency === entryCurrency
    })
  }, [pendingLinkModal, summary.available_withdrawals])

  const selectedWorker = useMemo(
    () => workers.find((worker) => Number(worker.id) === Number(workerPayoutForm.worker_id)) || null,
    [workers, workerPayoutForm.worker_id]
  )

  const workerPayoutCategoryId = workerPayoutForm.category_id || selectedWorker?.default_category_id || ''
  const workerPayoutProjectId = workerPayoutForm.project_id || selectedWorker?.default_project_id || getForcedExpenseProjectId(workerPayoutCategoryId) || ''
  const workerPayoutContracts = useMemo(() => {
    const selectedProjectId = workerPayoutProjectId ? parseInt(workerPayoutProjectId, 10) : null
    return getContractsForProject(selectedProjectId)
  }, [contracts, workerPayoutProjectId])

  const workerPayoutPreview = useMemo(() => {
    if (!selectedWorker) {
      return { gross: 0, cash: 0, remaining: 0, lodgingNights: 0, lodgingAmount: 0 }
    }
    const payoutType = workerPayoutForm.payout_type
    const workDays = toNumber(workerPayoutForm.work_days)
    const tripDays = toNumber(workerPayoutForm.trip_days)
    const regularDayRate = toNumber(selectedWorker.regular_day_rate)
    const monthlyRate = toNumber(selectedWorker.monthly_rate)
    const tripWorkDayRate = toNumber(selectedWorker.trip_work_day_rate) || regularDayRate
    const perDiemRate = toNumber(selectedWorker.trip_per_diem_rate)
    const foodRate = toNumber(selectedWorker.trip_food_rate)
    const advanceDayRate = toNumber(selectedWorker.trip_advance_day_rate)
    const lodgingNights = workerPayoutForm.lodging_nights !== ''
      ? toNumber(workerPayoutForm.lodging_nights)
      : Math.max(tripDays + Number(selectedWorker.lodging_nights_offset || 0), 0)
    const lodgingAmount = workerPayoutForm.lodging_amount !== ''
      ? toNumber(workerPayoutForm.lodging_amount)
      : lodgingNights * toNumber(selectedWorker.lodging_night_rate)
    const gross = payoutType === 'monthly'
      ? monthlyRate
      : payoutType === 'regular'
        ? workDays * regularDayRate
        : tripDays * (tripWorkDayRate + perDiemRate + foodRate) + lodgingAmount
    const defaultCash = payoutType === 'trip_advance'
      ? tripDays * advanceDayRate + lodgingAmount
      : payoutType === 'trip_final'
        ? Math.max(gross - toNumber(workerPayoutForm.advance_paid), 0)
        : gross
    const cash = workerPayoutForm.cash_paid_amount !== '' ? toNumber(workerPayoutForm.cash_paid_amount) : defaultCash
    const remaining = Math.max(gross - toNumber(workerPayoutForm.advance_paid) - cash, 0)
    return { gross, cash, remaining, lodgingNights, lodgingAmount }
  }, [selectedWorker, workerPayoutForm])

  const filteredEntries = useMemo(() => {
    const normalizedSearch = (search || '').trim().toLowerCase()
    let rows = summary.entries || []

    if (normalizedSearch) {
      rows = rows.filter((entry) => {
        const haystack = [
          entry.date,
          entry.description,
          entry.note,
          entry.bank_reference,
          entry.counterparty_name,
          entry.purpose,
          getEntryTypeLabel(entry),
          getEntrySourceLabel(entry),
          getProjectName(entry.project_id),
          entry.expense_id ? String(entry.expense_id) : '',
          entry.bank_transaction_id ? String(entry.bank_transaction_id) : '',
          amountSearchHay(entry.amount),
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
        return haystack.includes(normalizedSearch)
      })
    }

    return [...rows].sort((left, right) => {
      const leftIn = left.direction === 'in' ? Number(left.amount || 0) : 0
      const rightIn = right.direction === 'in' ? Number(right.amount || 0) : 0
      const leftOut = left.direction === 'out' ? Number(left.amount || 0) : 0
      const rightOut = right.direction === 'out' ? Number(right.amount || 0) : 0

      const leftValue = sortCol === 'entry_type'
        ? getEntryTypeLabel(left)
        : sortCol === 'source'
          ? getEntrySourceLabel(left)
          : sortCol === 'inflow'
            ? leftIn
            : sortCol === 'outflow'
              ? leftOut
              : sortCol === 'balance_after'
                ? Number(left.balance_after || 0)
                : sortCol === 'amount'
                  ? Number(left.amount || 0)
                  : sortCol === 'description'
                    ? `${left.description || ''} ${left.note || ''}`
                    : left[sortCol] ?? ''

      const rightValue = sortCol === 'entry_type'
        ? getEntryTypeLabel(right)
        : sortCol === 'source'
          ? getEntrySourceLabel(right)
          : sortCol === 'inflow'
            ? rightIn
            : sortCol === 'outflow'
              ? rightOut
              : sortCol === 'balance_after'
                ? Number(right.balance_after || 0)
                : sortCol === 'amount'
                  ? Number(right.amount || 0)
                  : sortCol === 'description'
                    ? `${right.description || ''} ${right.note || ''}`
                    : right[sortCol] ?? ''

      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
  }, [summary.entries, search, sortCol, sortAsc, projects, lang])

  const toggleSort = (column) => {
    if (sortCol === column) setSortAsc((value) => !value)
    else {
      setSortCol(column)
      setSortAsc(true)
    }
  }

  const openExpenseCreate = () => {
    setExpenseForm({
      date: todayIso(),
      description: '',
      amount: '',
      category_id: '',
      project_id: unassignedProject ? String(unassignedProject.id) : '',
      contract_id: '',
      note: '',
    })
    setExpenseModal({ entryId: null })
  }

  const openExpenseEdit = (entry) => {
    setExpenseForm({
      date: entry.date,
      description: entry.description || '',
      amount: entry.amount || '',
      category_id: entry.category_id ?? '',
      project_id: entry.project_id ?? (unassignedProject ? String(unassignedProject.id) : ''),
      contract_id: entry.contract_id ?? '',
      note: entry.note || '',
    })
    setExpenseModal({ entryId: entry.id })
  }

  const openAdjustmentCreate = () => {
    setAdjustmentForm({
      date: todayIso(),
      direction: summary.current_balance > 0 ? 'out' : 'in',
      amount: '',
      description: '',
      note: '',
    })
    setAdjustmentModal({ entryId: null })
  }

  const openAdjustmentEdit = (entry) => {
    setAdjustmentForm({
      date: entry.date,
      direction: entry.direction || 'out',
      amount: entry.amount || '',
      description: entry.description || '',
      note: entry.note || '',
    })
    setAdjustmentModal({ entryId: entry.id })
  }

  const openWithdrawalEdit = (entry) => {
    setWithdrawalForm({
      description: entry.description || '',
      project_id: entry.project_id ?? (unassignedProject ? String(unassignedProject.id) : ''),
      contract_id: entry.contract_id ?? '',
      note: entry.note || '',
    })
    setWithdrawalModal({ entryId: entry.id })
  }

  const openPendingWithdrawalCreate = () => {
    setPendingWithdrawalForm({
      date: todayIso(),
      amount: '',
      currency: 'RSD',
      description: tr('cashPendingWithdrawalDefaultDescription'),
      note: '',
    })
    setPendingWithdrawalModal({ entryId: null })
  }

  const openPendingWithdrawalEdit = (entry) => {
    setPendingWithdrawalForm({
      date: entry.date,
      amount: entry.amount || '',
      currency: entry.currency || 'RSD',
      description: entry.description || '',
      note: entry.note || '',
    })
    setPendingWithdrawalModal({ entryId: entry.id })
  }

  const updateExpenseProject = (projectId) => updateExpenseProjectBase(projectId)

  const updateExpenseContract = (contractId) => {
    if (!contractId) {
      updateExpenseContractBase('')
      return
    }
    setExpenseForm((previous) => {
      const selectedContract = contracts.find((contract) => String(contract.id) === String(contractId))
      const nextProjectId = selectedContract?.project_id ? String(selectedContract.project_id) : previous.project_id
      return {
        ...previous,
        project_id: nextProjectId,
      }
    })
    updateExpenseContractBase(contractId)
  }

  const updateExpenseCategory = (categoryId) => {
    setExpenseForm((previous) => {
      const forcedProjectId = getForcedExpenseProjectId(categoryId)
      return {
        ...previous,
        category_id: categoryId,
        project_id: forcedProjectId || previous.project_id,
        contract_id: forcedProjectId ? '' : previous.contract_id,
      }
    })
  }

  const updateWithdrawalProject = (projectId) => updateWithdrawalProjectBase(projectId)
  const updateWithdrawalContract = (contractId) => updateWithdrawalContractBase(contractId)

  const handleTransferToCash = async (transaction) => {
    setSaving(true)
    setPageError('')
    try {
      await api.cash.createWithdrawal({ bank_transaction_id: transaction.id })
      setBankModalOpen(false)
      await loadData()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveExpense = async (event) => {
    event.preventDefault()
    setSaving(true)
    setPageError('')
    try {
      const forcedProjectId = getForcedExpenseProjectId(expenseForm.category_id)
      const payload = {
        date: expenseForm.date,
        description: expenseForm.description.trim(),
        amount: parseFloat(expenseForm.amount) || 0,
        category_id: expenseForm.category_id ? parseInt(expenseForm.category_id, 10) : null,
        project_id: forcedProjectId
          ? parseInt(forcedProjectId, 10)
          : (expenseForm.project_id ? parseInt(expenseForm.project_id, 10) : (unassignedProject ? unassignedProject.id : null)),
        contract_id: expenseForm.contract_id ? parseInt(expenseForm.contract_id, 10) : null,
        note: expenseForm.note?.trim() || null,
      }
      if (expenseModal?.entryId) {
        await api.cash.updateEntry(expenseModal.entryId, payload)
      } else {
        await api.cash.createExpense(payload)
      }
      setExpenseModal(null)
      await loadData()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const openWorkerPayoutCreate = () => {
    setWorkerPayoutForm({
      ...emptyWorkerPayoutForm,
      date: todayIso(),
      worker_id: '',
      category_id: '',
      project_id: '',
    })
    setWorkerPayoutModal(true)
  }

  const updateWorkerPayoutWorker = (workerId) => {
    const worker = workers.find((item) => Number(item.id) === Number(workerId))
    setWorkerPayoutForm((previous) => ({
      ...previous,
      worker_id: workerId,
      project_id: worker?.default_project_id ? String(worker.default_project_id) : '',
      category_id: worker?.default_category_id ? String(worker.default_category_id) : '',
      contract_id: '',
    }))
  }

  const updateWorkerPayoutProject = (projectId) => {
    setWorkerPayoutForm((previous) => ({
      ...previous,
      project_id: projectId,
      contract_id: '',
    }))
  }

  const handleSaveWorkerPayout = async (event) => {
    event.preventDefault()
    setSaving(true)
    setPageError('')
    try {
      const payload = {
        worker_id: parseInt(workerPayoutForm.worker_id, 10),
        payout_type: workerPayoutForm.payout_type,
        date: workerPayoutForm.date,
        period_start: workerPayoutForm.period_start || null,
        period_end: workerPayoutForm.period_end || null,
        work_days: toNumber(workerPayoutForm.work_days),
        trip_days: toNumber(workerPayoutForm.trip_days),
        lodging_nights: workerPayoutForm.lodging_nights === '' ? null : toNumber(workerPayoutForm.lodging_nights),
        lodging_amount: workerPayoutForm.lodging_amount === '' ? null : toNumber(workerPayoutForm.lodging_amount),
        advance_paid: toNumber(workerPayoutForm.advance_paid),
        cash_paid_amount: workerPayoutForm.cash_paid_amount === '' ? null : toNumber(workerPayoutForm.cash_paid_amount),
        category_id: workerPayoutCategoryId ? parseInt(workerPayoutCategoryId, 10) : null,
        project_id: workerPayoutProjectId ? parseInt(workerPayoutProjectId, 10) : (unassignedProject ? unassignedProject.id : null),
        contract_id: workerPayoutForm.contract_id ? parseInt(workerPayoutForm.contract_id, 10) : null,
        description: workerPayoutForm.description?.trim() || null,
        note: workerPayoutForm.note?.trim() || null,
      }
      await api.workers.createPayout(payload)
      setWorkerPayoutModal(null)
      await loadData()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveAdjustment = async (event) => {
    event.preventDefault()
    setSaving(true)
    setPageError('')
    try {
      const payload = {
        date: adjustmentForm.date,
        direction: adjustmentForm.direction,
        amount: parseFloat(adjustmentForm.amount) || 0,
        description: adjustmentForm.description.trim(),
        note: adjustmentForm.note?.trim() || null,
      }
      if (adjustmentModal?.entryId) {
        await api.cash.updateEntry(adjustmentModal.entryId, payload)
      } else {
        await api.cash.createAdjustment(payload)
      }
      setAdjustmentModal(null)
      await loadData()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveWithdrawal = async (event) => {
    event.preventDefault()
    if (!withdrawalModal?.entryId) return
    setSaving(true)
    setPageError('')
    try {
      await api.cash.updateEntry(withdrawalModal.entryId, {
        description: withdrawalForm.description.trim(),
        project_id: withdrawalForm.project_id ? parseInt(withdrawalForm.project_id, 10) : (unassignedProject ? unassignedProject.id : null),
        contract_id: withdrawalForm.contract_id ? parseInt(withdrawalForm.contract_id, 10) : null,
        note: withdrawalForm.note?.trim() || null,
      })
      setWithdrawalModal(null)
      await loadData()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const handleSavePendingWithdrawal = async (event) => {
    event.preventDefault()
    setSaving(true)
    setPageError('')
    try {
      const payload = {
        date: pendingWithdrawalForm.date,
        amount: parseFloat(pendingWithdrawalForm.amount) || 0,
        currency: pendingWithdrawalForm.currency || 'RSD',
        description: pendingWithdrawalForm.description.trim(),
        note: pendingWithdrawalForm.note?.trim() || null,
      }
      if (pendingWithdrawalModal?.entryId) {
        await api.cash.updateEntry(pendingWithdrawalModal.entryId, payload)
      } else {
        await api.cash.createPendingWithdrawal(payload)
      }
      setPendingWithdrawalModal(null)
      await loadData()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const handleLinkPendingWithdrawal = async (transaction) => {
    if (!pendingLinkModal?.entry) return
    setSaving(true)
    setPageError('')
    try {
      await api.cash.linkPendingWithdrawal(pendingLinkModal.entry.id, { bank_transaction_id: transaction.id })
      setPendingLinkModal(null)
      setDetailModal(null)
      await loadData()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const openEditEntry = (entry) => {
    if (entry.entry_type === 'expense') {
      openExpenseEdit(entry)
      return
    }
    if (entry.entry_type === 'adjustment') {
      openAdjustmentEdit(entry)
      return
    }
    if (entry.entry_type === 'pending_withdrawal') {
      openPendingWithdrawalEdit(entry)
      return
    }
    openWithdrawalEdit(entry)
  }

  const openDetail = (entry) => {
    setDetailModal(entry)
  }

  const openEditFromDetail = (entry) => {
    setDetailModal(null)
    openEditEntry(entry)
  }

  const handleDeleteCashEntry = async (entry) => {
    if (!entry || !['expense', 'pending_withdrawal'].includes(entry.entry_type)) return
    const confirmMessage = entry.entry_type === 'pending_withdrawal'
      ? tr('cashDeletePendingWithdrawalConfirm')
      : tr('cashDeleteExpenseConfirm')
    if (!confirm(confirmMessage)) return
    setSaving(true)
    setPageError('')
    try {
      await api.cash.deleteEntry(entry.id)
      setDetailModal(null)
      await loadData()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">{tr('cashRegisterTitle')}</h1>
          <p className="page-subtitle">{tr('cashRegisterHint')}</p>
        </div>
        <div className="page-header-actions">
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
          <SearchInput
            placeholder={tr('search')}
            value={search}
            onChange={setSearch}
            style={{ width: 220 }}
          />
          <button className="btn btn-secondary" onClick={() => setBankModalOpen(true)}>{tr('cashAddFromBank')}</button>
          <button className="btn btn-secondary" onClick={openPendingWithdrawalCreate}>{tr('cashAddPendingWithdrawal')}</button>
          <button className="btn btn-secondary" onClick={openAdjustmentCreate}>{tr('cashAddAdjustment')}</button>
          <button className="btn btn-secondary" onClick={openWorkerPayoutCreate}>Выплата работнику</button>
          <button className="btn btn-primary" onClick={openExpenseCreate}>{tr('cashAddExpense')}</button>
        </div>
      </div>

      <div className="page-body">
        {pageError ? (
          <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
            {pageError}
          </div>
        ) : null}

        {loading ? (
          <div>{tr('loading')}</div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
              <div className="card">
                <div className="card-title">{tr('cashCurrentBalance')}</div>
                <div style={{ fontSize: '1.75rem', fontWeight: 700 }}>{fmtAmount(summary.current_balance)} RSD</div>
                {pendingWithdrawalTotal > 0 ? (
                  <div style={{ marginTop: '0.35rem', color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
                    {tr('cashPendingWithdrawalTotal')}: +{fmtAmount(pendingWithdrawalTotal)} RSD
                  </div>
                ) : null}
              </div>
              <div className="card">
                <div className="card-title">{tr('cashTotalIn')}</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-success)' }}>+{fmtAmount(summary.total_in)} RSD</div>
              </div>
              <div className="card">
                <div className="card-title">{tr('cashTotalOut')}</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-danger)' }}>-{fmtAmount(summary.total_out)} RSD</div>
              </div>
            </div>

            <div className="card">
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
                <div className="card-title" style={{ margin: 0 }}>{tr('cashEntries')}</div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIndicator active={sortCol === 'date'} asc={sortAsc} /></th>
                      <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('entry_type')}>{tr('cashEntryType')} <SortIndicator active={sortCol === 'entry_type'} asc={sortAsc} /></th>
                      <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('description')}>{tr('description')} <SortIndicator active={sortCol === 'description'} asc={sortAsc} /></th>
                      <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('source')}>{tr('cashSource')} <SortIndicator active={sortCol === 'source'} asc={sortAsc} /></th>
                      <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('inflow')}>{tr('cashflowInflow')} <SortIndicator active={sortCol === 'inflow'} asc={sortAsc} /></th>
                      <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('outflow')}>{tr('cashflowOutflow')} <SortIndicator active={sortCol === 'outflow'} asc={sortAsc} /></th>
                      <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('balance_after')}>{tr('cashBalanceAfter')} <SortIndicator active={sortCol === 'balance_after'} asc={sortAsc} /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredEntries.length === 0 ? (
                      <tr>
                        <td colSpan={7} style={{ color: 'var(--color-text-muted)' }}>{tr('cashNoEntries')}</td>
                      </tr>
                    ) : filteredEntries.map((entry) => {
                      const typeLabel = getEntryTypeLabel(entry)
                      const sourceLabel = getEntrySourceLabel(entry)
                      return (
                        <tr
                          key={entry.id}
                          className="record-row"
                          onClick={() => openDetail(entry)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault()
                              openDetail(entry)
                            }
                          }}
                          tabIndex={0}
                        >
                          <td>{entry.date}</td>
                          <td>{typeLabel}</td>
                          <td>
                            <div className="record-cell-ellipsis">{entry.description}</div>
                            {entry.note ? (
                              <div style={{ color: 'var(--color-text-muted)', fontSize: '0.8rem', marginTop: '0.2rem' }}>{entry.note}</div>
                            ) : null}
                          </td>
                          <td>{sourceLabel}</td>
                          <td style={{ textAlign: 'right', color: 'var(--color-success)' }}>
                            {entry.direction === 'in' ? `${fmtAmount(entry.amount)} ${entry.currency || 'RSD'}` : UI_DASH}
                          </td>
                          <td style={{ textAlign: 'right', color: 'var(--color-danger)' }}>
                            {entry.direction === 'out' ? `${fmtAmount(entry.amount)} ${entry.currency || 'RSD'}` : UI_DASH}
                          </td>
                          <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmtAmount(entry.balance_after)} RSD</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>

      <Modal isOpen={!!detailModal} onClose={() => setDetailModal(null)} title={detailModal ? `${tr('cashEntryType')}: ${getEntryTypeLabel(detailModal)}` : tr('cashEntryType')} maxWidth="860px">
        {detailModal ? (
          <div className="record-detail-grid">
            <div className="record-detail-card">
              <div className="record-field-grid">
                <div className="record-field">
                  <span className="record-field-label">{tr('date')}</span>
                  <span className="record-field-value">{detailModal.date || UI_DASH}</span>
                </div>
                <div className="record-field">
                  <span className="record-field-label">{tr('cashEntryType')}</span>
                  <span className="record-field-value">{getEntryTypeLabel(detailModal)}</span>
                </div>
                <div className="record-field">
                  <span className="record-field-label">{tr('cashflowInflow')}</span>
                  <span className="record-field-value">{detailModal.direction === 'in' ? `${fmtAmount(detailModal.amount)} ${detailModal.currency || 'RSD'}` : UI_DASH}</span>
                </div>
                <div className="record-field">
                  <span className="record-field-label">{tr('cashflowOutflow')}</span>
                  <span className="record-field-value">{detailModal.direction === 'out' ? `${fmtAmount(detailModal.amount)} ${detailModal.currency || 'RSD'}` : UI_DASH}</span>
                </div>
                <div className="record-field">
                  <span className="record-field-label">{tr('cashBalanceAfter')}</span>
                  <span className="record-field-value">{fmtAmount(detailModal.balance_after)} RSD</span>
                </div>
                <div className="record-field">
                  <span className="record-field-label">{tr('project')}</span>
                  <span className="record-field-value">{getProjectName(detailModal.project_id) || UI_DASH}</span>
                </div>
                <div className="record-field full">
                  <span className="record-field-label">{tr('description')}</span>
                  <div className="record-field-text">{detailModal.description || UI_DASH}</div>
                </div>
                <div className="record-field full">
                  <span className="record-field-label">{tr('cashSource')}</span>
                  <div className="record-field-text">{getEntrySourceLabel(detailModal)}</div>
                </div>
                {detailModal.category_id ? (
                  <div className="record-field">
                    <span className="record-field-label">{tr('category')}</span>
                    <span className="record-field-value">{getCategoryLabel(detailModal.category_id)}</span>
                  </div>
                ) : null}
                {detailModal.contract_id ? (
                  <div className="record-field">
                    <span className="record-field-label">{tr('contracts')}</span>
                    <span className="record-field-value">{getContractLabelById(contracts, detailModal.contract_id, UI_DASH)}</span>
                  </div>
                ) : null}
                <div className="record-field full">
                  <span className="record-field-label">{tr('note')}</span>
                  <div className="record-field-text">{detailModal.note || UI_DASH}</div>
                </div>
              </div>
            </div>
            <div className="record-detail-card">
              <div className="record-actions-grid">
                <button type="button" className="btn btn-secondary" disabled={saving} onClick={() => openEditFromDetail(detailModal)}>
                  {tr('edit')}
                </button>
                {detailModal.entry_type === 'expense' ? (
                  <button type="button" className="btn btn-danger" disabled={saving} onClick={() => handleDeleteCashEntry(detailModal)}>
                    {tr('cashDeleteExpense')}
                  </button>
                ) : null}
                {detailModal.entry_type === 'pending_withdrawal' ? (
                  <>
                    <button type="button" className="btn btn-primary" disabled={saving} onClick={() => setPendingLinkModal({ entry: detailModal })}>
                      {tr('cashLinkPendingWithdrawal')}
                    </button>
                    <button type="button" className="btn btn-danger" disabled={saving} onClick={() => handleDeleteCashEntry(detailModal)}>
                      {tr('cashDeletePendingWithdrawal')}
                    </button>
                  </>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal isOpen={bankModalOpen} onClose={() => setBankModalOpen(false)} title={tr('cashAddFromBank')}>
        <div className="card" style={{ padding: '1rem' }}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('date')}</th>
                  <th>{tr('description')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {summary.available_withdrawals.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ color: 'var(--color-text-muted)' }}>{tr('cashNoAvailableWithdrawals')}</td>
                  </tr>
                ) : summary.available_withdrawals.map((transaction) => (
                  <tr key={transaction.id}>
                    <td>{transaction.date}</td>
                    <td>
                      <div>{buildBankLabel(transaction)}</div>
                      {transaction.project_id ? (
                        <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                          {projects.find((project) => project.id === transaction.project_id)?.name || UI_DASH}
                        </div>
                      ) : null}
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmtAmount(transaction.amount)} {transaction.currency || 'RSD'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn btn-sm btn-primary" disabled={saving} onClick={() => handleTransferToCash(transaction)}>
                        {tr('cashTransferToCash')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Modal>

      <Modal isOpen={!!pendingLinkModal} onClose={() => setPendingLinkModal(null)} title={tr('cashLinkPendingWithdrawalTitle')}>
        <div className="card" style={{ padding: '1rem' }}>
          {pendingLinkModal?.entry ? (
            <div style={{ color: 'var(--color-text-muted)', marginBottom: '0.75rem' }}>
              {pendingLinkModal.entry.date} · {fmtAmount(pendingLinkModal.entry.amount)} {pendingLinkModal.entry.currency || 'RSD'} · {pendingLinkModal.entry.description}
            </div>
          ) : null}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('date')}</th>
                  <th>{tr('description')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {pendingLinkCandidates.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ color: 'var(--color-text-muted)' }}>{tr('cashNoMatchingWithdrawals')}</td>
                  </tr>
                ) : pendingLinkCandidates.map((transaction) => (
                  <tr key={transaction.id}>
                    <td>{transaction.date}</td>
                    <td>{buildBankLabel(transaction)}</td>
                    <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmtAmount(transaction.amount)} {transaction.currency || 'RSD'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn btn-sm btn-primary" disabled={saving} onClick={() => handleLinkPendingWithdrawal(transaction)}>
                        {tr('cashLinkPendingWithdrawal')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Modal>

      <Modal isOpen={!!expenseModal} onClose={() => setExpenseModal(null)} title={expenseModal?.entryId ? tr('cashEditOperation') : tr('cashAddExpense')}>
        <form onSubmit={handleSaveExpense} className="card" style={{ padding: '1rem' }}>
          <div style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '0.75rem' }}>
            {tr('cashCreateExpenseHint')}
          </div>
          <div className="form-group">
            <label className="form-label">{tr('date')}</label>
            <DatePicker value={expenseForm.date} onChange={(value) => setExpenseForm((previous) => ({ ...previous, date: value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('description')}</label>
            <input className="form-input" value={expenseForm.description} onChange={(event) => setExpenseForm((previous) => ({ ...previous, description: event.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('amount')}</label>
            <input className="form-input" type="number" min="0" step="0.01" value={expenseForm.amount} onChange={(event) => setExpenseForm((previous) => ({ ...previous, amount: event.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('category')}</label>
            <select className="form-input" value={expenseForm.category_id} onChange={(event) => updateExpenseCategory(event.target.value)}>
              <option value="">{tr('allCategories')}</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>{getCategoryLabel(category.id)}</option>
              ))}
            </select>
          </div>
          {!expenseUsesForcedProject ? (
            <>
              <div className="form-group">
                <label className="form-label">{tr('project')}</label>
                <ProjectSelect projects={projects} value={expenseForm.project_id} onChange={updateExpenseProject} allowEmpty emptyLabel={UI_DASH} />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('contracts')}</label>
                <select className="form-input" value={expenseForm.contract_id} onChange={(event) => updateExpenseContract(event.target.value)}>
                  <option value="">{UI_DASH}</option>
                  {expenseContracts.map((contract) => (
                    <option key={contract.id} value={contract.id}>{buildContractLabel(contract)}</option>
                  ))}
                </select>
              </div>
            </>
          ) : null}
          {expenseUsesForcedProject && expenseContracts.length > 0 ? (
            <div className="form-group">
              <label className="form-label">{tr('contracts')}</label>
              <select className="form-input" value={expenseForm.contract_id} onChange={(event) => updateExpenseContract(event.target.value)}>
                <option value="">{UI_DASH}</option>
                {expenseContracts.map((contract) => (
                  <option key={contract.id} value={contract.id}>{buildContractLabel(contract)}</option>
                ))}
              </select>
            </div>
          ) : null}
          <div className="form-group">
            <label className="form-label">{tr('note')}</label>
            <input className="form-input" value={expenseForm.note} onChange={(event) => setExpenseForm((previous) => ({ ...previous, note: event.target.value }))} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setExpenseModal(null)}>{tr('cancel')}</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? tr('loading') : tr('save')}</button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={!!workerPayoutModal} onClose={() => setWorkerPayoutModal(null)} title="Выплата работнику">
        <form onSubmit={handleSaveWorkerPayout} className="card" style={{ padding: '1rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
            <div className="form-group">
              <label className="form-label">Работник</label>
              <select className="form-input" value={workerPayoutForm.worker_id} onChange={(event) => updateWorkerPayoutWorker(event.target.value)} required>
                <option value="">{UI_DASH}</option>
                {workers.map((worker) => (
                  <option key={worker.id} value={worker.id}>{worker.name}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Тип выплаты</label>
              <select className="form-input" value={workerPayoutForm.payout_type} onChange={(event) => setWorkerPayoutForm((previous) => ({ ...previous, payout_type: event.target.value }))}>
                <option value="regular">Выходы</option>
                <option value="monthly">Месяц</option>
                <option value="trip_advance">Аванс за командировку</option>
                <option value="trip_final">Окончательный расчет командировки</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">{tr('date')}</label>
              <DatePicker value={workerPayoutForm.date} onChange={(value) => setWorkerPayoutForm((previous) => ({ ...previous, date: value }))} required />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.75rem' }}>
            <div className="form-group">
              <label className="form-label">Период с</label>
              <DatePicker value={workerPayoutForm.period_start} onChange={(value) => setWorkerPayoutForm((previous) => ({ ...previous, period_start: value }))} />
            </div>
            <div className="form-group">
              <label className="form-label">Период по</label>
              <DatePicker value={workerPayoutForm.period_end} onChange={(value) => setWorkerPayoutForm((previous) => ({ ...previous, period_end: value }))} />
            </div>
            {workerPayoutForm.payout_type === 'regular' ? (
              <div className="form-group">
                <label className="form-label">Выходов</label>
                <input className="form-input" type="number" min="0" step="0.5" value={workerPayoutForm.work_days} onChange={(event) => setWorkerPayoutForm((previous) => ({ ...previous, work_days: event.target.value }))} />
              </div>
            ) : null}
            {workerPayoutForm.payout_type.startsWith('trip') ? (
              <>
                <div className="form-group">
                  <label className="form-label">Дней командировки</label>
                  <input className="form-input" type="number" min="0" step="0.5" value={workerPayoutForm.trip_days} onChange={(event) => setWorkerPayoutForm((previous) => ({ ...previous, trip_days: event.target.value }))} />
                </div>
                <div className="form-group">
                  <label className="form-label">Ночей</label>
                  <input className="form-input" type="number" min="0" step="0.5" placeholder={String(workerPayoutPreview.lodgingNights)} value={workerPayoutForm.lodging_nights} onChange={(event) => setWorkerPayoutForm((previous) => ({ ...previous, lodging_nights: event.target.value }))} />
                </div>
                <div className="form-group">
                  <label className="form-label">Гостиница</label>
                  <input className="form-input" type="number" min="0" step="0.01" placeholder={String(workerPayoutPreview.lodgingAmount)} value={workerPayoutForm.lodging_amount} onChange={(event) => setWorkerPayoutForm((previous) => ({ ...previous, lodging_amount: event.target.value }))} />
                </div>
              </>
            ) : null}
            {workerPayoutForm.payout_type === 'trip_final' ? (
              <div className="form-group">
                <label className="form-label">Аванс уже выдан</label>
                <input className="form-input" type="number" min="0" step="0.01" value={workerPayoutForm.advance_paid} onChange={(event) => setWorkerPayoutForm((previous) => ({ ...previous, advance_paid: event.target.value }))} />
              </div>
            ) : null}
            <div className="form-group">
              <label className="form-label">Выдать сейчас</label>
              <input className="form-input" type="number" min="0" step="0.01" placeholder={String(workerPayoutPreview.cash)} value={workerPayoutForm.cash_paid_amount} onChange={(event) => setWorkerPayoutForm((previous) => ({ ...previous, cash_paid_amount: event.target.value }))} />
            </div>
          </div>

          <div className="record-field-grid" style={{ marginBottom: '0.75rem' }}>
            <div className="record-field">
              <span className="record-field-label">Начислено</span>
              <span className="record-field-value">{fmtAmount(workerPayoutPreview.gross)} RSD</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">К выдаче</span>
              <span className="record-field-value">{fmtAmount(workerPayoutPreview.cash)} RSD</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">Остаток</span>
              <span className="record-field-value">{fmtAmount(workerPayoutPreview.remaining)} RSD</span>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
            <div className="form-group">
              <label className="form-label">{tr('category')}</label>
              <select className="form-input" value={workerPayoutCategoryId} onChange={(event) => setWorkerPayoutForm((previous) => ({ ...previous, category_id: event.target.value }))}>
                <option value="">{tr('allCategories')}</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>{getCategoryLabel(category.id)}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">{tr('project')}</label>
              <ProjectSelect projects={projects} value={workerPayoutProjectId} onChange={updateWorkerPayoutProject} allowEmpty emptyLabel={UI_DASH} />
            </div>
            <div className="form-group">
              <label className="form-label">{tr('contracts')}</label>
              <select className="form-input" value={workerPayoutForm.contract_id} onChange={(event) => setWorkerPayoutForm((previous) => ({ ...previous, contract_id: event.target.value }))}>
                <option value="">{UI_DASH}</option>
                {workerPayoutContracts.map((contract) => (
                  <option key={contract.id} value={contract.id}>{buildContractLabel(contract)}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">{tr('description')}</label>
            <input className="form-input" value={workerPayoutForm.description} onChange={(event) => setWorkerPayoutForm((previous) => ({ ...previous, description: event.target.value }))} placeholder={selectedWorker ? selectedWorker.name : ''} />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('note')}</label>
            <input className="form-input" value={workerPayoutForm.note} onChange={(event) => setWorkerPayoutForm((previous) => ({ ...previous, note: event.target.value }))} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setWorkerPayoutModal(null)}>{tr('cancel')}</button>
            <button type="submit" className="btn btn-primary" disabled={saving || !selectedWorker}>{saving ? tr('loading') : tr('save')}</button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={!!pendingWithdrawalModal} onClose={() => setPendingWithdrawalModal(null)} title={pendingWithdrawalModal?.entryId ? tr('cashEditOperation') : tr('cashAddPendingWithdrawal')}>
        <form onSubmit={handleSavePendingWithdrawal} className="card" style={{ padding: '1rem' }}>
          <div style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '0.75rem' }}>
            {tr('cashPendingWithdrawalHint')}
          </div>
          <div className="form-group">
            <label className="form-label">{tr('date')}</label>
            <DatePicker value={pendingWithdrawalForm.date} onChange={(value) => setPendingWithdrawalForm((previous) => ({ ...previous, date: value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('amount')}</label>
            <input className="form-input" type="number" min="0" step="0.01" value={pendingWithdrawalForm.amount} onChange={(event) => setPendingWithdrawalForm((previous) => ({ ...previous, amount: event.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('valuta')}</label>
            <input className="form-input" value={pendingWithdrawalForm.currency} onChange={(event) => setPendingWithdrawalForm((previous) => ({ ...previous, currency: event.target.value.toUpperCase() }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('description')}</label>
            <input className="form-input" value={pendingWithdrawalForm.description} onChange={(event) => setPendingWithdrawalForm((previous) => ({ ...previous, description: event.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('note')}</label>
            <input className="form-input" value={pendingWithdrawalForm.note} onChange={(event) => setPendingWithdrawalForm((previous) => ({ ...previous, note: event.target.value }))} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setPendingWithdrawalModal(null)}>{tr('cancel')}</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? tr('loading') : tr('save')}</button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={!!adjustmentModal} onClose={() => setAdjustmentModal(null)} title={adjustmentModal?.entryId ? tr('cashEditOperation') : tr('cashAddAdjustment')}>
        <form onSubmit={handleSaveAdjustment} className="card" style={{ padding: '1rem' }}>
          <div className="form-group">
            <label className="form-label">{tr('date')}</label>
            <DatePicker value={adjustmentForm.date} onChange={(value) => setAdjustmentForm((previous) => ({ ...previous, date: value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('cashDirection')}</label>
            <select className="form-input" value={adjustmentForm.direction} onChange={(event) => setAdjustmentForm((previous) => ({ ...previous, direction: event.target.value }))}>
              <option value="in">{tr('cashDirectionIn')}</option>
              <option value="out">{tr('cashDirectionOut')}</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">{tr('amount')}</label>
            <input className="form-input" type="number" min="0" step="0.01" value={adjustmentForm.amount} onChange={(event) => setAdjustmentForm((previous) => ({ ...previous, amount: event.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('description')}</label>
            <input className="form-input" value={adjustmentForm.description} onChange={(event) => setAdjustmentForm((previous) => ({ ...previous, description: event.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('note')}</label>
            <input className="form-input" value={adjustmentForm.note} onChange={(event) => setAdjustmentForm((previous) => ({ ...previous, note: event.target.value }))} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setAdjustmentModal(null)}>{tr('cancel')}</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? tr('loading') : tr('save')}</button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={!!withdrawalModal} onClose={() => setWithdrawalModal(null)} title={tr('cashEditOperation')}>
        <form onSubmit={handleSaveWithdrawal} className="card" style={{ padding: '1rem' }}>
          <div style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '0.75rem' }}>
            {tr('cashEditWithdrawalHint')}
          </div>
          <div className="form-group">
            <label className="form-label">{tr('description')}</label>
            <input className="form-input" value={withdrawalForm.description} onChange={(event) => setWithdrawalForm((previous) => ({ ...previous, description: event.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('project')}</label>
            <ProjectSelect projects={projects} value={withdrawalForm.project_id} onChange={updateWithdrawalProject} allowEmpty emptyLabel={UI_DASH} />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('contracts')}</label>
            <select className="form-input" value={withdrawalForm.contract_id} onChange={(event) => updateWithdrawalContract(event.target.value)}>
              <option value="">{UI_DASH}</option>
              {withdrawalContracts.map((contract) => (
                <option key={contract.id} value={contract.id}>{buildContractLabel(contract)}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">{tr('note')}</label>
            <input className="form-input" value={withdrawalForm.note} onChange={(event) => setWithdrawalForm((previous) => ({ ...previous, note: event.target.value }))} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setWithdrawalModal(null)}>{tr('cancel')}</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? tr('loading') : tr('save')}</button>
          </div>
        </form>
      </Modal>
    </>
  )
}
