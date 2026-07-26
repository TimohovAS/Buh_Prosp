import { useCallback, useEffect, useMemo, useState } from 'react'
import { Building2, Eye, FileSpreadsheet, FileText, Pencil, Plus, Printer, Trash2 } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import PageHeader from '../components/PageHeader'
import SelectionSummary from '../components/SelectionSummary'
import SortIndicator from '../components/SortIndicator'
import WorkDiaryCostsTab from '../components/work-diaries/WorkDiaryCostsTab'
import WorkDiaryEntryModal from '../components/work-diaries/WorkDiaryEntryModal'
import WorkDiaryInvoiceModal from '../components/work-diaries/WorkDiaryInvoiceModal'
import WorkDiaryMaterialsTab from '../components/work-diaries/WorkDiaryMaterialsTab'
import WorkDiaryMetaModal from '../components/work-diaries/WorkDiaryMetaModal'
import WorkDiaryPrintDiary from '../components/work-diaries/WorkDiaryPrintDiary'
import WorkDiaryPrintReport from '../components/work-diaries/WorkDiaryPrintReport'
import {
  DEFAULT_MATERIAL_BILLING_MULTIPLIER,
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

const TABS = ['entries', 'costs', 'materials', 'diary', 'report']

const TAB_LABEL_KEYS = {
  entries: 'workDiariesEntries',
  costs: 'workDiariesCosts',
  materials: 'workDiariesMaterials',
  diary: 'workDiariesDiary',
  report: 'workDiariesReport',
}

export default function WorkDiaries() {
  const location = useLocation()
  const navigate = useNavigate()
  const isActivePage = location.pathname === '/work-diaries'
  const [projects, setProjects] = useState([])
  const [workers, setWorkers] = useState([])
  const [entries, setEntries] = useState([])
  const [summary, setSummary] = useState(null)
  const [meta, setMeta] = useState(emptyMeta)
  const [overtimeMultiplier, setOvertimeMultiplier] = useState(DEFAULT_OVERTIME_MULTIPLIER)
  const [materialBillingMultiplier, setMaterialBillingMultiplier] = useState(
    DEFAULT_MATERIAL_BILLING_MULTIPLIER
  )
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('entries')
  const [entryModalOpen, setEntryModalOpen] = useState(false)
  const [editingEntry, setEditingEntry] = useState(null)
  const [metaModalOpen, setMetaModalOpen] = useState(false)
  const [invoiceModalOpen, setInvoiceModalOpen] = useState(false)
  const [exportingProposal, setExportingProposal] = useState(false)
  const [selectedIds, setSelectedIds] = useState([])
  const [billingFilter, setBillingFilter] = useState('')
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

  const loadReferenceData = useCallback(() => {
    return Promise.all([
      api.projects.list({ show_archived: false }),
      api.workers.list({ active: true }),
    ]).then(([projectData, workerData]) => {
      setProjects(projectData)
      setWorkers(workerData)
    })
  }, [])

  useEffect(() => {
    if (!isActivePage) return
    loadReferenceData()
    api.enterprise.get().then((enterprise) => {
      setOvertimeMultiplier(Number(enterprise?.work_diary_overtime_multiplier) || DEFAULT_OVERTIME_MULTIPLIER)
      setMaterialBillingMultiplier(
        Number(enterprise?.work_diary_material_billing_multiplier) || DEFAULT_MATERIAL_BILLING_MULTIPLIER
      )
    })
  }, [isActivePage, loadReferenceData])

  useEffect(() => {
    if (!isActivePage) return
    loadEntries()
  }, [isActivePage, loadEntries])

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
      })
    })
  }, [filters.project_id])

  useEffect(() => {
    if (!isActivePage) return
    loadMeta()
  }, [isActivePage, loadMeta])

  const setFilter = (key, value) => {
    setSelectedIds([])
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
      materials: (entry) => entry.material_amount,
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

  const displayedEntries = useMemo(
    () =>
      billingFilter ? sortedEntries.filter((entry) => entry.billing_status === billingFilter) : sortedEntries,
    [billingFilter, sortedEntries]
  )

  const selectedEntries = useMemo(
    () => entries.filter((entry) => selectedIds.includes(entry.id)),
    [entries, selectedIds]
  )
  const selectedEntryProjectId = selectedEntries[0]?.project_id || null
  const invoiceProject = useMemo(() => {
    const projectId = selectedEntryProjectId || filters.project_id
    return projects.find((project) => String(project.id) === String(projectId)) || null
  }, [projects, selectedEntryProjectId, filters.project_id])

  const invoiceEntryUnavailableReason = useCallback(
    (entry) => {
      const project = projects.find((item) => String(item.id) === String(entry.project_id))
      if (project?.is_internal) return tr('workDiariesInvoiceUnavailableInternalProject')
      if (!project?.client_id) return tr('workDiariesInvoiceUnavailableMissingClient')
      if (entry.billing_status === 'invoiced') return tr('workDiariesInvoiceUnavailableAlreadyInvoiced')
      if (Number(entry.remaining_billable_amount) <= 0) {
        return tr('workDiariesInvoiceUnavailableNoAmount')
      }
      return ''
    },
    [projects]
  )
  const toggleEntrySelection = (entry) => {
    setSelectedIds((current) => {
      if (current.includes(entry.id)) return current.filter((id) => id !== entry.id)
      return [...current, entry.id]
    })
  }

  const selectAllDisplayedEntries = () => {
    const ids = displayedEntries.map((entry) => entry.id)
    const allSelected = ids.length > 0 && ids.every((id) => selectedIds.includes(id))
    setSelectedIds(allSelected ? [] : ids)
  }

  const allDisplayedSelected =
    displayedEntries.length > 0 && displayedEntries.every((entry) => selectedIds.includes(entry.id))
  const invoiceSelectionUnavailableReason = useMemo(() => {
    const projectIds = new Set(selectedEntries.map((entry) => String(entry.project_id)))
    if (projectIds.size > 1) return tr('workDiariesInvoiceSameProject')
    return selectedEntries.map(invoiceEntryUnavailableReason).find(Boolean) || ''
  }, [invoiceEntryUnavailableReason, selectedEntries])
  const proposalExportUnavailableReason = useMemo(() => {
    const projectIds = new Set(selectedEntries.map((entry) => String(entry.project_id)))
    if (projectIds.size > 1) return tr('workDiariesProposalSameProject')
    if (invoiceProject?.is_internal) return tr('workDiariesProposalUnavailableInternalProject')
    if (!invoiceProject?.client_id) return tr('workDiariesProposalUnavailableMissingClient')
    return ''
  }, [invoiceProject, selectedEntries])

  const billingStatusBadge = (entry) => {
    const status = entry.billing_status || 'not_invoiced'
    const badgeClass = {
      not_invoiced: 'badge-muted',
      partially_invoiced: 'badge-warning',
      invoiced: 'badge-success',
    }[status]
    return <span className={`badge ${badgeClass}`}>{tr(`workDiariesBillingStatus_${status}`)}</span>
  }

  const openNewEntry = async () => {
    try {
      await loadReferenceData()
    } finally {
      setEditingEntry(null)
      setEntryModalOpen(true)
    }
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

  const handleInvoiceCreated = async (createdInvoice) => {
    setInvoiceModalOpen(false)
    setSelectedIds([])
    await loadEntries()
    navigate('/income', { state: { openIncomeId: createdInvoice.income_id } })
  }

  const exportSelectedProposal = async () => {
    if (proposalExportUnavailableReason || exportingProposal) return
    setExportingProposal(true)
    try {
      await api.workDiaries.exportProposalXlsx(selectedEntries.map((entry) => entry.id))
    } finally {
      setExportingProposal(false)
    }
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
            <label className="form-group">
              <span className="form-label">{tr('workDiariesBillingStatus')}</span>
              <select
                className="form-input"
                value={billingFilter}
                onChange={(event) => {
                  setBillingFilter(event.target.value)
                  setSelectedIds([])
                }}
              >
                <option value="">{tr('workDiariesBillingStatusAll')}</option>
                <option value="not_invoiced">{tr('workDiariesBillingStatus_not_invoiced')}</option>
                <option value="partially_invoiced">
                  {tr('workDiariesBillingStatus_partially_invoiced')}
                </option>
                <option value="invoiced">{tr('workDiariesBillingStatus_invoiced')}</option>
              </select>
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
              [tr('workDiariesMaterials'), money(summary?.material_amount)],
              [
                tr('workDiariesCustomerLabor'),
                money(
                  Math.max(
                    Number(summary?.billable_amount || 0) - Number(summary?.billable_material_amount || 0),
                    0
                  )
                ),
              ],
              [tr('workDiariesBillableTotal'), money(summary?.billable_amount)],
              [tr('workDiariesInvoiced'), money(summary?.invoiced_amount)],
              [tr('workDiariesRemainingToInvoice'), money(summary?.remaining_billable_amount)],
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
                    <th className="no-print work-diaries-select-cell">
                      <span className="work-diaries-checkbox-wrapper">
                        <input
                          type="checkbox"
                          checked={allDisplayedSelected}
                          disabled={!displayedEntries.length}
                          onChange={selectAllDisplayedEntries}
                          aria-label={tr('workDiariesSelectAll')}
                        />
                      </span>
                    </th>
                    {sortableTh('date', tr('date'))}
                    {sortableTh('project', tr('project'))}
                    {sortableTh('workers', tr('worker'))}
                    <th>{tr('workDiariesDescription')}</th>
                    {sortableTh('person_hours', tr('workDiariesPersonHours'), true)}
                    {sortableTh('total_cost', tr('workDiariesTotalCost'), true)}
                    {sortableTh('materials', tr('workDiariesMaterialCost'), true)}
                    {sortableTh('billable', tr('workDiariesBillable'), true)}
                    <th>{tr('workDiariesBillingStatus')}</th>
                    <th>{tr('workDiariesInvoice')}</th>
                    <th className="no-print"></th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={12}>{tr('loading')}</td>
                    </tr>
                  ) : displayedEntries.length === 0 ? (
                    <tr>
                      <td colSpan={12} style={{ color: 'var(--color-text-muted)' }}>
                        {tr('workDiariesEmpty')}
                      </td>
                    </tr>
                  ) : (
                    displayedEntries.map((entry) => {
                      const selected = selectedIds.includes(entry.id)
                      const activeLinks = (entry.invoice_links || []).filter(
                        (link) => link.invoice_status !== 'cancelled'
                      )
                      const cancelledLinks = (entry.invoice_links || []).filter(
                        (link) => link.invoice_status === 'cancelled'
                      )
                      const entryLocked = entry.billing_status !== 'not_invoiced'
                      return (
                        <tr key={entry.id} className={selected ? 'record-row-selected' : ''}>
                          <td className="no-print work-diaries-select-cell">
                            <span className="work-diaries-checkbox-wrapper">
                              <input
                                type="checkbox"
                                checked={selected}
                                onChange={() => toggleEntrySelection(entry)}
                                aria-label={tr('workDiariesSelectEntry')}
                              />
                            </span>
                          </td>
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
                          <td style={{ textAlign: 'right' }}>{money(entry.material_amount)}</td>
                          <td className="work-diaries-billable-cell">
                            <strong>{money(entry.billable_amount)}</strong>
                            {entry.billable_amount_override != null ? (
                              <span>
                                {tr('workDiariesBillableAuto')}: {money(entry.calculated_billable_amount)}
                              </span>
                            ) : null}
                          </td>
                          <td>{billingStatusBadge(entry)}</td>
                          <td className="work-diaries-invoice-links">
                            {activeLinks.map((link) => (
                              <button
                                type="button"
                                className="work-diaries-invoice-link"
                                key={link.income_id}
                                onClick={() =>
                                  navigate('/income', { state: { openIncomeId: link.income_id } })
                                }
                              >
                                {link.invoice_number}
                              </button>
                            ))}
                            {!activeLinks.length && cancelledLinks.length ? (
                              <span className="work-diaries-cancelled-invoice">
                                {tr('workDiariesInvoiceCancelled')} {cancelledLinks.at(-1).invoice_number}
                              </span>
                            ) : null}
                            {entry.billing_status === 'partially_invoiced' ? (
                              <small>
                                {tr('workDiariesRemaining')}: {money(entry.remaining_billable_amount)}
                              </small>
                            ) : null}
                          </td>
                          <td className="no-print">
                            <div className="work-diaries-row-actions">
                              <button
                                type="button"
                                className="btn btn-sm btn-secondary"
                                onClick={() => openEditEntry(entry)}
                                title={tr(entryLocked ? 'workDiariesView' : 'workDiariesEdit')}
                                aria-label={tr(entryLocked ? 'workDiariesView' : 'workDiariesEdit')}
                              >
                                {entryLocked ? <Eye size={16} /> : <Pencil size={16} />}
                              </button>
                              <button
                                type="button"
                                className="btn btn-sm btn-danger"
                                onClick={() => deleteEntry(entry)}
                                disabled={entryLocked}
                                title={entryLocked ? tr('workDiariesInvoiceLocked') : tr('delete')}
                                aria-label={tr('delete')}
                              >
                                <Trash2 size={16} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })
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

        {tab === 'materials' ? <WorkDiaryMaterialsTab entries={entries} loading={loading} /> : null}

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

      {tab === 'entries' && selectedEntries.length ? (
        <SelectionSummary
          count={selectedEntries.length}
          countLabel={tr('workDiariesInvoiceSelected')}
          items={[
            {
              label: tr('workDiariesInvoiceSelectedTotal'),
              value: money(
                selectedEntries.reduce((sum, entry) => sum + Number(entry.remaining_billable_amount || 0), 0)
              ),
            },
          ]}
          actions={
            <>
              <span title={proposalExportUnavailableReason || undefined}>
                <button
                  type="button"
                  className="btn btn-sm btn-secondary"
                  disabled={Boolean(proposalExportUnavailableReason) || exportingProposal}
                  onClick={exportSelectedProposal}
                >
                  <FileSpreadsheet size={16} />
                  {tr(exportingProposal ? 'workDiariesProposalExporting' : 'workDiariesProposalExport')}
                </button>
              </span>
              <span title={invoiceSelectionUnavailableReason || undefined}>
                <button
                  type="button"
                  className="btn btn-sm btn-primary"
                  disabled={Boolean(invoiceSelectionUnavailableReason)}
                  onClick={() => {
                    if (!invoiceSelectionUnavailableReason) setInvoiceModalOpen(true)
                  }}
                >
                  <FileText size={16} /> {tr('workDiariesCreateInvoice')}
                </button>
              </span>
            </>
          }
          onClear={() => setSelectedIds([])}
        />
      ) : null}

      <WorkDiaryEntryModal
        isOpen={entryModalOpen}
        onClose={closeEntryModal}
        onSaved={handleEntrySaved}
        entry={editingEntry}
        projects={projects}
        workers={workers}
        defaultProjectId={filters.project_id}
        overtimeMultiplier={overtimeMultiplier}
        materialBillingMultiplier={materialBillingMultiplier}
        readOnly={Boolean(editingEntry && editingEntry.billing_status !== 'not_invoiced')}
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
      <WorkDiaryInvoiceModal
        isOpen={invoiceModalOpen}
        onClose={() => setInvoiceModalOpen(false)}
        onCreated={handleInvoiceCreated}
        entries={selectedEntries}
        project={invoiceProject}
      />
    </div>
  )
}
