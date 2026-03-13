import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { getLang, tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
const UI_DASH = '\u2014'
const UI_CLOSE = '\u00D7'
const UI_SORT_BOTH = '\u2195'
const UI_SORT_ASC = '\u2191'
const UI_SORT_DESC = '\u2193'
const DUPLICATE_DISMISS_STORAGE_KEY = 'expenses_duplicate_dismissed_v1'
function buildContractLabel(contract) {
  if (!contract) return ''
  const parts = []
  if (contract.number) parts.push(contract.number)
  if (contract.subject) parts.push(contract.subject)
  return parts.join(` ${UI_DASH} `) || contract.number || contract.subject || ''
}

function getDuplicateGroupKey(group) {
  const itemIds = (group.items || []).map((item) => item.id).sort((left, right) => left - right).join(',')
  return [group.reason, group.payment_reference || '', group.description || '', group.amount || 0, itemIds].join('|')
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

export default function Expenses() {
  const navigate = useNavigate()
  const currentYear = new Date().getFullYear()
  const [items, setItems] = useState([])
  const [duplicateGroups, setDuplicateGroups] = useState([])
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
  const [contracts, setContracts] = useState([])
  const [categories, setCategories] = useState([])
  const [assignProjectId, setAssignProjectId] = useState('')
  const [pageError, setPageError] = useState('')
  const [mergeKeepId, setMergeKeepId] = useState(null)
  const [dismissedDuplicateGroups, setDismissedDuplicateGroups] = useState(() => loadDismissedDuplicateGroups())
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    description: '',
    amount: '',
    category: '',
    category_id: '',
    project_id: '',
    contract_id: '',
    note: '',
  })

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
        setAvailableYears(years?.length ? years : [currentYear])
      })
      .catch((error) => {
        setItems([])
        setDuplicateGroups([])
        setPageError(error.message || tr('loadError'))
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [year, month])

  useEffect(() => {
    if (availableYears.length === 0) return
    if (year !== '' && !availableYears.includes(year)) {
      setYear(availableYears[0])
    }
  }, [availableYears, year])

  useEffect(() => {
    Promise.all([
      api.projects.list({ show_archived: true }),
      api.categories.list({ category_type: 'expense' }),
      api.contracts.list({ limit: 500 }),
    ])
      .then(([projectList, categoryList, contractList]) => {
        setProjects(projectList)
        setCategories(categoryList)
        setContracts(contractList)
      })
      .catch((error) => setPageError(error.message || tr('loadError')))
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(DUPLICATE_DISMISS_STORAGE_KEY, JSON.stringify(dismissedDuplicateGroups))
  }, [dismissedDuplicateGroups])

  const lang = getLang()
  const unassignedProject = projects.find((project) => project.code === 'INT-UNASSIGNED') || null

  const getProjectName = (projectId) => projects.find((project) => project.id === projectId)?.name || ''
  const getContractLabel = (contractId) => buildContractLabel(contracts.find((contract) => contract.id === contractId))
  const getContractsForProject = (projectId) => contracts
    .filter((contract) => contract.project_id === projectId || contract.project_id == null)
    .sort((left, right) => {
      const leftRank = left.project_id === projectId ? 0 : 1
      const rightRank = right.project_id === projectId ? 0 : 1
      if (leftRank !== rightRank) return leftRank - rightRank
      return buildContractLabel(left).localeCompare(buildContractLabel(right), 'sr')
    })

  const getCategoryLabel = (item) => {
    const selectedCategory = categories.find((category) => category.id === item.category_id)
    if (selectedCategory) {
      return lang === 'ru' ? selectedCategory.name_ru : selectedCategory.name_sr
    }
    return item.category || UI_DASH
  }

  const openExpenseSource = (item) => {
    const expenseDate = item?.date ? new Date(`${item.date}T12:00:00`) : null
    const expenseYear = expenseDate && !Number.isNaN(expenseDate.getTime()) ? expenseDate.getFullYear() : ''
    const expenseMonth = expenseDate && !Number.isNaN(expenseDate.getTime()) ? String(expenseDate.getMonth() + 1).padStart(2, '0') : ''
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
      const params = new URLSearchParams()
      if (expenseYear) params.set('year', String(expenseYear))
      if (expenseMonth) params.set('month', expenseMonth)
      params.set('direction', 'out')
      params.set('search', reference)
      navigate(`/bank?${params.toString()}`)
    }
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
    const projectId = assignProjectId === '' || assignProjectId === '_none'
      ? (unassignedProject ? unassignedProject.id : null)
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

  const openAdd = () => {
    setForm({
      date: new Date().toISOString().slice(0, 10),
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

  const openEdit = (item) => {
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
    setPageError('')
    setModal({ type: 'edit', id: item.id })
  }

  const updateProject = (projectId) => {
    setForm((previous) => {
      const selectedContract = previous.contract_id ? contracts.find((contract) => String(contract.id) === String(previous.contract_id)) : null
      const keepContract = selectedContract && String(selectedContract.project_id) === String(projectId)
      return {
        ...previous,
        project_id: projectId,
        contract_id: keepContract ? previous.contract_id : '',
      }
    })
  }

  const updateContract = (contractId) => {
    setForm((previous) => {
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

  const handleSubmit = async (event) => {
    event.preventDefault()
    setPageError('')
    try {
      const categoryValue = form.category?.trim() || null
      const payload = {
        date: form.date,
        description: form.description.trim(),
        amount: parseFloat(form.amount) || 0,
        category: categoryValue,
        category_id: form.category_id ? parseInt(form.category_id, 10) : null,
        project_id: form.project_id ? parseInt(form.project_id, 10) : (unassignedProject ? unassignedProject.id : null),
        contract_id: form.contract_id ? parseInt(form.contract_id, 10) : null,
        note: form.note || null,
      }
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
    setDismissedDuplicateGroups((previous) => previous.includes(groupKey) ? previous : [...previous, groupKey])
  }

  const visibleDuplicateGroups = useMemo(
    () => duplicateGroups.filter((group) => !dismissedDuplicateGroups.includes(getDuplicateGroupKey(group))),
    [dismissedDuplicateGroups, duplicateGroups],
  )

  const filteredContracts = useMemo(() => {
    const selectedProjectId = form.project_id ? parseInt(form.project_id, 10) : null
    return selectedProjectId ? getContractsForProject(selectedProjectId) : []
  }, [contracts, form.project_id])

  const filtered = useMemo(() => {
    const normalizedSearch = (search || '').trim().toLowerCase()
    let rows = items
    if (normalizedSearch) {
      rows = items.filter((item) =>
        (item.description || '').toLowerCase().includes(normalizedSearch) ||
        getCategoryLabel(item).toLowerCase().includes(normalizedSearch) ||
        String(item.amount || '').includes(normalizedSearch) ||
        getProjectName(item.project_id).toLowerCase().includes(normalizedSearch) ||
        getContractLabel(item.contract_id).toLowerCase().includes(normalizedSearch) ||
        String(item.bank_reference || '').toLowerCase().includes(normalizedSearch)
      )
    }
    return [...rows].sort((left, right) => {
      const leftValue = sortCol === 'project_id'
        ? getProjectName(left.project_id)
        : sortCol === 'contract_id'
          ? getContractLabel(left.contract_id)
          : sortCol === 'category'
            ? getCategoryLabel(left)
            : (left[sortCol] ?? '')
      const rightValue = sortCol === 'project_id'
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
  }, [items, search, sortCol, sortAsc, contracts, projects, categories, lang])

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

  const total = filtered.reduce((sum, item) => sum + item.amount, 0)

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
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const filename = `expenses${year ? `_${year}` : ''}${month ? `_${String(month).padStart(2, '0')}` : ''}.csv`
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">{tr('expenses')}</h1>
        </div>
        <div className="page-header-actions">
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
          <select className="form-input" style={{ width: 'auto' }} value={year} onChange={(event) => { const nextYear = event.target.value ? parseInt(event.target.value, 10) : ''; setYear(nextYear); if (!event.target.value) setMonth('') }}>
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
          <button className="btn btn-secondary" onClick={handleExportCsv} disabled={loading || filtered.length === 0}>
            {tr('download')} CSV
          </button>
          <button className="btn btn-primary" onClick={openAdd}>{tr('add')}</button>
        </div>
      </div>

      <div className="page-body">
        {pageError && (
          <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
            {pageError}
          </div>
        )}

        {visibleDuplicateGroups.length > 0 && (
          <div className="card" style={{ marginBottom: '1rem', borderColor: 'var(--color-warning)' }}>
            <div style={{ padding: '1rem 1rem 0.5rem', fontWeight: 700 }}>{tr('expenseDuplicatesTitle')}</div>
            <div style={{ padding: '0 1rem 1rem', color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
              {tr('expenseDuplicatesHint')}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', padding: '0 1rem 1rem' }}>
              {visibleDuplicateGroups.map((group, index) => (
                <div key={`${group.reason}-${group.payment_reference || group.description || index}`} className="card" style={{ padding: '0.75rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                    <div style={{ fontWeight: 700 }}>
                      {group.reason === 'payment_reference' ? tr('expenseDuplicateByPaymentRef') : tr('expenseDuplicateByDescription')}
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                      <div style={{ color: 'var(--color-text-muted)' }}>{tr('amount')}: {Number(group.amount || 0).toLocaleString('sr-RS')}</div>
                      <button type="button" className="btn btn-secondary" onClick={() => handleDismissDuplicateGroup(group)}>{tr('skip')}</button>
                    </div>
                  </div>
                  {group.payment_reference && (
                    <div style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>
                      {tr('paymentRef')}: {group.payment_reference}
                    </div>
                  )}
                  {group.description && (
                    <div style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>
                      {tr('description')}: {group.description}
                    </div>
                  )}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {group.items.map((item) => (
                      <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', alignItems: 'center', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '0.5rem' }}>
                        <div style={{ minWidth: 260, flex: 1 }}>
                          <div style={{ fontWeight: 600 }}>{item.description}</div>
                          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                            {item.date} {UI_DASH} {getProjectName(item.project_id) || tr('unassigned')} {UI_DASH} {getCategoryLabel(item)}
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
            <table>
              <thead>
                <tr>
                  <th style={{ width: 40 }}>
                    <input type="checkbox" checked={filtered.length > 0 && selectedIds.length >= filtered.length} onChange={toggleSelectAll} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIcon col="date" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('description')}>{tr('description')} <SortIcon col="description" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('project_id')}>{tr('project')} <SortIcon col="project_id" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('contract_id')}>{tr('contract')} <SortIcon col="contract_id" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('category')}>{tr('category')} <SortIcon col="category" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')} <SortIcon col="amount" /></th>
                  <th>{tr('paymentRef')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={9}>{tr('loading')}</td></tr>
                ) : filtered.length === 0 ? (
                  <tr><td colSpan={9} style={{ color: 'var(--color-text-muted)' }}>{tr('noRecords')}</td></tr>
                ) : (
                  filtered.map((item) => (
                    <tr
                      key={item.id}
                      className={(item.status === 'reversed' || item.reversal_of_id) ? 'row-reversal' : ''}
                      onDoubleClick={() => openExpenseSource(item)}
                      style={{ cursor: item.bank_reference || item.source === 'cash' || item.source === 'obligation' ? 'pointer' : 'default' }}
                    >
                      <td>
                        <input type="checkbox" checked={selectedIds.includes(item.id)} onChange={() => toggleSelect(item.id)} />
                      </td>
                      <td className="date-cell">{item.date}</td>
                      <td>{(item.description || '').slice(0, 50)}</td>
                      <td title={getProjectName(item.project_id) || ''}>
                        {item.project_id ? (
                          <span title={projects.find((project) => project.id === item.project_id)?.code || ''}>
                            {getProjectName(item.project_id) || UI_DASH}
                          </span>
                        ) : UI_DASH}
                      </td>
                      <td title={getContractLabel(item.contract_id) || ''}>{item.contract_id ? getContractLabel(item.contract_id) : UI_DASH}</td>
                      <td>{getCategoryLabel(item)}</td>
                      <td>{item.amount.toLocaleString('sr-RS')}</td>
                      <td
                        title={(item.bank_reference || item.note || (item.source === 'cash' ? tr('cashRegister') : '')) || ''}
                        style={{ fontSize: '0.85rem', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis' }}
                      >
                        {item.bank_reference || item.note || (item.source === 'cash' ? tr('cashRegister') : UI_DASH)}
                      </td>
                      <td>
                        <button className="btn btn-sm btn-secondary" disabled={item.status === 'reversed' || !!item.reversal_of_id} onClick={() => openEdit(item)}>{tr('edit')}</button>
                        <button
                          className="btn btn-sm btn-danger"
                          style={{ marginLeft: '0.5rem' }}
                          onClick={() => handleDelete(item)}
                          disabled={item.source === 'cash'}
                          title={item.source === 'cash' ? tr('cashManagedInRegister') : ''}
                        >
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
              <h2 className="modal-title">{modal === 'add' ? tr('add') : tr('edit')} {UI_DASH} {tr('expenses')}</h2>
              <button className="modal-close" onClick={() => setModal(null)}>{UI_CLOSE}</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('date')}</label>
                <DatePicker value={form.date} onChange={(value) => setForm({ ...form, date: value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('description')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.description}
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
                  required
                  placeholder={tr('expensePurposePlaceholder')}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('category')}</label>
                <select
                  className="form-input"
                  value={form.category_id}
                  onChange={(event) => {
                    const categoryId = event.target.value
                    const category = categories.find((item) => String(item.id) === categoryId)
                    setForm({ ...form, category_id: categoryId, category: category ? category.name_ru : '' })
                  }}
                >
                  <option value="">{`${UI_DASH} ${tr('allCategories')} ${UI_DASH}`}</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>{lang === 'ru' ? category.name_ru : category.name_sr}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('project')}</label>
                <ProjectSelect
                  projects={projects}
                  value={form.project_id}
                  onChange={updateProject}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('contract')}</label>
                <select className="form-input" value={form.contract_id} onChange={(event) => updateContract(event.target.value)}>
                  <option value="">{`${UI_DASH} ${tr('withoutContract')} ${UI_DASH}`}</option>
                  {filteredContracts.map((contract) => (
                    <option key={contract.id} value={contract.id}>{getContractLabel(contract.id)}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('amount')}</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  value={form.amount}
                  onChange={(event) => setForm({ ...form, amount: event.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('note')}</label>
                <input type="text" className="form-input" value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>{tr('cancel')}</button>
                <button type="submit" className="btn btn-primary">{tr('save')}</button>
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
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => { setModalAssign(false); setAssignProjectId('') }}>{tr('cancel')}</button>
              <button type="button" className="btn btn-primary" onClick={handleBulkAssign}>{tr('save')}</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
