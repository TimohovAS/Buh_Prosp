import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, getUser } from '../api'
import { getLang, tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import EntityDetailModal from '../components/EntityDetailModal'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import PageTabs from '../components/PageTabs'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'
import SelectionSummary from '../components/SelectionSummary'
import SortIndicator from '../components/SortIndicator'
import YearFilterSelect from '../components/YearFilterSelect'
import useAvailableYears from '../hooks/useAvailableYears'
import useCategoryProjectResolver from '../hooks/useCategoryProjectResolver'
import useListPageState from '../hooks/useListPageState'
import useProjectContractForm from '../hooks/useProjectContractForm'
import {
  filterContractsForProject,
  findUnassignedProject,
  getContractLabelById,
  getProjectName as resolveProjectName,
} from '../utils/entityLabels'
import { UI_DASH, formatMoney2 as fmtMoney, todayIso } from '../utils/formatters'
import { MONTHS } from '../utils/constants'
import { downloadTextFile } from '../utils/download'
import { amountSearchHay } from '../utils/searchUtils'
import { MODAL_CHAIN_CLOSE_EVENT, closeParentModalChain } from '../utils/modalNavigation'

const DUPLICATE_DISMISS_STORAGE_KEY = 'expenses_duplicate_dismissed_v1'

function getDuplicateGroupKey(group) {
  const itemIds = (group.items || [])
    .map((item) => item.id)
    .sort((left, right) => left - right)
    .join(',')
  return [
    group.reason,
    group.payment_reference || '',
    group.description || '',
    group.amount || 0,
    itemIds,
  ].join('|')
}

function loadDismissedDuplicateGroups() {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(DUPLICATE_DISMISS_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function csvEscape(value) {
  const text = value == null ? '' : String(value)
  if (text.includes('"') || text.includes(';') || text.includes('\n') || text.includes('\r')) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

function formatMoneyWithCurrency(value, currency = 'RSD') {
  return `${fmtMoney(value)} ${currency || 'RSD'}`
}

function makeExpenseLine(overrides = {}) {
  return {
    key: overrides.key || `expense-line-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    name: overrides.name || '',
    quantity: overrides.quantity ?? '',
    unit_price: overrides.unit_price ?? '',
    total_amount: overrides.total_amount ?? '',
    note: overrides.note || '',
  }
}

function toNumberOrZero(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

function hasExpenseLineUnitCalculation(line) {
  return line.quantity !== '' && line.quantity != null && line.unit_price !== '' && line.unit_price != null
}

function getExpenseLineCalculatedTotal(line) {
  if (!hasExpenseLineUnitCalculation(line)) return null
  const quantity = toNumberOrZero(line.quantity)
  const unitPrice = toNumberOrZero(line.unit_price)
  return Number((quantity * unitPrice).toFixed(2))
}

function getExpenseLineTotalInputValue(line) {
  const calculated = getExpenseLineCalculatedTotal(line)
  if (calculated == null) return line.total_amount
  return calculated.toFixed(2)
}

function normalizeExpenseLine(line) {
  const quantity = line.quantity === '' || line.quantity == null ? null : toNumberOrZero(line.quantity)
  const unitPrice = line.unit_price === '' || line.unit_price == null ? null : toNumberOrZero(line.unit_price)
  const calculatedTotal = getExpenseLineCalculatedTotal(line)
  const totalAmount =
    calculatedTotal == null
      ? line.total_amount === '' || line.total_amount == null
        ? 0
        : toNumberOrZero(line.total_amount)
      : calculatedTotal
  return {
    name: String(line.name || '').trim(),
    quantity,
    unit_price: unitPrice,
    total_amount: totalAmount,
    note: String(line.note || '').trim(),
  }
}

function isExpenseLineActive(line) {
  const normalized = normalizeExpenseLine(line)
  return Boolean(
    normalized.name ||
    normalized.quantity != null ||
    normalized.unit_price != null ||
    normalized.total_amount ||
    normalized.note
  )
}

function buildExpenseDescriptionFromLines(lines) {
  return lines
    .map((line) => normalizeExpenseLine(line).name)
    .filter(Boolean)
    .join('; ')
}

function getExpenseDisplayLines(expense) {
  if (expense?.items?.length) {
    return expense.items.map((line) => ({
      key: line.id || line.line_no,
      line_no: line.line_no,
      name: line.name || '',
      quantity: line.quantity,
      unit_price: line.unit_price,
      total_amount: line.total_amount,
      note: line.note || '',
    }))
  }
  if (!expense) return []
  return [
    {
      key: `fallback-${expense.id || 'expense'}`,
      line_no: 1,
      name: expense.description || expense.category || tr('expenses'),
      quantity: null,
      unit_price: null,
      total_amount: expense.amount || 0,
      note: expense.note || '',
    },
  ]
}

export default function Expenses() {
  const location = useLocation()
  const navigate = useNavigate()
  const isActivePage = location.pathname === '/expenses'
  const [items, setItems] = useState([])
  const [duplicateGroups, setDuplicateGroups] = useState([])
  const { year, setYear, availableYears, applyAvailableYears } = useAvailableYears({
    initialYear: new Date().getFullYear(),
  })
  const [month, setMonth] = useState('')
  const [loading, setLoading] = useState(true)
  const [selectedIds, setSelectedIds] = useState([])
  const { search, setSearch, sortCol, sortAsc, toggleSort } = useListPageState({
    initialSortCol: 'date',
    initialSortAsc: false,
  })
  const [modal, setModal] = useState(null)
  const [modalAssign, setModalAssign] = useState(false)
  const [detailModal, setDetailModal] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [detailEditMode, setDetailEditMode] = useState(false)
  const [detailReturnToPrevious, setDetailReturnToPrevious] = useState(false)
  const [detailReturnPath, setDetailReturnPath] = useState('')
  const [projects, setProjects] = useState([])
  const [contracts, setContracts] = useState([])
  const [categories, setCategories] = useState([])
  const [assignProjectId, setAssignProjectId] = useState('')
  const [pageError, setPageError] = useState('')
  const [mergeKeepId, setMergeKeepId] = useState(null)
  const [dismissedDuplicateGroups, setDismissedDuplicateGroups] = useState(() =>
    loadDismissedDuplicateGroups()
  )
  const [expenseLines, setExpenseLines] = useState([makeExpenseLine()])
  const [form, setForm] = useState({
    date: todayIso(),
    description: '',
    amount: '',
    category: '',
    category_id: '',
    project_id: '',
    contract_id: '',
    note: '',
  })

  useEffect(() => {
    const closeModalChain = (event) => {
      if (!detailReturnPath || event.detail?.returnPath !== detailReturnPath) return
      setDetailModal(null)
      setDetailEditMode(false)
      setDetailError('')
      setDetailLoading(false)
      setDetailReturnToPrevious(false)
      setDetailReturnPath('')
    }
    window.addEventListener(MODAL_CHAIN_CLOSE_EVENT, closeModalChain)
    return () => window.removeEventListener(MODAL_CHAIN_CLOSE_EVENT, closeModalChain)
  }, [detailReturnPath])

  const load = () => {
    setLoading(true)
    setPageError('')
    const params = {}
    if (year) params.year = year
    if (month && year) params.month = month
    return Promise.all([
      api.expenses.list(params),
      api.expenses.duplicates(params).catch(() => []),
      api.expenses.years(),
    ])
      .then(([expenseItems, groups, years]) => {
        setItems(expenseItems)
        setDuplicateGroups(groups)
        applyAvailableYears(years)
      })
      .catch((error) => {
        setItems([])
        setDuplicateGroups([])
        setPageError(error.message || tr('loadError'))
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, month, isActivePage])

  useEffect(() => {
    if (!isActivePage) return
    Promise.all([
      api.projects.list({ show_inactive: true }),
      api.categories.list({ category_type: 'expense' }),
      api.contracts.list(),
    ])
      .then(([projectList, categoryList, contractList]) => {
        setProjects(projectList)
        setCategories(categoryList)
        setContracts(contractList)
      })
      .catch((error) => setPageError(error.message || tr('loadError')))
  }, [isActivePage])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(DUPLICATE_DISMISS_STORAGE_KEY, JSON.stringify(dismissedDuplicateGroups))
  }, [dismissedDuplicateGroups])

  const lang = getLang()
  const currentUser = getUser()
  const isAdmin = currentUser?.role === 'admin'
  const unassignedProject = findUnassignedProject(projects)
  const {
    getCategoryById,
    getCategoryDefaultProjectId,
    usesCategoryProject,
    getCategoryLabel: getResolvedCategoryLabel,
  } = useCategoryProjectResolver(categories, lang)

  const getProjectName = (projectId) => resolveProjectName(projects, projectId, '')
  const getContractLabel = (contractId) => getContractLabelById(contracts, contractId, '')
  const getContractsForProject = (projectId) => filterContractsForProject(contracts, projectId)
  const { updateProject, updateContract } = useProjectContractForm({ contracts, setForm })

  const getCategoryLabel = (item) => {
    return getResolvedCategoryLabel(item, item.category || UI_DASH)
  }

  const activeExpenseLines = useMemo(
    () => expenseLines.filter(isExpenseLineActive).map(normalizeExpenseLine),
    [expenseLines]
  )
  const expenseLinesTotal = useMemo(
    () => activeExpenseLines.reduce((sum, line) => sum + toNumberOrZero(line.total_amount), 0),
    [activeExpenseLines]
  )
  const hasActiveExpenseLines = activeExpenseLines.length > 0

  const openExpenseSource = (item) => {
    const expenseDate = item?.date ? new Date(`${item.date}T12:00:00`) : null
    const expenseYear = expenseDate && !Number.isNaN(expenseDate.getTime()) ? expenseDate.getFullYear() : ''
    const expenseMonth =
      expenseDate && !Number.isNaN(expenseDate.getTime())
        ? String(expenseDate.getMonth() + 1).padStart(2, '0')
        : ''
    const reference = item?.bank_reference || ''
    const description = item?.description || ''

    if (item?.source === 'obligation') {
      const params = new URLSearchParams()
      if (expenseYear) params.set('year', String(expenseYear))
      if (reference || description) params.set('search', reference || description)
      navigate(`/payments?${params.toString()}`)
      return
    }

    if (item?.source === 'cash') {
      const params = new URLSearchParams()
      if (reference || description) params.set('search', reference || description)
      navigate(`/cash?${params.toString()}`)
      return
    }

    if (reference) {
      closeDetail()
      navigate('/bank', {
        state: {
          openBankReference: reference,
          openBankYear: expenseYear ? String(expenseYear) : '',
          openBankMonth: expenseMonth,
          openBankDirection: 'out',
          openBankStatus: 'all',
        },
      })
    }
  }

  const canOpenExpenseSource = (item) =>
    Boolean(item?.bank_reference || item?.source === 'cash' || item?.source === 'obligation')

  const openReceiptFromExpense = (receipt) => {
    if (!receipt?.id) return
    const returnPath = detailReturnPath || '/expenses'
    setDetailReturnPath(returnPath)
    navigate('/receipts', {
      state: {
        openReceiptId: receipt.id,
        modalReturn: true,
        modalReturnPath: returnPath,
      },
    })
  }

  const updateExpenseLine = (key, field, value) => {
    setExpenseLines((previous) =>
      previous.map((line) => (line.key === key ? { ...line, [field]: value } : line))
    )
  }

  const addExpenseLine = () => {
    setExpenseLines((previous) => [...previous, makeExpenseLine()])
  }

  const removeExpenseLine = (key) => {
    setExpenseLines((previous) => {
      const next = previous.filter((line) => line.key !== key)
      return next.length ? next : [makeExpenseLine()]
    })
  }

  const hydrateExpenseLines = (expense) => {
    const lines = (expense?.items || []).map((line) =>
      makeExpenseLine({
        key: `expense-line-${line.id || line.line_no}`,
        name: line.name || '',
        quantity: line.quantity ?? '',
        unit_price: line.unit_price ?? '',
        total_amount: line.total_amount ?? '',
        note: line.note || '',
      })
    )
    setExpenseLines(lines.length ? lines : [makeExpenseLine()])
  }

  const toggleSelect = (id) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((value) => value !== id) : [...prev, id]))
  }

  const toggleSelectAll = () => {
    if (selectedIds.length >= filtered.length) setSelectedIds([])
    else setSelectedIds(filtered.map((item) => item.id))
  }

  const handleBulkAssign = async () => {
    if (selectedIds.length === 0) return
    const projectId =
      assignProjectId === '' || assignProjectId === '_none'
        ? unassignedProject
          ? unassignedProject.id
          : null
        : parseInt(assignProjectId, 10)
    try {
      await api.expenses.bulkAssignProject({ ids: selectedIds, project_id: projectId })
      setModalAssign(false)
      setAssignProjectId('')
      setSelectedIds([])
      load()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
      console.error(error)
    }
  }

  const handleAdminHardDelete = async (ids) => {
    if (!isAdmin || ids.length === 0) return
    if (!confirm(tr('confirmAdminHardDeleteExpenses').replace('{count}', ids.length))) return
    try {
      await api.expenses.adminHardDelete({ ids })
      setSelectedIds((previous) => previous.filter((id) => !ids.includes(id)))
      setDetailModal((previous) => (previous && ids.includes(previous.id) ? null : previous))
      setDetailEditMode((previous) => (detailModal && ids.includes(detailModal.id) ? false : previous))
      load()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
      console.error(error)
    }
  }

  const openAdd = () => {
    setExpenseLines([makeExpenseLine()])
    setForm({
      date: todayIso(),
      description: '',
      amount: '',
      category: '',
      category_id: '',
      project_id: unassignedProject ? String(unassignedProject.id) : '',
      contract_id: '',
      note: '',
    })
    setPageError('')
    setModal('add')
  }

  const hydrateExpenseForm = (item) => {
    hydrateExpenseLines(item)
    setForm({
      date: item.date,
      description: item.description || '',
      amount: item.amount,
      category: item.category || '',
      category_id: item.category_id ?? '',
      project_id: item.project_id ?? (unassignedProject ? String(unassignedProject.id) : ''),
      contract_id: item.contract_id ?? '',
      note: item.note || '',
    })
  }

  const buildExpensePayload = () => {
    const categoryValue = form.category?.trim() || null
    const categoryDefaultProjectId = getCategoryDefaultProjectId(form.category_id)
    const description = form.description.trim() || buildExpenseDescriptionFromLines(expenseLines)
    const payloadItems = activeExpenseLines.map((line) => ({
      name: line.name,
      quantity: line.quantity,
      unit_price: line.unit_price,
      total_amount: line.total_amount,
      note: line.note || null,
    }))
    return {
      date: form.date,
      description,
      amount: hasActiveExpenseLines ? expenseLinesTotal : parseFloat(form.amount) || 0,
      category: categoryValue,
      category_id: form.category_id ? parseInt(form.category_id, 10) : null,
      project_id: categoryDefaultProjectId
        ? parseInt(categoryDefaultProjectId, 10)
        : form.project_id
          ? parseInt(form.project_id, 10)
          : unassignedProject
            ? unassignedProject.id
            : null,
      contract_id: form.contract_id ? parseInt(form.contract_id, 10) : null,
      note: form.note || null,
      items: payloadItems,
    }
  }

  const openDetail = async (item) => {
    setDetailModal(item)
    setDetailEditMode(false)
    setDetailError('')
    setDetailLoading(true)
    try {
      const details = await api.expenses.get(item.id)
      setDetailModal(details)
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
      console.error(error)
    } finally {
      setDetailLoading(false)
    }
  }

  const resetDetail = () => {
    setDetailModal(null)
    setDetailEditMode(false)
    setDetailError('')
    setDetailLoading(false)
    setDetailReturnToPrevious(false)
    setDetailReturnPath('')
  }

  const closeDetail = () => {
    const shouldCloseParentChain = detailReturnToPrevious
    const returnPath = detailReturnPath
    resetDetail()
    if (shouldCloseParentChain) {
      closeParentModalChain(returnPath)
      if (returnPath) navigate(returnPath, { replace: true })
      else navigate(-1)
    }
  }

  const backFromExpenseDetail = () => {
    if (detailEditMode) {
      setDetailEditMode(false)
      setDetailError('')
      return
    }
    if (!detailReturnToPrevious) return
    resetDetail()
    navigate(-1)
  }

  useEffect(() => {
    const openExpenseId = Number(location.state?.openExpenseId)
    if (!isActivePage || !Number.isInteger(openExpenseId) || openExpenseId <= 0) return
    setDetailReturnToPrevious(Boolean(location.state?.modalReturn))
    setDetailReturnPath(location.state?.modalReturnPath || '')
    openDetail({ id: openExpenseId })
    navigate('/expenses', { replace: true, state: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActivePage, location.state?.openExpenseId])

  const openEditFromDetail = (item) => {
    hydrateExpenseForm(item)
    setDetailError('')
    setDetailEditMode(true)
  }

  const handleDeleteFromDetail = async (item) => {
    closeDetail()
    await handleDelete(item)
  }

  const updateCategory = (categoryId) => {
    const category = getCategoryById(categoryId)
    const defaultProjectId = getCategoryDefaultProjectId(categoryId)
    setForm((previous) => {
      const selectedContract = previous.contract_id
        ? contracts.find((contract) => String(contract.id) === String(previous.contract_id))
        : null
      const nextProjectId = defaultProjectId || previous.project_id
      const keepContract =
        selectedContract &&
        (!nextProjectId ||
          String(selectedContract.project_id) === String(nextProjectId) ||
          selectedContract.project_id == null)
      return {
        ...previous,
        category_id: categoryId,
        category: category ? category.name_ru : '',
        project_id: nextProjectId,
        contract_id: keepContract ? previous.contract_id : '',
      }
    })
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setPageError('')
    try {
      const payload = buildExpensePayload()
      if (modal === 'add') {
        await api.expenses.create(payload)
      } else {
        await api.expenses.update(modal.id, payload)
      }
      setModal(null)
      load()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
      console.error(error)
    }
  }

  const handleDetailSubmit = async (event) => {
    event.preventDefault()
    if (!detailModal) return
    setDetailError('')
    try {
      const updated = await api.expenses.update(detailModal.id, buildExpensePayload())
      const details = await api.expenses.get(updated.id)
      setDetailModal(details)
      setDetailEditMode(false)
      load()
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
      console.error(error)
    }
  }

  const handleDelete = async (item) => {
    if (item.source === 'cash') {
      setPageError(tr('cashManagedInRegister'))
      return
    }
    const isReversal = item.status === 'reversed' || !!item.reversal_of_id
    const confirmKey = isReversal ? 'confirmDeleteReversalExpense' : 'confirmReverseExpense'
    if (!confirm(tr(confirmKey))) return
    try {
      await api.expenses.delete(item.id)
      load()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
      console.error(error)
    }
  }

  const handleMergeGroup = async (group, keepId) => {
    const mergeIds = group.items.filter((item) => item.id !== keepId).map((item) => item.id)
    if (mergeIds.length === 0) return
    if (!confirm(tr('expenseMergeConfirm'))) return
    setMergeKeepId(keepId)
    setPageError('')
    try {
      await api.expenses.mergeDuplicates({ keep_id: keepId, merge_ids: mergeIds })
      await load()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
      console.error(error)
    } finally {
      setMergeKeepId(null)
    }
  }

  const handleDismissDuplicateGroup = (group) => {
    const groupKey = getDuplicateGroupKey(group)
    setDismissedDuplicateGroups((previous) =>
      previous.includes(groupKey) ? previous : [...previous, groupKey]
    )
  }

  const visibleDuplicateGroups = useMemo(
    () => duplicateGroups.filter((group) => !dismissedDuplicateGroups.includes(getDuplicateGroupKey(group))),
    [dismissedDuplicateGroups, duplicateGroups]
  )

  const filteredContracts = useMemo(() => {
    const effectiveProjectId = getCategoryDefaultProjectId(form.category_id) || form.project_id || ''
    const selectedProjectId = effectiveProjectId ? parseInt(effectiveProjectId, 10) : null
    return getContractsForProject(selectedProjectId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contracts, form.project_id, form.category_id, categories])
  const usesDefaultCategoryProject = useMemo(
    () => usesCategoryProject(form.category_id),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [categories, form.category_id]
  )

  const filtered = useMemo(() => {
    const normalizedSearch = (search || '').trim().toLowerCase()
    let rows = items
    if (normalizedSearch) {
      rows = items.filter(
        (item) =>
          (item.description || '').toLowerCase().includes(normalizedSearch) ||
          getCategoryLabel(item).toLowerCase().includes(normalizedSearch) ||
          amountSearchHay(item.amount).includes(normalizedSearch) ||
          getProjectName(item.project_id).toLowerCase().includes(normalizedSearch) ||
          getContractLabel(item.contract_id).toLowerCase().includes(normalizedSearch) ||
          String(item.bank_reference || '')
            .toLowerCase()
            .includes(normalizedSearch)
      )
    }
    return [...rows].sort((left, right) => {
      const leftValue =
        sortCol === 'project_id'
          ? getProjectName(left.project_id)
          : sortCol === 'contract_id'
            ? getContractLabel(left.contract_id)
            : sortCol === 'category'
              ? getCategoryLabel(left)
              : (left[sortCol] ?? '')
      const rightValue =
        sortCol === 'project_id'
          ? getProjectName(right.project_id)
          : sortCol === 'contract_id'
            ? getContractLabel(right.contract_id)
            : sortCol === 'category'
              ? getCategoryLabel(right)
              : (right[sortCol] ?? '')
      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, search, sortCol, sortAsc, contracts, projects, categories, lang])

  const total = filtered.reduce((sum, item) => sum + item.amount, 0)
  const selectedItems = useMemo(() => {
    if (selectedIds.length === 0) return []
    const selectedIdSet = new Set(selectedIds)
    return items.filter((item) => selectedIdSet.has(item.id))
  }, [items, selectedIds])
  const selectedTotal = useMemo(
    () => selectedItems.reduce((sum, item) => sum + Number(item.amount || 0), 0),
    [selectedItems]
  )

  const handleExportCsv = () => {
    const rows = [
      [
        tr('date'),
        tr('description'),
        tr('project'),
        tr('contract'),
        tr('category'),
        tr('amount'),
        tr('paymentRef'),
        tr('note'),
        tr('status'),
      ],
      ...filtered.map((item) => [
        item.date || '',
        item.description || '',
        getProjectName(item.project_id) || '',
        getContractLabel(item.contract_id) || '',
        getCategoryLabel(item) || '',
        Number(item.amount || 0).toFixed(2),
        item.bank_reference || '',
        item.note || '',
        item.status || '',
      ]),
      ['', '', '', '', tr('total'), total.toFixed(2), '', '', ''],
    ]

    const content = `\ufeff${rows.map((row) => row.map(csvEscape).join(';')).join('\n')}`
    const filename = `expenses${year ? `_${year}` : ''}${month ? `_${String(month).padStart(2, '0')}` : ''}.csv`
    downloadTextFile(content, filename, 'text/csv;charset=utf-8;')
  }

  const renderExpenseLinesEditor = () => (
    <div className="expense-lines-editor">
      <div className="expense-lines-editor-header">
        <span className="record-field-label">{tr('expensePositions')}</span>
        <button type="button" className="btn btn-secondary btn-sm" onClick={addExpenseLine}>
          {tr('addExpensePosition')}
        </button>
      </div>
      <div className="table-wrap table-wrap-scroll expense-lines-table-wrap">
        <table className="expense-lines-table expense-lines-edit-table">
          <thead>
            <tr>
              <th>#</th>
              <th>{tr('expenseLineName')}</th>
              <th>{tr('receiptQuantity')}</th>
              <th>{tr('receiptUnitPrice')}</th>
              <th>{tr('amount')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {expenseLines.map((line, index) => {
              const isLineTotalCalculated = hasExpenseLineUnitCalculation(line)
              return (
                <tr key={line.key}>
                  <td>{index + 1}</td>
                  <td>
                    <div className="expense-line-name-stack">
                      <input
                        type="text"
                        className="form-input expense-line-name-input"
                        value={line.name}
                        onChange={(event) => updateExpenseLine(line.key, 'name', event.target.value)}
                        placeholder={tr('expenseLineName')}
                      />
                      <input
                        type="text"
                        className="form-input expense-line-note-input"
                        value={line.note}
                        onChange={(event) => updateExpenseLine(line.key, 'note', event.target.value)}
                        placeholder={tr('note')}
                      />
                    </div>
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.001"
                      className="form-input expense-line-number-input"
                      value={line.quantity}
                      onChange={(event) => updateExpenseLine(line.key, 'quantity', event.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      className="form-input expense-line-number-input"
                      value={line.unit_price}
                      onChange={(event) => updateExpenseLine(line.key, 'unit_price', event.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      className="form-input expense-line-number-input"
                      value={getExpenseLineTotalInputValue(line)}
                      onChange={(event) => updateExpenseLine(line.key, 'total_amount', event.target.value)}
                      readOnly={isLineTotalCalculated}
                      title={isLineTotalCalculated ? tr('expenseLineTotalAuto') : ''}
                    />
                  </td>
                  <td className="expense-line-actions-cell">
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={() => removeExpenseLine(line.key)}
                      title={tr('removeExpensePosition')}
                    >
                      {tr('removeExpensePosition')}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={4}>{tr('expenseLinesTotal')}</td>
              <td>{formatMoneyWithCurrency(expenseLinesTotal, form.currency || 'RSD')}</td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )

  const renderExpenseLinesTable = (expense) => {
    const lines = getExpenseDisplayLines(expense)
    return (
      <div className="table-wrap table-wrap-scroll expense-lines-table-wrap">
        <table className="expense-lines-table">
          <thead>
            <tr>
              <th>#</th>
              <th>{tr('expenseLineName')}</th>
              <th>{tr('receiptQuantity')}</th>
              <th>{tr('receiptUnitPrice')}</th>
              <th>{tr('amount')}</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line, index) => (
              <tr key={line.key}>
                <td>{line.line_no || index + 1}</td>
                <td>
                  <div>{line.name || UI_DASH}</div>
                  {line.note ? <div className="record-cell-subtitle">{line.note}</div> : null}
                </td>
                <td>{line.quantity == null || line.quantity === '' ? UI_DASH : fmtMoney(line.quantity)}</td>
                <td>
                  {line.unit_price == null || line.unit_price === ''
                    ? UI_DASH
                    : formatMoneyWithCurrency(line.unit_price, expense.currency)}
                </td>
                <td>{formatMoneyWithCurrency(line.total_amount, expense.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <>
      <PageHeader
        title={tr('expenses')}
        actions={
          <>
            <div
              style={{
                alignSelf: 'center',
                fontWeight: 600,
                color: 'var(--color-danger)',
                marginRight: '0.5rem',
              }}
            >
              {tr('total')}: {total.toLocaleString('sr-RS')} RSD
            </div>
            <YearFilterSelect
              value={year}
              availableYears={availableYears}
              onChange={(nextYear) => {
                setYear(nextYear)
                if (nextYear === '') setMonth('')
              }}
            />
            <select
              className="form-input"
              style={{ width: 'auto' }}
              value={month}
              onChange={(event) => setMonth(event.target.value ? parseInt(event.target.value, 10) : '')}
              disabled={!year}
            >
              <option value="">{tr('allMonths')}</option>
              {MONTHS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
            <SearchInput
              placeholder={tr('search')}
              value={search}
              onChange={setSearch}
              style={{ width: 180 }}
            />
            <button
              className="btn btn-secondary"
              onClick={handleExportCsv}
              disabled={loading || filtered.length === 0}
            >
              {tr('download')} CSV
            </button>
            <button className="btn btn-primary" onClick={openAdd}>
              {tr('add')}
            </button>
          </>
        }
      />

      <PageTabs group="expenses" />

      <div className="page-body">
        {pageError && <div className="alert alert-danger">{pageError}</div>}

        {visibleDuplicateGroups.length > 0 && (
          <div className="card" style={{ marginBottom: '1rem', borderColor: 'var(--color-warning)' }}>
            <div style={{ padding: '1rem 1rem 0.5rem', fontWeight: 700 }}>{tr('expenseDuplicatesTitle')}</div>
            <div style={{ padding: '0 1rem 1rem', color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
              {tr('expenseDuplicatesHint')}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', padding: '0 1rem 1rem' }}>
              {visibleDuplicateGroups.map((group, index) => (
                <div
                  key={`${group.reason}-${group.payment_reference || group.description || index}`}
                  className="card"
                  style={{ padding: '0.75rem' }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      gap: '1rem',
                      flexWrap: 'wrap',
                      marginBottom: '0.5rem',
                    }}
                  >
                    <div style={{ fontWeight: 700 }}>
                      {group.reason === 'payment_reference'
                        ? tr('expenseDuplicateByPaymentRef')
                        : tr('expenseDuplicateByDescription')}
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                      <div style={{ color: 'var(--color-text-muted)' }}>
                        {tr('amount')}: {Number(group.amount || 0).toLocaleString('sr-RS')}
                      </div>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => handleDismissDuplicateGroup(group)}
                      >
                        {tr('skip')}
                      </button>
                    </div>
                  </div>
                  {group.payment_reference && (
                    <div
                      style={{
                        fontSize: '0.9rem',
                        color: 'var(--color-text-muted)',
                        marginBottom: '0.25rem',
                      }}
                    >
                      {tr('paymentRef')}: {group.payment_reference}
                    </div>
                  )}
                  {group.description && (
                    <div
                      style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}
                    >
                      {tr('description')}: {group.description}
                    </div>
                  )}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {group.items.map((item) => (
                      <div
                        key={item.id}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          gap: '1rem',
                          flexWrap: 'wrap',
                          alignItems: 'center',
                          borderTop: '1px solid rgba(255,255,255,0.06)',
                          paddingTop: '0.5rem',
                        }}
                      >
                        <div style={{ minWidth: 260, flex: 1 }}>
                          <div style={{ fontWeight: 600 }}>{item.description}</div>
                          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                            {item.date} {UI_DASH} {getProjectName(item.project_id) || tr('unassigned')}{' '}
                            {UI_DASH} {getCategoryLabel(item)}
                          </div>
                        </div>
                        <button
                          type="button"
                          className="btn btn-secondary"
                          disabled={mergeKeepId === item.id}
                          onClick={() => handleMergeGroup(group, item.id)}
                        >
                          {mergeKeepId === item.id ? tr('loading') : tr('expenseMergeKeepThis')}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="card">
          <div className="table-wrap">
            <table className="expenses-list-table">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>
                    <input
                      type="checkbox"
                      checked={filtered.length > 0 && selectedIds.length >= filtered.length}
                      onChange={toggleSelectAll}
                    />
                  </th>
                  <th className="col-date" style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>
                    {tr('date')} <SortIndicator active={sortCol === 'date'} asc={sortAsc} />
                  </th>
                  <th
                    className="col-description"
                    style={{ cursor: 'pointer' }}
                    onClick={() => toggleSort('description')}
                  >
                    {tr('description')} <SortIndicator active={sortCol === 'description'} asc={sortAsc} />
                  </th>
                  <th
                    className="col-project"
                    style={{ cursor: 'pointer' }}
                    onClick={() => toggleSort('project_id')}
                  >
                    {tr('project')} <SortIndicator active={sortCol === 'project_id'} asc={sortAsc} />
                  </th>
                  <th
                    className="col-category"
                    style={{ cursor: 'pointer' }}
                    onClick={() => toggleSort('category')}
                  >
                    {tr('category')} <SortIndicator active={sortCol === 'category'} asc={sortAsc} />
                  </th>
                  <th
                    className="col-amount"
                    style={{ cursor: 'pointer' }}
                    onClick={() => toggleSort('amount')}
                  >
                    {tr('amount')} <SortIndicator active={sortCol === 'amount'} asc={sortAsc} />
                  </th>
                  <th className="col-payment">{tr('paymentRef')}</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={7}>{tr('loading')}</td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ color: 'var(--color-text-muted)' }}>
                      {tr('noRecords')}
                    </td>
                  </tr>
                ) : (
                  filtered.map((item) => (
                    <tr
                      key={item.id}
                      className={`record-row ${selectedIds.includes(item.id) ? 'record-row-selected' : ''} ${item.status === 'reversed' || item.reversal_of_id ? 'row-reversal' : ''}`.trim()}
                      onClick={() => openDetail(item)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          openDetail(item)
                        }
                      }}
                      tabIndex={0}
                    >
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(item.id)}
                          onChange={() => toggleSelect(item.id)}
                          onClick={(event) => event.stopPropagation()}
                        />
                      </td>
                      <td className="date-cell">{item.date}</td>
                      <td className="col-description">
                        <span className="record-cell-ellipsis" title={item.description || ''}>
                          {item.description || UI_DASH}
                        </span>
                      </td>
                      <td
                        className="col-project"
                        title={[getProjectName(item.project_id), getContractLabel(item.contract_id)]
                          .filter(Boolean)
                          .join(' • ')}
                      >
                        {item.project_id ? (
                          <>
                            <span
                              className="record-cell-ellipsis"
                              title={projects.find((project) => project.id === item.project_id)?.code || ''}
                            >
                              {getProjectName(item.project_id) || UI_DASH}
                            </span>
                            {item.contract_id && (
                              <span className="record-cell-subtitle">
                                {getContractLabel(item.contract_id)}
                              </span>
                            )}
                          </>
                        ) : (
                          UI_DASH
                        )}
                      </td>
                      <td className="col-category">
                        <span className="record-cell-ellipsis">{getCategoryLabel(item)}</span>
                      </td>
                      <td className="col-amount">{item.amount.toLocaleString('sr-RS')}</td>
                      <td
                        className="col-payment"
                        title={
                          item.bank_reference ||
                          item.note ||
                          (item.source === 'cash' ? tr('cashRegister') : '') ||
                          ''
                        }
                      >
                        <span className="record-cell-ellipsis">
                          {item.bank_reference ||
                            item.note ||
                            (item.source === 'cash' ? tr('cashRegister') : UI_DASH)}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <SelectionSummary
        count={selectedItems.length}
        items={[{ label: tr('selectedAmount'), value: `${fmtMoney(selectedTotal)} RSD` }]}
        actions={
          <>
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => {
                setAssignProjectId(unassignedProject ? String(unassignedProject.id) : '')
                setModalAssign(true)
              }}
            >
              {tr('assignProject')}
            </button>
            {isAdmin ? (
              <button
                type="button"
                className="btn btn-sm btn-danger"
                onClick={() => handleAdminHardDelete(selectedIds)}
              >
                {tr('adminHardDeleteSelected')}
              </button>
            ) : null}
          </>
        }
        onClear={() => setSelectedIds([])}
      />

      <EntityDetailModal
        isOpen={!!detailModal || detailLoading || !!detailError}
        onClose={closeDetail}
        onBack={detailEditMode || detailReturnToPrevious ? backFromExpenseDetail : undefined}
        backLabel={tr('back')}
        title={detailModal ? `${tr('expenses')} ${UI_DASH} #${detailModal.id}` : tr('expenses')}
        maxWidth="1560px"
        className="expense-detail-modal"
        details={
          detailLoading && !detailModal ? (
            <div>{tr('loading')}</div>
          ) : detailError && !detailModal ? (
            <div className="alert alert-danger">{detailError}</div>
          ) : detailModal && detailEditMode ? (
            <div className="expense-summary-grid expense-summary-grid-compact">
              <div className="record-field">
                <span className="record-field-label">{tr('status')}</span>
                <span className="record-field-value">{detailModal.status || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('source')}</span>
                <span className="record-field-value">{detailModal.source || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('paymentRef')}</span>
                <span className="record-field-value">{detailModal.bank_reference || UI_DASH}</span>
              </div>
            </div>
          ) : detailModal ? (
            <div className="expense-summary-grid">
              <div className="record-field">
                <span className="record-field-label">{tr('date')}</span>
                <span className="record-field-value">{detailModal.date || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('amount')}</span>
                <span className="record-field-value">
                  {formatMoneyWithCurrency(detailModal.amount, detailModal.currency)}
                </span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('status')}</span>
                <span className="record-field-value">{detailModal.status || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('project')}</span>
                <span className="record-field-value">
                  {getProjectName(detailModal.project_id) || UI_DASH}
                </span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('category')}</span>
                <span className="record-field-value">{getCategoryLabel(detailModal)}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('source')}</span>
                <span className="record-field-value">{detailModal.source || UI_DASH}</span>
              </div>
              <div className="record-field full">
                <span className="record-field-label">{tr('contract')}</span>
                <span className="record-field-value">
                  {detailModal.contract_id ? getContractLabel(detailModal.contract_id) : UI_DASH}
                </span>
              </div>
              <div className="record-field full">
                <span className="record-field-label">{tr('description')}</span>
                <div className="record-field-text">{detailModal.description || UI_DASH}</div>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('paymentRef')}</span>
                <span className="record-field-value">{detailModal.bank_reference || UI_DASH}</span>
              </div>
              <div className="record-field full">
                <span className="record-field-label">{tr('note')}</span>
                <div className="record-field-text">{detailModal.note || UI_DASH}</div>
              </div>
            </div>
          ) : null
        }
        actions={
          detailModal ? (
            <div className="expense-side-card">
              {detailError ? <div className="alert alert-danger">{detailError}</div> : null}
              <div className="record-actions-grid">
                {detailEditMode ? (
                  <>
                    <button type="submit" form="expense-detail-edit-form" className="btn btn-primary">
                      {tr('save')}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => {
                        hydrateExpenseForm(detailModal)
                        setDetailEditMode(false)
                        setDetailError('')
                      }}
                    >
                      {tr('cancel')}
                    </button>
                  </>
                ) : (
                  <>
                    {canOpenExpenseSource(detailModal) ? (
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => openExpenseSource(detailModal)}
                      >
                        {tr('openSource')}
                      </button>
                    ) : null}
                    {detailModal.receipt ? (
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => openReceiptFromExpense(detailModal.receipt)}
                      >
                        {tr('openReceipt')}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={detailModal.status === 'reversed' || !!detailModal.reversal_of_id}
                      onClick={() => openEditFromDetail(detailModal)}
                    >
                      {tr('edit')}
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={() => handleDeleteFromDetail(detailModal)}
                      disabled={detailModal.source === 'cash'}
                      title={detailModal.source === 'cash' ? tr('cashManagedInRegister') : ''}
                    >
                      {tr('delete')}
                    </button>
                    {isAdmin ? (
                      <button
                        type="button"
                        className="btn btn-danger"
                        onClick={() => handleAdminHardDelete([detailModal.id])}
                      >
                        {tr('adminHardDeleteExpense')}
                      </button>
                    ) : null}
                  </>
                )}
              </div>
              {detailModal.receipt ? (
                <div className="expense-linked-card expense-linked-documents">
                  <span className="record-field-label">{tr('linkedReceipt')}</span>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => openReceiptFromExpense(detailModal.receipt)}
                  >
                    {tr('openReceipt')}
                  </button>
                </div>
              ) : null}
            </div>
          ) : null
        }
      >
        {detailModal ? (
          <>
            <div className="record-detail-card expense-lines-card">
              <div className="receipt-items-header">
                <span className="record-field-label">{tr('expensePositions')}</span>
                {detailEditMode ? <span className="record-field-text">{tr('expenseEditHint')}</span> : null}
              </div>
              {detailEditMode ? (
                <form
                  id="expense-detail-edit-form"
                  onSubmit={handleDetailSubmit}
                  className="expense-edit-form"
                >
                  <div className="expense-form-grid">
                    <div className="form-group">
                      <label className="form-label">{tr('date')}</label>
                      <DatePicker
                        value={form.date}
                        onChange={(value) => setForm({ ...form, date: value })}
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{tr('description')}</label>
                      <input
                        type="text"
                        className="form-input"
                        value={form.description}
                        onChange={(event) => setForm({ ...form, description: event.target.value })}
                        placeholder={
                          buildExpenseDescriptionFromLines(expenseLines) || tr('expensePurposePlaceholder')
                        }
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{tr('category')}</label>
                      <select
                        className="form-input"
                        value={form.category_id}
                        onChange={(event) => updateCategory(event.target.value)}
                      >
                        <option value="">{`${UI_DASH} ${tr('allCategories')} ${UI_DASH}`}</option>
                        {categories.map((category) => (
                          <option key={category.id} value={category.id}>
                            {lang === 'ru' ? category.name_ru : category.name_sr}
                          </option>
                        ))}
                      </select>
                    </div>
                    {!usesDefaultCategoryProject ? (
                      <div className="form-group">
                        <label className="form-label">{tr('project')}</label>
                        <ProjectSelect
                          projects={projects}
                          value={form.project_id}
                          onChange={updateProject}
                          required
                        />
                      </div>
                    ) : null}
                    {filteredContracts.length > 0 ? (
                      <div className="form-group">
                        <label className="form-label">{tr('contract')}</label>
                        <select
                          className="form-input"
                          value={form.contract_id}
                          onChange={(event) => updateContract(event.target.value)}
                        >
                          <option value="">{`${UI_DASH} ${tr('withoutContract')} ${UI_DASH}`}</option>
                          {filteredContracts.map((contract) => (
                            <option key={contract.id} value={contract.id}>
                              {getContractLabel(contract.id)}
                            </option>
                          ))}
                        </select>
                      </div>
                    ) : null}
                    <div className="form-group">
                      <label className="form-label">{tr('amount')}</label>
                      <input
                        type="number"
                        step="0.01"
                        className="form-input"
                        value={hasActiveExpenseLines ? expenseLinesTotal.toFixed(2) : form.amount}
                        onChange={(event) => setForm({ ...form, amount: event.target.value })}
                        readOnly={hasActiveExpenseLines}
                        required
                      />
                    </div>
                    <div className="form-group expense-form-grid-wide">
                      <label className="form-label">{tr('note')}</label>
                      <input
                        type="text"
                        className="form-input"
                        value={form.note}
                        onChange={(event) => setForm({ ...form, note: event.target.value })}
                      />
                    </div>
                  </div>
                  {renderExpenseLinesEditor()}
                </form>
              ) : (
                renderExpenseLinesTable(detailModal)
              )}
            </div>
          </>
        ) : null}
      </EntityDetailModal>

      <Modal
        isOpen={!!modal}
        onClose={() => setModal(null)}
        title={`${modal === 'add' ? tr('add') : tr('edit')} ${UI_DASH} ${tr('expenses')}`}
        maxWidth="1100px"
      >
        {modal ? (
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
              <label className="form-label">{tr('description')}</label>
              <input
                type="text"
                className="form-input"
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
                placeholder={
                  buildExpenseDescriptionFromLines(expenseLines) || tr('expensePurposePlaceholder')
                }
              />
            </div>
            <div className="form-group">
              <label className="form-label">{tr('category')}</label>
              <select
                className="form-input"
                value={form.category_id}
                onChange={(event) => updateCategory(event.target.value)}
              >
                <option value="">{`${UI_DASH} ${tr('allCategories')} ${UI_DASH}`}</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {lang === 'ru' ? category.name_ru : category.name_sr}
                  </option>
                ))}
              </select>
            </div>
            {!usesDefaultCategoryProject ? (
              <div className="form-group">
                <label className="form-label">{tr('project')}</label>
                <ProjectSelect
                  projects={projects}
                  value={form.project_id}
                  onChange={updateProject}
                  required
                />
              </div>
            ) : null}
            {filteredContracts.length > 0 ? (
              <div className="form-group">
                <label className="form-label">{tr('contract')}</label>
                <select
                  className="form-input"
                  value={form.contract_id}
                  onChange={(event) => updateContract(event.target.value)}
                >
                  <option value="">{`${UI_DASH} ${tr('withoutContract')} ${UI_DASH}`}</option>
                  {filteredContracts.map((contract) => (
                    <option key={contract.id} value={contract.id}>
                      {getContractLabel(contract.id)}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            <div className="form-group">
              <label className="form-label">{tr('amount')}</label>
              <input
                type="number"
                step="0.01"
                className="form-input"
                value={hasActiveExpenseLines ? expenseLinesTotal.toFixed(2) : form.amount}
                onChange={(event) => setForm({ ...form, amount: event.target.value })}
                readOnly={hasActiveExpenseLines}
                required
              />
            </div>
            {renderExpenseLinesEditor()}
            <div className="form-group">
              <label className="form-label">{tr('note')}</label>
              <input
                type="text"
                className="form-input"
                value={form.note}
                onChange={(event) => setForm({ ...form, note: event.target.value })}
              />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>
                {tr('cancel')}
              </button>
              <button type="submit" className="btn btn-primary">
                {tr('save')}
              </button>
            </div>
          </form>
        ) : null}
      </Modal>

      <Modal
        isOpen={modalAssign}
        onClose={() => {
          setModalAssign(false)
          setAssignProjectId('')
        }}
        title={tr('assignProject')}
        maxWidth="400px"
      >
        {modalAssign ? (
          <>
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
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setModalAssign(false)
                  setAssignProjectId('')
                }}
              >
                {tr('cancel')}
              </button>
              <button type="button" className="btn btn-primary" onClick={handleBulkAssign}>
                {tr('save')}
              </button>
            </div>
          </>
        ) : null}
      </Modal>
    </>
  )
}
