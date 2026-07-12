import { useCallback, useEffect, useMemo, useState } from 'react'
import { Building2, Pencil, Plus, Printer, Trash2 } from 'lucide-react'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import PageHeader from '../components/PageHeader'
import SortIndicator from '../components/SortIndicator'
import WorkDiaryCostsTab from '../components/work-diaries/WorkDiaryCostsTab'
import WorkDiaryEntryModal from '../components/work-diaries/WorkDiaryEntryModal'
import WorkDiaryMetaModal from '../components/work-diaries/WorkDiaryMetaModal'
import WorkDiaryPrintDiary from '../components/work-diaries/WorkDiaryPrintDiary'
import WorkDiaryPrintReport from '../components/work-diaries/WorkDiaryPrintReport'
import {
  DEFAULT_OVERTIME_MULTIPLIER,
  dateLabel,
  hours,
  money,
} from '../components/work-diaries/workDiaryUtils'

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

function entryWorkerName(entry) {
  return entry.worker_names?.length ? entry.worker_names.join(', ') : tr('workDiariesNoWorker')
}

function groupByDate(entries) {
  return entries.reduce((acc, entry) => {
    if (!acc[entry.date]) acc[entry.date] = []
    acc[entry.date].push(entry)
    return acc
  }, {})
}

const TABS = ['entries', 'costs', 'diary', 'report']

const TAB_LABEL_KEYS = {
  entries: 'workDiariesEntries',
  costs: 'workDiariesCosts',
  diary: 'workDiariesDiary',
  report: 'workDiariesReport',
}

export default function WorkDiaries() {
  const [projects, setProjects] = useState([])
  const [workers, setWorkers] = useState([])
  const [entries, setEntries] = useState([])
  const [summary, setSummary] = useState(null)
  const [meta, setMeta] = useState(emptyMeta)
  const [overtimeMultiplier, setOvertimeMultiplier] = useState(DEFAULT_OVERTIME_MULTIPLIER)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('entries')
  const [entryModalOpen, setEntryModalOpen] = useState(false)
  const [editingEntry, setEditingEntry] = useState(null)
  const [metaModalOpen, setMetaModalOpen] = useState(false)
  const [sortCol, setSortCol] = useState('date')
  const [sortAsc, setSortAsc] = useState(false)
  const [filters, setFilters] = useState({
    project_id: '',
    worker_id: '',
    date_from: '',
    date_to: '',
  })

  const selectedProject = useMemo(
    () => projects.find((project) => String(project.id) === String(filters.project_id)),
    [projects, filters.project_id]
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

  useEffect(() => {
    Promise.all([api.projects.list({ show_archived: false }), api.workers.list({ active: true })]).then(
      ([projectData, workerData]) => {
        setProjects(projectData)
        setWorkers(workerData)
      }
    )
    api.enterprise.get().then((enterprise) => {
      setOvertimeMultiplier(Number(enterprise?.work_diary_overtime_multiplier) || DEFAULT_OVERTIME_MULTIPLIER)
    })
  }, [])

  useEffect(() => {
    loadEntries()
  }, [loadEntries])

  const loadMeta = useCallback(() => {
    if (!filters.project_id) {
      setMeta(emptyMeta)
      return Promise.resolve()
    }
    return api.workDiaries.projectMeta(filters.project_id).then((data) => {
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

  useEffect(() => {
    loadMeta()
  }, [loadMeta])

  const setFilter = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }))
  }

  const toggleSort = (col) => {
    if (sortCol === col) {
      setSortAsc((prev) => !prev)
    } else {
      setSortCol(col)
      setSortAsc(col === 'date' ? false : true)
    }
  }

  const sortedEntries = useMemo(() => {
    const accessor = {
      date: (entry) => entry.date,
      project: (entry) => entry.project_name || '',
      workers: (entry) => entryWorkerName(entry),
      person_hours: (entry) => entry.person_hours,
      total_cost: (entry) => entry.total_cost_amount,
      billable: (entry) => entry.billable_amount,
    }[sortCol]
    if (!accessor) return entries
    const sorted = [...entries].sort((left, right) => {
      const leftValue = accessor(left)
      const rightValue = accessor(right)
      if (typeof leftValue === 'number' && typeof rightValue === 'number') {
        return leftValue - rightValue
      }
      return String(leftValue).localeCompare(String(rightValue))
    })
    return sortAsc ? sorted : sorted.reverse()
  }, [entries, sortCol, sortAsc])

  const openNewEntry = () => {
    setEditingEntry(null)
    setEntryModalOpen(true)
  }

  const openEditEntry = (entry) => {
    setEditingEntry(entry)
    setEntryModalOpen(true)
  }

  const closeEntryModal = () => {
    setEntryModalOpen(false)
    setEditingEntry(null)
  }

  const handleEntrySaved = async () => {
    await loadEntries()
    closeEntryModal()
  }

  const deleteEntry = async (entry) => {
    if (!confirm(tr('workDiariesDeleteConfirm'))) return
    await api.workDiaries.deleteEntry(entry.id)
    loadEntries()
  }

  const sortedForPrint = useMemo(() => [...entries].sort((a, b) => a.date.localeCompare(b.date)), [entries])
  const entriesByDate = useMemo(() => groupByDate(sortedForPrint), [sortedForPrint])
  const printProjectName = selectedProject?.name || ''
  const objectName = meta.object_name || printProjectName
  const canPrint = (tab === 'diary' || tab === 'report') && Boolean(filters.project_id) && entries.length > 0

  const sortableTh = (col, label, alignRight = false) => (
    <th
      style={{ cursor: 'pointer', ...(alignRight ? { textAlign: 'right' } : {}) }}
      onClick={() => toggleSort(col)}
    >
      {label} <SortIndicator active={sortCol === col} asc={sortAsc} />
    </th>
  )

  return (
    <div className="page work-diaries-page">
      <PageHeader
        title={tr('workDiariesTitle')}
        subtitle={tr('workDiariesSubtitle')}
        actions={
          <>
            <button type="button" className="btn btn-sm btn-primary" onClick={openNewEntry}>
              <Plus size={16} /> {tr('workDiariesAddEntry')}
            </button>
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => setMetaModalOpen(true)}
              disabled={!filters.project_id}
              title={!filters.project_id ? tr('workDiariesSelectProject') : undefined}
            >
              <Building2 size={16} /> {tr('workDiariesMetaButton')}
            </button>
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => window.print()}
              disabled={!canPrint}
              title={!canPrint ? tr('workDiariesPrintHint') : undefined}
            >
              <Printer size={16} /> {tr('print')}
            </button>
          </>
        }
      />

      <div className="page-body">
        <div className="work-diaries-tabs no-print">
          {TABS.map((value) => (
            <button
              key={value}
              type="button"
              className={`work-diaries-tab ${tab === value ? 'active' : ''}`}
              onClick={() => setTab(value)}
            >
              {tr(TAB_LABEL_KEYS[value])}
            </button>
          ))}
        </div>

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
              <span className="form-label">{tr('workDiariesWorkerFilter')}</span>
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
              <DatePicker
                value={filters.date_from}
                onChange={(value) => setFilter('date_from', value)}
                placeholder={tr('dateFrom')}
              />
            </label>
            <label className="form-group">
              <span className="form-label">{tr('dateTo')}</span>
              <DatePicker
                value={filters.date_to}
                onChange={(value) => setFilter('date_to', value)}
                placeholder={tr('dateTo')}
              />
            </label>
          </div>
        </div>

        {tab !== 'costs' ? (
          <div className="work-diaries-summary no-print">
            {[
              [tr('workDiariesDays'), summary?.days_count || 0],
              [tr('workDiariesWorkers'), summary?.workers_count || 0],
              [tr('workDiariesPersonHours'), hours(summary?.person_hours)],
              [tr('workDiariesLabor'), money(summary?.labor_amount)],
              [tr('workDiariesPayout'), money(summary?.payout_amount)],
              [tr('workDiariesMaterials'), money(summary?.material_amount)],
              [tr('workDiariesBillable'), money(summary?.billable_amount)],
            ].map(([label, value]) => (
              <div className="work-diaries-summary-item" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        ) : null}

        {tab === 'entries' ? (
          <div className="card">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {sortableTh('date', tr('date'))}
                    {sortableTh('project', tr('project'))}
                    {sortableTh('workers', tr('worker'))}
                    <th>{tr('workDiariesDescription')}</th>
                    {sortableTh('person_hours', tr('workDiariesPersonHours'), true)}
                    {sortableTh('total_cost', tr('workDiariesTotalCost'), true)}
                    {sortableTh('billable', tr('workDiariesBillable'), true)}
                    <th className="no-print"></th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={8}>{tr('loading')}</td>
                    </tr>
                  ) : sortedEntries.length === 0 ? (
                    <tr>
                      <td colSpan={8} style={{ color: 'var(--color-text-muted)' }}>
                        {tr('workDiariesEmpty')}
                      </td>
                    </tr>
                  ) : (
                    sortedEntries.map((entry) => (
                      <tr key={entry.id}>
                        <td className="date-cell">{dateLabel(entry.date)}</td>
                        <td>{entry.project_name}</td>
                        <td>{entryWorkerName(entry)}</td>
                        <td>{entry.description}</td>
                        <td className="work-diaries-hours-cell">
                          <strong>{hours(entry.person_hours)}</strong>
                          <span>
                            {hours(entry.duration_hours)} × {entry.worker_ids.length}
                          </span>
                        </td>
                        <td style={{ textAlign: 'right' }}>{money(entry.total_cost_amount)}</td>
                        <td style={{ textAlign: 'right' }}>{money(entry.billable_amount)}</td>
                        <td className="no-print">
                          <div className="work-diaries-row-actions">
                            <button
                              type="button"
                              className="btn btn-sm btn-secondary"
                              onClick={() => openEditEntry(entry)}
                              title={tr('workDiariesEdit')}
                              aria-label={tr('workDiariesEdit')}
                            >
                              <Pencil size={16} />
                            </button>
                            <button
                              type="button"
                              className="btn btn-sm btn-danger"
                              onClick={() => deleteEntry(entry)}
                              title={tr('delete')}
                              aria-label={tr('delete')}
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {tab === 'costs' ? (
          <WorkDiaryCostsTab
            projectId={filters.project_id}
            dateFrom={filters.date_from}
            dateTo={filters.date_to}
          />
        ) : null}

        {tab === 'diary' ? (
          !filters.project_id ? (
            <div className="card work-diaries-empty-state no-print">{tr('workDiariesSelectProject')}</div>
          ) : Object.keys(entriesByDate).length === 0 ? (
            <div className="card work-diaries-empty-state no-print">{tr('workDiariesEmpty')}</div>
          ) : (
            <WorkDiaryPrintDiary entriesByDate={entriesByDate} meta={meta} objectName={objectName} />
          )
        ) : null}

        {tab === 'report' ? (
          !filters.project_id ? (
            <div className="card work-diaries-empty-state no-print">{tr('workDiariesSelectProject')}</div>
          ) : entries.length === 0 ? (
            <div className="card work-diaries-empty-state no-print">{tr('workDiariesEmpty')}</div>
          ) : (
            <WorkDiaryPrintReport
              entries={sortedForPrint}
              summary={summary}
              meta={meta}
              projectName={printProjectName}
              objectName={objectName}
              dateFrom={filters.date_from}
              dateTo={filters.date_to}
            />
          )
        ) : null}
      </div>

      <WorkDiaryEntryModal
        isOpen={entryModalOpen}
        onClose={closeEntryModal}
        onSaved={handleEntrySaved}
        entry={editingEntry}
        projects={projects}
        workers={workers}
        defaultProjectId={filters.project_id}
        overtimeMultiplier={overtimeMultiplier}
      />
      <WorkDiaryMetaModal
        isOpen={metaModalOpen}
        onClose={() => setMetaModalOpen(false)}
        projectId={filters.project_id}
        projectName={printProjectName}
        onSaved={async () => {
          await loadMeta()
          await loadEntries()
        }}
      />
    </div>
  )
}
