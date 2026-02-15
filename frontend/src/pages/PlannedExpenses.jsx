import { useState, useEffect } from 'react'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'

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
  { value: '', label: '—' },
  { value: 'rent', label: 'plannedCatRent' },
  { value: 'internet', label: 'plannedCatInternet' },
  { value: 'phone', label: 'plannedCatPhone' },
  { value: 'utilities', label: 'plannedCatUtilities' },
  { value: 'insurance', label: 'plannedCatInsurance' },
  { value: 'software', label: 'plannedCatSoftware' },
  { value: 'other', label: 'plannedCatOther' },
]

function formatDate(s) {
  if (!s) return '—'
  const d = new Date(s + 'T12:00:00')
  return d.toLocaleDateString('sr-RS', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export default function PlannedExpenses() {
  const [items, setItems] = useState([])
  const [upcoming, setUpcoming] = useState([])
  const [loading, setLoading] = useState(true)
  const [upcomingDays, setUpcomingDaysState] = useState(() => {
    const saved = localStorage.getItem('prospel_upcoming_days')
    const n = saved ? parseInt(saved, 10) : 60
    return (n === 30 || n === 60 || n === 90) ? n : 60
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
    paid_date: new Date().toISOString().slice(0, 10),
    note: '',
  })
  const [form, setForm] = useState({
    name: '',
    description: '',
    amount: '',
    currency: 'RSD',
    category: '',
    period: 'monthly',
    payment_day: 5,
    payment_day_of_week: 0,
    start_date: new Date().toISOString().slice(0, 10),
    end_date: '',
    reminder_days: 3,
    is_active: true,
    note: '',
  })

  const load = () => {
    setLoading(true)
    const params = {}
    if (filterActive === 'active') params.is_active = true
    else if (filterActive === 'inactive') params.is_active = false
    if (filterCategory) params.category = filterCategory
    api.plannedExpenses.list(params).then(setItems).finally(() => setLoading(false))
  }

  const loadUpcoming = () => {
    api.plannedExpenses.upcoming(upcomingDays).then(setUpcoming)
  }

  useEffect(load, [filterActive, filterCategory])
  useEffect(loadUpcoming, [upcomingDays, items.length])

  const openAdd = () => {
    setForm({
      name: '',
      description: '',
      amount: '',
      currency: 'RSD',
      category: '',
      period: 'monthly',
      payment_day: 5,
      payment_day_of_week: 0,
      start_date: new Date().toISOString().slice(0, 10),
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
      category: item.category || '',
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
      const payload = {
        name: form.name.trim(),
        description: form.description?.trim() || null,
        amount: parseFloat(form.amount) || 0,
        currency: form.currency || 'RSD',
        category: form.category || null,
        period: form.period || 'monthly',
        payment_day: form.period === 'weekly' ? null : (parseInt(form.payment_day) || 1),
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
      alert(err.message)
    }
  }

  const openPaidModal = (u) => {
    setPaidForm({
      paid_date: new Date().toISOString().slice(0, 10),
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
      alert(err.message)
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
      alert(err.message)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm(tr('confirmDeletePlannedExpense'))) return
    try {
      await api.plannedExpenses.delete(id)
      load()
      loadUpcoming()
    } catch (err) {
      alert(err.message)
    }
  }

  const filteredItems = items.filter((i) => {
    if (!search) return true
    const s = search.toLowerCase()
    return (i.name || '').toLowerCase().includes(s) ||
           (i.description || '').toLowerCase().includes(s)
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

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('plannedExpenses')}</h1>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
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
            <option value="">{tr('allCategories')}</option>
            {CATEGORIES.filter((c) => c.value).map((c) => (
              <option key={c.value} value={c.value}>
                {tr(c.label)}
              </option>
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
          <button className="btn btn-primary" onClick={openAdd}>
            {tr('add')}
          </button>
        </div>
      </div>

      <div className="page-body" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {/* Предстоящие платежи */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
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
                  <th>{tr('status')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {upcoming.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ color: 'var(--color-text-muted)' }}>
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
                        {u.amount.toLocaleString('sr-RS')} {u.currency}
                      </td>
                      <td>
                        <span
                          className="badge"
                          style={{
                            backgroundColor: u.is_paid ? 'var(--color-success)' : (new Date(u.due_date + 'T12:00:00') < new Date() ? 'var(--color-danger)' : 'var(--color-warning)'),
                            color: '#fff',
                            padding: '0.2rem 0.5rem',
                            borderRadius: 4,
                          }}
                        >
                          {u.is_paid ? tr('paid') : (new Date(u.due_date + 'T12:00:00') < new Date() ? tr('obligationsOverdue') : tr('unpaid'))}
                        </span>
                      </td>
                      <td>
                        {u.is_paid ? (
                          <button
                            className="btn btn-sm btn-secondary"
                            onClick={() => handleMarkUnpaid(u)}
                          >
                            {tr('markUnpaid')}
                          </button>
                        ) : (
                          <button
                            className="btn btn-sm btn-primary"
                            onClick={() => openPaidModal(u)}
                          >
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

        {/* Список планируемых расходов */}
        <div className="card">
          <h3 style={{ margin: '0 0 1rem', fontSize: '1rem' }}>{tr('plannedList')}</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('plannedName')}</th>
                  <th>{tr('category')}</th>
                  <th>{tr('amount')}</th>
                  <th>{tr('plannedPeriod')}</th>
                  <th>{tr('plannedPaymentDay')}</th>
                  <th>{tr('status')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={7}>{tr('loading')}</td>
                  </tr>
                ) : filteredItems.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ color: 'var(--color-text-muted)' }}>
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
                            {i.description.length > 40 ? '…' : ''}
                          </div>
                        )}
                      </td>
                      <td>{CATEGORIES.find((c) => c.value === i.category)?.label ? tr(CATEGORIES.find((c) => c.value === i.category).label) : i.category || '—'}</td>
                      <td>
                        {i.amount.toLocaleString('sr-RS')} {i.currency}
                      </td>
                      <td>{tr(PERIODS.find((p) => p.value === i.period)?.label || i.period)}</td>
                      <td>
                        {i.period === 'weekly'
                          ? tr(DAYS_OF_WEEK.find((d) => d.value === i.payment_day_of_week)?.label || 'dayMon')
                          : i.payment_day ?? '—'}
                      </td>
                      <td>
                        <span
                          className="badge"
                          style={{
                            backgroundColor: i.is_active ? 'var(--color-success)' : 'var(--color-text-muted)',
                            color: '#fff',
                            padding: '0.2rem 0.5rem',
                            borderRadius: 4,
                          }}
                        >
                          {i.is_active ? tr('active') : tr('inactive')}
                        </span>
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
              {tr('plannedMonthlyTotal')}: {totalMonthly.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ' ')} RSD
            </div>
          )}
        </div>
      </div>

      {/* Модальное окно «Отметить оплаченным» */}
      {paidModal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 400 }}>
            <div className="modal-header">
              <h2 className="modal-title">
                {tr('markPaid')} — {paidModal.name}
              </h2>
              <button className="modal-close" onClick={() => setPaidModal(null)}>×</button>
            </div>
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
                <button type="submit" className="btn btn-primary">{tr('save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Модальное окно добавления/редактирования */}
      {modal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <div className="modal-header">
              <h2 className="modal-title">
                {modal === 'add' ? tr('add') : tr('edit')} — {tr('plannedExpenses')}
              </h2>
              <button className="modal-close" onClick={() => setModal(null)}>
                ×
              </button>
            </div>
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
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                >
                  {CATEGORIES.map((c) => (
                    <option key={c.value || 'empty'} value={c.value}>
                      {tr(c.label)}
                    </option>
                  ))}
                </select>
              </div>
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
                  <DatePicker
                    value={form.end_date}
                    onChange={(v) => setForm({ ...form, end_date: v })}
                  />
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
          </div>
        </div>
      )}
    </>
  )
}
