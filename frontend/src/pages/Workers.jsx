import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import { formatInteger as fmtAmount } from '../utils/formatters'

const emptyForm = {
  name: '',
  worker_type: 'temporary',
  pay_scheme: 'per_day',
  phone: '',
  note: '',
  regular_day_rate: '',
  weekly_rate: '',
  monthly_rate: '',
  trip_pricing_mode: 'allowances',
  trip_work_day_rate: '',
  trip_per_diem_rate: '2500',
  trip_food_rate: '3000',
  trip_advance_day_rate: '3000',
  lodging_night_rate: '',
  lodging_nights_offset: '-1',
  is_active: true,
}

function num(value) {
  return Number(value || 0)
}

export default function Workers() {
  const location = useLocation()
  const isActivePage = location.pathname === '/workers'
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [sortCol, setSortCol] = useState('name')
  const [sortAsc, setSortAsc] = useState(true)
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState(emptyForm)

  const load = () => {
    setLoading(true)
    const workerParams = { search }
    if (!showInactive) workerParams.active = true
    return api.workers.list(workerParams)
      .then(setItems)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return
    load()
  }, [search, showInactive, isActivePage])

  const sorted = useMemo(() => {
    return [...items].sort((left, right) => {
      const leftValue = left[sortCol] ?? ''
      const rightValue = right[sortCol] ?? ''
      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
  }, [items, sortCol, sortAsc])

  const toggleSort = (col) => {
    if (sortCol === col) {
      setSortAsc((value) => !value)
      return
    }
    setSortCol(col)
    setSortAsc(true)
  }

  const openAdd = () => {
    setForm(emptyForm)
    setModal('add')
  }

  const openEdit = (item) => {
    setForm({
      name: item.name || '',
      worker_type: item.worker_type || 'temporary',
      pay_scheme: item.pay_scheme || 'per_day',
      phone: item.phone || '',
      note: item.note || '',
      regular_day_rate: item.regular_day_rate ?? '',
      weekly_rate: item.weekly_rate ?? '',
      monthly_rate: item.monthly_rate ?? '',
      trip_pricing_mode: item.trip_pricing_mode || 'allowances',
      trip_work_day_rate: item.trip_work_day_rate ?? '',
      trip_per_diem_rate: item.trip_per_diem_rate ?? '2500',
      trip_food_rate: item.trip_food_rate ?? '3000',
      trip_advance_day_rate: item.trip_advance_day_rate ?? '3000',
      lodging_night_rate: item.lodging_night_rate ?? '',
      lodging_nights_offset: item.lodging_nights_offset ?? '-1',
      is_active: item.is_active !== false,
    })
    setModal({ type: 'edit', id: item.id })
  }

  const payloadFromForm = () => ({
    ...form,
    regular_day_rate: num(form.regular_day_rate),
    weekly_rate: num(form.weekly_rate),
    monthly_rate: num(form.monthly_rate),
    trip_work_day_rate: num(form.trip_work_day_rate),
    trip_per_diem_rate: num(form.trip_per_diem_rate),
    trip_food_rate: num(form.trip_food_rate),
    trip_advance_day_rate: num(form.trip_advance_day_rate),
    lodging_night_rate: num(form.lodging_night_rate),
    lodging_nights_offset: parseInt(form.lodging_nights_offset || '-1', 10),
  })

  const handleSubmit = async (event) => {
    event.preventDefault()
    const payload = payloadFromForm()
    if (modal === 'add') {
      await api.workers.create(payload)
    } else {
      await api.workers.update(modal.id, payload)
    }
    setModal(null)
    load()
  }

  const archiveWorker = async (item) => {
    if (!confirm(`Архивировать работника "${item.name}"?`)) return
    await api.workers.delete(item.id)
    load()
  }

  return (
    <>
      <PageHeader
        title="Работники"
        subtitle="Постоянные и временные работники, ставки и правила командировок."
        actions={(
          <>
            <SearchInput placeholder="Поиск" value={search} onChange={setSearch} style={{ width: 220 }} />
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-text-muted)' }}>
              <input type="checkbox" checked={showInactive} onChange={(event) => setShowInactive(event.target.checked)} />
              Архив
            </label>
            <button className="btn btn-primary" onClick={openAdd}>Добавить</button>
          </>
        )}
      />

      <div className="page-body">
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('name')}>Имя <SortIndicator active={sortCol === 'name'} asc={sortAsc} /></th>
                  <th>Тип</th>
                  <th>Схема</th>
                  <th style={{ textAlign: 'right' }}>За выход</th>
                  <th style={{ textAlign: 'right' }}>Неделя</th>
                  <th style={{ textAlign: 'right' }}>Месяц</th>
                  <th style={{ textAlign: 'right' }}>Командировка/день</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={8}>Загрузка...</td></tr>
                ) : sorted.length === 0 ? (
                  <tr><td colSpan={8} style={{ color: 'var(--color-text-muted)' }}>Работники не добавлены</td></tr>
                ) : sorted.map((item) => (
                  <tr key={item.id} className="record-row" onClick={() => openEdit(item)} tabIndex={0}>
                    <td>{item.name}</td>
                    <td>{item.worker_type === 'permanent' ? 'Постоянный' : 'Временный'}</td>
                    <td>{item.pay_scheme === 'monthly' ? 'Раз в месяц' : item.pay_scheme === 'weekly' ? 'Еженедельно' : 'За выход'}</td>
                    <td style={{ textAlign: 'right' }}>{fmtAmount(item.regular_day_rate)} RSD</td>
                    <td style={{ textAlign: 'right' }}>{fmtAmount(item.weekly_rate)} RSD</td>
                    <td style={{ textAlign: 'right' }}>{fmtAmount(item.monthly_rate)} RSD</td>
                    <td style={{ textAlign: 'right' }}>{fmtAmount(num(item.trip_work_day_rate) + (item.trip_pricing_mode === 'fixed_plus_lodging' ? 0 : num(item.trip_per_diem_rate) + num(item.trip_food_rate)))} RSD</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn btn-sm btn-secondary" onClick={(event) => { event.stopPropagation(); archiveWorker(item) }}>Архив</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <Modal isOpen={!!modal} onClose={() => setModal(null)} title={modal === 'add' ? 'Добавить работника' : 'Изменить работника'}>
        {modal ? (
          <form onSubmit={handleSubmit} className="card" style={{ padding: '1rem' }}>
            <div className="form-group">
              <label className="form-label">Имя</label>
              <input className="form-input" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
              <div className="form-group">
                <label className="form-label">Тип</label>
                <select className="form-input" value={form.worker_type} onChange={(event) => setForm({ ...form, worker_type: event.target.value })}>
                  <option value="temporary">Временный</option>
                  <option value="permanent">Постоянный</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Схема оплаты</label>
                <select className="form-input" value={form.pay_scheme} onChange={(event) => setForm({ ...form, pay_scheme: event.target.value })}>
                  <option value="per_day">За выход</option>
                  <option value="weekly">Еженедельно</option>
                  <option value="monthly">Раз в месяц</option>
                </select>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem' }}>
              <div className="form-group">
                <label className="form-label">Ставка за выход</label>
                <input className="form-input" type="number" min="0" step="0.01" value={form.regular_day_rate} onChange={(event) => setForm({ ...form, regular_day_rate: event.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Недельная ставка</label>
                <input className="form-input" type="number" min="0" step="0.01" value={form.weekly_rate} onChange={(event) => setForm({ ...form, weekly_rate: event.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Месячная ставка</label>
                <input className="form-input" type="number" min="0" step="0.01" value={form.monthly_rate} onChange={(event) => setForm({ ...form, monthly_rate: event.target.value })} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
              <div className="form-group">
                <label className="form-label">Расчет командировки</label>
                <select
                  className="form-input"
                  value={form.trip_pricing_mode}
                  onChange={(event) => setForm({ ...form, trip_pricing_mode: event.target.value })}
                >
                  <option value="allowances">Работа + дневница + питание + проживание</option>
                  <option value="fixed_plus_lodging">Фиксированная ставка/день + проживание</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Работа в командировке/день</label>
                <input className="form-input" type="number" min="0" step="0.01" value={form.trip_work_day_rate} onChange={(event) => setForm({ ...form, trip_work_day_rate: event.target.value })} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem' }}>
              {form.trip_pricing_mode !== 'fixed_plus_lodging' ? (
                <>
                  <div className="form-group">
                    <label className="form-label">Дневница</label>
                    <input className="form-input" type="number" min="0" step="0.01" value={form.trip_per_diem_rate} onChange={(event) => setForm({ ...form, trip_per_diem_rate: event.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Питание/день</label>
                    <input className="form-input" type="number" min="0" step="0.01" value={form.trip_food_rate} onChange={(event) => setForm({ ...form, trip_food_rate: event.target.value })} />
                  </div>
                </>
              ) : null}
              <div className="form-group">
                <label className="form-label">Аванс/день</label>
                <input className="form-input" type="number" min="0" step="0.01" value={form.trip_advance_day_rate} onChange={(event) => setForm({ ...form, trip_advance_day_rate: event.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Гостиница/ночь</label>
                <input className="form-input" type="number" min="0" step="0.01" value={form.lodging_night_rate} onChange={(event) => setForm({ ...form, lodging_night_rate: event.target.value })} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Примечание</label>
              <input className="form-input" value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>Отмена</button>
              <button type="submit" className="btn btn-primary">Сохранить</button>
            </div>
          </form>
        ) : null}
      </Modal>
    </>
  )
}
