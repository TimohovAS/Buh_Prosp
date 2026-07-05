import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr, getLang } from '../i18n'
import DatePicker from '../components/DatePicker'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'
import SharedStatusBadge from '../components/StatusBadge'
import useCategoryProjectResolver from '../hooks/useCategoryProjectResolver'
import { findUnassignedProject } from '../utils/entityLabels'
import {
  UI_DASH,
  formatDateSr as formatDate,
  formatInteger as fmtAmount,
  todayIso,
} from '../utils/formatters'
import { amountSearchHay } from '../utils/searchUtils'

const PERIODS = [
  { value: 'weekly', label: 'weekly' },
  { value: 'monthly', label: 'monthly' },
  { value: 'quarterly', label: 'quarterly' },
  { value: 'yearly', label: 'yearly' },
]

const DAYS_OF_WEEK = [
  { value: 0, label: 'dayMon' },
  { value: 1, label: 'dayTue' },
  { value: 2, label: 'dayWed' },
  { value: 3, label: 'dayThu' },
  { value: 4, label: 'dayFri' },
  { value: 5, label: 'daySat' },
  { value: 6, label: 'daySun' },
]

const CATEGORIES = [
  { value: '', label: '\u2014' },
  { value: 'rent', label: 'plannedCatRent' },
  { value: 'internet', label: 'plannedCatInternet' },
  { value: 'phone', label: 'plannedCatPhone' },
  { value: 'utilities', label: 'plannedCatUtilities' },
  { value: 'insurance', label: 'plannedCatInsurance' },
  { value: 'software', label: 'plannedCatSoftware' },
  { value: 'other', label: 'plannedCatOther' },
] // legacy, kept for table display fallback

const WORKER_CATEGORY_MARKERS = ['зарп', 'zarad', 'salary', 'услуг', 'uslug', 'service']

const isWorkerLinkedCategory = (category) => {
  if (!category) return false
  const text =
    typeof category === 'string'
      ? category
      : [category.name_ru, category.name_sr, category.name, category.label, category.value, category.category]
          .filter(Boolean)
          .join(' ')
  const normalized = text.toLowerCase()
  return WORKER_CATEGORY_MARKERS.some((marker) => normalized.includes(marker))
}

export default function PlannedExpenses() {
  const location = useLocation()
  const isActivePage = location.pathname === '/planned-expenses'
  const [items, setItems] = useState([])
  const [upcoming, setUpcoming] = useState([])
  const [loading, setLoading] = useState(true)
  const [upcomingDays, setUpcomingDaysState] = useState(() => {
    const saved = localStorage.getItem('prospel_upcoming_days')
    const n = saved ? parseInt(saved, 10) : 60
    return n === 30 || n === 60 || n === 90 ? n : 60
  })
  const setUpcomingDays = (v) => {
    setUpcomingDaysState(v)
    localStorage.setItem('prospel_upcoming_days', String(v))
  }
  const [filterActive, setFilterActive] = useState('active') // 'all' | 'active' | 'inactive'
  const [filterCategory, setFilterCategory] = useState('')
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState(null)
  const [paidModal, setPaidModal] = useState(null)
  const [paidForm, setPaidForm] = useState({
    paid_date: todayIso(),
    note: '',
  })
  const [form, setForm] = useState({
    name: '',
    description: '',
    amount: '',
    currency: 'RSD',
    category: '',
    category_id: '',
    project_id: '',
    worker_id: '',
    period: 'monthly',
    payment_day: 5,
    payment_day_of_week: 0,
    start_date: todayIso(),
    end_date: '',
    reminder_days: 3,
    is_active: true,
    note: '',
  })
  const [projects, setProjects] = useState([])
  const [apiCategories, setApiCategories] = useState([])
  const [workers, setWorkers] = useState([])

  const load = () => {
    setLoading(true)
    const params = {}
    if (filterActive === 'active') params.is_active = true
    else if (filterActive === 'inactive') params.is_active = false
    if (filterCategory) params.category_id = filterCategory
    api.plannedExpenses
      .list(params)
      .then(setItems)
      .finally(() => setLoading(false))
  }

  const loadUpcoming = () => {
    api.plannedExpenses.upcoming(upcomingDays).then(setUpcoming)
  }

  useEffect(() => {
    if (!isActivePage) return
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterActive, filterCategory, isActivePage])
  useEffect(() => {
    if (!isActivePage) return
    loadUpcoming()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [upcomingDays, items.length, isActivePage])
  useEffect(() => {
    if (!isActivePage) return
    api.projects.list({ show_archived: true }).then(setProjects)
    api.categories.list({ category_type: 'expense' }).then(setApiCategories)
    api.workers
      .list()
      .then(setWorkers)
      .catch(() => setWorkers([]))
  }, [isActivePage])

  const openAdd = () => {
    const unassigned = findUnassignedProject(projects)
    setForm({
      name: '',
      description: '',
      amount: '',
      currency: 'RSD',
      category: '',
      category_id: '',
      project_id: unassigned ? String(unassigned.id) : '',
      worker_id: '',
      period: 'monthly',
      payment_day: 5,
      payment_day_of_week: 0,
      start_date: todayIso(),
      end_date: '',
      reminder_days: 3,
      is_active: true,
      note: '',
    })
    setModal('add')
  }

  const openEdit = (item) => {
    setForm({
      name: item.name || '',
      description: item.description || '',
      amount: item.amount,
      currency: item.currency || 'RSD',
      category: item.category || '\u2014',
      category_id: item.category_id ?? '',
      project_id: item.project_id ?? (unassignedProject ? String(unassignedProject.id) : ''),
      worker_id: item.worker_id ?? '',
      period: item.period || 'monthly',
      payment_day: item.payment_day ?? 5,
      payment_day_of_week: item.payment_day_of_week ?? 0,
      start_date: item.start_date,
      end_date: item.end_date || '',
      reminder_days: item.reminder_days ?? 3,
      is_active: item.is_active ?? true,
      note: item.note || '',
    })
    setModal({ type: 'edit', id: item.id })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      const categoryDefaultProjectId = getCategoryDefaultProjectId(form.category_id)
      const selectedPayloadCategory = form.category_id
        ? apiCategories.find((c) => String(c.id) === String(form.category_id))
        : form.category
      const shouldLinkWorker = isWorkerLinkedCategory(selectedPayloadCategory)
      const payload = {
        name: form.name.trim(),
        description: form.description?.trim() || null,
        amount: parseFloat(form.amount) || 0,
        currency: form.currency || 'RSD',
        category: form.category || null,
        category_id: form.category_id ? parseInt(form.category_id, 10) : null,
        project_id: categoryDefaultProjectId
          ? parseInt(categoryDefaultProjectId, 10)
          : form.project_id
            ? parseInt(form.project_id, 10)
            : unassignedProject
              ? unassignedProject.id
              : null,
        worker_id: shouldLinkWorker && form.worker_id ? parseInt(form.worker_id, 10) : null,
        period: form.period || 'monthly',
        payment_day: form.period === 'weekly' ? null : parseInt(form.payment_day) || 1,
        payment_day_of_week: form.period === 'weekly' ? (parseInt(form.payment_day_of_week) ?? 0) : null,
        start_date: form.start_date,
        end_date: form.end_date || null,
        reminder_days: parseInt(form.reminder_days) || 0,
        is_active: form.is_active,
        note: form.note?.trim() || null,
      }
      if (modal === 'add') {
        await api.plannedExpenses.create(payload)
      } else {
        await api.plannedExpenses.update(modal.id, payload)
      }
      setModal(null)
      load()
      loadUpcoming()
    } catch (err) {
      console.error(err)
    }
  }

  const openPaidModal = (u) => {
    setPaidForm({
      paid_date: todayIso(),
      note: '',
    })
    setPaidModal(u)
  }

  const handleMarkUnpaid = async (u) => {
    if (!confirm(tr('plannedConfirmUnmark'))) return
    try {
      await api.plannedExpenses.markUnpaid({
        planned_expense_id: u.planned_expense_id,
        due_date: u.due_date,
      })
      loadUpcoming()
    } catch (err) {
      console.error(err)
    }
  }

  const handleMarkPaidSubmit = async (e) => {
    e.preventDefault()
    if (!paidModal) return
    try {
      await api.plannedExpenses.markPaid({
        planned_expense_id: paidModal.planned_expense_id,
        due_date: paidModal.due_date,
        paid_date: paidForm.paid_date,
        note: paidForm.note || null,
      })
      setPaidModal(null)
      loadUpcoming()
    } catch (err) {
      console.error(err)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm(tr('confirmDeletePlannedExpense'))) return
    try {
      await api.plannedExpenses.delete(id)
      load()
      loadUpcoming()
    } catch (err) {
      console.error(err)
    }
  }

  const filteredItems = items.filter((i) => {
    if (!search) return true
    const s = search.toLowerCase()
    return (
      (i.name || '').toLowerCase().includes(s) ||
      (i.description || '').toLowerCase().includes(s) ||
      amountSearchHay(i.amount).includes(s)
    )
  })

  const totalMonthly = items
    .filter((i) => i.is_active)
    .reduce((sum, i) => {
      if (i.period === 'weekly') return sum + i.amount * 4.33
      if (i.period === 'monthly') return sum + i.amount
      if (i.period === 'quarterly') return sum + i.amount / 3
      if (i.period === 'yearly') return sum + i.amount / 12
      return sum
    }, 0)

  const lang = getLang()
  const unassignedProject = findUnassignedProject(projects)
  const {
    getCategoryById,
    getCategoryDefaultProjectId,
    usesCategoryProject,
    getCategoryLabel: getResolvedCategoryLabel,
  } = useCategoryProjectResolver(apiCategories, lang)
  const getCategoryLabel = (item) => {
    const resolved = getResolvedCategoryLabel(item, '')
    if (resolved) return resolved
    const legacy = CATEGORIES.find((c) => c.value === item.category)
    return legacy ? tr(legacy.label) : item.category || UI_DASH
  }
  const selectedFormCategory = form.category_id ? getCategoryById(form.category_id) : form.category
  const showWorkerField = isWorkerLinkedCategory(selectedFormCategory)
  const getWorkerName = (workerId) =>
    workers.find((worker) => Number(worker.id) === Number(workerId))?.name || ''

  return (
    <>
      <PageHeader
        title={tr('plannedExpenses')}
        actions={
          <>
            <select
              className="form-input"
              style={{ width: 'auto' }}
              value={filterActive}
              onChange={(e) => setFilterActive(e.target.value)}
            >
              <option value="active">{tr('plannedFilterActive')}</option>
              <option value="inactive">{tr('plannedFilterInactive')}</option>
              <option value="all">{tr('plannedFilterAll')}</option>
            </select>
            <select
              className="form-input"
              style={{ width: 'auto' }}
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
            >
              <option value="">{'\u2014'}</option>
              {apiCategories.map((c) => (
                <option key={c.id} value={c.id}>
                  {lang === 'ru' ? c.name_ru : c.name_sr}
                </option>
              ))}
            </select>
            <SearchInput
              placeholder={tr('search')}
              value={search}
              onChange={setSearch}
              style={{ width: 180 }}
            />
            <button className="btn btn-primary" onClick={openAdd}>
              {tr('add')}
            </button>
          </>
        }
      />

      <div className="page-body" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {/* Upcoming payments */}
        <div className="card">
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '1rem',
            }}
          >
            <h3 style={{ margin: 0, fontSize: '1rem' }}>{tr('plannedUpcoming')}</h3>
            <select
              className="form-input"
              style={{ width: 'auto' }}
              value={upcomingDays}
              onChange={(e) => setUpcomingDays(parseInt(e.target.value))}
            >
              <option value={30}>30 {tr('days')}</option>
              <option value={60}>60 {tr('days')}</option>
              <option value={90}>90 {tr('days')}</option>
            </select>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('plannedName')}</th>
                  <th>{tr('plannedDueDate')}</th>
                  <th>{tr('amount')}</th>
                  <th>{tr('worker')}</th>
                  <th>{tr('status')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {upcoming.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ color: 'var(--color-text-muted)' }}>
                      {tr('plannedNoUpcoming')}
                    </td>
                  </tr>
                ) : (
                  upcoming.map((u, idx) => (
                    <tr
                      key={`${u.planned_expense_id}-${u.due_date}-${idx}`}
                      style={u.is_paid ? { opacity: 0.85 } : {}}
                    >
                      <td>{u.name}</td>
                      <td>{formatDate(u.due_date)}</td>
                      <td>
                        {fmtAmount(u.amount)} {u.currency}
                      </td>
                      <td>{getWorkerName(u.worker_id) || UI_DASH}</td>
                      <td>
                        <SharedStatusBadge
                          tone={
                            u.is_paid
                              ? 'success'
                              : new Date(u.due_date + 'T12:00:00') < new Date()
                                ? 'danger'
                                : 'warning'
                          }
                          style={{ color: '#fff', padding: '0.2rem 0.5rem', borderRadius: 4 }}
                        >
                          {u.is_paid
                            ? tr('paid')
                            : new Date(u.due_date + 'T12:00:00') < new Date()
                              ? tr('obligationsOverdue')
                              : tr('unpaid')}
                        </SharedStatusBadge>
                      </td>
                      <td>
                        {u.is_paid ? (
                          <button className="btn btn-sm btn-secondary" onClick={() => handleMarkUnpaid(u)}>
                            {tr('markUnpaid')}
                          </button>
                        ) : (
                          <button className="btn btn-sm btn-primary" onClick={() => openPaidModal(u)}>
                            {tr('markPaid')}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Planned expenses list */}
        <div className="card">
          <h3 style={{ margin: '0 0 1rem', fontSize: '1rem' }}>{tr('plannedList')}</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('plannedName')}</th>
                  <th>{tr('category')}</th>
                  <th>{tr('amount')}</th>
                  <th>{tr('worker')}</th>
                  <th>{tr('plannedPeriod')}</th>
                  <th>{tr('plannedPaymentDay')}</th>
                  <th>{tr('status')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={8}>{tr('loading')}</td>
                  </tr>
                ) : filteredItems.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ color: 'var(--color-text-muted)' }}>
                      {tr('plannedNoItems')}
                    </td>
                  </tr>
                ) : (
                  filteredItems.map((i) => (
                    <tr key={i.id}>
                      <td>
                        <strong>{i.name}</strong>
                        {i.description && (
                          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                            {i.description.slice(0, 40)}
                            {i.description.length > 40 ? '\u2026' : ''}
                          </div>
                        )}
                      </td>
                      <td>{getCategoryLabel(i)}</td>
                      <td>
                        {fmtAmount(i.amount)} {i.currency}
                      </td>
                      <td>{getWorkerName(i.worker_id) || UI_DASH}</td>
                      <td>{tr(PERIODS.find((p) => p.value === i.period)?.label || i.period)}</td>
                      <td>
                        {i.period === 'weekly'
                          ? tr(DAYS_OF_WEEK.find((d) => d.value === i.payment_day_of_week)?.label || 'dayMon')
                          : (i.payment_day ?? '\u2014')}
                      </td>
                      <td>
                        <SharedStatusBadge
                          tone={i.is_active ? 'success' : 'muted'}
                          style={{ color: '#fff', padding: '0.2rem 0.5rem', borderRadius: 4 }}
                        >
                          {i.is_active ? tr('active') : tr('inactive')}
                        </SharedStatusBadge>
                      </td>
                      <td>
                        <button className="btn btn-sm btn-secondary" onClick={() => openEdit(i)}>
                          {tr('edit')}
                        </button>
                        <button
                          className="btn btn-sm btn-danger"
                          style={{ marginLeft: '0.5rem' }}
                          onClick={() => handleDelete(i.id)}
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
          {items.filter((i) => i.is_active).length > 0 && (
            <div style={{ marginTop: '1rem', fontWeight: 600, color: 'var(--color-accent)' }}>
              {tr('plannedMonthlyTotal')}: {fmtAmount(totalMonthly)} RSD
            </div>
          )}
        </div>
      </div>

      {/* Mark paid modal */}
      <Modal
        isOpen={!!paidModal}
        onClose={() => setPaidModal(null)}
        title={paidModal ? `${tr('markPaid')} \u2014 ${paidModal.name}` : tr('markPaid')}
        maxWidth="400px"
        closeOnOverlay
      >
        {paidModal ? (
          <>
            <p style={{ margin: '0 0 1rem', color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
              {tr('plannedMarkPaidHint')}
            </p>
            <form onSubmit={handleMarkPaidSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('date')}</label>
                <DatePicker
                  value={paidForm.paid_date}
                  onChange={(v) => setPaidForm({ ...paidForm, paid_date: v })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('note')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={paidForm.note}
                  onChange={(e) => setPaidForm({ ...paidForm, note: e.target.value })}
                  placeholder={tr('note')}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setPaidModal(null)}>
                  {tr('cancel')}
                </button>
                <button type="submit" className="btn btn-primary">
                  {tr('save')}
                </button>
              </div>
            </form>
          </>
        ) : null}
      </Modal>

      {/* Add/edit modal */}
      <Modal
        isOpen={!!modal}
        onClose={() => setModal(null)}
        title={`${modal === 'add' ? tr('add') : tr('edit')} \u2014 ${tr('plannedExpenses')}`}
        maxWidth="480px"
        closeOnOverlay
      >
        {modal ? (
          <>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('plannedName')} *</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                  placeholder={tr('plannedNamePlaceholder')}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('description')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder={tr('description')}
                />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('amount')} *</label>
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
                  <label className="form-label">{tr('plannedCurrency')}</label>
                  <select
                    className="form-input"
                    value={form.currency}
                    onChange={(e) => setForm({ ...form, currency: e.target.value })}
                  >
                    <option value="RSD">RSD</option>
                    <option value="EUR">EUR</option>
                    <option value="USD">USD</option>
                  </select>
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('category')}</label>
                <select
                  className="form-input"
                  value={form.category_id}
                  onChange={(e) => {
                    const cid = e.target.value
                    const cat = apiCategories.find((c) => String(c.id) === cid)
                    const defaultProjectId = cat?.default_project_id ? String(cat.default_project_id) : ''
                    setForm({
                      ...form,
                      category_id: cid,
                      category: cat ? cat.name_ru : '',
                      project_id: defaultProjectId || form.project_id,
                      worker_id: isWorkerLinkedCategory(cat) ? form.worker_id : '',
                    })
                  }}
                >
                  <option value="">{UI_DASH}</option>
                  {apiCategories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {lang === 'ru' ? c.name_ru : c.name_sr}
                    </option>
                  ))}
                </select>
              </div>
              {!usesCategoryProject(form.category_id) ? (
                <div className="form-group">
                  <label className="form-label">{tr('project')}</label>
                  <ProjectSelect
                    projects={projects}
                    value={form.project_id}
                    onChange={(nextValue) => setForm({ ...form, project_id: nextValue })}
                    required
                  />
                </div>
              ) : null}
              {showWorkerField ? (
                <div className="form-group">
                  <label className="form-label">{tr('worker')}</label>
                  <select
                    className="form-input"
                    value={form.worker_id}
                    onChange={(e) => setForm({ ...form, worker_id: e.target.value })}
                  >
                    <option value="">{UI_DASH}</option>
                    {workers.map((worker) => (
                      <option key={worker.id} value={worker.id}>
                        {worker.name}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}
              <div className="form-group">
                <label className="form-label">{tr('plannedPeriod')}</label>
                <select
                  className="form-input"
                  value={form.period}
                  onChange={(e) => setForm({ ...form, period: e.target.value })}
                >
                  {PERIODS.map((p) => (
                    <option key={p.value} value={p.value}>
                      {tr(p.label)}
                    </option>
                  ))}
                </select>
              </div>
              {form.period === 'weekly' ? (
                <div className="form-group">
                  <label className="form-label">{tr('plannedPaymentDayOfWeek')}</label>
                  <select
                    className="form-input"
                    value={form.payment_day_of_week}
                    onChange={(e) => setForm({ ...form, payment_day_of_week: parseInt(e.target.value) })}
                  >
                    {DAYS_OF_WEEK.map((d) => (
                      <option key={d.value} value={d.value}>
                        {tr(d.label)}
                      </option>
                    ))}
                  </select>
                </div>
              ) : (
                <div className="form-group">
                  <label className="form-label">{tr('plannedPaymentDay')}</label>
                  <input
                    type="number"
                    min={1}
                    max={31}
                    className="form-input"
                    value={form.payment_day}
                    onChange={(e) => setForm({ ...form, payment_day: e.target.value })}
                    placeholder="1-31"
                  />
                </div>
              )}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('plannedStartDate')} *</label>
                  <DatePicker
                    value={form.start_date}
                    onChange={(v) => setForm({ ...form, start_date: v })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('plannedEndDate')}</label>
                  <DatePicker value={form.end_date} onChange={(v) => setForm({ ...form, end_date: v })} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('plannedReminderDays')}</label>
                <input
                  type="number"
                  min={0}
                  max={30}
                  className="form-input"
                  value={form.reminder_days}
                  onChange={(e) => setForm({ ...form, reminder_days: e.target.value })}
                  placeholder={tr('plannedReminderPlaceholder')}
                />
              </div>
              <div className="form-group">
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                  />
                  {tr('active')}
                </label>
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
                <button type="submit" className="btn btn-primary">
                  {tr('save')}
                </button>
              </div>
            </form>
          </>
        ) : null}
      </Modal>
    </>
  )
}
