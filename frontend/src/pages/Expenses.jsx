import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, getUser } from '../api'
import { getLang, tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import EntityDetailModal from '../components/EntityDetailModal'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import YearFilterSelect from '../components/YearFilterSelect'
import useAvailableYears from '../hooks/useAvailableYears'
import useCategoryProjectResolver from '../hooks/useCategoryProjectResolver'
import useListPageState from '../hooks/useListPageState'
import useProjectContractForm from '../hooks/useProjectContractForm'
import { filterContractsForProject, findUnassignedProject, getContractLabelById, getProjectName as resolveProjectName } from '../utils/entityLabels'
import { UI_CLOSE, UI_DASH, todayIso } from '../utils/formatters'
import { MONTHS } from '../utils/constants'
import { downloadTextFile } from '../utils/download'

const DUPLICATE_DISMISS_STORAGE_KEY = 'expenses_duplicate_dismissed_v1'

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
  const location = useLocation()
  const navigate = useNavigate()
  const isActivePage = location.pathname === '/expenses'
  const [items, setItems] = useState([])
  const [duplicateGroups, setDuplicateGroups] = useState([])
  const { currentYear, year, setYear, availableYears, applyAvailableYears } = useAvailableYears({ initialYear: new Date().getFullYear() })
  const [month, setMonth] = useState('')
  const [loading, setLoading] = useState(true)
  const [selectedIds, setSelectedIds] = useState([])
  const {
    search,
    setSearch,
    sortCol,
    sortAsc,
    toggleSort,
  } = useListPageState({ initialSortCol: 'date', initialSortAsc: false })
  const [modal, setModal] = useState(null)
  const [modalAssign, setModalAssign] = useState(false)
  const [detailModal, setDetailModal] = useState(null)
  const [projects, setProjects] = useState([])
  const [contracts, setContracts] = useState([])
  const [categories, setCategories] = useState([])
  const [assignProjectId, setAssignProjectId] = useState('')
  const [pageError, setPageError] = useState('')
  const [mergeKeepId, setMergeKeepId] = useState(null)
  const [dismissedDuplicateGroups, setDismissedDuplicateGroups] = useState(() => loadDismissedDuplicateGroups())
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
  }, [year, month, isActivePage])

  useEffect(() => {
    if (!isActivePage) return
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
  const {
    updateProject,
    updateContract,
  } = useProjectContractForm({ contracts, setForm })

  const getCategoryLabel = (item) => {
    return getResolvedCategoryLabel(item, item.category || UI_DASH)
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
      setDetailModal(null)
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

  const canOpenExpenseSource = (item) => Boolean(item?.bank_reference || item?.source === 'cash' || item?.source === 'obligation')

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

  const handleAdminHardDelete = async (ids) => {
    if (!isAdmin || ids.length === 0) return
    if (!confirm(tr('confirmAdminHardDeleteExpenses').replace('{count}', ids.length))) return
    try {
      await api.expenses.adminHardDelete({ ids })
      setSelectedIds((previous) => previous.filter((id) => !ids.includes(id)))
      setDetailModal((previous) => (previous && ids.includes(previous.id) ? null : previous))
      load()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
      console.error(error)
    }
  }

  const openAdd = () => {
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

  const openDetail = (item) => {
    setDetailModal(item)
  }

  const openEditFromDetail = (item) => {
    setDetailModal(null)
    openEdit(item)
  }

  const handleDeleteFromDetail = async (item) => {
    setDetailModal(null)
    await handleDelete(item)
  }

  const updateCategory = (categoryId) => {
    const category = getCategoryById(categoryId)
    const defaultProjectId = getCategoryDefaultProjectId(categoryId)
    setForm((previous) => {
      const selectedContract = previous.contract_id ? contracts.find((contract) => String(contract.id) === String(previous.contract_id)) : null
      const nextProjectId = defaultProjectId || previous.project_id
      const keepContract = selectedContract && (!nextProjectId || String(selectedContract.project_id) === String(nextProjectId) || selectedContract.project_id == null)
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
      const categoryValue = form.category?.trim() || null
      const categoryDefaultProjectId = getCategoryDefaultProjectId(form.category_id)
      const payload = {
        date: form.date,
        description: form.description.trim(),
        amount: parseFloat(form.amount) || 0,
        category: categoryValue,
        category_id: form.category_id ? parseInt(form.category_id, 10) : null,
        project_id: categoryDefaultProjectId
          ? parseInt(categoryDefaultProjectId, 10)
          : (form.project_id ? parseInt(form.project_id, 10) : (unassignedProject ? unassignedProject.id : null)),
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
    const effectiveProjectId = getCategoryDefaultProjectId(form.category_id) || form.project_id || ''
    const selectedProjectId = effectiveProjectId ? parseInt(effectiveProjectId, 10) : null
    return getContractsForProject(selectedProjectId)
  }, [contracts, form.project_id, form.category_id, categories])
  const usesDefaultCategoryProject = useMemo(() => usesCategoryProject(form.category_id), [categories, form.category_id])

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
    const filename = `expenses${year ? `_${year}` : ''}${month ? `_${String(month).padStart(2, '0')}` : ''}.csv`
    downloadTextFile(content, filename, 'text/csv;charset=utf-8;')
  }

  return (
    <>
      <PageHeader
        title={tr('expenses')}
        actions={(
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
          {isAdmin ? (
            <button
              className="btn btn-danger"
              disabled={selectedIds.length === 0}
              onClick={() => handleAdminHardDelete(selectedIds)}
            >
              {tr('adminHardDeleteSelected')} {selectedIds.length > 0 ? `(${selectedIds.length})` : ''}
            </button>
          ) : null}
          <button className="btn btn-secondary" onClick={handleExportCsv} disabled={loading || filtered.length === 0}>
            {tr('download')} CSV
          </button>
          <button className="btn btn-primary" onClick={openAdd}>{tr('add')}</button>
          </>
        )}
      />

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
            <table className="expenses-list-table">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>
                    <input type="checkbox" checked={filtered.length > 0 && selectedIds.length >= filtered.length} onChange={toggleSelectAll} />
                  </th>
                  <th className="col-date" style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIndicator active={sortCol === 'date'} asc={sortAsc} /></th>
                  <th className="col-description" style={{ cursor: 'pointer' }} onClick={() => toggleSort('description')}>{tr('description')} <SortIndicator active={sortCol === 'description'} asc={sortAsc} /></th>
                  <th className="col-project" style={{ cursor: 'pointer' }} onClick={() => toggleSort('project_id')}>{tr('project')} <SortIndicator active={sortCol === 'project_id'} asc={sortAsc} /></th>
                  <th className="col-category" style={{ cursor: 'pointer' }} onClick={() => toggleSort('category')}>{tr('category')} <SortIndicator active={sortCol === 'category'} asc={sortAsc} /></th>
                  <th className="col-amount" style={{ cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')} <SortIndicator active={sortCol === 'amount'} asc={sortAsc} /></th>
                  <th className="col-payment">{tr('paymentRef')}</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={7}>{tr('loading')}</td></tr>
                ) : filtered.length === 0 ? (
                  <tr><td colSpan={7} style={{ color: 'var(--color-text-muted)' }}>{tr('noRecords')}</td></tr>
                ) : (
                  filtered.map((item) => (
                    <tr
                      key={item.id}
                      className={`record-row ${(item.status === 'reversed' || item.reversal_of_id) ? 'row-reversal' : ''}`.trim()}
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
                      <td className="col-description"><span className="record-cell-ellipsis" title={item.description || ''}>{item.description || UI_DASH}</span></td>
                      <td className="col-project" title={[getProjectName(item.project_id), getContractLabel(item.contract_id)].filter(Boolean).join(' • ')}>
                        {item.project_id ? (
                          <>
                            <span className="record-cell-ellipsis" title={projects.find((project) => project.id === item.project_id)?.code || ''}>
                              {getProjectName(item.project_id) || UI_DASH}
                            </span>
                            {item.contract_id && (
                              <span className="record-cell-subtitle">{getContractLabel(item.contract_id)}</span>
                            )}
                          </>
                        ) : UI_DASH}
                      </td>
                      <td className="col-category"><span className="record-cell-ellipsis">{getCategoryLabel(item)}</span></td>
                      <td className="col-amount">{item.amount.toLocaleString('sr-RS')}</td>
                      <td
                        className="col-payment"
                        title={(item.bank_reference || item.note || (item.source === 'cash' ? tr('cashRegister') : '')) || ''}
                      >
                        <span className="record-cell-ellipsis">{item.bank_reference || item.note || (item.source === 'cash' ? tr('cashRegister') : UI_DASH)}</span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <EntityDetailModal
        isOpen={!!detailModal}
        onClose={() => setDetailModal(null)}
        title={detailModal ? `${tr('expenses')} ${UI_DASH} #${detailModal.id}` : ''}
        maxWidth="860px"
        details={detailModal ? (
          <div className="record-field-grid">
            <div className="record-field">
              <span className="record-field-label">{tr('date')}</span>
              <span className="record-field-value">{detailModal.date || UI_DASH}</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('amount')}</span>
              <span className="record-field-value">{Number(detailModal.amount || 0).toLocaleString('sr-RS')} RSD</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('category')}</span>
              <span className="record-field-value">{getCategoryLabel(detailModal)}</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('project')}</span>
              <span className="record-field-value">{getProjectName(detailModal.project_id) || UI_DASH}</span>
            </div>
            <div className="record-field full">
              <span className="record-field-label">{tr('contract')}</span>
              <span className="record-field-value">{detailModal.contract_id ? getContractLabel(detailModal.contract_id) : UI_DASH}</span>
            </div>
            <div className="record-field full">
              <span className="record-field-label">{tr('description')}</span>
              <div className="record-field-text">{detailModal.description || UI_DASH}</div>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('paymentRef')}</span>
              <span className="record-field-value">{detailModal.bank_reference || UI_DASH}</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('status')}</span>
              <span className="record-field-value">{detailModal.status || UI_DASH}</span>
            </div>
            <div className="record-field full">
              <span className="record-field-label">{tr('note')}</span>
              <div className="record-field-text">{detailModal.note || UI_DASH}</div>
            </div>
          </div>
        ) : null}
        actions={detailModal ? (
          <div className="record-actions-grid">
            {canOpenExpenseSource(detailModal) ? (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => openExpenseSource(detailModal)}
              >
                {tr('openSource')}
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
          </div>
        ) : null}
      />

      <Modal
        isOpen={!!modal}
        onClose={() => setModal(null)}
        title={`${modal === 'add' ? tr('add') : tr('edit')} ${UI_DASH} ${tr('expenses')}`}
        closeOnOverlay
      >
        {modal ? (
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
                  onChange={(event) => updateCategory(event.target.value)}
                >
                  <option value="">{`${UI_DASH} ${tr('allCategories')} ${UI_DASH}`}</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>{lang === 'ru' ? category.name_ru : category.name_sr}</option>
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
                    <select className="form-input" value={form.contract_id} onChange={(event) => updateContract(event.target.value)}>
                      <option value="">{`${UI_DASH} ${tr('withoutContract')} ${UI_DASH}`}</option>
                    {filteredContracts.map((contract) => (
                      <option key={contract.id} value={contract.id}>{getContractLabel(contract.id)}</option>
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
        ) : null}
      </Modal>

      <Modal
        isOpen={modalAssign}
        onClose={() => { setModalAssign(false); setAssignProjectId('') }}
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
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => { setModalAssign(false); setAssignProjectId('') }}>{tr('cancel')}</button>
              <button type="button" className="btn btn-primary" onClick={handleBulkAssign}>{tr('save')}</button>
            </div>
          </>
        ) : null}
      </Modal>
    </>
  )
}
