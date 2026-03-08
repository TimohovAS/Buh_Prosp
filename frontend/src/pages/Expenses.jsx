import { useState, useEffect, useMemo } from 'react'
import { api } from '../api'
import { tr, getLang } from '../i18n'
import DatePicker from '../components/DatePicker'

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

export default function Expenses() {
  const [items, setItems] = useState([])
  const [year, setYear] = useState(new Date().getFullYear())
  const [month, setMonth] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [sortCol, setSortCol] = useState('date')
  const [sortAsc, setSortAsc] = useState(false)
  const [selectedIds, setSelectedIds] = useState([])
  const [modal, setModal] = useState(null)
  const [modalAssign, setModalAssign] = useState(false)
  const [projects, setProjects] = useState([])
  const [categories, setCategories] = useState([])
  const [assignProjectId, setAssignProjectId] = useState('')
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    description: '',
    amount: '',
    category: '',
    category_id: '',
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
    api.categories.list({ category_type: 'expense' }).then(setCategories)
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
    const pid = assignProjectId === '' || assignProjectId === '_none' ? (unassignedProject ? unassignedProject.id : null) : parseInt(assignProjectId, 10)
    try {
      await api.expenses.bulkAssignProject({ ids: selectedIds, project_id: pid })
      setModalAssign(false)
      setAssignProjectId('')
      setSelectedIds([])
      load()
    } catch (err) {
      console.error(err)
    }
  }

  const openAdd = () => {
    // Default project = INT-UNASSIGNED
    const unassigned = projects.find(p => p.code === 'INT-UNASSIGNED')
    setForm({
      date: new Date().toISOString().slice(0, 10),
      description: '',
      amount: '',
      category: '',
      category_id: '',
      project_id: unassigned ? String(unassigned.id) : '',
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
      category_id: item.category_id ?? '',
      project_id: item.project_id ?? (unassignedProject ? String(unassignedProject.id) : ''),
      note: item.note || '',
    })
    setModal({ type: 'edit', id: item.id })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      const categoryValue = form.category?.trim() || null
      const payload = {
        date: form.date,
        description: form.description.trim(),
        amount: parseFloat(form.amount) || 0,
        category: categoryValue,
        category_id: form.category_id ? parseInt(form.category_id, 10) : null,
        project_id: form.project_id ? parseInt(form.project_id, 10) : (unassignedProject ? unassignedProject.id : null),
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
      console.error(err)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm(tr('confirmDeleteExpense'))) return
    try {
      await api.expenses.delete(id)
      load()
    } catch (err) {
      console.error(err)
    }
  }

  const lang = getLang()
  const unassignedProject = projects.find((p) => p.code === 'INT-UNASSIGNED') || null
  const commercialProjects = projects.filter(p => !p.is_internal && p.status !== 'archived')
  const internalProjects = projects.filter(p => p.is_internal && p.status !== 'archived')
  const getProjectName = (projectId) => projects.find((p) => p.id === projectId)?.name || ''
  const getCategoryLabel = (item) => {
    const selectedCategory = categories.find((category) => category.id === item.category_id)
    if (selectedCategory) {
      return lang === 'ru' ? selectedCategory.name_ru : selectedCategory.name_sr
    }
    return item.category || 'вЂ”'
  }

  const filtered = useMemo(() => {
    const s = (search || '').trim().toLowerCase()
    let rows = items
    if (s) {
      rows = items.filter((item) =>
        (item.description || '').toLowerCase().includes(s) ||
        getCategoryLabel(item).toLowerCase().includes(s) ||
        String(item.amount || '').includes(s) ||
        getProjectName(item.project_id).toLowerCase().includes(s)
      )
    }
    return [...rows].sort((a, b) => {
      const valA = sortCol === 'project_id' ? getProjectName(a.project_id) : (sortCol === 'category' ? getCategoryLabel(a) : (a[sortCol] ?? ''))
      const valB = sortCol === 'project_id' ? getProjectName(b.project_id) : (sortCol === 'category' ? getCategoryLabel(b) : (b[sortCol] ?? ''))
      if (valA < valB) return sortAsc ? -1 : 1
      if (valA > valB) return sortAsc ? 1 : -1
      return 0
    })
  }, [items, search, sortCol, sortAsc, projects, categories, lang])

  const toggleSort = (col) => {
    if (sortCol === col) setSortAsc(v => !v)
    else { setSortCol(col); setSortAsc(true) }
  }
  const SortIcon = ({ col }) => {
    if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 4 }}>РІвЂ вЂў</span>
    return <span style={{ marginLeft: 4 }}>{sortAsc ? 'РІвЂ вЂ' : 'РІвЂ вЂњ'}</span>
  }

  const total = filtered.reduce((sum, i) => sum + i.amount, 0)

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('expenses')}</h1>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
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
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value))}
          >
            {[year - 2, year - 1, year, year + 1].map((y) => (
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
            onClick={() => { setAssignProjectId(unassignedProject ? String(unassignedProject.id) : ''); setModalAssign(true) }}
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
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIcon col="date" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('description')}>{tr('description')} <SortIcon col="description" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('project_id')}>{tr('project')} <SortIcon col="project_id" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('category')}>{tr('category')} <SortIcon col="category" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')} <SortIcon col="amount" /></th>
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
                        {i.project_id ? (
                          <span title={projects.find(p => p.id === i.project_id)?.code || ''}>
                            {projects.find((p) => p.id === i.project_id)?.name || 'РІР‚вЂќ'}
                          </span>
                        ) : 'РІР‚вЂќ'}
                      </td>
                      <td>{getCategoryLabel(i)}</td>
                      <td>{i.amount.toLocaleString('sr-RS')}</td>
                      <td title={(i.bank_reference || i.note) || ''} style={{ fontSize: '0.85rem', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {i.bank_reference || i.note || 'РІР‚вЂќ'}
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
        </div>
      </div>

      {modal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">{modal === 'add' ? tr('add') : tr('edit')} РІР‚вЂќ {tr('expenses')}</h2>
              <button className="modal-close" onClick={() => setModal(null)}>Р“вЂ”</button>
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
                  value={form.category_id}
                  onChange={(e) => {
                    const cid = e.target.value
                    const cat = categories.find(c => String(c.id) === cid)
                    setForm({ ...form, category_id: cid, category: cat ? cat.name_ru : '' })
                  }}
                >
                  <option value="">РІР‚вЂќ {tr('allCategories')} РІР‚вЂќ</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{lang === 'ru' ? c.name_ru : c.name_sr}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('project')}</label>
                <select
                  className="form-input"
                  value={form.project_id}
                  onChange={(e) => setForm({ ...form, project_id: e.target.value })}
                  required
                >
                  <option value="">РІР‚вЂќ</option>
                  {commercialProjects.length > 0 && (
                    <optgroup label={tr('commercialProject')}>
                      {commercialProjects.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}{p.code ? ` РІР‚вЂќ ${p.code}` : ''}</option>
                      ))}
                    </optgroup>
                  )}
                  {internalProjects.length > 0 && (
                    <optgroup label={tr('internalProject')}>
                      {internalProjects.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}{p.code ? ` РІР‚вЂќ ${p.code}` : ''}</option>
                      ))}
                    </optgroup>
                  )}
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
              <button className="modal-close" onClick={() => { setModalAssign(false); setAssignProjectId(''); }}>Р“вЂ”</button>
            </div>
            <div className="form-group" style={{ margin: '1rem' }}>
              <label className="form-label">{tr('project')}</label>
              <select
                className="form-input"
                value={assignProjectId}
                onChange={(e) => setAssignProjectId(e.target.value)}
              >
                <option value="">вЂ”</option>
                {commercialProjects.length > 0 && (
                  <optgroup label={tr('commercialProject')}>
                    {commercialProjects.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}{p.code ? ` вЂ” ${p.code}` : ''}</option>
                    ))}
                  </optgroup>
                )}
                {internalProjects.length > 0 && (
                  <optgroup label={tr('internalProject')}>
                    {internalProjects.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}{p.code ? ` вЂ” ${p.code}` : ''}</option>
                    ))}
                  </optgroup>
                )}
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
