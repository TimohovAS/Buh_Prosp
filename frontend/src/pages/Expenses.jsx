import { useState, useEffect } from 'react'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'

const MONTHS = [1,2,3,4,5,6,7,8,9,10,11,12];
const getCategories = (tr) => [
  { value: '', label: '—' },
  { value: 'materials', label: tr('expenseCategoryMaterials') },
  { value: 'services', label: tr('expenseCategoryServices') },
  { value: 'rent', label: tr('expenseCategoryRent') },
  { value: 'other', label: tr('expenseCategoryOther') },
];

export default function Expenses() {
  const [items, setItems] = useState([])
  const [year, setYear] = useState(new Date().getFullYear())
  const [month, setMonth] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [selectedIds, setSelectedIds] = useState([])
  const [modal, setModal] = useState(null)
  const [modalAssign, setModalAssign] = useState(false)
  const [projects, setProjects] = useState([])
  const [assignProjectId, setAssignProjectId] = useState('')
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    description: '',
    amount: '',
    category: '',
    project_id: '',
    note: '',
  })

  const load = () => {
    setLoading(true)
    const params = { year }
    if (month) params.month = month
    api.expenses.list(params).then(setItems).finally(() => setLoading(false))
  }

  useEffect(load, [year, month])
  useEffect(() => {
    api.projects.list({ show_archived: true }).then(setProjects)
  }, [])

  const toggleSelect = (id) => {
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }
  const toggleSelectAll = () => {
    if (selectedIds.length >= filtered.length) setSelectedIds([])
    else setSelectedIds(filtered.map((i) => i.id))
  }
  const handleBulkAssign = async () => {
    if (selectedIds.length === 0) return
    const pid = assignProjectId === '' || assignProjectId === '_none' ? null : parseInt(assignProjectId, 10)
    try {
      await api.expenses.bulkAssignProject({ ids: selectedIds, project_id: pid })
      setModalAssign(false)
      setAssignProjectId('')
      setSelectedIds([])
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const openAdd = () => {
    setForm({
      date: new Date().toISOString().slice(0, 10),
      description: '',
      amount: '',
      category: '',
      project_id: '',
      note: '',
    })
    setModal('add')
  }

  const openEdit = (item) => {
    setForm({
      date: item.date,
      description: item.description || '',
      amount: item.amount,
      category: item.category || '',
      project_id: item.project_id ?? '',
      note: item.note || '',
    })
    setModal({ type: 'edit', id: item.id })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      const payload = {
        date: form.date,
        description: form.description.trim(),
        amount: parseFloat(form.amount) || 0,
        category: form.category || null,
        project_id: form.project_id ? parseInt(form.project_id, 10) : null,
        note: form.note || null,
      }
      if (modal === 'add') {
        await api.expenses.create(payload)
      } else {
        await api.expenses.update(modal.id, payload)
      }
      setModal(null)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm(tr('confirmDeleteExpense'))) return
    try {
      await api.expenses.delete(id)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const filtered = items.filter((i) => {
    if (!search) return true
    const s = search.toLowerCase()
    return (i.description || '').toLowerCase().includes(s) ||
           (i.category || '').toLowerCase().includes(s)
  })

  const total = filtered.reduce((sum, i) => sum + i.amount, 0)

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('expenses')}</h1>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value))}
          >
            {[year-2, year-1, year, year+1].map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={month}
            onChange={(e) => setMonth(e.target.value ? parseInt(e.target.value) : '')}
          >
            <option value="">{tr('allMonths')}</option>
            {MONTHS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <input
            type="text"
            className="form-input"
            placeholder={tr('search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 180 }}
          />
          <button
            className="btn btn-secondary"
            disabled={selectedIds.length === 0}
            onClick={() => setModalAssign(true)}
          >
            {tr('assignProject')} {selectedIds.length > 0 ? `(${selectedIds.length})` : ''}
          </button>
          <button className="btn btn-primary" onClick={openAdd}>
            {tr('add')}
          </button>
        </div>
      </div>

      <div className="page-body">
      <div className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 40 }}>
                  <input
                    type="checkbox"
                    checked={filtered.length > 0 && selectedIds.length >= filtered.length}
                    onChange={toggleSelectAll}
                  />
                </th>
                <th>{tr('date')}</th>
                <th>{tr('description')}</th>
                <th>{tr('project')}</th>
                <th>{tr('category')}</th>
                <th>{tr('amount')}</th>
                <th>{tr('paymentRef')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8}>{tr('loading')}</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={8} style={{ color: 'var(--color-text-muted)' }}>{tr('noRecords')}</td></tr>
              ) : (
                filtered.map((i) => (
                  <tr
                    key={i.id}
                    className={(i.status === 'reversed' || i.reversal_of_id) ? 'row-reversal' : ''}
                  >
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(i.id)}
                        onChange={() => toggleSelect(i.id)}
                      />
                    </td>
                    <td>{i.date}</td>
                    <td>{(i.description || '').slice(0, 50)}</td>
                    <td title={projects.find((p) => p.id === i.project_id)?.name || ''}>
                      {i.project_id ? (projects.find((p) => p.id === i.project_id)?.code || '—') : '—'}
                    </td>
                    <td>{getCategories(tr).find(c => c.value === i.category)?.label || i.category || '-'}</td>
                    <td>{i.amount.toLocaleString('sr-RS')}</td>
                    <td title={(i.bank_reference || i.note) || ''} style={{ fontSize: '0.85rem', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {i.bank_reference || i.note || '—'}
                    </td>
                    <td>
                      <button className="btn btn-sm btn-secondary" onClick={() => openEdit(i)}>{tr('edit')}</button>
                      <button className="btn btn-sm btn-danger" style={{ marginLeft: '0.5rem' }} onClick={() => handleDelete(i.id)}>
                        {tr('delete')}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {filtered.length > 0 && (
          <div style={{ marginTop: '1rem', fontWeight: 600, color: 'var(--color-danger)' }}>
            {tr('total')}: {total.toLocaleString('sr-RS')} RSD
          </div>
        )}
      </div>
      </div>

      {modal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">{modal === 'add' ? tr('add') : tr('edit')} — {tr('expenses')}</h2>
              <button className="modal-close" onClick={() => setModal(null)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('date')}</label>
                <DatePicker
                  value={form.date}
                  onChange={(v) => setForm({ ...form, date: v })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('description')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  required
                  placeholder={tr('expensePurposePlaceholder')}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('category')}</label>
                <select
                  className="form-input"
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                >
                  {getCategories(tr).map((c) => (
                    <option key={c.value || 'empty'} value={c.value}>{c.label}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('project')}</label>
                <select
                  className="form-input"
                  value={form.project_id}
                  onChange={(e) => setForm({ ...form, project_id: e.target.value })}
                >
                  <option value="">— {tr('unassignProject')} —</option>
                  {projects.filter((p) => p.status !== 'archived').map((p) => (
                    <option key={p.id} value={p.id}>{p.code || p.name} — {p.name}</option>
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
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('note')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.note}
                  onChange={(e) => setForm({ ...form, note: e.target.value })}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>
                  {tr('cancel')}
                </button>
                <button type="submit" className="btn btn-primary">{tr('save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {modalAssign && (
        <div className="modal-overlay" onClick={() => { setModalAssign(false); setAssignProjectId(''); }}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 400 }}>
            <div className="modal-header">
              <h2 className="modal-title">{tr('assignProject')}</h2>
              <button className="modal-close" onClick={() => { setModalAssign(false); setAssignProjectId(''); }}>×</button>
            </div>
            <div className="form-group" style={{ margin: '1rem' }}>
              <label className="form-label">{tr('project')}</label>
              <select
                className="form-input"
                value={assignProjectId}
                onChange={(e) => setAssignProjectId(e.target.value)}
              >
                <option value="_none">— {tr('unassignProject')} —</option>
                {projects.filter((p) => p.status !== 'archived').map((p) => (
                  <option key={p.id} value={p.id}>{p.code || p.name} — {p.name}</option>
                ))}
              </select>
            </div>
            <div className="modal-actions" style={{ padding: '0 1rem 1rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => { setModalAssign(false); setAssignProjectId(''); }}>
                {tr('cancel')}
              </button>
              <button type="button" className="btn btn-primary" onClick={handleBulkAssign}>
                {tr('save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
