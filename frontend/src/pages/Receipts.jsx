import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { getMonthNamesFull, tr } from '../i18n'
import EntityDetailModal from '../components/EntityDetailModal'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'
import SharedStatusBadge from '../components/StatusBadge'
import SortIndicator from '../components/SortIndicator'
import YearFilterSelect from '../components/YearFilterSelect'
import { buildContractLabel, filterContractsForProject, findUnassignedProject } from '../utils/entityLabels'
import { UI_DASH, formatDateTimeSr as fmtDateTime, formatMoney2 as fmtMoney } from '../utils/formatters'

function getReceiptStatusMeta(status) {
  switch (status) {
    case 'linked_expense':
      return {
        label: tr('receiptStatusLinkedExpense'),
        background: 'rgba(59,130,246,0.18)',
        color: '#93c5fd',
      }
    case 'waiting_bank':
      return { label: tr('receiptStatusWaitingBank'), background: 'rgba(245,158,11,0.18)', color: '#fbbf24' }
    case 'matched_bank':
      return { label: tr('receiptStatusMatchedBank'), background: 'rgba(34,197,94,0.18)', color: '#4ade80' }
    case 'cash_expense':
      return { label: tr('receiptStatusCashExpense'), background: 'rgba(20,184,166,0.18)', color: '#2dd4bf' }
    case 'error':
      return { label: tr('receiptStatusError'), background: 'rgba(239,68,68,0.18)', color: '#f87171' }
    default:
      return { label: tr('receiptStatusNew'), background: 'rgba(148,163,184,0.18)', color: '#cbd5e1' }
  }
}

function ReceiptStatusBadge({ status }) {
  const meta = getReceiptStatusMeta(status)
  return (
    <SharedStatusBadge
      tone="muted"
      style={{
        background: meta.background,
        color: meta.color,
        borderRadius: 999,
        padding: '0.25rem 0.55rem',
      }}
    >
      {meta.label}
    </SharedStatusBadge>
  )
}

function formatMoneyWithCurrency(value, currency = 'RSD') {
  return `${fmtMoney(value)} ${currency || 'RSD'}`
}

function getReceiptDateParts(receipt) {
  if (!receipt?.receipt_datetime) return null
  const parsed = new Date(receipt.receipt_datetime)
  if (Number.isNaN(parsed.getTime())) return null
  return {
    year: parsed.getFullYear(),
    month: parsed.getMonth() + 1,
  }
}

function normalizeSearchDigits(value) {
  return String(value || '').replace(/[^\d]/g, '')
}

export default function Receipts() {
  const location = useLocation()
  const navigate = useNavigate()
  const isActivePage = location.pathname === '/receipts'
  const videoRef = useRef(null)
  const scanTimerRef = useRef(null)
  const streamRef = useRef(null)

  const [receipts, setReceipts] = useState([])
  const [projects, setProjects] = useState([])
  const [categories, setCategories] = useState([])
  const [contracts, setContracts] = useState([])
  const [expenseYears, setExpenseYears] = useState([])
  const [loading, setLoading] = useState(true)
  const [pageError, setPageError] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [projectFilter, setProjectFilter] = useState('')
  const [search, setSearch] = useState('')
  const [sortCol, setSortCol] = useState('receipt_datetime')
  const [sortAsc, setSortAsc] = useState(false)

  const [importModalOpen, setImportModalOpen] = useState(false)
  const [importUrl, setImportUrl] = useState('')
  const [importing, setImporting] = useState(false)
  const [pastingClipboard, setPastingClipboard] = useState(false)
  const [scannerOpen, setScannerOpen] = useState(false)
  const [scanSupported, setScanSupported] = useState(false)
  const [scanError, setScanError] = useState('')

  const [detailReceipt, setDetailReceipt] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [detailAction, setDetailAction] = useState('')
  const [expenseCandidates, setExpenseCandidates] = useState([])
  const [expenseCandidatesLoading, setExpenseCandidatesLoading] = useState(false)
  const [expenseLinkMode, setExpenseLinkMode] = useState('candidates')
  const [periodExpenseYear, setPeriodExpenseYear] = useState(new Date().getFullYear())
  const [periodExpenseMonth, setPeriodExpenseMonth] = useState('')
  const [periodExpenseSearch, setPeriodExpenseSearch] = useState('')
  const [periodExpenses, setPeriodExpenses] = useState([])
  const [periodExpensesLoading, setPeriodExpensesLoading] = useState(false)
  const [createExpenseSaving, setCreateExpenseSaving] = useState(false)
  const [unlinkingExpense, setUnlinkingExpense] = useState(false)
  const [updatingCashPayment, setUpdatingCashPayment] = useState(false)
  const [deletingReceipt, setDeletingReceipt] = useState(false)
  const [createForm, setCreateForm] = useState({
    project_id: '',
    category_id: '',
    contract_id: '',
    description: '',
    note: '',
    payment_mode: 'auto',
  })

  const scannerRequiresHttps =
    typeof window !== 'undefined' && !window.isSecureContext && window.location.hostname !== 'localhost'
  const canUseScanner = scanSupported && !scannerRequiresHttps
  const monthNames = getMonthNamesFull()

  const statusOptions = useMemo(
    () => [
      { value: 'all', label: tr('receiptStatusAll') },
      { value: 'new', label: tr('receiptStatusNew') },
      { value: 'linked_expense', label: tr('receiptStatusLinkedExpense') },
      { value: 'waiting_bank', label: tr('receiptStatusWaitingBank') },
      { value: 'matched_bank', label: tr('receiptStatusMatchedBank') },
      { value: 'cash_expense', label: tr('receiptStatusCashExpense') },
      { value: 'error', label: tr('receiptStatusError') },
    ],
    []
  )

  const filteredContracts = useMemo(() => {
    return filterContractsForProject(contracts, createForm.project_id)
  }, [contracts, createForm.project_id])

  const unassignedProject = useMemo(() => findUnassignedProject(projects), [projects])

  const availableExpenseYears = useMemo(() => {
    const years = Array.from(
      new Set(
        (Array.isArray(expenseYears) ? expenseYears : [])
          .map((value) => Number(value))
          .filter((value) => Number.isInteger(value))
      )
    )
    const receiptYear = getReceiptDateParts(detailReceipt)?.year
    if (receiptYear && !years.includes(receiptYear)) {
      years.push(receiptYear)
    }
    if (!years.length) {
      years.push(new Date().getFullYear())
    }
    return years.sort((left, right) => right - left)
  }, [detailReceipt, expenseYears])

  const receiptRows = useMemo(() => {
    const query = search.trim().toLowerCase()
    const queryDigits = normalizeSearchDigits(query)
    const rows = receipts
      .map((receipt) => ({ ...receipt, statusMeta: getReceiptStatusMeta(receipt.status) }))
      .filter((receipt) => {
        if (!query) return true
        const textHaystack = [
          receipt.id,
          receipt.receipt_datetime,
          fmtDateTime(receipt.receipt_datetime),
          receipt.seller_name,
          receipt.seller_tax_id,
          receipt.seller_address,
          receipt.seller_city,
          receipt.invoice_number,
          receipt.verification_url,
          receipt.qr_hash,
          receipt.token,
          receipt.payment_type,
          receipt.payment_kind,
          receipt.project_name,
          receipt.project_code,
          receipt.status,
          receipt.statusMeta?.label,
          receipt.currency,
          receipt.category_id,
          receipt.expense_id,
          receipt.expense_status,
          receipt.expense_source,
          receipt.bank_transaction_id,
          receipt.cash_entry_id,
          receipt.item_count,
        ]
          .filter((value) => value !== null && value !== undefined && value !== '')
          .join(' ')
          .toLowerCase()
        if (textHaystack.includes(query)) return true
        if (!queryDigits) return false
        const amountDigits = normalizeSearchDigits(
          [
            receipt.total_amount,
            Number(receipt.total_amount || 0).toFixed(2),
            fmtMoney(receipt.total_amount),
            formatMoneyWithCurrency(receipt.total_amount, receipt.currency || 'RSD'),
            receipt.amount_delta,
            receipt.amount_delta_abs,
          ].join(' ')
        )
        return amountDigits.includes(queryDigits)
      })

    const getSortValue = (receipt) => {
      switch (sortCol) {
        case 'seller_name':
          return receipt.seller_name || ''
        case 'invoice_number':
          return receipt.invoice_number || ''
        case 'payment_type':
          return receipt.payment_type || receipt.payment_kind || ''
        case 'project_name':
          return receipt.project_name || receipt.project_code || ''
        case 'total_amount':
          return Number(receipt.total_amount || 0)
        case 'status':
          return receipt.statusMeta?.label || receipt.status || ''
        case 'receipt_datetime':
        default:
          return receipt.receipt_datetime || ''
      }
    }

    return [...rows].sort((left, right) => {
      const leftValue = getSortValue(left)
      const rightValue = getSortValue(right)
      if (typeof leftValue === 'number' || typeof rightValue === 'number') {
        return sortAsc ? Number(leftValue) - Number(rightValue) : Number(rightValue) - Number(leftValue)
      }
      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
  }, [receipts, search, sortAsc, sortCol])

  const getCategoryLabel = (categoryId) => {
    const category = categories.find((item) => String(item.id) === String(categoryId))
    return category ? category.name_ru : UI_DASH
  }

  const getAmountDeltaLabel = (delta, currency = 'RSD') => formatMoneyWithCurrency(delta, currency)

  const detailProjectLabel = useMemo(() => {
    if (!detailReceipt) return ''
    const project = projects.find((item) => String(item.id) === String(detailReceipt.project_id))
    const projectName = project?.name || detailReceipt.project_name || ''
    const projectCode = project?.code || ''
    const isUnassigned =
      (unassignedProject && String(detailReceipt.project_id) === String(unassignedProject.id)) ||
      projectCode === 'INT-UNASSIGNED' ||
      (unassignedProject?.name && projectName === unassignedProject.name)
    if (!projectName || isUnassigned) return ''
    return projectName
  }, [detailReceipt, projects, unassignedProject])

  const detailCategoryLabel = useMemo(() => {
    if (!detailReceipt?.category_id) return ''
    const label = getCategoryLabel(detailReceipt.category_id)
    return label === UI_DASH ? '' : label
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categories, detailReceipt])

  const detailAddressLabel = useMemo(
    () => [detailReceipt?.seller_address, detailReceipt?.seller_city].filter(Boolean).join(', '),
    [detailReceipt]
  )

  const loadReceipts = async () => {
    setLoading(true)
    setPageError('')
    try {
      const payload = await api.receipts.list({
        ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
        ...(projectFilter ? { project_id: projectFilter } : {}),
      })
      setReceipts(payload || [])
    } catch (error) {
      setReceipts([])
      setPageError(error.message || tr('loadError'))
    } finally {
      setLoading(false)
    }
  }

  const loadLookups = async () => {
    try {
      const [projectList, categoryList, contractList, expenseYearList] = await Promise.all([
        api.projects.list({ show_archived: true }),
        api.categories.list({ category_type: 'expense' }),
        api.contracts.list({ limit: 500 }),
        api.expenses.years(),
      ])
      setProjects(projectList || [])
      setCategories(categoryList || [])
      setContracts(contractList || [])
      setExpenseYears(expenseYearList || [])
    } catch (error) {
      setPageError((previous) => previous || error.message || tr('loadError'))
    }
  }

  useEffect(() => {
    if (!isActivePage) return
    loadReceipts()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActivePage, statusFilter, projectFilter])

  useEffect(() => {
    if (!isActivePage) return
    loadLookups()
  }, [isActivePage])

  useEffect(() => {
    if (typeof window === 'undefined') return
    setScanSupported(Boolean(window.BarcodeDetector) && Boolean(navigator.mediaDevices?.getUserMedia))
  }, [])

  useEffect(() => {
    if (!importModalOpen || !scannerOpen) return undefined

    let cancelled = false

    const stopScanner = () => {
      if (scanTimerRef.current) {
        clearTimeout(scanTimerRef.current)
        scanTimerRef.current = null
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop())
        streamRef.current = null
      }
      if (videoRef.current) {
        videoRef.current.srcObject = null
      }
    }

    const startScanner = async () => {
      try {
        setScanError('')
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } },
          audio: false,
        })
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play()
        }
        const detector = new window.BarcodeDetector({ formats: ['qr_code'] })
        const tick = async () => {
          if (cancelled || !videoRef.current) return
          try {
            const codes = await detector.detect(videoRef.current)
            const qrCode = codes.find((entry) => entry?.rawValue)
            if (qrCode?.rawValue) {
              setImportUrl(qrCode.rawValue)
              setScannerOpen(false)
              stopScanner()
              return
            }
          } catch {}
          scanTimerRef.current = setTimeout(tick, 350)
        }
        tick()
      } catch (error) {
        setScanError(error.message || tr('receiptScannerUnavailable'))
      }
    }

    startScanner()

    return () => {
      cancelled = true
      stopScanner()
    }
  }, [importModalOpen, scannerOpen, scanSupported])

  const resetImportState = () => {
    setImportUrl('')
    setImporting(false)
    setScannerOpen(false)
    setScanError('')
  }

  const openImportModal = () => {
    resetImportState()
    setImportModalOpen(true)
  }

  const closeImportModal = () => {
    resetImportState()
    setImportModalOpen(false)
  }

  const handleToggleScanner = () => {
    if (scannerOpen) {
      setScannerOpen(false)
      setScanError('')
      return
    }
    if (!scanSupported) {
      setScanError(tr('receiptScannerUnavailable'))
      return
    }
    if (scannerRequiresHttps) {
      setScanError(tr('receiptScanRequiresHttps'))
      return
    }
    setScanError('')
    setScannerOpen(true)
  }

  const handlePasteClipboard = async () => {
    if (pastingClipboard) return
    if (typeof navigator === 'undefined' || !navigator.clipboard?.readText) {
      setScanError(tr('receiptClipboardUnavailable'))
      return
    }
    setPastingClipboard(true)
    try {
      const text = (await navigator.clipboard.readText())?.trim()
      if (!text) {
        setScanError(tr('receiptClipboardEmpty'))
        return
      }
      setImportUrl(text)
      setScannerOpen(false)
      setScanError('')
    } catch (error) {
      setScanError(error?.message || tr('receiptClipboardUnavailable'))
    } finally {
      setPastingClipboard(false)
    }
  }

  const hydrateDetailState = (receipt) => {
    const receiptDateParts = getReceiptDateParts(receipt)
    setDetailReceipt(receipt)
    setDetailError('')
    setDetailAction('')
    setExpenseLinkMode('candidates')
    setExpenseCandidates([])
    setPeriodExpenseSearch('')
    setPeriodExpenses([])
    setPeriodExpenseYear(receiptDateParts?.year || availableExpenseYears[0] || new Date().getFullYear())
    setPeriodExpenseMonth(receiptDateParts?.month || '')
    setCreateForm({
      project_id: receipt?.project_id ? String(receipt.project_id) : '',
      category_id: receipt?.category_id ? String(receipt.category_id) : '',
      contract_id: '',
      description: '',
      note: '',
      payment_mode: receipt?.payment_kind === 'cash' ? 'cash' : 'auto',
    })
  }

  const getResolvedProjectName = (projectId) => {
    const project = projects.find((item) => String(item.id) === String(projectId))
    return project?.name || project?.code || UI_DASH
  }

  const getResolvedContractLabel = (contractId) => {
    const contract = contracts.find((item) => String(item.id) === String(contractId))
    return contract ? buildContractLabel(contract) : UI_DASH
  }

  const normalizeExpenseLinkCandidate = (item) => {
    if (!item) return item
    if (typeof item.matches_amount === 'boolean' && item.amount_delta_abs != null) {
      return item
    }
    const receiptAmount = Number(detailReceipt?.total_amount || 0)
    const expenseAmount = Number(item.amount || 0)
    const amountDeltaAbs = Math.abs(receiptAmount - expenseAmount)
    return {
      ...item,
      amount_delta_abs: amountDeltaAbs,
      matches_amount: amountDeltaAbs < 0.005,
    }
  }

  const compareExpenseLinkCandidates = (left, right) => {
    const leftCandidate = normalizeExpenseLinkCandidate(left)
    const rightCandidate = normalizeExpenseLinkCandidate(right)
    const deltaDiff =
      Number(leftCandidate?.amount_delta_abs || 0) - Number(rightCandidate?.amount_delta_abs || 0)
    if (Math.abs(deltaDiff) > 0.0001) return deltaDiff
    const dateDiff = String(right?.date || '').localeCompare(String(left?.date || ''))
    if (dateDiff !== 0) return dateDiff
    return Number(right?.id || 0) - Number(left?.id || 0)
  }

  const sortedExpenseCandidates = useMemo(
    () => [...expenseCandidates].sort(compareExpenseLinkCandidates),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [detailReceipt, expenseCandidates]
  )

  const filteredPeriodExpenses = useMemo(() => {
    const query = periodExpenseSearch.trim().toLowerCase()
    const queryDigits = normalizeSearchDigits(query)
    const rows = !query
      ? periodExpenses
      : periodExpenses.filter((expense) => {
          const project = projects.find((item) => String(item.id) === String(expense.project_id))
          const contract = contracts.find((item) => String(item.id) === String(expense.contract_id))
          const textHaystack = [
            expense.id,
            expense.description,
            expense.bank_reference,
            expense.date,
            project?.name,
            project?.code,
            contract?.number,
            contract?.subject,
          ]
            .filter(Boolean)
            .join(' ')
            .toLowerCase()
          if (textHaystack.includes(query)) return true
          if (!queryDigits) return false
          const amountDigits = normalizeSearchDigits(
            [expense.amount, Number(expense.amount || 0).toFixed(2), fmtMoney(expense.amount)].join(' ')
          )
          return amountDigits.includes(queryDigits)
        })
    return [...rows].sort(compareExpenseLinkCandidates)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contracts, detailReceipt, periodExpenseSearch, periodExpenses, projects])

  useEffect(() => {
    if (detailAction !== 'link' || expenseLinkMode !== 'period' || !periodExpenseYear) return
    let cancelled = false

    const loadPeriodExpenses = async () => {
      setDetailError('')
      setPeriodExpensesLoading(true)
      try {
        const items = await api.expenses.list({
          year: periodExpenseYear,
          ...(periodExpenseMonth ? { month: periodExpenseMonth } : {}),
          limit: 500,
        })
        if (!cancelled) {
          setPeriodExpenses(items || [])
        }
      } catch (error) {
        if (!cancelled) {
          setPeriodExpenses([])
          setDetailError(error.message || tr('loadError'))
        }
      } finally {
        if (!cancelled) {
          setPeriodExpensesLoading(false)
        }
      }
    }

    loadPeriodExpenses()
    return () => {
      cancelled = true
    }
  }, [detailAction, expenseLinkMode, periodExpenseMonth, periodExpenseYear])

  const openReceiptDetail = async (receiptId) => {
    setDetailLoading(true)
    setDetailError('')
    try {
      const receipt = await api.receipts.get(receiptId)
      hydrateDetailState(receipt)
    } catch (error) {
      setDetailReceipt(null)
      setDetailError(error.message || tr('loadError'))
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    if (!isActivePage) return
    const receiptId = location.state?.openReceiptId
    if (!receiptId) return
    openReceiptDetail(receiptId)
    navigate(location.pathname, { replace: true, state: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActivePage, location.state?.openReceiptId])

  const handleImportReceipt = async () => {
    if (!importUrl.trim()) return
    setImporting(true)
    setPageError('')
    try {
      const payload = await api.receipts.importFromQr({ verification_url: importUrl.trim() })
      closeImportModal()
      await loadReceipts()
      hydrateDetailState(payload.receipt)
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setImporting(false)
    }
  }

  const handleCreateContractChange = (value) => {
    const contract = contracts.find((item) => String(item.id) === String(value))
    const contractProjectId = contract?.project_id ? String(contract.project_id) : ''
    setCreateForm((prev) => ({
      ...prev,
      contract_id: value,
      project_id: contractProjectId || prev.project_id,
    }))
  }

  const openExpenseCandidates = async () => {
    if (!detailReceipt) return
    setDetailAction('link')
    setExpenseLinkMode('candidates')
    setDetailError('')
    setExpenseCandidatesLoading(true)
    try {
      const items = await api.receipts.expenseCandidates(detailReceipt.id)
      setExpenseCandidates(items || [])
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
      setExpenseCandidates([])
    } finally {
      setExpenseCandidatesLoading(false)
    }
  }

  const handleLinkExpense = async (candidate) => {
    if (!detailReceipt) return
    const normalizedCandidate = normalizeExpenseLinkCandidate(candidate)
    if (!normalizedCandidate) return
    if (!normalizedCandidate.matches_amount && typeof window !== 'undefined') {
      const confirmation = tr('receiptLinkMismatchConfirm')
        .replace(
          '{receipt}',
          formatMoneyWithCurrency(
            detailReceipt.total_amount,
            detailReceipt.currency || normalizedCandidate.currency || 'RSD'
          )
        )
        .replace(
          '{expense}',
          formatMoneyWithCurrency(
            normalizedCandidate.amount,
            normalizedCandidate.currency || detailReceipt.currency || 'RSD'
          )
        )
        .replace(
          '{delta}',
          getAmountDeltaLabel(
            normalizedCandidate.amount_delta_abs,
            normalizedCandidate.currency || detailReceipt.currency || 'RSD'
          )
        )
      if (!window.confirm(confirmation)) return
    }
    setExpenseCandidatesLoading(true)
    try {
      const receipt = await api.receipts.linkExpense(detailReceipt.id, { expense_id: normalizedCandidate.id })
      hydrateDetailState(receipt)
      await loadReceipts()
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
    } finally {
      setExpenseCandidatesLoading(false)
    }
  }

  const handleCreateExpense = async (event) => {
    event.preventDefault()
    if (!detailReceipt) return
    setCreateExpenseSaving(true)
    try {
      const receipt = await api.receipts.createExpense(detailReceipt.id, {
        project_id: createForm.project_id || null,
        category_id: createForm.category_id || null,
        contract_id: createForm.contract_id || null,
        description: createForm.description || null,
        note: createForm.note || null,
        payment_mode: createForm.payment_mode || 'auto',
      })
      hydrateDetailState(receipt)
      await loadReceipts()
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
    } finally {
      setCreateExpenseSaving(false)
    }
  }

  const handleUnlinkExpense = async () => {
    if (!detailReceipt) return
    setUnlinkingExpense(true)
    try {
      const receipt = await api.receipts.unlinkExpense(detailReceipt.id)
      hydrateDetailState(receipt)
      await loadReceipts()
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
    } finally {
      setUnlinkingExpense(false)
    }
  }

  const handleMarkCashPaid = async () => {
    if (!detailReceipt) return
    setUpdatingCashPayment(true)
    try {
      const receipt = await api.receipts.markCashPaid(detailReceipt.id)
      hydrateDetailState(receipt)
      await loadReceipts()
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
    } finally {
      setUpdatingCashPayment(false)
    }
  }

  const handleMarkWaitingBank = async () => {
    if (!detailReceipt) return
    if (typeof window !== 'undefined' && !window.confirm(tr('receiptMarkWaitingBankConfirm'))) return
    setUpdatingCashPayment(true)
    try {
      const receipt = await api.receipts.markWaitingBank(detailReceipt.id)
      hydrateDetailState(receipt)
      await loadReceipts()
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
    } finally {
      setUpdatingCashPayment(false)
    }
  }

  const handleDeleteReceipt = async () => {
    if (!detailReceipt || deletingReceipt) return
    if (typeof window !== 'undefined' && !window.confirm(tr('receiptDeleteConfirm'))) return
    setDeletingReceipt(true)
    try {
      await api.receipts.delete(detailReceipt.id)
      setDetailReceipt(null)
      setDetailError('')
      setDetailAction('')
      await loadReceipts()
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
    } finally {
      setDeletingReceipt(false)
    }
  }

  const handleOpenReceiptInBrowser = () => {
    if (!detailReceipt?.verification_url) {
      setDetailError(tr('receiptOpenBrowserUnavailable'))
      return
    }
    if (typeof window === 'undefined') return
    window.open(detailReceipt.verification_url, '_blank', 'noopener,noreferrer')
  }

  const toggleSort = (column) => {
    if (sortCol === column) {
      setSortAsc((value) => !value)
    } else {
      setSortCol(column)
      setSortAsc(false)
    }
  }

  const canMarkCashPaid =
    detailReceipt &&
    (!detailReceipt.expense_id ||
      (detailReceipt.status === 'waiting_bank' &&
        detailReceipt.expense_source === 'receipt' &&
        detailReceipt.expense_status === 'planned' &&
        !detailReceipt.bank_transaction_id))
  const canMarkWaitingBank =
    detailReceipt &&
    detailReceipt.status === 'cash_expense' &&
    detailReceipt.expense_source === 'cash' &&
    !!detailReceipt.cash_entry_id &&
    !detailReceipt.bank_transaction_id

  return (
    <div className="page">
      <PageHeader
        title={tr('receipts')}
        actions={
          <>
            <select
              className="form-input"
              style={{ width: 180 }}
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              {statusOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <select
              className="form-input"
              style={{ width: 220 }}
              value={projectFilter}
              onChange={(event) => setProjectFilter(event.target.value)}
            >
              <option value="">{tr('receiptProjectFilterAll')}</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
            <SearchInput
              placeholder={tr('search')}
              value={search}
              onChange={setSearch}
              style={{ width: 220 }}
            />
            <button type="button" className="btn btn-primary" onClick={openImportModal}>
              {tr('receiptImportButton')}
            </button>
          </>
        }
      />

      {pageError ? (
        <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
          {pageError}
        </div>
      ) : null}

      <div className="card">
        <div className="card-title">{tr('receipts')}</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('receipt_datetime')}>
                  {tr('date')} <SortIndicator active={sortCol === 'receipt_datetime'} asc={sortAsc} />
                </th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('seller_name')}>
                  {tr('receiptSeller')} <SortIndicator active={sortCol === 'seller_name'} asc={sortAsc} />
                </th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('invoice_number')}>
                  {tr('invoiceNumber')} <SortIndicator active={sortCol === 'invoice_number'} asc={sortAsc} />
                </th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('payment_type')}>
                  {tr('receiptPaymentType')}{' '}
                  <SortIndicator active={sortCol === 'payment_type'} asc={sortAsc} />
                </th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('project_name')}>
                  {tr('project')} <SortIndicator active={sortCol === 'project_name'} asc={sortAsc} />
                </th>
                <th
                  style={{ textAlign: 'right', cursor: 'pointer' }}
                  onClick={() => toggleSort('total_amount')}
                >
                  {tr('amount')} <SortIndicator active={sortCol === 'total_amount'} asc={sortAsc} />
                </th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('status')}>
                  {tr('status')} <SortIndicator active={sortCol === 'status'} asc={sortAsc} />
                </th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7}>{tr('loading')}</td>
                </tr>
              ) : receiptRows.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ color: 'var(--color-text-muted)' }}>
                    {tr('noRecords')}
                  </td>
                </tr>
              ) : (
                receiptRows.map((receipt) => (
                  <tr
                    key={receipt.id}
                    className="record-row"
                    onClick={() => openReceiptDetail(receipt.id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        openReceiptDetail(receipt.id)
                      }
                    }}
                    tabIndex={0}
                  >
                    <td className="date-cell">{fmtDateTime(receipt.receipt_datetime)}</td>
                    <td>
                      <div style={{ fontWeight: 700 }}>{receipt.seller_name || UI_DASH}</div>
                      <div style={{ color: 'var(--color-text-muted)', fontSize: '0.82rem' }}>
                        {receipt.seller_tax_id || UI_DASH}
                      </div>
                    </td>
                    <td>{receipt.invoice_number || UI_DASH}</td>
                    <td>{receipt.payment_type || UI_DASH}</td>
                    <td>{receipt.project_name || UI_DASH}</td>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap', fontWeight: 700 }}>
                      {fmtMoney(receipt.total_amount)} {receipt.currency || 'RSD'}
                    </td>
                    <td>
                      <ReceiptStatusBadge status={receipt.status} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Modal
        isOpen={importModalOpen}
        onClose={closeImportModal}
        title={tr('receiptImportTitle')}
        closeOnOverlay
        className="receipt-import-modal"
      >
        {importModalOpen ? (
          <div className="receipt-import-layout">
            <div className="record-detail-card receipt-import-card">
              <div className="form-group">
                <label className="form-label">{tr('receiptQrUrl')}</label>
                <textarea
                  className="form-input"
                  rows={5}
                  value={importUrl}
                  onChange={(event) => setImportUrl(event.target.value)}
                  placeholder="https://suf.purs.gov.rs/v/?vl=..."
                  style={{ resize: 'vertical' }}
                />
              </div>
              <div className="receipt-import-actions">
                <button type="button" className="btn btn-secondary" onClick={handleToggleScanner}>
                  {scannerOpen ? tr('receiptScanStop') : tr('receiptScanStart')}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handlePasteClipboard}
                  disabled={pastingClipboard}
                >
                  {pastingClipboard ? tr('loading') : tr('receiptPasteClipboard')}
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleImportReceipt}
                  disabled={importing || !importUrl.trim()}
                >
                  {importing ? tr('receiptImporting') : tr('receiptImportButton')}
                </button>
              </div>
              <div className="receipt-import-help">
                {canUseScanner
                  ? tr('receiptScanHint')
                  : scannerRequiresHttps
                    ? tr('receiptScanRequiresHttps')
                    : tr('receiptScannerUnavailable')}
              </div>
              {scanError ? (
                <div className="alert alert-danger" style={{ marginTop: '0.75rem' }}>
                  {scanError}
                </div>
              ) : null}
            </div>
            <div className="record-detail-card receipt-camera-card">
              <div className="record-field-label">{tr('receiptScanCamera')}</div>
              {scannerOpen && canUseScanner ? (
                <video ref={videoRef} autoPlay playsInline muted className="receipt-camera-preview" />
              ) : (
                <div className="receipt-camera-placeholder">
                  <strong style={{ display: 'block', marginBottom: '0.35rem' }}>
                    {canUseScanner ? tr('receiptScanCameraIdle') : tr('receiptScanCamera')}
                  </strong>
                  <span>
                    {canUseScanner
                      ? tr('receiptScanHint')
                      : scannerRequiresHttps
                        ? tr('receiptScanRequiresHttps')
                        : tr('receiptScannerUnavailable')}
                  </span>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </Modal>

      <EntityDetailModal
        isOpen={!!(detailReceipt || detailLoading || detailError)}
        onClose={() => {
          setDetailReceipt(null)
          setDetailError('')
          setDetailAction('')
        }}
        title={`${tr('receiptDetailTitle')} ${UI_DASH} ${detailReceipt?.invoice_number || (detailReceipt ? `#${detailReceipt.id}` : UI_DASH)}`}
        maxWidth="1200px"
        className="receipt-detail-modal"
        details={
          detailLoading ? (
            <div>{tr('loading')}</div>
          ) : detailError && !detailReceipt ? (
            <div className="alert alert-danger">{detailError}</div>
          ) : detailReceipt ? (
            <div className="receipt-summary-grid">
              <div className="record-field">
                <span className="record-field-label">{tr('receiptSeller')}</span>
                <span className="record-field-value">{detailReceipt.seller_name || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('invoiceNumber')}</span>
                <span className="record-field-value">{detailReceipt.invoice_number || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('date')}</span>
                <span className="record-field-value">{fmtDateTime(detailReceipt.receipt_datetime)}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('status')}</span>
                <span className="record-field-value">
                  <ReceiptStatusBadge status={detailReceipt.status} />
                </span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('receiptPaymentType')}</span>
                <span className="record-field-value">{detailReceipt.payment_type || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('amount')}</span>
                <span className="record-field-value">
                  {fmtMoney(detailReceipt.total_amount)} {detailReceipt.currency || 'RSD'}
                </span>
              </div>
              {detailProjectLabel ? (
                <div className="record-field">
                  <span className="record-field-label">{tr('project')}</span>
                  <span className="record-field-value">{detailProjectLabel}</span>
                </div>
              ) : null}
              {detailCategoryLabel ? (
                <div className="record-field">
                  <span className="record-field-label">{tr('category')}</span>
                  <span className="record-field-value">{detailCategoryLabel}</span>
                </div>
              ) : null}
              {detailAddressLabel ? (
                <div className="record-field full">
                  <span className="record-field-label">{tr('address')}</span>
                  <div className="record-field-text">{detailAddressLabel}</div>
                </div>
              ) : null}
            </div>
          ) : null
        }
        actions={
          detailReceipt ? (
            <>
              {detailError ? (
                <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
                  {detailError}
                </div>
              ) : null}
              <div className="receipt-side-card">
                <div className="record-actions-grid" style={{ marginBottom: '1rem' }}>
                  {!detailReceipt.expense_id ? (
                    <>
                      <button type="button" className="btn btn-primary" onClick={openExpenseCandidates}>
                        {tr('receiptLinkExpense')}
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => setDetailAction('create')}
                      >
                        {tr('receiptCreateExpense')}
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={handleUnlinkExpense}
                      disabled={unlinkingExpense}
                    >
                      {unlinkingExpense ? tr('loading') : tr('receiptUnlinkExpense')}
                    </button>
                  )}
                  {canMarkCashPaid ? (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleMarkCashPaid}
                      disabled={updatingCashPayment}
                    >
                      {updatingCashPayment ? tr('loading') : tr('receiptMarkCashPaid')}
                    </button>
                  ) : null}
                  {canMarkWaitingBank ? (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleMarkWaitingBank}
                      disabled={updatingCashPayment}
                    >
                      {updatingCashPayment ? tr('loading') : tr('receiptMarkWaitingBank')}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleOpenReceiptInBrowser}
                    disabled={!detailReceipt.verification_url}
                    title={!detailReceipt.verification_url ? tr('receiptOpenBrowserUnavailable') : ''}
                  >
                    {tr('receiptOpenBrowser')}
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={handleDeleteReceipt}
                    disabled={
                      deletingReceipt || unlinkingExpense || createExpenseSaving || updatingCashPayment
                    }
                  >
                    {deletingReceipt ? tr('loading') : tr('receiptDelete')}
                  </button>
                </div>

                {detailReceipt.expense_id ||
                detailReceipt.bank_transaction_id ||
                detailReceipt.cash_entry_id ? (
                  <div className="receipt-linked-grid">
                    {detailReceipt.expense_id ? (
                      <div className="record-field">
                        <span className="record-field-label">{tr('receiptLinkedExpense')}</span>
                        <span className="record-field-value">
                          {`#${detailReceipt.expense_id} ${UI_DASH} ${(detailReceipt.expense_source || '').trim() || UI_DASH} ${UI_DASH} ${(detailReceipt.expense_status || '').trim() || UI_DASH}`}
                        </span>
                      </div>
                    ) : null}
                    {detailReceipt.bank_transaction_id ? (
                      <div className="record-field">
                        <span className="record-field-label">{tr('receiptLinkedBank')}</span>
                        <span className="record-field-value">#{detailReceipt.bank_transaction_id}</span>
                      </div>
                    ) : null}
                    {detailReceipt.cash_entry_id ? (
                      <div className="record-field">
                        <span className="record-field-label">{tr('cashRegister')}</span>
                        <span className="record-field-value">#{detailReceipt.cash_entry_id}</span>
                      </div>
                    ) : null}
                    {detailReceipt.expense_id && !detailReceipt.matches_amount ? (
                      <div className="record-field">
                        <span className="record-field-label">{tr('receiptAmountDelta')}</span>
                        <span className="record-field-value" style={{ color: 'var(--color-warning)' }}>
                          {getAmountDeltaLabel(
                            detailReceipt.amount_delta_abs,
                            detailReceipt.currency || 'RSD'
                          )}
                        </span>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {detailAction === 'link' ? (
                  <div className="receipt-detail-section">
                    <div
                      style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.85rem', flexWrap: 'wrap' }}
                    >
                      <button
                        type="button"
                        className={expenseLinkMode === 'candidates' ? 'btn btn-primary' : 'btn btn-secondary'}
                        onClick={() => setExpenseLinkMode('candidates')}
                      >
                        {tr('receiptLinkModeCandidates')}
                      </button>
                      <button
                        type="button"
                        className={expenseLinkMode === 'period' ? 'btn btn-primary' : 'btn btn-secondary'}
                        onClick={() => setExpenseLinkMode('period')}
                      >
                        {tr('receiptLinkModePeriod')}
                      </button>
                    </div>

                    {expenseLinkMode === 'period' ? (
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: '110px minmax(140px, 1fr)',
                          gap: '0.75rem',
                          marginBottom: '0.85rem',
                        }}
                      >
                        <YearFilterSelect
                          value={periodExpenseYear}
                          availableYears={availableExpenseYears}
                          onChange={setPeriodExpenseYear}
                          includeAllTime={false}
                          style={{ width: '100%' }}
                        />
                        <select
                          className="form-input"
                          value={periodExpenseMonth === '' ? '' : String(periodExpenseMonth)}
                          onChange={(event) =>
                            setPeriodExpenseMonth(event.target.value ? Number(event.target.value) : '')
                          }
                        >
                          <option value="">{tr('allMonths')}</option>
                          {monthNames.map((label, index) => (
                            <option key={label} value={index + 1}>
                              {label}
                            </option>
                          ))}
                        </select>
                        <div style={{ gridColumn: '1 / -1' }}>
                          <SearchInput
                            placeholder={tr('search')}
                            value={periodExpenseSearch}
                            onChange={setPeriodExpenseSearch}
                            style={{ width: '100%' }}
                          />
                        </div>
                      </div>
                    ) : null}

                    <div className="record-field-label" style={{ marginBottom: '0.75rem' }}>
                      {expenseLinkMode === 'period'
                        ? tr('receiptLinkModePeriod')
                        : tr('receiptExpenseCandidates')}
                    </div>
                    {expenseLinkMode === 'period' ? (
                      periodExpensesLoading ? (
                        <div>{tr('loading')}</div>
                      ) : filteredPeriodExpenses.length === 0 ? (
                        <div style={{ color: 'var(--color-text-muted)' }}>
                          {tr('receiptNoPeriodExpenses')}
                        </div>
                      ) : (
                        <div className="receipt-candidates-list">
                          {filteredPeriodExpenses.map((expense) => {
                            const candidate = normalizeExpenseLinkCandidate(expense)
                            return (
                              <div
                                key={expense.id}
                                className="record-detail-card"
                                style={{ padding: '0.85rem' }}
                              >
                                <div className="receipt-candidate-card">
                                  <div>
                                    <div style={{ fontWeight: 700 }}>{expense.description || UI_DASH}</div>
                                    <div
                                      style={{
                                        color: 'var(--color-text-muted)',
                                        fontSize: '0.84rem',
                                        marginTop: '0.25rem',
                                      }}
                                    >
                                      {expense.date} {UI_DASH} {getResolvedProjectName(expense.project_id)}
                                    </div>
                                    <div
                                      style={{
                                        color: 'var(--color-text-muted)',
                                        fontSize: '0.84rem',
                                        marginTop: '0.25rem',
                                      }}
                                    >
                                      {getResolvedContractLabel(expense.contract_id)}
                                    </div>
                                    <div
                                      style={{
                                        color: candidate.matches_amount
                                          ? 'var(--color-text-muted)'
                                          : 'var(--color-warning)',
                                        fontSize: '0.84rem',
                                        marginTop: '0.35rem',
                                      }}
                                    >
                                      {candidate.matches_amount
                                        ? tr('receiptAmountExact')
                                        : `${tr('receiptAmountDelta')}: ${getAmountDeltaLabel(candidate.amount_delta_abs, expense.currency || detailReceipt.currency || 'RSD')}`}
                                    </div>
                                    {expense.bank_reference ? (
                                      <div
                                        style={{
                                          color: 'var(--color-text-muted)',
                                          fontSize: '0.8rem',
                                          marginTop: '0.2rem',
                                        }}
                                      >
                                        {expense.bank_reference}
                                      </div>
                                    ) : null}
                                  </div>
                                  <div style={{ textAlign: 'right' }}>
                                    <div style={{ fontWeight: 700 }}>
                                      {fmtMoney(expense.amount)} {expense.currency || 'RSD'}
                                    </div>
                                    <button
                                      type="button"
                                      className="btn btn-sm btn-primary"
                                      style={{ marginTop: '0.5rem' }}
                                      onClick={() => handleLinkExpense(candidate)}
                                    >
                                      {tr('receiptLinkExpense')}
                                    </button>
                                  </div>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      )
                    ) : expenseCandidatesLoading ? (
                      <div>{tr('loading')}</div>
                    ) : expenseCandidates.length === 0 ? (
                      <div style={{ color: 'var(--color-text-muted)' }}>{tr('receiptNoCandidates')}</div>
                    ) : (
                      <div className="receipt-candidates-list">
                        {sortedExpenseCandidates.map((candidate) => (
                          <div
                            key={candidate.id}
                            className="record-detail-card"
                            style={{ padding: '0.85rem' }}
                          >
                            <div className="receipt-candidate-card">
                              <div>
                                <div style={{ fontWeight: 700 }}>{candidate.description || UI_DASH}</div>
                                <div
                                  style={{
                                    color: 'var(--color-text-muted)',
                                    fontSize: '0.84rem',
                                    marginTop: '0.25rem',
                                  }}
                                >
                                  {candidate.date} {UI_DASH} {candidate.project_name || UI_DASH}
                                </div>
                                <div
                                  style={{
                                    color: 'var(--color-text-muted)',
                                    fontSize: '0.84rem',
                                    marginTop: '0.25rem',
                                  }}
                                >
                                  {candidate.contract_number || UI_DASH}
                                </div>
                                <div
                                  style={{
                                    color: candidate.matches_amount
                                      ? 'var(--color-text-muted)'
                                      : 'var(--color-warning)',
                                    fontSize: '0.84rem',
                                    marginTop: '0.35rem',
                                  }}
                                >
                                  {candidate.matches_amount
                                    ? tr('receiptAmountExact')
                                    : `${tr('receiptAmountDelta')}: ${getAmountDeltaLabel(candidate.amount_delta_abs, candidate.currency || detailReceipt.currency || 'RSD')}`}
                                </div>
                                {!candidate.matches_amount ? (
                                  <div
                                    style={{
                                      color: 'var(--color-text-muted)',
                                      fontSize: '0.8rem',
                                      marginTop: '0.2rem',
                                    }}
                                  >
                                    {tr('receiptLinkMismatchHint')}
                                  </div>
                                ) : null}
                              </div>
                              <div style={{ textAlign: 'right' }}>
                                <div style={{ fontWeight: 700 }}>
                                  {fmtMoney(candidate.amount)} {candidate.currency || 'RSD'}
                                </div>
                                <button
                                  type="button"
                                  className="btn btn-sm btn-primary"
                                  style={{ marginTop: '0.5rem' }}
                                  onClick={() => handleLinkExpense(candidate)}
                                >
                                  {tr('receiptLinkExpense')}
                                </button>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : null}

                {detailAction === 'create' ? (
                  <form onSubmit={handleCreateExpense} className="receipt-detail-section">
                    <div className="form-group">
                      <label className="form-label">{tr('receiptCreateMode')}</label>
                      <select
                        className="form-input"
                        value={createForm.payment_mode}
                        onChange={(event) =>
                          setCreateForm((prev) => ({ ...prev, payment_mode: event.target.value }))
                        }
                      >
                        <option value="auto">{tr('receiptCreateModeAuto')}</option>
                        <option value="bank">{tr('receiptCreateModeBank')}</option>
                        <option value="cash">{tr('receiptCreateModeCash')}</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">{tr('project')}</label>
                      <ProjectSelect
                        projects={projects}
                        value={createForm.project_id}
                        onChange={(value) =>
                          setCreateForm((prev) => ({ ...prev, project_id: value, contract_id: '' }))
                        }
                        allowEmpty
                        emptyLabel={UI_DASH}
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{tr('category')}</label>
                      <select
                        className="form-input"
                        value={createForm.category_id}
                        onChange={(event) =>
                          setCreateForm((prev) => ({ ...prev, category_id: event.target.value }))
                        }
                      >
                        <option value="">{UI_DASH}</option>
                        {categories.map((category) => (
                          <option key={category.id} value={category.id}>
                            {category.name_ru}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">{tr('contracts')}</label>
                      <select
                        className="form-input"
                        value={createForm.contract_id}
                        onChange={(event) => handleCreateContractChange(event.target.value)}
                      >
                        <option value="">{UI_DASH}</option>
                        {filteredContracts.map((contract) => (
                          <option key={contract.id} value={contract.id}>
                            {buildContractLabel(contract)}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">{tr('description')}</label>
                      <input
                        className="form-input"
                        value={createForm.description}
                        onChange={(event) =>
                          setCreateForm((prev) => ({ ...prev, description: event.target.value }))
                        }
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{tr('note')}</label>
                      <textarea
                        className="form-input"
                        rows={3}
                        value={createForm.note}
                        onChange={(event) => setCreateForm((prev) => ({ ...prev, note: event.target.value }))}
                      />
                    </div>
                    <button type="submit" className="btn btn-primary" disabled={createExpenseSaving}>
                      {createExpenseSaving ? tr('loading') : tr('receiptCreateExpense')}
                    </button>
                  </form>
                ) : null}
              </div>
            </>
          ) : null
        }
      >
        {detailReceipt ? (
          <div className="record-detail-card receipt-items-card">
            <div className="receipt-items-header">
              <span className="record-field-label">{tr('receiptItems')}</span>
              <span className="receipt-items-count">{detailReceipt.items?.length || 0}</span>
            </div>
            <div className="table-wrap table-wrap-scroll receipt-items-table-wrap">
              <table className="receipt-items-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>{tr('name')}</th>
                    <th style={{ textAlign: 'right' }}>{tr('receiptQuantity')}</th>
                    <th style={{ textAlign: 'right' }}>{tr('receiptUnitPrice')}</th>
                    <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
                  </tr>
                </thead>
                <tbody>
                  {detailReceipt.items?.length ? (
                    detailReceipt.items.map((item) => (
                      <tr key={item.id}>
                        <td>{item.line_no}</td>
                        <td>{item.name}</td>
                        <td style={{ textAlign: 'right' }}>{fmtMoney(item.quantity)}</td>
                        <td style={{ textAlign: 'right' }}>{fmtMoney(item.unit_price)} RSD</td>
                        <td style={{ textAlign: 'right' }}>{fmtMoney(item.total_amount)} RSD</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} style={{ color: 'var(--color-text-muted)' }}>
                        {tr('noRecords')}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </EntityDetailModal>
    </div>
  )
}
