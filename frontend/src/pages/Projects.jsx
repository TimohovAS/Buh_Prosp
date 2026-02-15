import { useState, useEffect } from 'react'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'

function fmt(n) {
  return (n ?? 0).toLocaleString('sr-RS')
}

export default function Projects() {
  const [projects, setProjects] = useState([])
  const [clients, setClients] = useState([])
  const [byProject, setByProject] = useState([])
  const [unassigned, setUnassigned] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({ name: '', code: '', status: 'active', client_id: '', contract_id: '', start_date: '', end_date: '', planned_income: '', planned_expense: '', notes: '' })
  const [showInactive, setShowInactive] = useState(false)
  const [search, setSearch] = useState('')
  const [periodQuick, setPeriodQuick] = useState('year')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [mode, setMode] = useState('accrual')

  const currentYear = new Date().getFullYear()
  const getPeriod = () => {
    if (periodQuick === 'month') {
      const m = new Date().getMonth() + 1
      const lastDay = new Date(currentYear, m, 0).getDate()
      return {
        from: `${currentYear}-${String(m).padStart(2, '0')}-01`,
        to: `${currentYear}-${String(m).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
      }
    }
    if (periodQuick === 'quarter') {
      const m = new Date().getMonth() + 1
      const q = Math.ceil(m / 3)
      const startM = (q - 1) * 3 + 1
      const endM = q * 3
      const lastDay = new Date(currentYear, endM + 1, 0).getDate()
      return {
        from: `${currentYear}-${String(startM).padStart(2, '0')}-01`,
        to: `${currentYear}-${String(endM).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
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
    Promise.all([api.projects.list({ show_archived: showInactive }), api.finance.byProject({ from, to, mode })])
      .then(([projs, fin]) => {
        setProjects(projs)
        setByProject(fin.by_project || [])
        setUnassigned(fin.unassigned || null)
        setError(null)
      })
      .catch((e) => {
        setError(e.message)
      })
      .finally(() => setLoading(false))
  }

  useEffect(loadAll, [showInactive, from, to, mode])
  useEffect(() => { api.clients.listBrief().then(setClients) }, [])

  const openAdd = () => {
    setForm({ name: '', code: '', status: 'active', client_id: '', contract_id: '', start_date: '', end_date: '', planned_income: '', planned_expense: '', notes: '' })
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
    })
    setModal({ type: 'edit', id: item.id })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const payload = {
      name: form.name || undefined,
      code: form.code || undefined,
      status: form.status || 'active',
      client_id: form.client_id ? parseInt(form.client_id, 10) : null,
      contract_id: form.contract_id ? parseInt(form.contract_id, 10) : null,
      start_date: form.start_date || undefined,
      end_date: form.end_date || undefined,
      planned_income: form.planned_income !== '' ? parseFloat(form.planned_income) : undefined,
      planned_expense: form.planned_expense !== '' ? parseFloat(form.planned_expense) : undefined,
      notes: form.notes || undefined,
    }
    try {
      if (modal === 'add') {
        await api.projects.create(payload)
      } else {
        await api.projects.update(modal.id, payload)
      }
      setModal(null)
      loadAll()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm(tr('confirmDeleteProject'))) return
    try {
      await api.projects.delete(id)
      loadAll()
    } catch (err) {
      alert(err.message)
    }
  }

  const getRowData = (p) => {
    const row = byProject.find((r) => r.project_id === p.id)
    return row || { project_name: p.name, revenue: 0, expenses: 0, profit: 0 }
  }

  const filteredProjects = projects.filter((p) => {
    if (!search) return true
    const s = search.toLowerCase()
    return (p.name || '').toLowerCase().includes(s) ||
           (p.code || '').toLowerCase().includes(s) ||
           (p.client_name || '').toLowerCase().includes(s)
  })

  return (
    <div className="page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.5rem' }}>
        <h1>{tr('projects')}</h1>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="text"
            className="form-input"
            placeholder={tr('search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 180 }}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
            <span>{tr('showInactive')}</span>
          </label>
          <button className="btn btn-primary" onClick={openAdd}>{tr('add')}</button>
        </div>
      </div>

      {/* Фильтр периода и режима */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end' }}>
          <div>
            <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>{tr('financePeriod')}</label>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
              {['month', 'quarter', 'year', 'custom'].map((q) => (
                <button
                  key={q}
                  className={`btn btn-sm ${periodQuick === q ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setPeriodQuick(q)}
                >
                  {tr(`financePeriod${q.charAt(0).toUpperCase() + q.slice(1)}`)}
                </button>
              ))}
            </div>
          </div>
          {periodQuick === 'custom' && (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <DatePicker value={customFrom} onChange={setCustomFrom} placeholder={tr('periodFrom')} className="form-input" />
              <span>—</span>
              <DatePicker value={customTo} onChange={setCustomTo} placeholder={tr('periodTo')} className="form-input" />
            </div>
          )}
          <div>
            <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>{tr('financeMode')}</label>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
              {['accrual', 'cash'].map((m) => (
                <button
                  key={m}
                  className={`btn btn-sm ${mode === m ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setMode(m)}
                >
                  {tr(`financeMode${m.charAt(0).toUpperCase() + m.slice(1)}`)}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>{error}</div>
      )}

      {/* Таблица проектов с revenue/profit */}
      <div className="card">
        <div className="card-title">{tr('projectsTable')}</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{tr('project')}</th>
                <th>{tr('projectCode')}</th>
                <th>{tr('client')}</th>
                <th>{tr('income')}</th>
                <th>{tr('expenses')}</th>
                <th>{tr('projectProfit')}</th>
                <th style={{ width: 140 }}></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7}>{tr('loading')}</td></tr>
              ) : filteredProjects.length === 0 ? (
                <tr><td colSpan={7} style={{ color: 'var(--color-text-muted)' }}>{tr('noProjects')}</td></tr>
              ) : (
                filteredProjects.map((p) => {
                  const row = getRowData(p)
                  return (
                    <tr key={p.id} style={p.status === 'archived' ? { opacity: 0.6 } : {}}>
                      <td>{p.name}</td>
                      <td>{p.code || '—'}</td>
                      <td>{p.client_name || '—'}</td>
                      <td>{fmt(row.revenue)} RSD</td>
                      <td>{fmt(row.expenses)} RSD</td>
                      <td style={{
                        fontWeight: 600,
                        color: (row.profit ?? 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)',
                      }}>
                        {fmt(row.profit)} RSD
                      </td>
                      <td>
                        <button className="btn btn-sm btn-secondary" onClick={() => openEdit(p)}>{tr('edit')}</button>
                        <button className="btn btn-sm btn-danger" style={{ marginLeft: '0.5rem' }} onClick={() => handleDelete(p.id)}>
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

      {/* Карточка «Без проекта» — из unassigned, не из by_project */}
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

      {/* Модалка Add/Edit */}
      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 420 }}>
            <div className="modal-header">
              <h2 className="modal-title">{modal === 'add' ? tr('add') : tr('edit')} {tr('project')}</h2>
              <button className="modal-close" onClick={() => setModal(null)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('name')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('projectCode')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.code}
                  onChange={(e) => setForm({ ...form, code: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('client')}</label>
                <select
                  className="form-input"
                  value={form.client_id}
                  onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                >
                  <option value="">—</option>
                  {clients.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('status')}</label>
                <select
                  className="form-input"
                  value={form.status}
                  onChange={(e) => setForm({ ...form, status: e.target.value })}
                >
                  <option value="lead">lead</option>
                  <option value="active">active</option>
                  <option value="completed">completed</option>
                  <option value="archived">archived</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('note')}</label>
                <textarea
                  className="form-input"
                  rows={2}
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
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
