import { useCallback, useEffect, useMemo, useState } from 'react'
import { FileText, Plus, Printer, Save, Trash2 } from 'lucide-react'
import { api } from '../api'
import { tr } from '../i18n'
import PageHeader from '../components/PageHeader'
import { formatInteger as fmtAmount } from '../utils/formatters'

const todayIso = () => new Date().toISOString().slice(0, 10)

const emptyForm = {
  date: todayIso(),
  project_id: '',
  worker_id: '',
  description: '',
  start_time: '07:00',
  end_time: '15:00',
  hours: '',
  hourly_rate_snapshot: '',
  per_diem: false,
  per_diem_amount: '',
  lodging_amount: '',
  food_allowance: false,
  food_amount: '',
  weather: '',
  temperature: '',
  note: '',
}

const emptyMeta = {
  investor: '',
  permit_number: '',
  contractor: '',
  place: '',
  supervision: '',
  object_name: '',
  sector: '',
  responsible_person: '',
  billing_hourly_rate: '',
}

function num(value) {
  return Number(value || 0)
}

function money(value) {
  return `${fmtAmount(value || 0)} RSD`
}

function hours(value) {
  return Number(value || 0).toFixed(2)
}

function dateLabel(value) {
  if (!value) return ''
  const [year, month, day] = value.split('-')
  return day && month && year ? `${day}.${month}.${year}.` : value
}

function dayName(value) {
  if (!value) return ''
  return ['Недеља', 'Понедељак', 'Уторак', 'Среда', 'Четвртак', 'Петак', 'Субота'][
    new Date(value).getDay()
  ]
}

function groupByDate(entries) {
  return entries.reduce((acc, entry) => {
    if (!acc[entry.date]) acc[entry.date] = []
    acc[entry.date].push(entry)
    return acc
  }, {})
}

function entryWorkerName(entry) {
  return entry.worker_name || tr('workDiariesNoWorker')
}

export default function WorkDiaries() {
  const [projects, setProjects] = useState([])
  const [workers, setWorkers] = useState([])
  const [entries, setEntries] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [tab, setTab] = useState('entries')
  const [filters, setFilters] = useState({
    project_id: '',
    worker_id: '',
    date_from: '',
    date_to: '',
  })
  const [form, setForm] = useState(emptyForm)
  const [materials, setMaterials] = useState([])
  const [meta, setMeta] = useState(emptyMeta)

  const selectedProject = useMemo(
    () => projects.find((project) => String(project.id) === String(filters.project_id || form.project_id)),
    [projects, filters.project_id, form.project_id]
  )

  const queryParams = useMemo(() => {
    const params = {}
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params[key] = value
    })
    return params
  }, [filters])

  const loadEntries = useCallback(() => {
    setLoading(true)
    return Promise.all([api.workDiaries.entries(queryParams), api.workDiaries.summary(queryParams)])
      .then(([entryData, summaryData]) => {
        setEntries(entryData)
        setSummary(summaryData)
      })
      .finally(() => setLoading(false))
  }, [queryParams])

  const loadDictionaries = useCallback(() => {
    return Promise.all([api.projects.list({ show_archived: false }), api.workers.list({ active: true })]).then(
      ([projectData, workerData]) => {
        setProjects(projectData)
        setWorkers(workerData)
      }
    )
  }, [])

  useEffect(() => {
    loadDictionaries()
  }, [loadDictionaries])

  useEffect(() => {
    loadEntries()
  }, [loadEntries])

  useEffect(() => {
    if (!filters.project_id) {
      setMeta(emptyMeta)
      return
    }
    api.workDiaries.projectMeta(filters.project_id).then((data) => {
      setMeta({
        investor: data.investor || '',
        permit_number: data.permit_number || '',
        contractor: data.contractor || '',
        place: data.place || '',
        supervision: data.supervision || '',
        object_name: data.object_name || '',
        sector: data.sector || '',
        responsible_person: data.responsible_person || '',
        billing_hourly_rate: data.billing_hourly_rate || '',
      })
    })
  }, [filters.project_id])

  const setFilter = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }))
    if (key === 'project_id') setForm((prev) => ({ ...prev, project_id: value }))
  }

  const setFormField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const addMaterial = () => {
    setMaterials((prev) => [...prev, { description: '', quantity: '', amount: '' }])
  }

  const updateMaterial = (index, key, value) => {
    setMaterials((prev) => prev.map((item, itemIndex) => (itemIndex === index ? { ...item, [key]: value } : item)))
  }

  const removeMaterial = (index) => {
    setMaterials((prev) => prev.filter((_, itemIndex) => itemIndex !== index))
  }

  const submitEntry = async (event) => {
    event.preventDefault()
    setSaving(true)
    try {
      await api.workDiaries.createEntry({
        ...form,
        project_id: Number(form.project_id),
        worker_id: form.worker_id ? Number(form.worker_id) : null,
        hours: form.hours === '' ? null : num(form.hours),
        hourly_rate_snapshot: form.hourly_rate_snapshot === '' ? null : num(form.hourly_rate_snapshot),
        per_diem_amount: num(form.per_diem_amount),
        lodging_amount: num(form.lodging_amount),
        food_amount: num(form.food_amount),
        materials: materials
          .filter((item) => item.description.trim())
          .map((item) => ({
            description: item.description.trim(),
            quantity: item.quantity,
            amount: num(item.amount),
          })),
      })
      setForm((prev) => ({
        ...emptyForm,
        project_id: prev.project_id,
        date: prev.date,
        weather: '',
        temperature: '',
      }))
      setMaterials([])
      await loadEntries()
    } finally {
      setSaving(false)
    }
  }

  const saveMeta = async () => {
    if (!filters.project_id) return
    const saved = await api.workDiaries.updateProjectMeta(filters.project_id, {
      ...meta,
      billing_hourly_rate: num(meta.billing_hourly_rate),
    })
    setMeta({
      investor: saved.investor || '',
      permit_number: saved.permit_number || '',
      contractor: saved.contractor || '',
      place: saved.place || '',
      supervision: saved.supervision || '',
      object_name: saved.object_name || '',
      sector: saved.sector || '',
      responsible_person: saved.responsible_person || '',
      billing_hourly_rate: saved.billing_hourly_rate || '',
    })
    await loadEntries()
  }

  const deleteEntry = async (entry) => {
    if (!confirm(tr('workDiariesDeleteConfirm'))) return
    await api.workDiaries.deleteEntry(entry.id)
    loadEntries()
  }

  const sortedForPrint = useMemo(() => [...entries].sort((a, b) => a.date.localeCompare(b.date)), [entries])
  const entriesByDate = useMemo(() => groupByDate(sortedForPrint), [sortedForPrint])
  const printProjectName = selectedProject?.name || entries[0]?.project_name || ''
  const objectName = meta.object_name || printProjectName

  return (
    <div className="page work-diaries-page">
      <PageHeader
        title={tr('workDiariesTitle')}
        subtitle={tr('workDiariesSubtitle')}
        actions={
          <>
            <button
              type="button"
              className={`btn btn-sm ${tab === 'entries' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setTab('entries')}
            >
              <Plus size={16} /> {tr('workDiariesEntries')}
            </button>
            <button
              type="button"
              className={`btn btn-sm ${tab === 'diary' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setTab('diary')}
            >
              <FileText size={16} /> {tr('workDiariesDiary')}
            </button>
            <button
              type="button"
              className={`btn btn-sm ${tab === 'report' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setTab('report')}
            >
              <FileText size={16} /> {tr('workDiariesReport')}
            </button>
            <button type="button" className="btn btn-sm btn-secondary" onClick={() => window.print()}>
              <Printer size={16} /> {tr('print')}
            </button>
          </>
        }
      />

      <div className="page-body">
        <div className="card work-diaries-filters no-print">
          <div className="work-diaries-filter-grid">
            <label className="form-group">
              <span className="form-label">{tr('project')}</span>
              <select
                className="form-input"
                value={filters.project_id}
                onChange={(event) => setFilter('project_id', event.target.value)}
              >
                <option value="">{tr('allProjects')}</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-group">
              <span className="form-label">{tr('worker')}</span>
              <select
                className="form-input"
                value={filters.worker_id}
                onChange={(event) => setFilter('worker_id', event.target.value)}
              >
                <option value="">{tr('allWorkers')}</option>
                {workers.map((worker) => (
                  <option key={worker.id} value={worker.id}>
                    {worker.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-group">
              <span className="form-label">{tr('dateFrom')}</span>
              <input
                className="form-input"
                type="date"
                value={filters.date_from}
                onChange={(event) => setFilter('date_from', event.target.value)}
              />
            </label>
            <label className="form-group">
              <span className="form-label">{tr('dateTo')}</span>
              <input
                className="form-input"
                type="date"
                value={filters.date_to}
                onChange={(event) => setFilter('date_to', event.target.value)}
              />
            </label>
          </div>
        </div>

        {filters.project_id ? (
          <div className="card no-print">
            <div className="work-diaries-meta-grid">
              {[
                ['investor', tr('workDiariesInvestor')],
                ['permit_number', tr('workDiariesPermit')],
                ['contractor', tr('workDiariesContractor')],
                ['place', tr('workDiariesPlace')],
                ['supervision', tr('workDiariesSupervision')],
                ['object_name', tr('workDiariesObject')],
                ['sector', tr('workDiariesSector')],
                ['responsible_person', tr('workDiariesResponsible')],
                ['billing_hourly_rate', tr('workDiariesBillingRate')],
              ].map(([key, label]) => (
                <label className="form-group" key={key}>
                  <span className="form-label">{label}</span>
                  <input
                    className="form-input"
                    type={key === 'billing_hourly_rate' ? 'number' : 'text'}
                    min="0"
                    step="0.01"
                    value={meta[key]}
                    onChange={(event) => setMeta((prev) => ({ ...prev, [key]: event.target.value }))}
                  />
                </label>
              ))}
              <button type="button" className="btn btn-primary work-diaries-save-meta" onClick={saveMeta}>
                <Save size={16} /> {tr('save')}
              </button>
            </div>
          </div>
        ) : null}

        <div className="work-diaries-summary no-print">
          {[
            [tr('workDiariesDays'), summary?.days_count || 0],
            [tr('workDiariesWorkers'), summary?.workers_count || 0],
            [tr('workDiariesHours'), hours(summary?.hours)],
            [tr('workDiariesLabor'), money(summary?.labor_amount)],
            [tr('workDiariesMaterials'), money(summary?.material_amount)],
            [tr('workDiariesBillable'), money(summary?.billable_amount)],
          ].map(([label, value]) => (
            <div className="work-diaries-summary-item" key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>

        {tab === 'entries' ? (
          <>
            <form className="card no-print work-diaries-entry-form" onSubmit={submitEntry}>
              <div className="work-diaries-form-grid">
                <label className="form-group">
                  <span className="form-label">{tr('date')}</span>
                  <input
                    className="form-input"
                    type="date"
                    value={form.date}
                    required
                    onChange={(event) => setFormField('date', event.target.value)}
                  />
                </label>
                <label className="form-group">
                  <span className="form-label">{tr('project')}</span>
                  <select
                    className="form-input"
                    value={form.project_id}
                    required
                    onChange={(event) => setFormField('project_id', event.target.value)}
                  >
                    <option value="">{tr('select')}</option>
                    {projects.map((project) => (
                      <option key={project.id} value={project.id}>
                        {project.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-group">
                  <span className="form-label">{tr('worker')}</span>
                  <select
                    className="form-input"
                    value={form.worker_id}
                    onChange={(event) => setFormField('worker_id', event.target.value)}
                  >
                    <option value="">{tr('workDiariesNoWorker')}</option>
                    {workers.map((worker) => (
                      <option key={worker.id} value={worker.id}>
                        {worker.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-group">
                  <span className="form-label">{tr('workDiariesStart')}</span>
                  <input
                    className="form-input"
                    type="time"
                    value={form.start_time}
                    onChange={(event) => setFormField('start_time', event.target.value)}
                  />
                </label>
                <label className="form-group">
                  <span className="form-label">{tr('workDiariesEnd')}</span>
                  <input
                    className="form-input"
                    type="time"
                    value={form.end_time}
                    onChange={(event) => setFormField('end_time', event.target.value)}
                  />
                </label>
                <label className="form-group">
                  <span className="form-label">{tr('workDiariesHoursManual')}</span>
                  <input
                    className="form-input"
                    type="number"
                    min="0"
                    step="0.25"
                    value={form.hours}
                    onChange={(event) => setFormField('hours', event.target.value)}
                  />
                </label>
                <label className="form-group">
                  <span className="form-label">{tr('workDiariesHourlyRate')}</span>
                  <input
                    className="form-input"
                    type="number"
                    min="0"
                    step="0.01"
                    value={form.hourly_rate_snapshot}
                    onChange={(event) => setFormField('hourly_rate_snapshot', event.target.value)}
                  />
                </label>
                <label className="form-group">
                  <span className="form-label">{tr('workDiariesWeather')}</span>
                  <select
                    className="form-input"
                    value={form.weather}
                    onChange={(event) => setFormField('weather', event.target.value)}
                  >
                    <option value="">{tr('select')}</option>
                    {['Сунчано', 'Облачно', 'Киша', 'Снег', 'Ветар', 'Магла'].map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-group">
                  <span className="form-label">{tr('workDiariesTemperature')}</span>
                  <input
                    className="form-input"
                    value={form.temperature}
                    onChange={(event) => setFormField('temperature', event.target.value)}
                  />
                </label>
                <label className="form-group work-diaries-wide">
                  <span className="form-label">{tr('workDiariesDescription')}</span>
                  <textarea
                    className="form-input"
                    rows={3}
                    value={form.description}
                    required
                    onChange={(event) => setFormField('description', event.target.value)}
                  />
                </label>
                <label className="form-group work-diaries-wide">
                  <span className="form-label">{tr('note')}</span>
                  <textarea
                    className="form-input"
                    rows={2}
                    value={form.note}
                    onChange={(event) => setFormField('note', event.target.value)}
                  />
                </label>
              </div>

              <div className="work-diaries-allowances">
                <label>
                  <input
                    type="checkbox"
                    checked={form.per_diem}
                    onChange={(event) => setFormField('per_diem', event.target.checked)}
                  />{' '}
                  {tr('workDiariesPerDiem')}
                </label>
                <input
                  className="form-input"
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.per_diem_amount}
                  placeholder={tr('amount')}
                  onChange={(event) => setFormField('per_diem_amount', event.target.value)}
                />
                <label>
                  <input
                    type="checkbox"
                    checked={form.food_allowance}
                    onChange={(event) => setFormField('food_allowance', event.target.checked)}
                  />{' '}
                  {tr('workDiariesFood')}
                </label>
                <input
                  className="form-input"
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.food_amount}
                  placeholder={tr('amount')}
                  onChange={(event) => setFormField('food_amount', event.target.value)}
                />
                <input
                  className="form-input"
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.lodging_amount}
                  placeholder={tr('workDiariesLodging')}
                  onChange={(event) => setFormField('lodging_amount', event.target.value)}
                />
              </div>

              <div className="work-diaries-materials">
                <div className="work-diaries-section-row">
                  <strong>{tr('workDiariesMaterials')}</strong>
                  <button type="button" className="btn btn-sm btn-secondary" onClick={addMaterial}>
                    <Plus size={16} /> {tr('add')}
                  </button>
                </div>
                {materials.map((material, index) => (
                  <div className="work-diaries-material-row" key={index}>
                    <input
                      className="form-input"
                      value={material.description}
                      placeholder={tr('description')}
                      onChange={(event) => updateMaterial(index, 'description', event.target.value)}
                    />
                    <input
                      className="form-input"
                      value={material.quantity}
                      placeholder={tr('quantity')}
                      onChange={(event) => updateMaterial(index, 'quantity', event.target.value)}
                    />
                    <input
                      className="form-input"
                      type="number"
                      min="0"
                      step="0.01"
                      value={material.amount}
                      placeholder={tr('amount')}
                      onChange={(event) => updateMaterial(index, 'amount', event.target.value)}
                    />
                    <button type="button" className="btn btn-sm btn-danger" onClick={() => removeMaterial(index)}>
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>

              <button type="submit" className="btn btn-primary" disabled={saving}>
                <Save size={16} /> {saving ? tr('saving') : tr('save')}
              </button>
            </form>

            <div className="card">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>{tr('date')}</th>
                      <th>{tr('project')}</th>
                      <th>{tr('worker')}</th>
                      <th>{tr('workDiariesDescription')}</th>
                      <th style={{ textAlign: 'right' }}>{tr('workDiariesHours')}</th>
                      <th style={{ textAlign: 'right' }}>{tr('workDiariesMaterials')}</th>
                      <th style={{ textAlign: 'right' }}>{tr('workDiariesBillable')}</th>
                      <th className="no-print"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr>
                        <td colSpan={8}>{tr('loading')}</td>
                      </tr>
                    ) : entries.length === 0 ? (
                      <tr>
                        <td colSpan={8} style={{ color: 'var(--color-text-muted)' }}>
                          {tr('workDiariesEmpty')}
                        </td>
                      </tr>
                    ) : (
                      entries.map((entry) => (
                        <tr key={entry.id}>
                          <td className="date-cell">{dateLabel(entry.date)}</td>
                          <td>{entry.project_name}</td>
                          <td>{entryWorkerName(entry)}</td>
                          <td>{entry.description}</td>
                          <td style={{ textAlign: 'right' }}>{hours(entry.hours)}</td>
                          <td style={{ textAlign: 'right' }}>{money(entry.material_amount)}</td>
                          <td style={{ textAlign: 'right' }}>{money(entry.billable_amount)}</td>
                          <td className="no-print" style={{ textAlign: 'right' }}>
                            <button className="btn btn-sm btn-danger" onClick={() => deleteEntry(entry)}>
                              <Trash2 size={16} />
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        ) : null}

        {tab === 'diary' ? (
          <div className="work-diaries-print-surface">
            {!filters.project_id ? (
              <div className="card no-print">{tr('workDiariesSelectProject')}</div>
            ) : Object.keys(entriesByDate).length === 0 ? (
              <div className="card no-print">{tr('workDiariesEmpty')}</div>
            ) : (
              Object.entries(entriesByDate).map(([date, dayEntries], index) => {
                const dayMaterials = dayEntries.flatMap((entry) => entry.materials || [])
                const descriptions = [...new Set(dayEntries.map((entry) => entry.description).filter(Boolean))]
                const notes = [...new Set(dayEntries.map((entry) => entry.note).filter(Boolean))]
                return (
                  <section className="work-diary-print-page" key={date}>
                    <div className="work-diary-grid">
                      <div>
                        <strong>ИЗВОЂАЧ РАДОВА:</strong> {meta.contractor}
                        <br />
                        <strong>ОБЈЕКАТ:</strong> {objectName}
                        <br />
                        <strong>МЕСТО:</strong> {meta.place}
                      </div>
                      <div>
                        <strong>ИНВЕСТИТОР:</strong>
                        <br />
                        {meta.investor}
                        <br />
                        <strong>Бр. грађ. дозволе:</strong> {meta.permit_number}
                      </div>
                      <div className="work-diary-title-cell">
                        <h2>ГРАЂЕВИНСКИ ДНЕВНИК</h2>
                        <span>
                          ДАН: <strong>{dayName(date)}</strong>
                        </span>
                        <span>
                          ДАТУМ: <strong>{dateLabel(date)}</strong>
                        </span>
                        <span>
                          Лист бр. <strong>{index + 1}</strong>
                        </span>
                      </div>
                      <div>
                        <strong>РАДНО ВРЕМЕ</strong>
                        <br />
                        од {dayEntries[0]?.start_time || ''} до {dayEntries[0]?.end_time || ''}
                      </div>
                      <div>
                        <strong>БРОЈ РАДНИКА</strong>
                        <br />
                        {new Set(dayEntries.map((entry) => entry.worker_id).filter(Boolean)).size}
                      </div>
                      <div>
                        <strong>ВРЕМЕНСКИ УСЛОВИ</strong>
                        <br />
                        {dayEntries.find((entry) => entry.weather)?.weather || ''}{' '}
                        {dayEntries.find((entry) => entry.temperature)?.temperature || ''}
                      </div>
                    </div>
                    <table className="work-diary-print-table">
                      <tbody>
                        <tr>
                          <th>ОПИС РАДОВА</th>
                          <td>
                            {descriptions.map((description) => (
                              <p key={description}>{description}</p>
                            ))}
                            {dayMaterials.length ? (
                              <>
                                <strong>Материјал:</strong>
                                {dayMaterials.map((material) => (
                                  <p key={material.id}>
                                    {material.description}
                                    {material.quantity ? ` - ${material.quantity}` : ''}
                                    {material.amount ? ` - ${money(material.amount)}` : ''}
                                  </p>
                                ))}
                              </>
                            ) : null}
                          </td>
                        </tr>
                        <tr>
                          <th>РАДНИЦИ</th>
                          <td>{dayEntries.map((entry) => entryWorkerName(entry)).join(', ')}</td>
                        </tr>
                        <tr>
                          <th>ПРИМЕДБЕ</th>
                          <td>{notes.join('; ')}</td>
                        </tr>
                      </tbody>
                    </table>
                    <div className="work-diary-signatures">
                      <span>Одговорни извођач</span>
                      <span>Надзорни орган</span>
                    </div>
                  </section>
                )
              })
            )}
          </div>
        ) : null}

        {tab === 'report' ? (
          <div className="work-diaries-print-surface">
            <section className="work-diary-report-page">
              <div className="work-diary-report-header">
                <div>
                  <span>Градилиште</span>
                  <strong>{printProjectName}</strong>
                </div>
                <div>
                  <span>Сектор</span>
                  <strong>{meta.sector}</strong>
                </div>
                <div>
                  <span>Објекат</span>
                  <strong>{objectName}</strong>
                </div>
                <div>
                  <span>Период</span>
                  <strong>
                    {filters.date_from || '...'} - {filters.date_to || '...'}
                  </strong>
                </div>
              </div>
              <h2>Евиденција радних сати и утрошеног материјала</h2>
              <table className="work-diary-report-table">
                <thead>
                  <tr>
                    <th>Датум</th>
                    <th>Радник</th>
                    <th>Опис радова</th>
                    <th>Поч.</th>
                    <th>Крај</th>
                    <th>Сати</th>
                    <th>Ред.</th>
                    <th>Прек.</th>
                    <th>Материјал</th>
                    <th>За фактурисање</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedForPrint.map((entry) => (
                    <tr key={entry.id}>
                      <td>{dateLabel(entry.date)}</td>
                      <td>{entryWorkerName(entry)}</td>
                      <td>{entry.description}</td>
                      <td>{entry.start_time}</td>
                      <td>{entry.end_time}</td>
                      <td>{hours(entry.hours)}</td>
                      <td>{hours(entry.regular_hours)}</td>
                      <td>{entry.overtime_hours > 0 ? hours(entry.overtime_hours) : ''}</td>
                      <td>{money(entry.material_amount)}</td>
                      <td>{money(entry.billable_amount)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={5}>УКУПНО</td>
                    <td>{hours(summary?.hours)}</td>
                    <td>{hours(summary?.regular_hours)}</td>
                    <td>{hours(summary?.overtime_hours)}</td>
                    <td>{money(summary?.material_amount)}</td>
                    <td>{money(summary?.billable_amount)}</td>
                  </tr>
                </tfoot>
              </table>
            </section>
          </div>
        ) : null}
      </div>
    </div>
  )
}
