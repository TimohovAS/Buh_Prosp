import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import { UI_DASH, formatInteger as fmtAmount } from '../utils/formatters'
import { getLang } from '../i18n'

const emptyForm = {
  name: '',
  worker_type: 'temporary',
  pay_scheme: 'per_day',
  phone: '',
  note: '',
  regular_day_rate: '',
  monthly_rate: '',
  trip_work_day_rate: '',
  trip_per_diem_rate: '2500',
  trip_food_rate: '3000',
  trip_advance_day_rate: '3000',
  lodging_night_rate: '',
  lodging_nights_offset: '-1',
  default_project_id: '',
  default_category_id: '',
  is_active: true,
}

function num(value) {
  return Number(value || 0)
}

export default function Workers() {
  const location = useLocation()
  const isActivePage = location.pathname === '/workers'
  const [items, setItems] = useState([])
  const [projects, setProjects] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [sortCol, setSortCol] = useState('name')
  const [sortAsc, setSortAsc] = useState(true)
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const lang = getLang()

  const load = () => {
    setLoading(true)
    const workerParams = { search }
    if (!showInactive) workerParams.active = true
    return Promise.all([
      api.workers.list(workerParams),
      api.projects.list({ show_archived: true }),
      api.categories.list({ category_type: 'expense' }),
    ])
      .then(([workers, projectList, categoryList]) => {
        setItems(workers)
        setProjects(projectList)
        setCategories(categoryList)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return
    load()
  }, [search, showInactive, isActivePage])

  const getCategoryLabel = (id) => {
    const category = categories.find((item) => Number(item.id) === Number(id))
    if (!category) return UI_DASH
    return lang === 'ru' ? (category.name_ru || category.name_sr) : (category.name_sr || category.name_ru)
  }

  const getProjectName = (id) => projects.find((project) => Number(project.id) === Number(id))?.name || UI_DASH

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
      monthly_rate: item.monthly_rate ?? '',
      trip_work_day_rate: item.trip_work_day_rate ?? '',
      trip_per_diem_rate: item.trip_per_diem_rate ?? '2500',
      trip_food_rate: item.trip_food_rate ?? '3000',
      trip_advance_day_rate: item.trip_advance_day_rate ?? '3000',
      lodging_night_rate: item.lodging_night_rate ?? '',
      lodging_nights_offset: item.lodging_nights_offset ?? '-1',
      default_project_id: item.default_project_id ?? '',
      default_category_id: item.default_category_id ?? '',
      is_active: item.is_active !== false,
    })
    setModal({ type: 'edit', id: item.id })
  }

  const payloadFromForm = () => ({
    ...form,
    regular_day_rate: num(form.regular_day_rate),
    monthly_rate: num(form.monthly_rate),
    trip_work_day_rate: num(form.trip_work_day_rate),
    trip_per_diem_rate: num(form.trip_per_diem_rate),
    trip_food_rate: num(form.trip_food_rate),
    trip_advance_day_rate: num(form.trip_advance_day_rate),
    lodging_night_rate: num(form.lodging_night_rate),
    lodging_nights_offset: parseInt(form.lodging_nights_offset || '-1', 10),
    default_project_id: form.default_project_id ? parseInt(form.default_project_id, 10) : null,
    default_category_id: form.default_category_id ? parseInt(form.default_category_id, 10) : null,
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
                  <th style={{ textAlign: 'right' }}>Месяц</th>
                  <th style={{ textAlign: 'right' }}>Командировка/день</th>
                  <th>Проект</th>
                  <th>Категория</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={9}>Загрузка...</td></tr>
                ) : sorted.length === 0 ? (
                  <tr><td colSpan={9} style={{ color: 'var(--color-text-muted)' }}>Работники не добавлены</td></tr>
                ) : sorted.map((item) => (
                  <tr key={item.id} className="record-row" onClick={() => openEdit(item)} tabIndex={0}>
                    <td>{item.name}</td>
                    <td>{item.worker_type === 'permanent' ? 'Постоянный' : 'Временный'}</td>
                    <td>{item.pay_scheme === 'monthly' ? 'Раз в месяц' : 'За выход'}</td>
                    <td style={{ textAlign: 'right' }}>{fmtAmount(item.regular_day_rate)} RSD</td>
                    <td style={{ textAlign: 'right' }}>{fmtAmount(item.monthly_rate)} RSD</td>
                    <td style={{ textAlign: 'right' }}>{fmtAmount(num(item.trip_work_day_rate) + num(item.trip_per_diem_rate) + num(item.trip_food_rate))} RSD</td>
                    <td>{getProjectName(item.default_project_id)}</td>
                    <td>{getCategoryLabel(item.default_category_id)}</td>
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
                <label className="form-label">Месячная ставка</label>
                <input className="form-input" type="number" min="0" step="0.01" value={form.monthly_rate} onChange={(event) => setForm({ ...form, monthly_rate: event.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Работа в командировке/день</label>
                <input className="form-input" type="number" min="0" step="0.01" value={form.trip_work_day_rate} onChange={(event) => setForm({ ...form, trip_work_day_rate: event.target.value })} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem' }}>
              <div className="form-group">
                <label className="form-label">Дневница</label>
                <input className="form-input" type="number" min="0" step="0.01" value={form.trip_per_diem_rate} onChange={(event) => setForm({ ...form, trip_per_diem_rate: event.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Питание/день</label>
                <input className="form-input" type="number" min="0" step="0.01" value={form.trip_food_rate} onChange={(event) => setForm({ ...form, trip_food_rate: event.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Аванс/день</label>
                <input className="form-input" type="number" min="0" step="0.01" value={form.trip_advance_day_rate} onChange={(event) => setForm({ ...form, trip_advance_day_rate: event.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Гостиница/ночь</label>
                <input className="form-input" type="number" min="0" step="0.01" value={form.lodging_night_rate} onChange={(event) => setForm({ ...form, lodging_night_rate: event.target.value })} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
              <div className="form-group">
                <label className="form-label">Проект по умолчанию</label>
                <ProjectSelect projects={projects} value={form.default_project_id} onChange={(value) => setForm({ ...form, default_project_id: value })} allowEmpty emptyLabel={UI_DASH} />
              </div>
              <div className="form-group">
                <label className="form-label">Категория по умолчанию</label>
                <select className="form-input" value={form.default_category_id} onChange={(event) => setForm({ ...form, default_category_id: event.target.value })}>
                  <option value="">{UI_DASH}</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>{getCategoryLabel(category.id)}</option>
                  ))}
                </select>
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
