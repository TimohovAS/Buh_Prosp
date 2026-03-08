import { useState, useEffect, useMemo } from 'react'
import { api } from '../api'
import { tr, getLang } from '../i18n'
import DatePicker from '../components/DatePicker'

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

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
    else setSelectedIds(filtered.map((item) => item.id))
  }

  const handleBulkAssign = async () => {
    if (selectedIds.length === 0) return
    const pid = assignProjectId === '' || assignProjectId === '_none'
      ? (unassignedProject ? unassignedProject.id : null)
      : parseInt(assignProjectId, 10)
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
    const unassigned = projects.find((project) => project.code === 'INT-UNASSIGNED')
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

  const handleSubmit = async (event) => {
    event.preventDefault()
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
  const unassignedProject = projects.find((project) => project.code === 'INT-UNASSIGNED') || null
  const commercialProjects = projects.filter((project) => !project.is_internal && project.status !== 'archived')
  const internalProjects = projects.filter((project) => project.is_internal && project.status !== 'archived')
  const getProjectName = (projectId) => projects.find((project) => project.id === projectId)?.name || ''

  const getCategoryLabel = (item) => {
    const selectedCategory = categories.find((category) => category.id === item.category_id)
    if (selectedCategory) {
      return lang === 'ru' ? selectedCategory.name_ru : selectedCategory.name_sr
    }
    return item.category || '-'
  }

  const filtered = useMemo(() => {
    const normalizedSearch = (search || '').trim().toLowerCase()
    let rows = items
    if (normalizedSearch) {
      rows = items.filter((item) =>
        (item.description || '').toLowerCase().includes(normalizedSearch) ||
        getCategoryLabel(item).toLowerCase().includes(normalizedSearch) ||
        String(item.amount || '').includes(normalizedSearch) ||
        getProjectName(item.project_id).toLowerCase().includes(normalizedSearch)
      )
    }
    return [...rows].sort((left, right) => {
      const leftValue = sortCol === 'project_id'
        ? getProjectName(left.project_id)
        : (sortCol === 'category' ? getCategoryLabel(left) : (left[sortCol] ?? ''))
      const rightValue = sortCol === 'project_id'
        ? getProjectName(right.project_id)
        : (sortCol === 'category' ? getCategoryLabel(right) : (right[sortCol] ?? ''))
      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
  }, [items, search, sortCol, sortAsc, projects, categories, lang])

  const toggleSort = (col) => {
    if (sortCol === col) setSortAsc((value) => !value)
    else {
      setSortCol(col)
      setSortAsc(true)
    }
  }

  const SortIcon = ({ col }) => {
    if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 4 }}>^v</span>
    return <span style={{ marginLeft: 4 }}>{sortAsc ? '^' : 'v'}</span>
  }

  const total = filtered.reduce((sum, item) => sum + item.amount, 0)

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
            onChange={(event) => setYear(parseInt(event.target.value, 10))}
          >
            {[year - 2, year - 1, year, year + 1].map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={month}
            onChange={(event) => setMonth(event.target.value ? parseInt(event.target.value, 10) : '')}
          >
            <option value="">{tr('allMonths')}</option>
            {MONTHS.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <input
            type="text"
            className="form-input"
            placeholder={tr('search')}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
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
                  filtered.map((item) => (
                    <tr
                      key={item.id}
                      className={(item.status === 'reversed' || item.reversal_of_id) ? 'row-reversal' : ''}
                    >
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(item.id)}
                          onChange={() => toggleSelect(item.id)}
                        />
                      </td>
                      <td>{item.date}</td>
                      <td>{(item.description || '').slice(0, 50)}</td>
                      <td title={projects.find((project) => project.id === item.project_id)?.name || ''}>
                        {item.project_id ? (
                          <span title={projects.find((project) => project.id === item.project_id)?.code || ''}>
                            {projects.find((project) => project.id === item.project_id)?.name || '-'}
                          </span>
                        ) : '-'}
                      </td>
                      <td>{getCategoryLabel(item)}</td>
                      <td>{item.amount.toLocaleString('sr-RS')}</td>
                      <td
                        title={(item.bank_reference || item.note) || ''}
                        style={{ fontSize: '0.85rem', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis' }}
                      >
                        {item.bank_reference || item.note || '-'}
                      </td>
                      <td>
                        <button className="btn btn-sm btn-secondary" onClick={() => openEdit(item)}>{tr('edit')}</button>
                        <button className="btn btn-sm btn-danger" style={{ marginLeft: '0.5rem' }} onClick={() => handleDelete(item.id)}>
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
              <h2 className="modal-title">{modal === 'add' ? tr('add') : tr('edit')} {tr('expenses')}</h2>
              <button className="modal-close" onClick={() => setModal(null)}>x</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('date')}</label>
                <DatePicker
                  value={form.date}
                  onChange={(value) => setForm({ ...form, date: value })}
                  required
                />
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
                  <option value="">- {tr('allCategories')} -</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>{lang === 'ru' ? category.name_ru : category.name_sr}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('project')}</label>
                <select
                  className="form-input"
                  value={form.project_id}
                  onChange={(event) => setForm({ ...form, project_id: event.target.value })}
                  required
                >
                  <option value="">-</option>
                  {commercialProjects.length > 0 && (
                    <optgroup label={tr('commercialProject')}>
                      {commercialProjects.map((project) => (
                        <option key={project.id} value={project.id}>{project.name}{project.code ? ` - ${project.code}` : ''}</option>
                      ))}
                    </optgroup>
                  )}
                  {internalProjects.length > 0 && (
                    <optgroup label={tr('internalProject')}>
                      {internalProjects.map((project) => (
                        <option key={project.id} value={project.id}>{project.name}{project.code ? ` - ${project.code}` : ''}</option>
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
                  onChange={(event) => setForm({ ...form, amount: event.target.value })}
                  required
                />
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
        <div className="modal-overlay" onClick={() => { setModalAssign(false); setAssignProjectId('') }}>
          <div className="modal" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 400 }}>
            <div className="modal-header">
              <h2 className="modal-title">{tr('assignProject')}</h2>
              <button className="modal-close" onClick={() => { setModalAssign(false); setAssignProjectId('') }}>x</button>
            </div>
            <div className="form-group" style={{ margin: '1rem' }}>
              <label className="form-label">{tr('project')}</label>
              <select
                className="form-input"
                value={assignProjectId}
                onChange={(event) => setAssignProjectId(event.target.value)}
              >
                <option value="">-</option>
                {commercialProjects.length > 0 && (
                  <optgroup label={tr('commercialProject')}>
                    {commercialProjects.map((project) => (
                      <option key={project.id} value={project.id}>{project.name}{project.code ? ` - ${project.code}` : ''}</option>
                    ))}
                  </optgroup>
                )}
                {internalProjects.length > 0 && (
                  <optgroup label={tr('internalProject')}>
                    {internalProjects.map((project) => (
                      <option key={project.id} value={project.id}>{project.name}{project.code ? ` - ${project.code}` : ''}</option>
                    ))}
                  </optgroup>
                )}
              </select>
            </div>
            <div className="modal-actions" style={{ padding: '0 1rem 1rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => { setModalAssign(false); setAssignProjectId('') }}>
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
