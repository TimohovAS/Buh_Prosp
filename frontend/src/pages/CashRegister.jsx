import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
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

function fmtAmount(value) {
  return Number(value || 0).toLocaleString('sr-RS')
}

function buildContractLabel(contract) {
  if (!contract) return ''
  const parts = []
  if (contract.number) parts.push(contract.number)
  if (contract.subject) parts.push(contract.subject)
  return parts.join(` ${UI_DASH} `) || contract.number || contract.subject || ''
}

function buildBankLabel(item) {
  const parts = [item.counterparty_name, item.purpose, item.bank_reference].filter(Boolean)
  return parts.join(` ${UI_DASH} `) || UI_DASH
}

function isSalaryCategory(category) {
  const sr = String(category?.name_sr || '').trim().toLowerCase()
  const ru = String(category?.name_ru || '').trim().toLowerCase()
  return sr === 'zarade' || sr.includes('zarad') || ru.includes('зарп')
}

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

export default function CashRegister() {
  const location = useLocation()
  const isActivePage = location.pathname === '/cash'
  const currentYear = new Date().getFullYear()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [pageError, setPageError] = useState('')
  const [year, setYear] = useState('')
  const [availableYears, setAvailableYears] = useState([currentYear])
  const [month, setMonth] = useState('')
  const [search, setSearch] = useState('')
  const [sortCol, setSortCol] = useState('date')
  const [sortAsc, setSortAsc] = useState(false)
  const [summary, setSummary] = useState({ current_balance: 0, total_in: 0, total_out: 0, entries: [], available_withdrawals: [] })
  const [projects, setProjects] = useState([])
  const [contracts, setContracts] = useState([])
  const [categories, setCategories] = useState([])
  const [bankModalOpen, setBankModalOpen] = useState(false)
  const [expenseModal, setExpenseModal] = useState(null)
  const [adjustmentModal, setAdjustmentModal] = useState(null)
  const [withdrawalModal, setWithdrawalModal] = useState(null)
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

  const lang = getLang()
  const unassignedProject = projects.find((project) => project.code === 'INT-UNASSIGNED') || null
  const salaryProject = projects.find((project) => project.code === 'INT-SALARY') || null
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
    ])
      .then(([cashSummary, years, projectList, categoryList, contractList]) => {
        setSummary(cashSummary)
        setAvailableYears(years?.length ? years : [currentYear])
        setProjects(projectList)
        setCategories(categoryList)
        setContracts(contractList)
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

  useEffect(() => {
    if (availableYears.length === 0) return
    if (year !== '' && !availableYears.includes(year)) {
      setYear(availableYears[0])
    }
  }, [availableYears, year])

  const getCategoryLabel = (categoryId) => {
    const selectedCategory = categories.find((item) => item.id === categoryId)
    if (!selectedCategory) return UI_DASH
    return lang === 'ru' ? selectedCategory.name_ru : selectedCategory.name_sr
  }
  const getCategoryById = (categoryId) => categories.find((item) => String(item.id) === String(categoryId)) || null
  const getCategoryDefaultProjectId = (categoryId) => {
    const category = getCategoryById(categoryId)
    return category?.default_project_id ? String(category.default_project_id) : ''
  }
  const getForcedExpenseProjectId = (categoryId) => {
    const category = getCategoryById(categoryId)
    const defaultProjectId = category?.default_project_id ? String(category.default_project_id) : ''
    if (defaultProjectId) return defaultProjectId
    if (isSalaryCategory(category) && salaryProject) return String(salaryProject.id)
    return ''
  }

  const getEntryTypeLabel = (entry) => {
    if (entry.entry_type === 'withdrawal') return tr('cashEntryTypeWithdrawal')
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

  const getContractsForProject = (projectId) => contracts
    .filter((contract) => contract.project_id === projectId || contract.project_id == null)
    .sort((left, right) => {
      const leftRank = left.project_id === projectId ? 0 : 1
      const rightRank = right.project_id === projectId ? 0 : 1
      if (leftRank !== rightRank) return leftRank - rightRank
      return buildContractLabel(left).localeCompare(buildContractLabel(right), 'sr')
    })

  const expenseContracts = useMemo(() => {
    const effectiveProjectId = getForcedExpenseProjectId(expenseForm.category_id) || expenseForm.project_id || ''
    const selectedProjectId = effectiveProjectId ? parseInt(effectiveProjectId, 10) : null
    return selectedProjectId ? getContractsForProject(selectedProjectId) : []
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
    return selectedProjectId ? getContractsForProject(selectedProjectId) : []
  }, [contracts, withdrawalForm.project_id])

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

  const SortIcon = ({ col }) => {
    if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 4 }}>{UI_SORT_BOTH}</span>
    return <span style={{ marginLeft: 4 }}>{sortAsc ? UI_SORT_ASC : UI_SORT_DESC}</span>
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
      if (!contractId) return { ...previous, contract_id: '' }
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
      const forcedProjectId = getForcedExpenseProjectId(categoryId)
      return {
        ...previous,
        category_id: categoryId,
        project_id: forcedProjectId || previous.project_id,
        contract_id: forcedProjectId ? '' : previous.contract_id,
      }
    })
  }

  const updateWithdrawalProject = (projectId) => {
    setWithdrawalForm((previous) => {
      const selectedContract = previous.contract_id ? contracts.find((contract) => String(contract.id) === String(previous.contract_id)) : null
      const keepContract = selectedContract && String(selectedContract.project_id) === String(projectId)
      return {
        ...previous,
        project_id: projectId,
        contract_id: keepContract ? previous.contract_id : '',
      }
    })
  }

  const updateWithdrawalContract = (contractId) => {
    setWithdrawalForm((previous) => {
      if (!contractId) return { ...previous, contract_id: '' }
      const selectedContract = contracts.find((contract) => String(contract.id) === String(contractId))
      return {
        ...previous,
        contract_id: contractId,
        project_id: selectedContract?.project_id ? String(selectedContract.project_id) : previous.project_id,
      }
    })
  }

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

  const openEditEntry = (entry) => {
    if (entry.entry_type === 'expense') {
      openExpenseEdit(entry)
      return
    }
    if (entry.entry_type === 'adjustment') {
      openAdjustmentEdit(entry)
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

  return (
    <>
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">{tr('cashRegisterTitle')}</h1>
          <p className="page-subtitle">{tr('cashRegisterHint')}</p>
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
          <SearchInput
            placeholder={tr('search')}
            value={search}
            onChange={setSearch}
            style={{ width: 220 }}
          />
          <button className="btn btn-secondary" onClick={() => setBankModalOpen(true)}>{tr('cashAddFromBank')}</button>
          <button className="btn btn-secondary" onClick={openAdjustmentCreate}>{tr('cashAddAdjustment')}</button>
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
                      <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIcon col="date" /></th>
                      <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('entry_type')}>{tr('cashEntryType')} <SortIcon col="entry_type" /></th>
                      <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('description')}>{tr('description')} <SortIcon col="description" /></th>
                      <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('source')}>{tr('cashSource')} <SortIcon col="source" /></th>
                      <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('inflow')}>{tr('cashflowInflow')} <SortIcon col="inflow" /></th>
                      <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('outflow')}>{tr('cashflowOutflow')} <SortIcon col="outflow" /></th>
                      <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('balance_after')}>{tr('cashBalanceAfter')} <SortIcon col="balance_after" /></th>
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
                    <span className="record-field-value">{buildContractLabel(contracts.find((contract) => contract.id === detailModal.contract_id)) || UI_DASH}</span>
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
                <select className="form-input" value={expenseForm.contract_id} onChange={(event) => updateExpenseContract(event.target.value)} disabled={!expenseForm.project_id}>
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
            <select className="form-input" value={withdrawalForm.contract_id} onChange={(event) => updateWithdrawalContract(event.target.value)} disabled={!withdrawalForm.project_id}>
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
