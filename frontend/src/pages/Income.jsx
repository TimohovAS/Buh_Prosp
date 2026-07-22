import { useState, useEffect, useMemo, useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import EntityDetailModal from '../components/EntityDetailModal'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'
import SelectionSummary from '../components/SelectionSummary'
import SortIndicator from '../components/SortIndicator'
import YearFilterSelect from '../components/YearFilterSelect'
import useAvailableYears from '../hooks/useAvailableYears'
import useListPageState from '../hooks/useListPageState'
import useProjectContractForm from '../hooks/useProjectContractForm'
import {
  buildContractLabel,
  filterContractsForProject,
  findUnassignedProject,
  getProjectName as resolveProjectName,
} from '../utils/entityLabels'
import { UI_CLOSE, UI_DASH, todayIso } from '../utils/formatters'
import { MONTHS } from '../utils/constants'
import { amountSearchHay } from '../utils/searchUtils'

const PAYMENT_TYPE_KEYS = {
  advance: 'contractPaymentAdvance',
  intermediate: 'contractPaymentIntermediate',
  closing: 'contractPaymentClosing',
}
const INCOME_UNIT_OPTIONS = ['kom', 'sat', 'dan', 'm', 'm2', 'm3', 'kg', 'l', 'set', 'usl']
const EFAKTURA_REFERENCE_FIELDS = [
  { name: 'efaktura_contract_number', label: 'efakturaContractNumber' },
  { name: 'efaktura_order_reference', label: 'efakturaOrderReference' },
  { name: 'efaktura_framework_agreement_number', label: 'efakturaFrameworkAgreementNumber' },
  { name: 'efaktura_object_code', label: 'efakturaObjectCode' },
  { name: 'efaktura_buyer_reference', label: 'efakturaBuyerReference' },
  { name: 'efaktura_payment_reference', label: 'efakturaPaymentReference' },
  { name: 'efaktura_payment_model', label: 'efakturaPaymentModel', maxLength: 10 },
]
const newIncomeLine = () => ({
  name: '',
  quantity: '1',
  unit: 'kom',
  unit_price: '',
  total_amount: '',
  note: '',
})

const numericValue = (value) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

const formatMoney = (value) =>
  numericValue(value).toLocaleString('sr-RS', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })

const computeLineTotal = (line) => {
  const explicit = numericValue(line.total_amount)
  if (explicit > 0) return explicit
  return numericValue(line.quantity) * numericValue(line.unit_price)
}

const unitOptionsForLine = (unit) => {
  const normalizedUnit = String(unit || '').trim()
  if (!normalizedUnit || INCOME_UNIT_OPTIONS.includes(normalizedUnit)) {
    return INCOME_UNIT_OPTIONS
  }
  return [normalizedUnit, ...INCOME_UNIT_OPTIONS]
}

export default function Income() {
  const location = useLocation()
  const navigate = useNavigate()
  const isActivePage = location.pathname === '/income'
  const [items, setItems] = useState([])
  const [clients, setClients] = useState([])
  const [contracts, setContracts] = useState([])
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
  const [projects, setProjects] = useState([])
  const [assignProjectId, setAssignProjectId] = useState('')
  const [pageError, setPageError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [paymentModal, setPaymentModal] = useState(null)
  const [detailModal, setDetailModal] = useState(null)
  const [paymentDetails, setPaymentDetails] = useState(null)
  const [paymentLoading, setPaymentLoading] = useState(false)
  const [paymentActionLoading, setPaymentActionLoading] = useState(false)
  const [paymentError, setPaymentError] = useState('')
  const [itemSuggestions, setItemSuggestions] = useState([])
  const [itemSearchSuggestions, setItemSearchSuggestions] = useState([])
  const [activeLineIndex, setActiveLineIndex] = useState(null)
  const [efakturaFieldsOpen, setEfakturaFieldsOpen] = useState(false)
  const [form, setForm] = useState({
    date: todayIso(),
    due_date: '',
    invoice_number: '',
    client_id: '',
    contract_id: '',
    contract_payment_type: '',
    project_id: '',
    description: '',
    efaktura_contract_number: '',
    efaktura_order_reference: '',
    efaktura_framework_agreement_number: '',
    efaktura_object_code: '',
    efaktura_buyer_reference: '',
    efaktura_payment_reference: '',
    efaktura_payment_model: '',
    amount_rsd: '',
    items: [newIncomeLine()],
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
        applyAvailableYears(years)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    if (!modal || !form.client_id) return setContracts([])
    const params = form.client_id ? { client_id: form.client_id } : {}
    if (modal === 'add' || !modal?.id) params.status = 'active'
    api.contracts.list(params).then(setContracts)
  }, [modal, form.client_id])
  useEffect(() => {
    if (!modal || !form.client_id) {
      setItemSuggestions([])
      return
    }
    api.income
      .itemSuggestions({ client_id: form.client_id, limit: 12 })
      .then(setItemSuggestions)
      .catch(() => setItemSuggestions([]))
  }, [modal, form.client_id])
  useEffect(() => {
    if (!modal || activeLineIndex == null) {
      setItemSearchSuggestions([])
      return undefined
    }
    const term = String(form.items?.[activeLineIndex]?.name || '').trim()
    if (term.length < 2) {
      setItemSearchSuggestions([])
      return undefined
    }
    const timer = window.setTimeout(() => {
      const params = { search: term, limit: 8 }
      if (form.client_id) params.client_id = form.client_id
      api.income
        .itemSuggestions(params)
        .then(setItemSearchSuggestions)
        .catch(() => setItemSearchSuggestions([]))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [modal, form.client_id, form.items, activeLineIndex])

  const [nextInvoiceHint, setNextInvoiceHint] = useState('')
  const getDefaultIncomeDate = () => {
    const today = new Date()
    const targetYear = Number.isInteger(year) ? year : today.getFullYear()
    const targetMonth = month ? Number(month) : today.getMonth() + 1
    const lastDay = new Date(targetYear, targetMonth, 0).getDate()
    const targetDay = Math.min(today.getDate(), lastDay)
    return targetYear + '-' + String(targetMonth).padStart(2, '0') + '-' + String(targetDay).padStart(2, '0')
  }
  const closeItemSearchSuggestions = useCallback((lineIndex = null) => {
    setActiveLineIndex((current) => {
      if (lineIndex !== null && current !== lineIndex) return current
      return null
    })
    setItemSearchSuggestions([])
  }, [])

  const closeModal = () => {
    setModal(null)
    setNextInvoiceHint('')
    setSubmitError('')
    closeItemSearchSuggestions()
  }

  useEffect(() => {
    if (modal !== 'add') {
      setNextInvoiceHint('')
      return
    }
    const hintYear = /^\d{4}-\d{2}-\d{2}$/.test(form.date || '') ? parseInt(form.date.slice(0, 4), 10) : year
    api.income
      .nextInvoice(hintYear)
      .then((response) => setNextInvoiceHint(response.invoice_number))
      .catch(() => setNextInvoiceHint(''))
  }, [modal, form.date, year])

  const openAdd = () => {
    const defaultForm = {
      date: getDefaultIncomeDate(),
      due_date: '',
      invoice_number: '',
      client_id: '',
      contract_id: '',
      contract_payment_type: '',
      project_id: unassignedProject ? String(unassignedProject.id) : '',
      description: '',
      efaktura_contract_number: '',
      efaktura_order_reference: '',
      efaktura_framework_agreement_number: '',
      efaktura_object_code: '',
      efaktura_buyer_reference: '',
      efaktura_payment_reference: '',
      efaktura_payment_model: '',
      amount_rsd: '',
      items: [newIncomeLine()],
      note: '',
    }
    setForm(defaultForm)
    setSubmitError('')
    setPageError('')
    setEfakturaFieldsOpen(false)
    setModal('add')
  }

  const openEdit = (item) => {
    setForm({
      date: item.date,
      due_date: item.due_date || '',
      invoice_number: item.invoice_number,
      client_id: item.client_id || '',
      contract_id: item.contract_id || '',
      contract_payment_type: item.contract_payment_type || '',
      project_id: item.project_id ?? (unassignedProject ? String(unassignedProject.id) : ''),
      description: item.description || '',
      efaktura_contract_number: item.efaktura_contract_number || '',
      efaktura_order_reference: item.efaktura_order_reference || '',
      efaktura_framework_agreement_number: item.efaktura_framework_agreement_number || '',
      efaktura_object_code: item.efaktura_object_code || '',
      efaktura_buyer_reference: item.efaktura_buyer_reference || '',
      efaktura_payment_reference: item.efaktura_payment_reference || '',
      efaktura_payment_model: item.efaktura_payment_model || '',
      amount_rsd: item.amount_rsd,
      items: item.items?.length
        ? item.items.map((line) => ({
            name: line.name || '',
            quantity: String(line.quantity ?? '1'),
            unit: line.unit || 'kom',
            unit_price: String(line.unit_price ?? ''),
            total_amount: String(line.total_amount ?? ''),
            note: line.note || '',
          }))
        : [],
      note: item.note || '',
    })
    setSubmitError('')
    setPageError('')
    setEfakturaFieldsOpen(EFAKTURA_REFERENCE_FIELDS.some(({ name }) => String(item[name] || '').trim()))
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
      const normalizedItems = (form.items || [])
        .filter((line) => String(line.name || '').trim())
        .map((line, index) => ({
          name: String(line.name || '').trim(),
          quantity: numericValue(line.quantity) || 1,
          unit: String(line.unit || 'kom').trim() || 'kom',
          unit_price: numericValue(line.unit_price),
          total_amount: computeLineTotal(line),
          note: line.note || null,
          line_no: index + 1,
        }))
      const itemsTotal = normalizedItems.reduce((sum, line) => sum + numericValue(line.total_amount), 0)
      const payload = {
        date: form.date,
        due_date: form.due_date || null,
        invoice_number: modal === 'add' ? invoiceValue : invoiceValue || undefined,
        invoice_year: new Date(form.date).getFullYear(),
        client_id: toInt(form.client_id),
        contract_id: toInt(form.contract_id),
        contract_payment_type: form.contract_payment_type || null,
        project_id: toInt(form.project_id) ?? (unassignedProject ? unassignedProject.id : null),
        description: form.description || null,
        efaktura_contract_number: form.efaktura_contract_number?.trim() || null,
        efaktura_order_reference: form.efaktura_order_reference?.trim() || null,
        efaktura_framework_agreement_number: form.efaktura_framework_agreement_number?.trim() || null,
        efaktura_object_code: form.efaktura_object_code?.trim() || null,
        efaktura_buyer_reference: form.efaktura_buyer_reference?.trim() || null,
        efaktura_payment_reference: form.efaktura_payment_reference?.trim() || null,
        efaktura_payment_model: form.efaktura_payment_model?.trim() || null,
        amount_rsd: normalizedItems.length ? itemsTotal : parseFloat(form.amount_rsd) || 0,
        items: normalizedItems,
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
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const toggleSelectAll = () => {
    if (selectedIds.length >= filtered.length) setSelectedIds([])
    else setSelectedIds(filtered.map((item) => item.id))
  }

  const handleBulkAssign = async () => {
    if (selectedIds.length === 0) return
    const pid =
      assignProjectId === '' || assignProjectId === '_none'
        ? unassignedProject
          ? unassignedProject.id
          : null
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
    setPaymentError('')
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
    setPaymentError('')
  }

  const openDetail = (item) => {
    setDetailModal(item)
  }

  const openEditFromDetail = (item) => {
    setDetailModal(null)
    openEdit(item)
  }

  const openPaymentFromDetail = async (item) => {
    setDetailModal(null)
    await openPaymentModal(item)
  }

  const handleDeleteFromDetail = async (item) => {
    setDetailModal(null)
    await handleDelete(item)
  }

  const handleExportEfakturaXml = async (item) => {
    await api.income
      .exportEfakturaXml(item.id, `efaktura_${item.invoice_number || item.id}.xml`)
      .catch((error) => {
        setPageError(error.message || tr('loadError'))
        console.error(error)
      })
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

  const renderPaymentStatus = (item, compact = false) => {
    let badge
    if (item.status === 'cancelled') {
      return (
        <span className="badge" style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#fda4af' }}>
          {tr('cancelled')}
        </span>
      )
    }
    if (item.status === 'paid') {
      badge = (
        <span className="badge badge-success" title={`${tr('paid')}: ${item.paid_date || UI_DASH}`}>
          {tr('paid')}
        </span>
      )
    } else if (item.status === 'partial') {
      if (compact) {
        return (
          <span
            className="badge badge-info"
            title={`${tr('partial')}: ${(item.paid_amount || 0).toLocaleString('sr-RS')} / ${item.amount_rsd.toLocaleString('sr-RS')} RSD`}
          >
            {tr('partial')}
          </span>
        )
      }
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

    return badge
  }

  const invoiceDuplicate =
    modal === 'add' &&
    form.invoice_number?.trim() &&
    items.some((item) => item.invoice_number === form.invoice_number.trim())

  const exportCsv = () =>
    api.reports.downloadCsv(year, month || undefined).catch((error) => console.error(error))
  const exportPdf = () =>
    api.reports.downloadPdf(year, month || undefined).catch((error) => console.error(error))

  const unassignedProject = findUnassignedProject(projects)
  const unassignedProjectId = unassignedProject ? String(unassignedProject.id) : ''

  useEffect(() => {
    const incomeId = location.state?.openIncomeId
    if (!isActivePage || !incomeId) return
    api.income
      .get(incomeId)
      .then((item) => openEdit(item))
      .catch((error) => setPageError(error.message || tr('loadError')))
    navigate('/income', { replace: true, state: null })
    // openEdit intentionally uses the latest reference data already loaded by this page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActivePage, location.state?.openIncomeId, navigate])
  const selectedClientId = form.client_id ? String(form.client_id) : ''
  const incomeProjectFilter = useCallback(
    (project) => {
      if (!project) return false
      if (unassignedProjectId && String(project.id) === unassignedProjectId) return true
      if (!selectedClientId) return false
      return String(project.client_id || '') === selectedClientId
    },
    [selectedClientId, unassignedProjectId]
  )
  const incomeProjects = useMemo(() => projects.filter(incomeProjectFilter), [incomeProjectFilter, projects])
  const getProjectName = (projectId) => resolveProjectName(projects, projectId, '')
  const getContractsForProject = (projectId) => filterContractsForProject(contracts, projectId)
  const { updateProject: updateProjectBase, updateContract: updateContractBase } = useProjectContractForm({
    contracts,
    setForm,
  })

  const updateProject = (projectId) => {
    setForm((previous) => {
      const selectedContract = previous.contract_id
        ? contracts.find((contract) => String(contract.id) === String(previous.contract_id))
        : null
      const keepPaymentType =
        selectedContract &&
        (!projectId ||
          String(selectedContract.project_id) === String(projectId) ||
          selectedContract.project_id == null)
      return {
        ...previous,
        contract_payment_type: keepPaymentType ? previous.contract_payment_type : '',
      }
    })
    updateProjectBase(projectId)
  }

  useEffect(() => {
    if (!modal) return
    const currentProjectId = form.project_id == null ? '' : String(form.project_id)
    if (!currentProjectId) return
    const projectAllowed = incomeProjects.some((project) => String(project.id) === currentProjectId)
    if (projectAllowed) return
    setForm((previous) => {
      const previousProjectId = previous.project_id == null ? '' : String(previous.project_id)
      if (!previousProjectId || incomeProjects.some((project) => String(project.id) === previousProjectId)) {
        return previous
      }
      return {
        ...previous,
        project_id: unassignedProjectId,
        contract_id: '',
        contract_payment_type: '',
      }
    })
  }, [form.project_id, incomeProjects, modal, unassignedProjectId])

  const updateContract = (contractId) => {
    setForm((previous) => ({
      ...previous,
      contract_payment_type:
        String(previous.contract_id) === String(contractId) ? previous.contract_payment_type : '',
    }))
    updateContractBase(contractId)
  }

  const updateIncomeLine = (index, patch) => {
    setForm((previous) => {
      const lines = [...(previous.items || [])]
      const current = { ...(lines[index] || newIncomeLine()), ...patch }
      if ('quantity' in patch || 'unit_price' in patch) {
        const total = numericValue(current.quantity) * numericValue(current.unit_price)
        current.total_amount = total ? total.toFixed(2) : ''
      }
      lines[index] = current
      return { ...previous, items: lines }
    })
  }

  const addIncomeLine = (line = null) => {
    setForm((previous) => ({ ...previous, items: [...(previous.items || []), line || newIncomeLine()] }))
  }

  const removeIncomeLine = (index) => {
    if (activeLineIndex === index) {
      setActiveLineIndex(null)
      setItemSearchSuggestions([])
    } else if (activeLineIndex > index) {
      setActiveLineIndex(activeLineIndex - 1)
    }
    setForm((previous) => ({
      ...previous,
      items: (previous.items || []).filter((_, itemIndex) => itemIndex !== index),
    }))
  }

  const lineFromSuggestion = (suggestion) => ({
    name: suggestion.name || '',
    quantity: String(suggestion.quantity ?? 1),
    unit: suggestion.unit || 'kom',
    unit_price: String(suggestion.unit_price ?? ''),
    total_amount: String(suggestion.total_amount ?? ''),
    note: '',
  })

  const applySuggestedLine = (index, suggestion) => {
    const line = lineFromSuggestion(suggestion)
    setForm((previous) => {
      const lines = [...(previous.items || [])]
      lines[index] = line
      return { ...previous, items: lines }
    })
    setActiveLineIndex(null)
    setItemSearchSuggestions([])
  }

  const useSuggestedLine = (suggestion) => {
    const line = lineFromSuggestion(suggestion)
    setForm((previous) => {
      const lines = previous.items || []
      const firstEmpty = lines.findIndex((item) => !String(item.name || '').trim())
      if (firstEmpty >= 0) {
        const next = [...lines]
        next[firstEmpty] = line
        return { ...previous, items: next }
      }
      return { ...previous, items: [...lines, line] }
    })
  }

  const groupedSuggestions = (suggestionsList) =>
    [
      {
        key: 'client',
        items: (suggestionsList || []).filter((suggestion) => suggestion.match_scope === 'client'),
      },
      {
        key: 'global',
        items: (suggestionsList || []).filter((suggestion) => suggestion.match_scope !== 'client'),
      },
    ].filter((group) => group.items.length > 0)

  const suggestionGroupLabel = (scope) =>
    scope === 'client' ? tr('suggestionsThisClient') : tr('suggestionsAllClients')

  const suggestionMeta = (suggestion) =>
    [
      suggestion.client_name,
      suggestion.project_name,
      suggestion.invoice_number ? `${tr('invoiceNumber')} ${suggestion.invoice_number}` : null,
      suggestion.contract_number ? `${tr('contract')} ${suggestion.contract_number}` : null,
      suggestion.issued_date,
    ]
      .filter(Boolean)
      .join(' · ')

  const renderSuggestionGroups = (suggestionsList, onSelect, options = {}) =>
    groupedSuggestions(suggestionsList).map((group) => (
      <div key={group.key} className="income-suggestion-group">
        <div className="income-suggestion-group-title">{suggestionGroupLabel(group.key)}</div>
        <div className={options.dropdown ? 'income-suggestion-options' : 'income-sidebar-suggestion-list'}>
          {group.items.map((suggestion, suggestionIndex) => {
            const meta = suggestionMeta(suggestion)
            return (
              <button
                key={`${group.key}-${suggestion.source}-${suggestion.invoice_id || suggestion.contract_id || suggestionIndex}-${suggestion.name}-${suggestionIndex}`}
                type="button"
                className="income-suggestion-option"
                onMouseDown={options.dropdown ? (event) => event.preventDefault() : undefined}
                onClick={() => onSelect(suggestion)}
                title={meta}
              >
                <span className="income-suggestion-main">
                  <span className="income-suggestion-name">{suggestion.name}</span>
                  <span className="income-suggestion-price">
                    {Number(suggestion.unit_price || 0).toLocaleString('sr-RS')} RSD
                  </span>
                </span>
                {meta ? <span className="income-suggestion-meta">{meta}</span> : null}
              </button>
            )
          })}
        </div>
      </div>
    ))

  const invoiceLineTotal = useMemo(
    () => (form.items || []).reduce((sum, line) => sum + computeLineTotal(line), 0),
    [form.items]
  )

  const filteredContracts = useMemo(() => {
    const selectedProjectId = form.project_id ? parseInt(form.project_id, 10) : null
    return getContractsForProject(selectedProjectId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contracts, form.project_id])

  const filtered = useMemo(() => {
    const normalizedSearch = (search || '').trim().toLowerCase()
    let rows = items
    if (normalizedSearch) {
      rows = items.filter(
        (item) =>
          (item.client_name || '').toLowerCase().includes(normalizedSearch) ||
          (item.invoice_number || '').toLowerCase().includes(normalizedSearch) ||
          (item.description || '').toLowerCase().includes(normalizedSearch) ||
          amountSearchHay(item.amount_rsd).includes(normalizedSearch) ||
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, search, sortCol, sortAsc, projects])

  const selectedItems = useMemo(() => {
    if (selectedIds.length === 0) return []
    const selectedIdSet = new Set(selectedIds)
    return items.filter((item) => selectedIdSet.has(item.id))
  }, [items, selectedIds])

  const selectedTotal = useMemo(
    () => selectedItems.reduce((sum, item) => sum + Number(item.amount_rsd || 0), 0),
    [selectedItems]
  )

  return (
    <>
      <PageHeader
        title={tr('income')}
        actions={
          <>
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
            <button className="btn btn-secondary" onClick={exportCsv}>
              {tr('exportKpo')} CSV
            </button>
            <button className="btn btn-secondary" onClick={exportPdf}>
              {tr('exportKpo')} PDF
            </button>
            <button className="btn btn-primary" onClick={openAdd}>
              {tr('add')}
            </button>
          </>
        }
      />

      <div className="page-body">
        {pageError && (
          <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
            {pageError}
          </div>
        )}
        <div className="card">
          <div className="table-wrap">
            <table className="income-list-table">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>
                    <input
                      type="checkbox"
                      checked={filtered.length > 0 && selectedIds.length >= filtered.length}
                      onChange={toggleSelectAll}
                    />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>
                    {tr('date')} <SortIndicator active={sortCol === 'date'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('invoice_number')}>
                    {tr('invoiceNumber')}{' '}
                    <SortIndicator active={sortCol === 'invoice_number'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('client_name')}>
                    {tr('client')} <SortIndicator active={sortCol === 'client_name'} asc={sortAsc} />
                  </th>
                  <th>{tr('description')}</th>
                  <th
                    style={{ textAlign: 'right', cursor: 'pointer' }}
                    onClick={() => toggleSort('amount_rsd')}
                  >
                    {tr('amount')} <SortIndicator active={sortCol === 'amount_rsd'} asc={sortAsc} />
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6}>{tr('loading')}</td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ color: 'var(--color-text-muted)' }}>
                      {tr('noRecords')}
                    </td>
                  </tr>
                ) : (
                  filtered.map((item) => (
                    <tr
                      key={item.id}
                      className={`record-row ${selectedIds.includes(item.id) ? 'record-row-selected' : ''} ${item.status === 'cancelled' ? 'row-reversal' : ''}`.trim()}
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
                      <td className="income-list-date-cell">
                        <div className="income-date-primary">{item.date || UI_DASH}</div>
                        <div className="income-date-secondary">
                          {item.due_date
                            ? `${tr('valuta')}: ${item.due_date}`
                            : `${tr('valuta')}: ${UI_DASH}`}
                        </div>
                      </td>
                      <td className="income-list-document-cell">
                        <div className="income-document-number">{item.invoice_number || UI_DASH}</div>
                        <div className="income-document-meta">
                          {item.status === 'paid' && item.paid_date
                            ? `${tr('paid')}: ${item.paid_date}`
                            : `${tr('status')}: ${tr(item.status || 'unpaid')}`}
                        </div>
                      </td>
                      <td className="income-list-party-cell">
                        <div className="income-party-name" title={item.client_name || UI_DASH}>
                          {item.client_name || UI_DASH}
                        </div>
                        <div className="income-meta-chips">
                          <span
                            className="income-meta-chip"
                            title={getProjectName(item.project_id) || UI_DASH}
                          >
                            {getProjectName(item.project_id) || UI_DASH}
                          </span>
                          {item.contract_number ? (
                            <span className="income-meta-chip" title={item.contract_number}>
                              {item.contract_number}
                            </span>
                          ) : null}
                          {item.contract_payment_type ? (
                            <span className="income-meta-chip income-meta-chip-accent">
                              {tr(
                                PAYMENT_TYPE_KEYS[item.contract_payment_type] || item.contract_payment_type
                              )}
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td className="income-list-description-cell">
                        <div className="income-description-text" title={item.description || UI_DASH}>
                          {item.description || UI_DASH}
                        </div>
                      </td>
                      <td className="income-list-amount-cell">
                        <div className="income-amount-value">
                          {item.amount_rsd.toLocaleString('sr-RS')} RSD
                        </div>
                        <div className="income-amount-status">{renderPaymentStatus(item, true)}</div>
                        {item.status === 'partial' ? (
                          <div className="income-amount-meta">
                            +{(item.paid_amount || 0).toLocaleString('sr-RS')} /{' '}
                            {item.amount_rsd.toLocaleString('sr-RS')}
                          </div>
                        ) : null}
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
        items={[{ label: tr('selectedAmount'), value: `${formatMoney(selectedTotal)} RSD` }]}
        actions={
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
        }
        onClear={() => setSelectedIds([])}
      />

      <EntityDetailModal
        isOpen={!!detailModal}
        onClose={() => setDetailModal(null)}
        title={
          detailModal
            ? `${tr('income')} ${UI_DASH} ${detailModal.invoice_number || `#${detailModal.id}`}`
            : ''
        }
        maxWidth="860px"
        details={
          detailModal ? (
            <div className="record-field-grid">
              <div className="record-field">
                <span className="record-field-label">{tr('date')}</span>
                <span className="record-field-value">{detailModal.date || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('valuta')}</span>
                <span className="record-field-value">{detailModal.due_date || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('amount')}</span>
                <span className="record-field-value">
                  {Number(detailModal.amount_rsd || 0).toLocaleString('sr-RS')} RSD
                </span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('status')}</span>
                <div>{renderPaymentStatus(detailModal)}</div>
              </div>
              <div className="record-field full">
                <span className="record-field-label">{tr('client')}</span>
                <span className="record-field-value">{detailModal.client_name || UI_DASH}</span>
              </div>
              <div className="record-field full">
                <span className="record-field-label">{tr('contracts')}</span>
                <span className="record-field-value">{detailModal.contract_number || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('project')}</span>
                <span className="record-field-value">
                  {getProjectName(detailModal.project_id) || UI_DASH}
                </span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('incomeType')}</span>
                <span className="record-field-value">
                  {detailModal.contract_payment_type
                    ? tr(
                        PAYMENT_TYPE_KEYS[detailModal.contract_payment_type] ||
                          detailModal.contract_payment_type
                      )
                    : UI_DASH}
                </span>
              </div>
              <div className="record-field full">
                <span className="record-field-label">{tr('description')}</span>
                <div className="record-field-text">{detailModal.description || UI_DASH}</div>
              </div>
              {EFAKTURA_REFERENCE_FIELDS.map(({ name, label }) =>
                detailModal[name] ? (
                  <div className="record-field" key={name}>
                    <span className="record-field-label">{tr(label)}</span>
                    <span className="record-field-value">{detailModal[name]}</span>
                  </div>
                ) : null
              )}
              {detailModal.items?.length ? (
                <div className="record-field full">
                  <span className="record-field-label">{tr('invoiceItems')}</span>
                  <div className="table-wrap" style={{ marginTop: '0.4rem' }}>
                    <table>
                      <thead>
                        <tr>
                          <th style={{ width: 42 }}>#</th>
                          <th>{tr('name')}</th>
                          <th style={{ textAlign: 'right' }}>{tr('quantity')}</th>
                          <th>{tr('unit')}</th>
                          <th style={{ textAlign: 'right' }}>{tr('unitPrice')}</th>
                          <th style={{ textAlign: 'right' }}>{tr('total')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detailModal.items.map((line, index) => (
                          <tr key={line.id || line.line_no}>
                            <td>{line.line_no || index + 1}</td>
                            <td>{line.name}</td>
                            <td style={{ textAlign: 'right' }}>
                              {Number(line.quantity || 0).toLocaleString('sr-RS')}
                            </td>
                            <td>{line.unit || 'kom'}</td>
                            <td style={{ textAlign: 'right' }}>
                              {Number(line.unit_price || 0).toLocaleString('sr-RS')}
                            </td>
                            <td style={{ textAlign: 'right' }}>
                              {Number(line.total_amount || 0).toLocaleString('sr-RS')} RSD
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
              <div className="record-field full">
                <span className="record-field-label">{tr('note')}</span>
                <div className="record-field-text">{detailModal.note || UI_DASH}</div>
              </div>
            </div>
          ) : null
        }
        actions={
          detailModal ? (
            <div className="record-actions-grid">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => openPaymentFromDetail(detailModal)}
              >
                {tr('incomePaymentDetails')}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => handleExportEfakturaXml(detailModal)}
              >
                {tr('exportEfakturaXml')}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={detailModal.status === 'cancelled'}
                onClick={() => openEditFromDetail(detailModal)}
              >
                {tr('edit')}
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={() => handleDeleteFromDetail(detailModal)}
              >
                {tr('delete')}
              </button>
            </div>
          ) : null
        }
      />

      <Modal
        isOpen={!!paymentModal}
        onClose={closePaymentModal}
        title={paymentModal ? `${tr('incomePaymentDetails')} ${UI_DASH} ${paymentModal.invoice_number}` : ''}
        maxWidth="760px"
      >
        {paymentModal ? (
          <>
            <div className="card" style={{ marginBottom: '1rem', padding: '0.75rem 1rem' }}>
              <div style={{ fontWeight: 700 }}>{paymentModal.client_name || UI_DASH}</div>
              <div style={{ color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
                {paymentModal.description || UI_DASH}
              </div>
              <div style={{ marginTop: '0.5rem', fontWeight: 700 }}>
                {paymentModal.amount_rsd.toLocaleString('sr-RS')} RSD
              </div>
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
                  <div
                    style={{
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      color: 'var(--color-text-muted)',
                      marginBottom: '0.5rem',
                      textTransform: 'uppercase',
                    }}
                  >
                    {tr('incomeLinkedBankPayments')}
                  </div>
                  {paymentDetails?.linked_transactions?.length ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                      {paymentDetails.linked_transactions.map((transaction) => (
                        <div
                          key={transaction.id}
                          className="card"
                          style={{
                            padding: '0.75rem',
                            display: 'flex',
                            justifyContent: 'space-between',
                            gap: '0.75rem',
                            alignItems: 'flex-start',
                          }}
                        >
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontWeight: 700 }}>
                              {Number(transaction.amount || 0).toLocaleString('sr-RS')}{' '}
                              {transaction.currency || 'RSD'}
                            </div>
                            {transaction.transaction_amount != null &&
                            Number(transaction.transaction_amount || 0) !==
                              Number(transaction.amount || 0) ? (
                              <div
                                style={{
                                  fontSize: '0.8rem',
                                  color: 'var(--color-text-muted)',
                                  marginTop: '0.2rem',
                                }}
                              >
                                {tr('incomePaymentTransactionTotal')}:{' '}
                                {Number(transaction.transaction_amount || 0).toLocaleString('sr-RS')}{' '}
                                {transaction.currency || 'RSD'}
                              </div>
                            ) : null}
                            <div
                              style={{
                                fontSize: '0.85rem',
                                color: 'var(--color-text-muted)',
                                marginTop: '0.25rem',
                              }}
                            >
                              {transaction.date}
                            </div>
                            <div style={{ marginTop: '0.35rem' }}>
                              {transaction.counterparty_name || UI_DASH}
                            </div>
                            <div
                              style={{
                                fontSize: '0.85rem',
                                color: 'var(--color-text-muted)',
                                marginTop: '0.25rem',
                              }}
                            >
                              {transaction.purpose || UI_DASH}
                            </div>
                            {transaction.link_kind === 'allocation' && transaction.allocation_count > 1 ? (
                              <div
                                style={{
                                  fontSize: '0.8rem',
                                  color: 'var(--color-text-muted)',
                                  marginTop: '0.25rem',
                                }}
                              >
                                {tr('incomePaymentEditInBank')}
                              </div>
                            ) : null}
                            {transaction.bank_reference ? (
                              <div
                                style={{
                                  fontSize: '0.8rem',
                                  color: 'var(--color-text-muted)',
                                  marginTop: '0.25rem',
                                }}
                              >
                                {tr('bankTxReference')}: {transaction.bank_reference}
                              </div>
                            ) : null}
                          </div>
                          {transaction.can_unlink ? (
                            <button
                              type="button"
                              className="btn btn-sm btn-danger"
                              onClick={() => handleUnlinkIncomePayment(transaction.id)}
                              disabled={paymentActionLoading}
                            >
                              {paymentActionLoading ? tr('loading') : tr('bankTxUnmatchBtn')}
                            </button>
                          ) : (
                            <div
                              style={{
                                fontSize: '0.8rem',
                                color: 'var(--color-text-muted)',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {tr('incomePaymentEditInBank')}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
                      {tr('incomeNoLinkedPayments')}
                    </div>
                  )}
                </div>
                {paymentDetails?.has_manual_payment && (
                  <div className="card" style={{ padding: '1rem', borderColor: 'var(--color-warning)' }}>
                    <div
                      style={{
                        fontSize: '0.78rem',
                        fontWeight: 700,
                        color: 'var(--color-text-muted)',
                        marginBottom: '0.5rem',
                        textTransform: 'uppercase',
                      }}
                    >
                      {tr('incomeManualPaymentMark')}
                    </div>
                    <div
                      style={{
                        color: 'var(--color-text-muted)',
                        fontSize: '0.9rem',
                        marginBottom: '0.75rem',
                      }}
                    >
                      {tr('incomeManualPaymentHint')}
                    </div>
                    <div>
                      {tr('amount')}: {Number(paymentDetails.manual_paid_amount || 0).toLocaleString('sr-RS')}{' '}
                      RSD
                    </div>
                    <div style={{ marginTop: '0.25rem' }}>
                      {tr('dateOfPayment')}: {paymentDetails.manual_paid_date || UI_DASH}
                    </div>
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
          </>
        ) : null}
      </Modal>

      <Modal
        isOpen={!!modal}
        onClose={closeModal}
        title={modal === 'add' ? tr('add') : tr('edit')}
        maxWidth="1280px"
        style={{ width: 'min(1280px, 96vw)', height: 'min(920px, 96vh)' }}
        bodyClassName="income-modal-body"
      >
        {modal ? (
          <form
            className={`income-modal-form ${itemSuggestions.length > 0 ? 'has-sidebar' : ''}`.trim()}
            onSubmit={handleSubmit}
          >
            <div className="income-modal-main">
              <div className="income-form-grid income-form-grid-dates">
                <div className="form-group">
                  <label className="form-label">{tr('date')}</label>
                  <DatePicker
                    value={form.date}
                    onChange={(value) => setForm({ ...form, date: value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('valuta')}</label>
                  <DatePicker
                    value={form.due_date}
                    onChange={(value) => setForm({ ...form, due_date: value })}
                  />
                </div>
              </div>
              <div className="form-group form-group-compact">
                <label className="form-label">{tr('invoiceNumber')}</label>
                {modal === 'add' && (
                  <div
                    style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}
                  >
                    {nextInvoiceHint
                      ? `${tr('suggestedNext')}: ${nextInvoiceHint}. ${tr('invoiceYearHint')}`
                      : tr('invoiceYearHint')}
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
              <div className="income-form-grid">
                <div className="form-group">
                  <label className="form-label">{tr('client')}</label>
                  <select
                    className="form-input"
                    value={form.client_id}
                    onChange={(event) => {
                      const id = event.target.value ? parseInt(event.target.value, 10) : ''
                      setForm({ ...form, client_id: id, contract_id: '', contract_payment_type: '' })
                    }}
                    required
                  >
                    <option value="">{`${UI_DASH} ${tr('selectClient')} ${UI_DASH}`}</option>
                    {clients.map((client) => (
                      <option key={client.id} value={client.id}>
                        {client.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="income-form-grid">
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
                        <option key={contract.id} value={contract.id}>
                          {buildContractLabel(contract)} {UI_DASH} {contract.client_name} (
                          {contract.amount?.toLocaleString?.('sr-RS')} RSD)
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="form-group">
                  <label className="form-label">{tr('project')}</label>
                  <ProjectSelect
                    projects={incomeProjects}
                    value={form.project_id}
                    onChange={updateProject}
                    required
                    projectFilter={incomeProjectFilter}
                  />
                </div>
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
              <details
                className="income-efaktura-fields"
                open={efakturaFieldsOpen}
                onToggle={(event) => setEfakturaFieldsOpen(event.currentTarget.open)}
              >
                <summary>{tr('efakturaAdditionalFields')}</summary>
                <div className="income-efaktura-fields-grid">
                  {EFAKTURA_REFERENCE_FIELDS.map(({ name, label, maxLength }) => (
                    <div className="form-group" key={name}>
                      <label className="form-label">{tr(label)}</label>
                      <input
                        type="text"
                        className="form-input"
                        value={form[name]}
                        maxLength={maxLength}
                        onChange={(event) => setForm({ ...form, [name]: event.target.value })}
                      />
                    </div>
                  ))}
                </div>
              </details>
              <div className="form-group">
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: '0.75rem',
                    alignItems: 'center',
                    marginBottom: '0.5rem',
                  }}
                >
                  <label className="form-label" style={{ margin: 0 }}>
                    {tr('invoiceItems')}
                  </label>
                  <button type="button" className="btn btn-sm btn-secondary" onClick={() => addIncomeLine()}>
                    {tr('addLine')}
                  </button>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th style={{ width: 42 }}>#</th>
                        <th>{tr('name')}</th>
                        <th style={{ width: 95 }}>{tr('quantity')}</th>
                        <th style={{ width: 80 }}>{tr('unit')}</th>
                        <th style={{ width: 120 }}>{tr('unitPrice')}</th>
                        <th style={{ width: 125 }}>{tr('total')}</th>
                        <th style={{ width: 54 }}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {(form.items || []).length ? (
                        (form.items || []).map((line, index) => (
                          <tr key={index}>
                            <td className="income-line-number">{index + 1}</td>
                            <td>
                              <div
                                className="income-item-name-field"
                                onBlur={(event) => {
                                  if (event.currentTarget.contains(event.relatedTarget)) return
                                  closeItemSearchSuggestions(index)
                                }}
                              >
                                <input
                                  type="text"
                                  className="form-input"
                                  value={line.name}
                                  onFocus={() => setActiveLineIndex(index)}
                                  onKeyDown={(event) => {
                                    if (event.key === 'Escape') {
                                      event.preventDefault()
                                      closeItemSearchSuggestions(index)
                                    }
                                  }}
                                  onChange={(event) => updateIncomeLine(index, { name: event.target.value })}
                                  placeholder={tr('invoiceItemName')}
                                />
                                {activeLineIndex === index && itemSearchSuggestions.length > 0 ? (
                                  <div className="income-item-suggestion-dropdown">
                                    {renderSuggestionGroups(
                                      itemSearchSuggestions,
                                      (suggestion) => applySuggestedLine(index, suggestion),
                                      { dropdown: true }
                                    )}
                                  </div>
                                ) : null}
                              </div>
                            </td>
                            <td>
                              <input
                                type="number"
                                step="0.001"
                                className="form-input"
                                value={line.quantity}
                                onChange={(event) =>
                                  updateIncomeLine(index, { quantity: event.target.value })
                                }
                              />
                            </td>
                            <td>
                              <select
                                className="form-input"
                                value={line.unit}
                                onChange={(event) => updateIncomeLine(index, { unit: event.target.value })}
                              >
                                {unitOptionsForLine(line.unit).map((unit) => (
                                  <option key={unit} value={unit}>
                                    {unit}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td>
                              <input
                                type="number"
                                step="0.01"
                                className="form-input"
                                value={line.unit_price}
                                onChange={(event) =>
                                  updateIncomeLine(index, { unit_price: event.target.value })
                                }
                              />
                            </td>
                            <td>
                              <div className="income-calculated-field income-line-total">
                                {formatMoney(computeLineTotal(line))}
                              </div>
                            </td>
                            <td>
                              <button
                                type="button"
                                className="btn btn-sm btn-danger"
                                onClick={() => removeIncomeLine(index)}
                              >
                                {UI_CLOSE}
                              </button>
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={7} style={{ color: 'var(--color-text-muted)' }}>
                            {tr('invoiceNoItems')}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="income-invoice-total-row">
                  <div className="income-invoice-total-label">{tr('amount')}</div>
                  <div>
                    <div className="income-calculated-field income-invoice-total">
                      {formatMoney(invoiceLineTotal || form.amount_rsd)} RSD
                    </div>
                    <div className="income-invoice-total-hint">{tr('amountFromInvoiceItems')}</div>
                  </div>
                </div>
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
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={closeModal}
                  disabled={submitting}
                >
                  {tr('cancel')}
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  style={{ display: 'flex', alignItems: 'center' }}
                  disabled={submitting}
                >
                  {tr('save')}
                </button>
              </div>
            </div>
            {itemSuggestions.length > 0 ? (
              <aside className="income-suggestion-sidebar">
                <div className="income-suggestion-sidebar-title">{tr('previousInvoiceItems')}</div>
                {renderSuggestionGroups(itemSuggestions, useSuggestedLine)}
              </aside>
            ) : null}
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
        closeOnOverlay
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
            <div className="modal-actions" style={{ padding: '0 1rem 1rem' }}>
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
