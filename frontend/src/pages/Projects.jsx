import { useState, useEffect, useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import SearchInput from '../components/SearchInput'

function fmt(n) {
  return (n ?? 0).toLocaleString('sr-RS')
}

const UI_DASH = '\u2014'
const UI_CLOSE = '\u00D7'
const UI_SORT_BOTH = '\u2195'
const UI_SORT_ASC = '\u2191'
const UI_SORT_DESC = '\u2193'

export default function Projects() {
  const location = useLocation()
  const isActivePage = location.pathname === '/projects'
  const [projects, setProjects] = useState([])
  const [clients, setClients] = useState([])
  const [byProject, setByProject] = useState([])
  const [unassigned, setUnassigned] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
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
  const [search, setSearch] = useState('')
  const [sortCol, setSortCol] = useState('name')
  const [sortAsc, setSortAsc] = useState(true)
  const [projectFilter, setProjectFilter] = useState('all')
  const [periodQuick, setPeriodQuick] = useState('year')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [mode, setMode] = useState('accrual')

  const currentYear = new Date().getFullYear()

  const getPeriod = () => {
    if (periodQuick === 'month') {
      const month = new Date().getMonth() + 1
      const lastDay = new Date(currentYear, month, 0).getDate()
      return {
        from: `${currentYear}-${String(month).padStart(2, '0')}-01`,
        to: `${currentYear}-${String(month).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
      }
    }
    if (periodQuick === 'quarter') {
      const month = new Date().getMonth() + 1
      const quarter = Math.ceil(month / 3)
      const startMonth = (quarter - 1) * 3 + 1
      const endMonth = quarter * 3
      const lastDay = new Date(currentYear, endMonth + 1, 0).getDate()
      return {
        from: `${currentYear}-${String(startMonth).padStart(2, '0')}-01`,
        to: `${currentYear}-${String(endMonth).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
      }
    }
    if (periodQuick === 'year') {
      return { from: `${currentYear}-01-01`, to: `${currentYear}-12-31` }
    }
    return {
      from: customFrom || `${currentYear}-01-01`,
      to: customTo || `${currentYear}-12-31`,
    }
  }

  const { from, to } = getPeriod()

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

  const handleDelete = async (id) => {
    if (!confirm(tr('confirmDeleteProject'))) return
    try {
      await api.projects.delete(id)
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
      rows = rows.filter((project) =>
        (project.name || '').toLowerCase().includes(normalizedSearch) ||
        (project.code || '').toLowerCase().includes(normalizedSearch) ||
        (project.client_name || '').toLowerCase().includes(normalizedSearch)
      )
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

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">{tr('projects')}</h1>
        </div>
        <div className="page-header-actions">
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
        </div>
      </div>

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
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('name')}>{tr('project')} <SortIcon col="name" /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('code')}>{tr('projectCode')} <SortIcon col="code" /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('client_name')}>{tr('client')} <SortIcon col="client_name" /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('revenue')}>{tr('income')} <SortIcon col="revenue" /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('expenses')}>{tr('expenses')} <SortIcon col="expenses" /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('profit')}>{tr('projectProfit')} <SortIcon col="profit" /></th>
                <th style={{ width: 140 }}></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7}>{tr('loading')}</td></tr>
              ) : filteredProjects.length === 0 ? (
                <tr><td colSpan={7} style={{ color: 'var(--color-text-muted)' }}>{tr('noProjects')}</td></tr>
              ) : (
                filteredProjects.map((project) => {
                  const row = getRowData(project)
                  return (
                    <tr key={project.id} style={project.status === 'archived' ? { opacity: 0.6 } : {}}>
                      <td>
                        {project.name}
                        {project.is_internal ? (
                          <span className="badge" style={{ marginLeft: '0.5rem', backgroundColor: 'var(--color-info, #0ea5e9)', color: '#fff', padding: '0.15rem 0.45rem', borderRadius: 999 }}>
                            {tr('internalProject')}
                          </span>
                        ) : null}
                      </td>
                      <td>{project.code || UI_DASH}</td>
                      <td>{project.client_name || UI_DASH}</td>
                      <td>{fmt(row.revenue)} RSD</td>
                      <td>{fmt(row.expenses)} RSD</td>
                      <td style={{ fontWeight: 600, color: (row.profit ?? 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)' }}>
                        {fmt(row.profit)} RSD
                      </td>
                      <td>
                        <button className="btn btn-sm btn-secondary" onClick={() => openEdit(project)}>{tr('edit')}</button>
                        <button className="btn btn-sm btn-danger" style={{ marginLeft: '0.5rem' }} onClick={() => handleDelete(project.id)}>
                          {tr('delete')}
                        </button>
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

      {modal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 420 }}>
            <div className="modal-header">
              <h2 className="modal-title">{modal === 'add' ? tr('add') : tr('edit')} {UI_DASH} {tr('project')}</h2>
              <button className="modal-close" onClick={() => setModal(null)}>{UI_CLOSE}</button>
            </div>
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
          </div>
        </div>
      )}
    </div>
  )
}
