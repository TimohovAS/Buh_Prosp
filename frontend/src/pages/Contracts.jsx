import { useEffect, useMemo, useState } from 'react'
import { FileText, ListChecks, Pencil, Plus, Save, StickyNote, Trash2 } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import ClientSelect from '../components/ClientSelect'
import EntityDetailModal from '../components/EntityDetailModal'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import StatusBadge from '../components/StatusBadge'
import useListPageState from '../hooks/useListPageState'
import { getProjectName as resolveProjectName } from '../utils/entityLabels'
import { UI_DASH, formatDateSr, formatInteger, formatMoney2, todayIso } from '../utils/formatters'
import { amountSearchHay } from '../utils/searchUtils'

const CONTRACT_TYPE_KEYS = { service: 'service', supply: 'supply', rent: 'rent', commission: 'commission' }
const STATUS_KEYS = { active: 'active', completed: 'completed', cancelled: 'cancelled' }
const DEFAULT_UNIT = '\u0448\u0442'

export default function Contracts() {
  const location = useLocation()
  const isActivePage = location.pathname === '/contracts'
  const [items, setItems] = useState([])
  const [clients, setClients] = useState([])
  const [projects, setProjects] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [clientFilter, setClientFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [detailModal, setDetailModal] = useState(null)
  const [modal, setModal] = useState(null)
  const { search, setSearch, sortCol, sortAsc, toggleSort } = useListPageState({
    initialSortCol: 'date',
    initialSortAsc: false,
  })
  const [form, setForm] = useState({
    number: '',
    date: todayIso(),
    client_id: '',
    project_id: '',
    contract_type: 'service',
    subject: '',
    amount: 0,
    validity_start: '',
    validity_end: '',
    status: 'active',
    note: '',
  })
  const [itemsForm, setItemsForm] = useState([])
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  const hasContractItems = useMemo(() => itemsForm.some((item) => item.description?.trim()), [itemsForm])
  const contractItemsTotal = useMemo(
    () =>
      itemsForm
        .filter((item) => item.description?.trim())
        .reduce((sum, item) => sum + (parseFloat(item.quantity) || 0) * (parseFloat(item.price) || 0), 0),
    [itemsForm]
  )

  const detailItemsTotal = useMemo(
    () =>
      (detailModal?.items || []).reduce(
        (sum, item) => sum + (parseFloat(item.quantity) || 0) * (parseFloat(item.price) || 0),
        0
      ),
    [detailModal]
  )

  const detailSubject = useMemo(() => {
    const subject = (detailModal?.subject || '').trim()
    if (!subject) return ''
    // Предмет не повторяем, если он дословно совпал с описанием позиции
    const descriptions = (detailModal?.items || []).map((item) => (item.description || '').trim())
    return descriptions.includes(subject) ? '' : subject
  }, [detailModal])

  const detailValidity = useMemo(() => {
    const start = detailModal?.validity_start || ''
    const end = detailModal?.validity_end || ''
    if (start && end) {
      return {
        label: tr('contractValidity'),
        value: `${formatDateSr(start)} ${UI_DASH} ${formatDateSr(end)}`,
      }
    }
    if (start) return { label: tr('validFrom'), value: formatDateSr(start) }
    if (end) return { label: tr('validTo'), value: formatDateSr(end) }
    return { label: tr('contractValidity'), value: UI_DASH }
  }, [detailModal])

  const getProjectName = (projectId) => resolveProjectName(projects, projectId, '')

  const load = () => {
    setLoading(true)
    const params = {}
    if (statusFilter) params.status = statusFilter
    if (clientFilter) params.client_id = clientFilter
    api.contracts
      .list(params)
      .then(setItems)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, clientFilter, isActivePage])

  useEffect(() => {
    if (!isActivePage) return
    Promise.all([api.clients.listBrief(), api.projects.list({ show_inactive: true })]).then(
      ([clientList, projectList]) => {
        setClients(clientList)
        setProjects(projectList)
      }
    )
  }, [isActivePage])

  const openAdd = () => {
    setFormError('')
    const currentYear = new Date().getFullYear()
    const fallbackNumber = `${currentYear}-0001`
    api.contracts
      .nextNumber()
      .then((response) => {
        setForm({
          number: response.number || fallbackNumber,
          date: todayIso(),
          client_id: '',
          project_id: '',
          contract_type: 'service',
          subject: '',
          amount: 0,
          validity_start: '',
          validity_end: '',
          status: 'active',
          note: '',
        })
        setItemsForm([{ description: '', quantity: 1, unit: DEFAULT_UNIT, price: 0 }])
        setModal('add')
      })
      .catch(() => {
        setForm({
          number: fallbackNumber,
          date: todayIso(),
          client_id: '',
          project_id: '',
          contract_type: 'service',
          subject: '',
          amount: 0,
          validity_start: '',
          validity_end: '',
          status: 'active',
          note: '',
        })
        setItemsForm([{ description: '', quantity: 1, unit: DEFAULT_UNIT, price: 0 }])
        setModal('add')
      })
  }

  const openEdit = (contract) => {
    setFormError('')
    setForm({
      number: contract.number,
      date: contract.date,
      client_id: contract.client_id,
      project_id: contract.project_id ?? '',
      contract_type: contract.contract_type,
      subject: contract.subject,
      amount: contract.amount,
      validity_start: contract.validity_start || '',
      validity_end: contract.validity_end || '',
      status: contract.status,
      note: contract.note || '',
    })
    setItemsForm(
      contract.items?.length
        ? contract.items.map((item) => ({
            description: item.description,
            quantity: item.quantity,
            unit: item.unit,
            price: item.price,
          }))
        : []
    )
    setModal({ type: 'edit', id: contract.id })
  }

  const openDetail = (contract) => {
    setDetailModal(contract)
  }

  const openEditFromDetail = (contract) => {
    setDetailModal(null)
    openEdit(contract)
  }

  const addItem = () => {
    setItemsForm([...itemsForm, { description: '', quantity: 1, unit: DEFAULT_UNIT, price: 0 }])
  }

  const removeItem = (index) => {
    setItemsForm(itemsForm.filter((_, itemIndex) => itemIndex !== index))
  }

  const updateItem = (index, field, value) => {
    const next = [...itemsForm]
    next[index] = { ...next[index], [field]: value }
    if (field === 'quantity' || field === 'price') {
      next[index].amount =
        (field === 'quantity' ? parseFloat(value) || 0 : next[index].quantity) *
        (field === 'price' ? parseFloat(value) || 0 : next[index].price)
    }
    setItemsForm(next)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setFormError('')
    if (!form.number?.trim()) {
      setFormError(tr('contractNumberRequired'))
      return
    }
    if (!form.client_id) {
      setFormError(tr('selectClient'))
      return
    }

    setSaving(true)
    try {
      const payload = {
        ...form,
        client_id: parseInt(form.client_id, 10),
        project_id: form.project_id ? parseInt(form.project_id, 10) : null,
        amount: itemsForm.filter((item) => item.description?.trim()).length
          ? 0
          : parseFloat(form.amount) || 0,
        validity_start: form.validity_start || null,
        validity_end: form.validity_end || null,
        items:
          modal === 'add'
            ? itemsForm.filter((item) => item.description.trim()).length
              ? itemsForm
                  .filter((item) => item.description.trim())
                  .map((item) => ({
                    description: item.description,
                    quantity: parseFloat(item.quantity) || 1,
                    unit: item.unit || DEFAULT_UNIT,
                    price: parseFloat(item.price) || 0,
                  }))
              : null
            : itemsForm
                .filter((item) => item.description.trim())
                .map((item) => ({
                  description: item.description,
                  quantity: parseFloat(item.quantity) || 1,
                  unit: item.unit || DEFAULT_UNIT,
                  price: parseFloat(item.price) || 0,
                })),
      }
      if (modal === 'add') {
        await api.contracts.create(payload)
      } else {
        await api.contracts.update(modal.id, payload)
      }
      setModal(null)
      load()
    } catch (error) {
      console.error(error)
      setFormError(error?.message || tr('contractSaveError'))
    } finally {
      setSaving(false)
    }
  }

  const closeContractModal = () => {
    if (saving) return
    setModal(null)
    setFormError('')
  }

  const filteredItems = useMemo(() => {
    const normalizedSearch = (search || '').trim().toLowerCase()
    let rows = items
    if (normalizedSearch) {
      rows = items.filter(
        (contract) =>
          (contract.number || '').toLowerCase().includes(normalizedSearch) ||
          (contract.subject || '').toLowerCase().includes(normalizedSearch) ||
          (contract.client_name || '').toLowerCase().includes(normalizedSearch) ||
          getProjectName(contract.project_id).toLowerCase().includes(normalizedSearch) ||
          amountSearchHay(contract.amount).includes(normalizedSearch)
      )
    }
    return [...rows].sort((left, right) => {
      const leftValue = sortCol === 'project_name' ? getProjectName(left.project_id) : (left[sortCol] ?? '')
      const rightValue =
        sortCol === 'project_name' ? getProjectName(right.project_id) : (right[sortCol] ?? '')
      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, projects, search, sortCol, sortAsc])

  const handleDeleteFromDetail = async (contract) => {
    if (!confirm(tr('deleteContract'))) return
    try {
      await api.contracts.delete(contract.id)
      setDetailModal(null)
      load()
    } catch (error) {
      console.error(error)
    }
  }

  return (
    <>
      <PageHeader
        title={tr('contracts')}
        actions={
          <>
            <select
              className="form-input"
              style={{ width: 'auto' }}
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="">{tr('statusFilterAll')}</option>
              <option value="active">{tr('active')}</option>
              <option value="completed">{tr('completed')}</option>
              <option value="cancelled">{tr('cancelled')}</option>
            </select>
            <select
              className="form-input"
              style={{ width: 180 }}
              value={clientFilter}
              onChange={(event) => setClientFilter(event.target.value)}
            >
              <option value="">{tr('filterAll')}</option>
              {clients.map((client) => (
                <option key={client.id} value={client.id}>
                  {client.name}
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

      <div className="page-body">
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('number')}>
                    {'\u2116'} <SortIndicator active={sortCol === 'number'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>
                    {tr('date')} <SortIndicator active={sortCol === 'date'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('client_name')}>
                    {tr('client')} <SortIndicator active={sortCol === 'client_name'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('project_name')}>
                    {tr('project')} <SortIndicator active={sortCol === 'project_name'} asc={sortAsc} />
                  </th>
                  <th>{tr('type')}</th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('subject')}>
                    {tr('contractSubject')} <SortIndicator active={sortCol === 'subject'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('amount')}>
                    {tr('amount')} <SortIndicator active={sortCol === 'amount'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('total_received')}>
                    {tr('contractReceived')}{' '}
                    <SortIndicator active={sortCol === 'total_received'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('total_expenses')}>
                    {tr('contractExpenses')}{' '}
                    <SortIndicator active={sortCol === 'total_expenses'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('profit')}>
                    {tr('contractProfit')} <SortIndicator active={sortCol === 'profit'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('status')}>
                    {tr('status')} <SortIndicator active={sortCol === 'status'} asc={sortAsc} />
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={11}>{tr('loading')}</td>
                  </tr>
                ) : filteredItems.length === 0 ? (
                  <tr>
                    <td colSpan={11} style={{ color: 'var(--color-text-muted)' }}>
                      {tr('noContracts')}
                    </td>
                  </tr>
                ) : (
                  filteredItems.map((contract) => (
                    <tr
                      key={contract.id}
                      className="record-row"
                      onClick={() => openDetail(contract)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          openDetail(contract)
                        }
                      }}
                      tabIndex={0}
                    >
                      <td>{contract.number}</td>
                      <td>{formatDateSr(contract.date)}</td>
                      <td>{contract.client_name || UI_DASH}</td>
                      <td>{getProjectName(contract.project_id) || UI_DASH}</td>
                      <td>{tr(CONTRACT_TYPE_KEYS[contract.contract_type] || 'service')}</td>
                      <td>{(contract.subject || '').slice(0, 36)}</td>
                      <td>{formatInteger(contract.amount || 0)}</td>
                      <td
                        title={`${tr('contractPaymentAdvance')}: ${formatInteger(contract.advance_sum || 0)}, ${tr('contractPaymentIntermediate')}: ${formatInteger(contract.intermediate_sum || 0)}, ${tr('contractPaymentClosing')}: ${formatInteger(contract.closing_sum || 0)}`}
                      >
                        {formatInteger(contract.total_received || 0)}
                        {(contract.total_received || 0) > 0 ? (
                          <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                            {'A:'}
                            {formatInteger(contract.advance_sum || 0)} {'P:'}
                            {formatInteger(contract.intermediate_sum || 0)} {'Z:'}
                            {formatInteger(contract.closing_sum || 0)}
                          </div>
                        ) : null}
                      </td>
                      <td>{formatInteger(contract.total_expenses || 0)}</td>
                      <td
                        style={{
                          color: (contract.profit || 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)',
                          fontWeight: 700,
                        }}
                      >
                        {formatInteger(contract.profit || 0)}
                      </td>
                      <td>
                        <StatusBadge
                          tone={
                            contract.status === 'active'
                              ? 'success'
                              : contract.status === 'cancelled'
                                ? 'danger'
                                : 'warning'
                          }
                        >
                          {tr(STATUS_KEYS[contract.status] || 'active')}
                        </StatusBadge>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <EntityDetailModal
        isOpen={!!detailModal}
        onClose={() => setDetailModal(null)}
        title={
          detailModal ? (
            <span className="record-title">
              <span className="record-title-icon">
                <FileText aria-hidden="true" size={20} />
              </span>
              <span className="record-title-main">
                <span className="record-title-name">
                  {tr('contract')} {detailModal.number || `#${detailModal.id}`}
                  <StatusBadge
                    tone={
                      detailModal.status === 'active'
                        ? 'success'
                        : detailModal.status === 'cancelled'
                          ? 'danger'
                          : 'warning'
                    }
                  >
                    {tr(STATUS_KEYS[detailModal.status] || 'active')}
                  </StatusBadge>
                </span>
                <span className="record-title-meta">
                  <span>{tr(CONTRACT_TYPE_KEYS[detailModal.contract_type] || 'service')}</span>
                  <span>{detailModal.client_name || UI_DASH}</span>
                  <span>{formatDateSr(detailModal.date)}</span>
                </span>
              </span>
            </span>
          ) : (
            tr('contract')
          )
        }
        headerExtra={
          detailModal ? (
            <div className="record-title-actions">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => openEditFromDetail(detailModal)}
              >
                <Pencil aria-hidden="true" size={15} /> {tr('edit')}
              </button>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={() => handleDeleteFromDetail(detailModal)}
              >
                <Trash2 aria-hidden="true" size={15} /> {tr('delete')}
              </button>
            </div>
          ) : null
        }
        maxWidth="1100px"
        className="contract-detail-modal"
        details={
          detailModal ? (
            <div className="record-profile">
              <div className="record-profile-content record-profile-content--stack">
                {/* Плитки подписаны сами — отдельный заголовок блока не нужен */}
                <div className="record-profile-facts record-profile-facts--contract">
                  <div className="record-profile-fact record-profile-fact--money">
                    <span>{tr('amount')}</span>
                    <strong>{formatInteger(detailModal.amount || 0)}</strong>
                  </div>
                  <div className="record-profile-fact record-profile-fact--money">
                    <span>{tr('contractReceived')}</span>
                    <strong>{formatInteger(detailModal.total_received || 0)}</strong>
                  </div>
                  <div className="record-profile-fact record-profile-fact--money">
                    <span>{tr('contractExpenses')}</span>
                    <strong>{formatInteger(detailModal.total_expenses || 0)}</strong>
                  </div>
                  <div className="record-profile-fact record-profile-fact--money">
                    <span>{tr('contractProfit')}</span>
                    <strong className={(detailModal.profit || 0) >= 0 ? 'is-positive' : 'is-negative'}>
                      {formatInteger(detailModal.profit || 0)}
                    </strong>
                  </div>
                  <div className="record-profile-fact">
                    <span>{detailValidity.label}</span>
                    <strong>{detailValidity.value}</strong>
                  </div>
                  <div className="record-profile-fact record-profile-fact--wide">
                    <span>{tr('project')}</span>
                    <strong>{getProjectName(detailModal.project_id) || UI_DASH}</strong>
                  </div>
                </div>

                {detailSubject ? (
                  <section className="record-profile-panel">
                    <div className="record-profile-panel-title">
                      <FileText aria-hidden="true" size={17} />
                      <h4>{tr('contractSubject')}</h4>
                    </div>
                    <div className="record-profile-text">{detailSubject}</div>
                  </section>
                ) : null}

                {detailModal.items?.length ? (
                  <section className="record-profile-panel">
                    <div className="record-profile-panel-title">
                      <ListChecks aria-hidden="true" size={17} />
                      <h4>{tr('contractItems')}</h4>
                    </div>
                    <div className="record-profile-table-wrap">
                      <table className="record-profile-items">
                        <thead>
                          <tr>
                            <th>{tr('description')}</th>
                            <th className="num">{tr('quantity')}</th>
                            <th>{tr('unit')}</th>
                            <th className="num">{tr('price')}</th>
                            <th className="num">{tr('amount')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {detailModal.items.map((item, index) => (
                            <tr key={`${detailModal.id}-${index}`}>
                              <td>{item.description || UI_DASH}</td>
                              <td className="num">{formatInteger(item.quantity || 0)}</td>
                              <td>{item.unit || UI_DASH}</td>
                              <td className="num">{formatInteger(item.price || 0)}</td>
                              <td className="num">
                                {formatMoney2((item.quantity || 0) * (item.price || 0))}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                        {/* Итог дублирует единственную строку — показываем от двух позиций */}
                        {detailModal.items.length > 1 ? (
                          <tfoot>
                            <tr>
                              <td colSpan={4}>{tr('contractItemsTotal')}</td>
                              <td className="num">{formatMoney2(detailItemsTotal)}</td>
                            </tr>
                          </tfoot>
                        ) : null}
                      </table>
                    </div>
                  </section>
                ) : null}

                {detailModal.note ? (
                  <section className="record-profile-panel record-profile-note">
                    <div className="record-profile-panel-title">
                      <StickyNote aria-hidden="true" size={17} />
                      <h4>{tr('note')}</h4>
                    </div>
                    <div className="record-profile-text">{detailModal.note}</div>
                  </section>
                ) : null}
              </div>
            </div>
          ) : null
        }
      />

      <Modal
        isOpen={!!modal}
        onClose={closeContractModal}
        title={modal === 'add' ? tr('contractAddTitle') : tr('contractEditTitle')}
        maxWidth="1120px"
        className="contract-editor-modal"
        bodyClassName="contract-editor-modal-body"
      >
        {modal ? (
          <form onSubmit={handleSubmit} className="contract-editor-form">
            <section className="contract-editor-section">
              <div className="contract-editor-section-head">
                <span className="contract-editor-section-icon">
                  <FileText size={18} />
                </span>
                <div>
                  <h4>{tr('contractGeneralDetails')}</h4>
                  <p>{tr('contractGeneralHint')}</p>
                </div>
              </div>
              <div className="contract-editor-fields">
                <div className="form-group">
                  <label className="form-label">{tr('contractNumber')}</label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.number}
                    onChange={(event) => setForm({ ...form, number: event.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('date')}</label>
                  <DatePicker
                    value={form.date}
                    onChange={(value) => setForm({ ...form, date: value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('client')}</label>
                  <ClientSelect
                    clients={clients}
                    value={form.client_id}
                    onChange={(value) => setForm({ ...form, client_id: value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('project')}</label>
                  <ProjectSelect
                    projects={projects}
                    value={form.project_id}
                    onChange={(value) => setForm({ ...form, project_id: value })}
                    allowEmpty
                    emptyLabel={UI_DASH}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('contractType')}</label>
                  <select
                    className="form-input"
                    value={form.contract_type}
                    onChange={(event) => setForm({ ...form, contract_type: event.target.value })}
                  >
                    {Object.entries(CONTRACT_TYPE_KEYS).map(([value, key]) => (
                      <option key={value} value={value}>
                        {tr(key)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('contractSubject')}</label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.subject}
                    onChange={(event) => setForm({ ...form, subject: event.target.value })}
                    placeholder={tr('contractSubjectPlaceholder')}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">
                    {tr('amount')} {tr('amountIfNoItems')}
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    className="form-input"
                    value={form.amount}
                    onChange={(event) => setForm({ ...form, amount: event.target.value })}
                    disabled={hasContractItems}
                  />
                  {hasContractItems ? (
                    <span className="contract-editor-field-hint">{tr('contractAmountCalculated')}</span>
                  ) : null}
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('validFrom')}</label>
                  <DatePicker
                    value={form.validity_start}
                    onChange={(value) => setForm({ ...form, validity_start: value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('validTo')}</label>
                  <DatePicker
                    value={form.validity_end}
                    onChange={(value) => setForm({ ...form, validity_end: value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('status')}</label>
                  <select
                    className="form-input"
                    value={form.status}
                    onChange={(event) => setForm({ ...form, status: event.target.value })}
                  >
                    <option value="active">{tr('active')}</option>
                    <option value="completed">{tr('completed')}</option>
                    <option value="cancelled">{tr('cancelled')}</option>
                  </select>
                </div>
              </div>
            </section>

            <section className="contract-editor-section contract-editor-items-section">
              <div className="contract-editor-section-head">
                <span className="contract-editor-section-icon">
                  <FileText size={18} />
                </span>
                <div>
                  <h4>{tr('contractItems')}</h4>
                  <p>{tr('contractItemsHint')}</p>
                </div>
                <button type="button" className="btn btn-secondary btn-sm" onClick={addItem}>
                  <Plus size={16} /> {tr('addItem')}
                </button>
              </div>
              <div className="contract-editor-item-columns" aria-hidden="true">
                <span>{tr('description')}</span>
                <span>{tr('quantity')}</span>
                <span>{tr('unit')}</span>
                <span>{tr('price')}</span>
                <span>{tr('amount')}</span>
                <span></span>
              </div>
              <div className="contract-editor-items-list">
                {itemsForm.length === 0 ? (
                  <div className="contract-editor-items-empty">{tr('contractItemsEmpty')}</div>
                ) : null}
                {itemsForm.map((item, index) => (
                  <div key={index} className="contract-editor-item-row">
                    <span className="contract-editor-item-index">{index + 1}</span>
                    <div className="form-group contract-editor-item-description">
                      <label className="form-label">{tr('description')}</label>
                      <input
                        type="text"
                        className="form-input"
                        value={item.description}
                        onChange={(event) => updateItem(index, 'description', event.target.value)}
                        placeholder={tr('contractItemDescriptionPlaceholder')}
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{tr('quantity')}</label>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        className="form-input"
                        value={item.quantity}
                        onChange={(event) => updateItem(index, 'quantity', event.target.value)}
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{tr('unit')}</label>
                      <input
                        type="text"
                        className="form-input"
                        value={item.unit}
                        onChange={(event) => updateItem(index, 'unit', event.target.value)}
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{tr('price')}</label>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        className="form-input"
                        value={item.price}
                        onChange={(event) => updateItem(index, 'price', event.target.value)}
                      />
                    </div>
                    <div className="contract-editor-item-amount">
                      <span>{tr('amount')}</span>
                      <strong>{formatMoney2((item.quantity || 0) * (item.price || 0))} RSD</strong>
                    </div>
                    <button
                      type="button"
                      className="contract-editor-remove-item"
                      onClick={() => removeItem(index)}
                      aria-label={`${tr('delete')} ${index + 1}`}
                      title={tr('delete')}
                    >
                      <Trash2 size={17} />
                    </button>
                  </div>
                ))}
              </div>
            </section>

            <section className="contract-editor-section">
              <div className="contract-editor-section-head">
                <span className="contract-editor-section-icon">
                  <StickyNote size={18} />
                </span>
                <div>
                  <h4>{tr('note')}</h4>
                  <p>{tr('contractNoteHint')}</p>
                </div>
              </div>
              <div className="contract-editor-note">
                <textarea
                  className="form-input"
                  aria-label={tr('note')}
                  value={form.note}
                  onChange={(event) => setForm({ ...form, note: event.target.value })}
                  rows={6}
                />
              </div>
            </section>

            {formError ? <div className="alert alert-danger contract-editor-error">{formError}</div> : null}

            <div className="modal-actions contract-editor-actions">
              <div className="contract-editor-total">
                <span>{hasContractItems ? tr('contractItemsTotal') : tr('amount')}</span>
                <strong>{formatMoney2(hasContractItems ? contractItemsTotal : form.amount || 0)} RSD</strong>
              </div>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={closeContractModal}
                disabled={saving}
              >
                {tr('cancel')}
              </button>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                <Save size={17} /> {saving ? tr('saving') : tr('save')}
              </button>
            </div>
          </form>
        ) : null}
      </Modal>
    </>
  )
}
