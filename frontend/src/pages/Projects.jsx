import { useState, useEffect, useMemo, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr, getLang } from '../i18n'
import DatePicker from '../components/DatePicker'
import EntityDetailModal from '../components/EntityDetailModal'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import StatusBadge from '../components/StatusBadge'
import useListPageState from '../hooks/useListPageState'
import { UI_DASH, UI_CLOSE, formatInteger as fmt, formatMoney2, todayIso } from '../utils/formatters'
import { getPeriodRange } from '../utils/periods'
import { amountSearchHay } from '../utils/searchUtils'
export default function Projects() {
  const location = useLocation()
  const isActivePage = location.pathname === '/projects'
  const [projects, setProjects] = useState([])
  const [clients, setClients] = useState([])
  const [byProject, setByProject] = useState([])
  const [unassigned, setUnassigned] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [detailModal, setDetailModal] = useState(null)
  const [movementModal, setMovementModal] = useState(null)
  const [movementLoading, setMovementLoading] = useState(false)
  const [movementError, setMovementError] = useState(null)
  const [movementPeriodQuick, setMovementPeriodQuick] = useState('all')
  const [movementCustomFrom, setMovementCustomFrom] = useState('')
  const [movementCustomTo, setMovementCustomTo] = useState('')
  const [purchaseModal, setPurchaseModal] = useState(null)
  const [purchaseLoading, setPurchaseLoading] = useState(false)
  const [purchaseError, setPurchaseError] = useState(null)
  const [purchasePeriodQuick, setPurchasePeriodQuick] = useState('all')
  const [purchaseCustomFrom, setPurchaseCustomFrom] = useState('')
  const [purchaseCustomTo, setPurchaseCustomTo] = useState('')
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({
    name: '',
    code: '',
    status: 'active',
    client_id: '',
    contract_id: '',
    start_date: '',
    end_date: '',
    planned_income: '',
    planned_expense: '',
    notes: '',
    is_internal: false,
  })
  const [showInactive, setShowInactive] = useState(false)
  const [projectFilter, setProjectFilter] = useState('all')
  const [periodQuick, setPeriodQuick] = useState('year')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [mode, setMode] = useState('accrual')
  const {
    search,
    setSearch,
    sortCol,
    sortAsc,
    toggleSort,
  } = useListPageState({ initialSortCol: 'name', initialSortAsc: true })
  const rowClickTimeoutRef = useRef(null)

  const currentYear = new Date().getFullYear()
  const { from, to } = getPeriodRange(periodQuick, customFrom, customTo, {
    fallbackFrom: `${currentYear}-01-01`,
    fallbackTo: `${currentYear}-12-31`,
  })

  const loadAll = () => {
    setLoading(true)
    Promise.all([
      api.projects.list({ show_archived: showInactive }),
      api.finance.byProject({ from, to, mode }),
    ])
      .then(([projectList, finance]) => {
        setProjects(projectList)
        setByProject(finance.by_project || [])
        setUnassigned(finance.unassigned || null)
        setError(null)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return
    loadAll()
  }, [showInactive, from, to, mode, isActivePage])
  useEffect(() => {
    if (!isActivePage) return
    api.clients.listBrief().then(setClients)
  }, [isActivePage])

  useEffect(() => () => {
    if (rowClickTimeoutRef.current) clearTimeout(rowClickTimeoutRef.current)
  }, [])

  const openAdd = () => {
    setForm({
      name: '',
      code: '',
      status: 'active',
      client_id: '',
      contract_id: '',
      start_date: '',
      end_date: '',
      planned_income: '',
      planned_expense: '',
      notes: '',
      is_internal: false,
    })
    setModal('add')
  }

  const openEdit = (item) => {
    setForm({
      name: item.name || '',
      code: item.code || '',
      status: item.status || 'active',
      client_id: item.client_id ?? '',
      contract_id: item.contract_id ?? '',
      start_date: item.start_date || '',
      end_date: item.end_date || '',
      planned_income: item.planned_income ?? '',
      planned_expense: item.planned_expense ?? '',
      notes: item.notes || '',
      is_internal: item.is_internal || false,
    })
    setModal({ type: 'edit', id: item.id })
  }

  const openDetail = (item) => {
    setDetailModal(item)
  }

  const openEditFromDetail = (item) => {
    setDetailModal(null)
    openEdit(item)
  }

  const getProjectAllTimeRange = (item) => {
    const createdAt = item?.created_at || item?.project_created_date || ''
    const createdDate = typeof createdAt === 'string' ? createdAt.slice(0, 10) : ''
    const fallbackStart = createdDate || todayIso
    const firstMovementDate = item?.first_movement_date || item?.project_first_movement_date || null
    const lastMovementDate = item?.last_movement_date || item?.project_last_movement_date || null
    const projectStart = item?.start_date || item?.project_start_date || fallbackStart
    const projectEnd = item?.end_date || item?.project_end_date || null
    const resolvedFrom = firstMovementDate || projectStart
    const resolvedTo = lastMovementDate || (projectEnd && projectEnd < todayIso ? projectEnd : todayIso)
    return { from: resolvedFrom, to: resolvedTo }
  }

  const getMovementRange = (item = movementModal) => {
    const allTime = getProjectAllTimeRange(item)
    if (movementPeriodQuick === 'all') return allTime
    if (movementPeriodQuick === 'month') {
      const currentMonth = new Date().getMonth() + 1
      const lastDay = new Date(currentYear, currentMonth, 0).getDate()
      return {
        from: `${currentYear}-${String(currentMonth).padStart(2, '0')}-01`,
        to: `${currentYear}-${String(currentMonth).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
      }
    }
    if (movementPeriodQuick === 'quarter') {
      const currentMonth = new Date().getMonth() + 1
      const quarter = Math.ceil(currentMonth / 3)
      const startMonth = (quarter - 1) * 3 + 1
      const endMonth = quarter * 3
      const lastDay = new Date(currentYear, endMonth, 0).getDate()
      return {
        from: `${currentYear}-${String(startMonth).padStart(2, '0')}-01`,
        to: `${currentYear}-${String(endMonth).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
      }
    }
    if (movementPeriodQuick === 'year') {
      return { from: `${currentYear}-01-01`, to: `${currentYear}-12-31` }
    }
    return {
      from: movementCustomFrom || allTime.from,
      to: movementCustomTo || allTime.to,
    }
  }

  const loadMovements = async (item) => {
    if (!item?.project_id) return
    const range = getMovementRange(item)
    setMovementLoading(true)
    setMovementError(null)
    try {
      const payload = await api.finance.projectMovements({
        project_id: item.project_id,
        from: range.from,
        to: range.to,
        mode,
      })
      setMovementModal((current) => current ? {
        ...current,
        ...payload,
        from_date: payload.from_date,
        to_date: payload.to_date,
        project_first_movement_date: current.project_first_movement_date,
        project_last_movement_date: current.project_last_movement_date,
        project_start_date: current.project_start_date,
        project_end_date: current.project_end_date,
        project_created_date: current.project_created_date,
      } : current)
    } catch (err) {
      console.error(err)
      setMovementError(err.message)
    } finally {
      setMovementLoading(false)
    }
  }

  const openMovements = async (item) => {
    const allTime = getProjectAllTimeRange(item)
    setMovementPeriodQuick('all')
    setMovementCustomFrom(allTime.from)
    setMovementCustomTo(allTime.to)
    setMovementModal({
      project_id: item.id,
      project_name: item.name,
      project_first_movement_date: item.first_movement_date || null,
      project_last_movement_date: item.last_movement_date || null,
      project_start_date: item.start_date || null,
      project_end_date: item.end_date || null,
      project_created_date: (item.created_at || '').slice(0, 10) || null,
      mode,
      from_date: allTime.from,
      to_date: allTime.to,
      items: [],
    })
  }

  const openMovementsFromDetail = (item) => {
    setDetailModal(null)
    openMovements(item)
  }

  const getPurchaseRange = (item = purchaseModal) => {
    const allTime = getProjectAllTimeRange(item)
    if (purchasePeriodQuick === 'all') return allTime
    if (purchasePeriodQuick === 'month') {
      const currentMonth = new Date().getMonth() + 1
      const lastDay = new Date(currentYear, currentMonth, 0).getDate()
      return {
        from: `${currentYear}-${String(currentMonth).padStart(2, '0')}-01`,
        to: `${currentYear}-${String(currentMonth).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
      }
    }
    if (purchasePeriodQuick === 'quarter') {
      const currentMonth = new Date().getMonth() + 1
      const quarter = Math.ceil(currentMonth / 3)
      const startMonth = (quarter - 1) * 3 + 1
      const endMonth = quarter * 3
      const lastDay = new Date(currentYear, endMonth, 0).getDate()
      return {
        from: `${currentYear}-${String(startMonth).padStart(2, '0')}-01`,
        to: `${currentYear}-${String(endMonth).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
      }
    }
    if (purchasePeriodQuick === 'year') {
      return { from: `${currentYear}-01-01`, to: `${currentYear}-12-31` }
    }
    return {
      from: purchaseCustomFrom || allTime.from,
      to: purchaseCustomTo || allTime.to,
    }
  }

  const handleExportPurchasesXlsx = async () => {
    if (!purchaseModal?.project_id) return
    const range = getPurchaseRange(purchaseModal)
    const safeName = (purchaseModal.project_name || `project_${purchaseModal.project_id}`)
      .replace(/[^\w\-]+/g, '_')
      .replace(/^_+|_+$/g, '') || `project_${purchaseModal.project_id}`
    const filename = `purchases_${safeName}_${range.from}_${range.to}.xlsx`
    try {
      await api.receipts.exportByProjectXlsx(purchaseModal.project_id, {
        from: range.from,
        to: range.to,
        lang: getLang(),
      }, filename)
    } catch (err) {
      console.error(err)
      setPurchaseError(err.message || tr('projectPurchasesExportError'))
    }
  }

  const loadPurchases = async (item) => {
    if (!item?.project_id) return
    const range = getPurchaseRange(item)
    setPurchaseLoading(true)
    setPurchaseError(null)
    try {
      const payload = await api.receipts.byProject(item.project_id, {
        from: range.from,
        to: range.to,
      })
      setPurchaseModal((current) => current ? {
        ...current,
        ...payload,
        project_first_movement_date: current.project_first_movement_date,
        project_last_movement_date: current.project_last_movement_date,
        project_start_date: current.project_start_date,
        project_end_date: current.project_end_date,
        project_created_date: current.project_created_date,
      } : current)
    } catch (err) {
      console.error(err)
      setPurchaseError(err.message)
    } finally {
      setPurchaseLoading(false)
    }
  }

  const openPurchases = (item) => {
    const allTime = getProjectAllTimeRange(item)
    setPurchasePeriodQuick('all')
    setPurchaseCustomFrom(allTime.from)
    setPurchaseCustomTo(allTime.to)
    setPurchaseModal({
      project_id: item.id,
      project_name: item.name,
      project_first_movement_date: item.first_movement_date || null,
      project_last_movement_date: item.last_movement_date || null,
      project_start_date: item.start_date || null,
      project_end_date: item.end_date || null,
      project_created_date: (item.created_at || '').slice(0, 10) || null,
      from_date: allTime.from,
      to_date: allTime.to,
      items: [],
    })
  }

  const openPurchasesFromDetail = (item) => {
    setDetailModal(null)
    openPurchases(item)
  }

  const handleProjectRowClick = (item) => {
    if (rowClickTimeoutRef.current) clearTimeout(rowClickTimeoutRef.current)
    rowClickTimeoutRef.current = setTimeout(() => {
      openDetail(item)
      rowClickTimeoutRef.current = null
    }, 180)
  }

  const handleProjectRowDoubleClick = (item) => {
    if (rowClickTimeoutRef.current) {
      clearTimeout(rowClickTimeoutRef.current)
      rowClickTimeoutRef.current = null
    }
    openMovements(item)
  }

  useEffect(() => {
    if (!movementModal?.project_id) return
    loadMovements(movementModal)
  }, [movementModal?.project_id, movementPeriodQuick, movementCustomFrom, movementCustomTo, mode])

  useEffect(() => {
    if (!purchaseModal?.project_id) return
    loadPurchases(purchaseModal)
  }, [purchaseModal?.project_id, purchasePeriodQuick, purchaseCustomFrom, purchaseCustomTo])

  const handleSubmit = async (event) => {
    event.preventDefault()
    const payload = {
      name: form.name || undefined,
      code: form.code || undefined,
      status: form.status || 'active',
      client_id: form.client_id ? parseInt(form.client_id, 10) : null,
      is_internal: !!form.is_internal,
      start_date: form.start_date || undefined,
      end_date: form.end_date || undefined,
      planned_income: form.planned_income !== '' ? parseFloat(form.planned_income) : undefined,
      planned_expense: form.planned_expense !== '' ? parseFloat(form.planned_expense) : undefined,
      notes: form.notes || undefined,
    }
    try {
      if (modal === 'add') await api.projects.create(payload)
      else await api.projects.update(modal.id, payload)
      setModal(null)
      loadAll()
    } catch (err) {
      console.error(err)
    }
  }

  const handleDeleteFromDetail = async (item) => {
    if (!confirm(tr('confirmDeleteProject'))) return
    try {
      await api.projects.delete(item.id)
      setDetailModal(null)
      loadAll()
    } catch (err) {
      console.error(err)
    }
  }

  const getRowData = (project) => {
    const row = byProject.find((item) => item.project_id === project.id)
    return row || { project_name: project.name, revenue: 0, expenses: 0, profit: 0 }
  }

  const filteredProjects = useMemo(() => {
    const normalizedSearch = (search || '').trim().toLowerCase()
    let rows = projects
    if (projectFilter === 'internal') rows = rows.filter((project) => project.is_internal)
    if (projectFilter === 'commercial') rows = rows.filter((project) => !project.is_internal)
    if (normalizedSearch) {
      rows = rows.filter((project) => {
        const row = getRowData(project)
        return (project.name || '').toLowerCase().includes(normalizedSearch) ||
          (project.code || '').toLowerCase().includes(normalizedSearch) ||
          (project.client_name || '').toLowerCase().includes(normalizedSearch) ||
          amountSearchHay(row.revenue).includes(normalizedSearch) ||
          amountSearchHay(row.expenses).includes(normalizedSearch) ||
          amountSearchHay(row.profit).includes(normalizedSearch)
      })
    }
    return [...rows].sort((left, right) => {
      let leftValue
      let rightValue
      if (sortCol === 'revenue' || sortCol === 'expenses' || sortCol === 'profit') {
        leftValue = getRowData(left)[sortCol] ?? 0
        rightValue = getRowData(right)[sortCol] ?? 0
      } else {
        leftValue = left[sortCol] ?? ''
        rightValue = right[sortCol] ?? ''
      }
      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
  }, [projects, search, sortCol, sortAsc, byProject, projectFilter])

  const getMovementTypeLabel = (item) => item.movement_type === 'income'
    ? tr('projectMovementSourceIncome')
    : tr('projectMovementSourceExpense')

  const getMovementSourceLabel = (item) => {
    if (item.source_kind === 'allocation') return tr('projectMovementSourceAllocation')
    if (item.source_kind === 'bank') return tr('projectMovementSourceBank')
    if (item.source_kind === 'income') return tr('projectMovementSourceIncome')
    if (item.source_kind === 'expense') return tr('projectMovementSourceExpense')
    return item.source_kind || UI_DASH
  }

  return (
    <div className="page">
      <PageHeader
        title={tr('projects')}
        actions={(
          <>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
              <input type="checkbox" checked={showInactive} onChange={(event) => setShowInactive(event.target.checked)} />
              <span>{tr('showInactive')}</span>
            </label>
            <div style={{ display: 'flex', gap: '0.25rem' }}>
              {['all', 'commercial', 'internal'].map((filterValue) => (
                <button
                  key={filterValue}
                  className={`btn btn-sm ${projectFilter === filterValue ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setProjectFilter(filterValue)}
                >
                  {tr(`filter${filterValue.charAt(0).toUpperCase() + filterValue.slice(1)}`)}
                </button>
              ))}
            </div>
            <SearchInput
              placeholder={tr('search')}
              value={search}
              onChange={setSearch}
              style={{ width: 180 }}
            />
            <button className="btn btn-primary" onClick={openAdd}>{tr('add')}</button>
          </>
        )}
      />

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end' }}>
          <div>
            <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>{tr('financePeriod')}</label>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
              {['month', 'quarter', 'year', 'custom'].map((quickPeriod) => (
                <button
                  key={quickPeriod}
                  className={`btn btn-sm ${periodQuick === quickPeriod ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setPeriodQuick(quickPeriod)}
                >
                  {tr(`financePeriod${quickPeriod.charAt(0).toUpperCase() + quickPeriod.slice(1)}`)}
                </button>
              ))}
            </div>
          </div>
          {periodQuick === 'custom' && (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <DatePicker value={customFrom} onChange={setCustomFrom} placeholder={tr('periodFrom')} className="form-input" />
              <span>{UI_DASH}</span>
              <DatePicker value={customTo} onChange={setCustomTo} placeholder={tr('periodTo')} className="form-input" />
            </div>
          )}
          <div>
            <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>{tr('financeMode')}</label>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
              {['accrual', 'cash'].map((modeValue) => (
                <button
                  key={modeValue}
                  className={`btn btn-sm ${mode === modeValue ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setMode(modeValue)}
                >
                  {tr(`financeMode${modeValue.charAt(0).toUpperCase() + modeValue.slice(1)}`)}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>{error}</div>}

      <div className="card">
        <div className="card-title">{tr('projectsTable')}</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('name')}>{tr('project')} <SortIndicator active={sortCol === 'name'} asc={sortAsc} /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('code')}>{tr('projectCode')} <SortIndicator active={sortCol === 'code'} asc={sortAsc} /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('client_name')}>{tr('client')} <SortIndicator active={sortCol === 'client_name'} asc={sortAsc} /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('revenue')}>{tr('income')} <SortIndicator active={sortCol === 'revenue'} asc={sortAsc} /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('expenses')}>{tr('expenses')} <SortIndicator active={sortCol === 'expenses'} asc={sortAsc} /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('profit')}>{tr('projectProfit')} <SortIndicator active={sortCol === 'profit'} asc={sortAsc} /></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6}>{tr('loading')}</td></tr>
              ) : filteredProjects.length === 0 ? (
                <tr><td colSpan={6} style={{ color: 'var(--color-text-muted)' }}>{tr('noProjects')}</td></tr>
              ) : (
                filteredProjects.map((project) => {
                  const row = getRowData(project)
                  return (
                    <tr
                      key={project.id}
                      className="record-row"
                      style={project.status === 'archived' ? { opacity: 0.6 } : {}}
                      onClick={() => handleProjectRowClick(project)}
                      onDoubleClick={() => handleProjectRowDoubleClick(project)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          openDetail(project)
                        }
                      }}
                      tabIndex={0}
                    >
                      <td>
                        {project.name}
                        {project.is_internal ? (
                          <StatusBadge tone="info" className="badge-pill" style={{ marginLeft: '0.5rem' }}>
                            {tr('internalProject')}
                          </StatusBadge>
                        ) : null}
                      </td>
                      <td>{project.code || UI_DASH}</td>
                      <td>{project.client_name || UI_DASH}</td>
                      <td>{fmt(row.revenue)} RSD</td>
                      <td>{fmt(row.expenses)} RSD</td>
                      <td style={{ fontWeight: 600, color: (row.profit ?? 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)' }}>
                        {fmt(row.profit)} RSD
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {unassigned && (unassigned.revenue > 0 || unassigned.expenses > 0) && (
        <div className="card">
          <div className="card-title">{tr('projectWithoutProject')}</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('project')}</th>
                  <th>{tr('income')}</th>
                  <th>{tr('expenses')}</th>
                  <th>{tr('projectProfit')}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{tr('projectWithoutProject')}</td>
                  <td>{fmt(unassigned.revenue)} RSD</td>
                  <td>{fmt(unassigned.expenses)} RSD</td>
                  <td style={{ fontWeight: 600, color: (unassigned.profit ?? 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)' }}>
                    {fmt(unassigned.profit)} RSD
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      <EntityDetailModal
        isOpen={!!detailModal}
        onClose={() => setDetailModal(null)}
        title={detailModal ? `${tr('project')} ${UI_DASH} ${detailModal.name || `#${detailModal.id}`}` : tr('project')}
        maxWidth="920px"
        details={detailModal ? (
          <div className="record-field-grid">
            <div className="record-field">
              <span className="record-field-label">{tr('name')}</span>
              <span className="record-field-value">{detailModal.name || UI_DASH}</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('projectCode')}</span>
              <span className="record-field-value">{detailModal.code || UI_DASH}</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('client')}</span>
              <span className="record-field-value">{detailModal.client_name || UI_DASH}</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('status')}</span>
              <span className="record-field-value">{detailModal.status || UI_DASH}</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('isInternal')}</span>
              <span className="record-field-value">{detailModal.is_internal ? tr('yes') : tr('no')}</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('projectPlannedIncome')}</span>
              <span className="record-field-value">{fmt(detailModal.planned_income)} RSD</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('projectPlannedExpenses')}</span>
              <span className="record-field-value">{fmt(detailModal.planned_expense)} RSD</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('projectStartDate')}</span>
              <span className="record-field-value">{detailModal.start_date || UI_DASH}</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('validTo')}</span>
              <span className="record-field-value">{detailModal.end_date || UI_DASH}</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('projectFirstMovement')}</span>
              <span className="record-field-value">{detailModal.first_movement_date || UI_DASH}</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('projectLastMovement')}</span>
              <span className="record-field-value">{detailModal.last_movement_date || UI_DASH}</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('income')}</span>
              <span className="record-field-value">{fmt(getRowData(detailModal).revenue)} RSD</span>
            </div>
            <div className="record-field">
              <span className="record-field-label">{tr('expenses')}</span>
              <span className="record-field-value">{fmt(getRowData(detailModal).expenses)} RSD</span>
            </div>
            <div className="record-field full">
              <span className="record-field-label">{tr('projectProfit')}</span>
              <span className="record-field-value" style={{ color: (getRowData(detailModal).profit ?? 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)', fontWeight: 700 }}>
                {fmt(getRowData(detailModal).profit)} RSD
              </span>
            </div>
            <div className="record-field full">
              <span className="record-field-label">{tr('note')}</span>
              <div className="record-field-text">{detailModal.notes || UI_DASH}</div>
            </div>
          </div>
        ) : null}
        actions={detailModal ? (
          <div className="record-actions-grid">
            <button type="button" className="btn btn-primary" onClick={() => openMovementsFromDetail(detailModal)}>
              {tr('projectMovements')}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => openPurchasesFromDetail(detailModal)}>
              {tr('projectPurchases')}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => openEditFromDetail(detailModal)}>
              {tr('edit')}
            </button>
            <button type="button" className="btn btn-danger" onClick={() => handleDeleteFromDetail(detailModal)}>
              {tr('delete')}
            </button>
          </div>
        ) : null}
      />

      <Modal
        isOpen={!!movementModal}
        onClose={() => { setMovementModal(null); setMovementError(null) }}
        title={movementModal ? `${tr('projectMovements')} ${UI_DASH} ${movementModal.project_name || `#${movementModal.project_id}`}` : ''}
        closeOnOverlay
        style={{
          width: 'min(96vw, 1520px)',
          maxWidth: 'none',
          height: 'min(92vh, 980px)',
          display: 'flex',
          flexDirection: 'column',
        }}
        bodyClassName="project-workflow-modal-body"
      >
        {movementModal ? (
            <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div style={{ marginBottom: '1rem', display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end' }}>
                <div>
                  <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>{tr('financePeriod')}</label>
                  <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem', flexWrap: 'wrap' }}>
                    {['all', 'month', 'quarter', 'year', 'custom'].map((quickPeriod) => (
                      <button
                        key={quickPeriod}
                        className={`btn btn-sm ${movementPeriodQuick === quickPeriod ? 'btn-primary' : 'btn-secondary'}`}
                        onClick={() => setMovementPeriodQuick(quickPeriod)}
                      >
                        {quickPeriod === 'all' ? tr('allTime') : tr(`financePeriod${quickPeriod.charAt(0).toUpperCase() + quickPeriod.slice(1)}`)}
                      </button>
                    ))}
                  </div>
                </div>
                {movementPeriodQuick === 'custom' ? (
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <DatePicker value={movementCustomFrom} onChange={setMovementCustomFrom} placeholder={tr('periodFrom')} className="form-input" />
                    <span>{UI_DASH}</span>
                    <DatePicker value={movementCustomTo} onChange={setMovementCustomTo} placeholder={tr('periodTo')} className="form-input" />
                  </div>
                ) : null}
                <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
                  {movementModal.from_date} {UI_DASH} {movementModal.to_date} · {tr(movementModal.mode === 'cash' ? 'financeModeCash' : 'financeModeAccrual')}
                </div>
              </div>
              {movementError ? (
                <div className="alert alert-danger">{movementError}</div>
              ) : movementLoading ? (
                <div style={{ color: 'var(--color-text-muted)' }}>{tr('loading')}</div>
              ) : movementModal.items?.length ? (
                <div className="table-wrap table-wrap-scroll" style={{ flex: 1, maxHeight: 'none' }}>
                  <table>
                    <colgroup>
                      <col style={{ width: '6rem' }} />
                      <col style={{ width: '5.5rem' }} />
                      <col style={{ width: '7rem' }} />
                      <col style={{ width: '11rem' }} />
                      <col style={{ width: '12rem' }} />
                      <col />
                      <col style={{ width: '9rem' }} />
                    </colgroup>
                    <thead>
                      <tr>
                        <th>{tr('date')}</th>
                        <th>{tr('projectMovementType')}</th>
                        <th>{tr('projectMovementSource')}</th>
                        <th>{tr('projectMovementDocument')}</th>
                        <th>{tr('projectMovementCounterparty')}</th>
                        <th>{tr('description')}</th>
                        <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {movementModal.items.map((item) => (
                        <tr key={item.row_key}>
                          <td>{item.date}</td>
                          <td>{getMovementTypeLabel(item)}</td>
                          <td>{getMovementSourceLabel(item)}</td>
                          <td title={item.document_number || ''}>{item.document_number || UI_DASH}</td>
                          <td title={item.counterparty_name || ''}>{item.counterparty_name || UI_DASH}</td>
                          <td title={item.description || ''}>{item.description || UI_DASH}</td>
                          <td style={{ textAlign: 'right', fontWeight: 700, color: item.direction === 'in' ? 'var(--color-success)' : 'var(--color-danger)' }}>
                            {item.direction === 'in' ? '+' : '-'}{formatMoney2(item.amount || 0)} RSD
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div style={{ color: 'var(--color-text-muted)' }}>{tr('projectMovementNoItems')}</div>
              )}
            </div>
        ) : null}
      </Modal>

      <Modal
        isOpen={!!purchaseModal}
        onClose={() => { setPurchaseModal(null); setPurchaseError(null) }}
        title={purchaseModal ? `${tr('projectPurchases')} ${UI_DASH} ${purchaseModal.project_name || `#${purchaseModal.project_id}`}` : ''}
        closeOnOverlay
        style={{
          width: 'min(96vw, 1520px)',
          maxWidth: 'none',
          height: 'min(92vh, 980px)',
          display: 'flex',
          flexDirection: 'column',
        }}
        bodyClassName="project-workflow-modal-body"
      >
        {purchaseModal ? (
            <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div style={{ marginBottom: '1rem', display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end' }}>
                <div>
                  <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>{tr('financePeriod')}</label>
                  <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem', flexWrap: 'wrap' }}>
                    {['all', 'month', 'quarter', 'year', 'custom'].map((quickPeriod) => (
                      <button
                        key={quickPeriod}
                        className={`btn btn-sm ${purchasePeriodQuick === quickPeriod ? 'btn-primary' : 'btn-secondary'}`}
                        onClick={() => setPurchasePeriodQuick(quickPeriod)}
                      >
                        {quickPeriod === 'all' ? tr('allTime') : tr(`financePeriod${quickPeriod.charAt(0).toUpperCase() + quickPeriod.slice(1)}`)}
                      </button>
                    ))}
                  </div>
                </div>
                {purchasePeriodQuick === 'custom' ? (
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <DatePicker value={purchaseCustomFrom} onChange={setPurchaseCustomFrom} placeholder={tr('periodFrom')} className="form-input" />
                    <span>{UI_DASH}</span>
                    <DatePicker value={purchaseCustomTo} onChange={setPurchaseCustomTo} placeholder={tr('periodTo')} className="form-input" />
                  </div>
                ) : null}
                <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
                  {purchaseModal.from_date} {UI_DASH} {purchaseModal.to_date}
                </div>
                <button
                  type="button"
                  className="btn btn-sm btn-secondary"
                  style={{ marginLeft: 'auto' }}
                  onClick={handleExportPurchasesXlsx}
                  disabled={purchaseLoading || !purchaseModal.items?.length}
                  title={tr('projectPurchasesExportXlsx')}
                >
                  {tr('projectPurchasesExportXlsx')}
                </button>
              </div>
              {purchaseError ? (
                <div className="alert alert-danger">{purchaseError}</div>
              ) : purchaseLoading ? (
                <div style={{ color: 'var(--color-text-muted)' }}>{tr('loading')}</div>
              ) : purchaseModal.items?.length ? (
                <div className="table-wrap table-wrap-scroll" style={{ flex: 1, maxHeight: 'none' }}>
                  <table>
                    <colgroup>
                      <col style={{ width: '6rem' }} />
                      <col style={{ width: '18rem' }} />
                      <col />
                      <col style={{ width: '6rem' }} />
                      <col style={{ width: '8rem' }} />
                      <col style={{ width: '9rem' }} />
                    </colgroup>
                    <thead>
                      <tr>
                        <th>{tr('date')}</th>
                        <th>{tr('receiptSeller')}</th>
                        <th>{tr('name')}</th>
                        <th style={{ textAlign: 'right' }}>{tr('receiptQuantity')}</th>
                        <th style={{ textAlign: 'right' }}>{tr('receiptUnitPrice')}</th>
                        <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {purchaseModal.items.map((item) => (
                        <tr key={item.item_id}>
                          <td>{item.receipt_datetime ? String(item.receipt_datetime).slice(0, 10) : UI_DASH}</td>
                          <td title={[item.seller_name, item.invoice_number].filter(Boolean).join(' · ')}>
                            <div style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.seller_name || UI_DASH}</div>
                            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.82rem', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.invoice_number || UI_DASH}</div>
                          </td>
                          <td title={item.item_name || ''}>{item.item_name || UI_DASH}</td>
                          <td style={{ textAlign: 'right' }}>{fmt(item.quantity || 0)}</td>
                          <td style={{ textAlign: 'right' }}>{formatMoney2(item.unit_price || 0)} RSD</td>
                          <td style={{ textAlign: 'right', fontWeight: 700 }}>{formatMoney2(item.total_amount || 0)} RSD</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div style={{ color: 'var(--color-text-muted)' }}>{tr('projectPurchasesNoItems')}</div>
              )}
            </div>
        ) : null}
      </Modal>

      <Modal
        isOpen={!!modal}
        onClose={() => setModal(null)}
        title={modal ? `${modal === 'add' ? tr('add') : tr('edit')} ${UI_DASH} ${tr('project')}` : ''}
        maxWidth="420px"
      >
        {modal ? (
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('name')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('projectCode')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.code}
                  onChange={(event) => setForm({ ...form, code: event.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('client')}</label>
                <select
                  className="form-input"
                  value={form.client_id}
                  onChange={(event) => setForm({ ...form, client_id: event.target.value })}
                >
                  <option value="">{UI_DASH}</option>
                  {clients.map((client) => (
                    <option key={client.id} value={client.id}>{client.name}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('status')}</label>
                <select
                  className="form-input"
                  value={form.status}
                  onChange={(event) => setForm({ ...form, status: event.target.value })}
                >
                  <option value="lead">lead</option>
                  <option value="active">active</option>
                  <option value="completed">completed</option>
                  <option value="archived">archived</option>
                </select>
              </div>
              <div className="form-group">
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input type="checkbox" checked={form.is_internal} onChange={(event) => setForm({ ...form, is_internal: event.target.checked })} />
                  <span>{tr('isInternal')}</span>
                </label>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('note')}</label>
                <textarea
                  className="form-input"
                  rows={2}
                  value={form.notes}
                  onChange={(event) => setForm({ ...form, notes: event.target.value })}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>{tr('cancel')}</button>
                <button type="submit" className="btn btn-primary">{tr('save')}</button>
              </div>
            </form>
        ) : null}
      </Modal>
    </div>
  )
}
