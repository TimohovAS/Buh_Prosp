import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import EntityDetailModal from '../components/EntityDetailModal'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import StatusBadge from '../components/StatusBadge'
import useListPageState from '../hooks/useListPageState'
import { getProjectName as resolveProjectName } from '../utils/entityLabels'
import { UI_DASH, formatInteger, todayIso } from '../utils/formatters'
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
    Promise.all([api.clients.listBrief(), api.projects.list({ show_archived: true })]).then(
      ([clientList, projectList]) => {
        setClients(clientList)
        setProjects(projectList)
      }
    )
  }, [isActivePage])

  const openAdd = () => {
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
    if (!form.number?.trim()) {
      alert(tr('contractNumberRequired'))
      return
    }
    if (!form.client_id) {
      alert(tr('selectClient'))
      return
    }

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
    }
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
                      <td>{contract.date}</td>
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
          detailModal
            ? `${tr('contractForm')} ${UI_DASH} ${detailModal.number || `#${detailModal.id}`}`
            : tr('contractForm')
        }
        maxWidth="960px"
        details={
          detailModal ? (
            <div className="record-field-grid">
              <div className="record-field">
                <span className="record-field-label">{tr('contractNumber')}</span>
                <span className="record-field-value">{detailModal.number || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('date')}</span>
                <span className="record-field-value">{detailModal.date || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('client')}</span>
                <span className="record-field-value">{detailModal.client_name || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('project')}</span>
                <span className="record-field-value">
                  {getProjectName(detailModal.project_id) || UI_DASH}
                </span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('contractType')}</span>
                <span className="record-field-value">
                  {tr(CONTRACT_TYPE_KEYS[detailModal.contract_type] || 'service')}
                </span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('status')}</span>
                <span className="record-field-value">
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
              </div>
              <div className="record-field full">
                <span className="record-field-label">{tr('contractSubject')}</span>
                <div className="record-field-text">{detailModal.subject || UI_DASH}</div>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('amount')}</span>
                <span className="record-field-value">{formatInteger(detailModal.amount || 0)}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('contractReceived')}</span>
                <span className="record-field-value">{formatInteger(detailModal.total_received || 0)}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('contractExpenses')}</span>
                <span className="record-field-value">{formatInteger(detailModal.total_expenses || 0)}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('contractProfit')}</span>
                <span
                  className="record-field-value"
                  style={{
                    color: (detailModal.profit || 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)',
                    fontWeight: 700,
                  }}
                >
                  {formatInteger(detailModal.profit || 0)}
                </span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('validFrom')}</span>
                <span className="record-field-value">{detailModal.validity_start || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('validTo')}</span>
                <span className="record-field-value">{detailModal.validity_end || UI_DASH}</span>
              </div>
              <div className="record-field full">
                <span className="record-field-label">{tr('note')}</span>
                <div className="record-field-text">{detailModal.note || UI_DASH}</div>
              </div>
            </div>
          ) : null
        }
        actions={
          detailModal ? (
            <div className="record-actions-grid">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => openEditFromDetail(detailModal)}
              >
                {tr('edit')}
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={() => handleDeleteFromDetail(detailModal)}
              >
                {tr('delete')}
              </button>
            </div>
          ) : null
        }
      >
        {detailModal?.items?.length ? (
          <div className="record-detail-card">
            <div className="card-title">{tr('contractItems')}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.75rem' }}>
              {detailModal.items.map((item, index) => (
                <div key={`${detailModal.id}-${index}`} className="card" style={{ padding: '0.85rem' }}>
                  <div style={{ fontWeight: 700 }}>{item.description || UI_DASH}</div>
                  <div style={{ marginTop: '0.4rem', color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
                    {tr('quantity')}: {formatInteger(item.quantity || 0)} | {tr('unit')}:{' '}
                    {item.unit || UI_DASH} | {tr('price')}: {formatInteger(item.price || 0)}
                  </div>
                  <div style={{ marginTop: '0.35rem' }}>
                    {tr('amount')}: {formatInteger((item.quantity || 0) * (item.price || 0))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </EntityDetailModal>

      <Modal
        isOpen={!!modal}
        onClose={() => setModal(null)}
        title={`${modal === 'add' ? tr('add') : tr('edit')} ${tr('contractForm')}`}
        maxWidth="600px"
      >
        {modal ? (
          <form onSubmit={handleSubmit}>
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
              <select
                className="form-input"
                value={form.client_id}
                onChange={(event) => setForm({ ...form, client_id: event.target.value })}
                required
              >
                <option value="">
                  {UI_DASH} {tr('selectClient')} {UI_DASH}
                </option>
                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name}
                  </option>
                ))}
              </select>
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
                step="0.01"
                className="form-input"
                value={form.amount}
                onChange={(event) => setForm({ ...form, amount: event.target.value })}
              />
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
            <div className="card-title" style={{ marginTop: '1rem' }}>
              {tr('contractItems')}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.75rem' }}>
              {itemsForm.map((item, index) => (
                <div key={index} className="card" style={{ padding: '0.75rem' }}>
                  <div className="form-group">
                    <label className="form-label">{tr('description')}</label>
                    <input
                      type="text"
                      className="form-input"
                      value={item.description}
                      onChange={(event) => updateItem(index, 'description', event.target.value)}
                    />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
                    <div className="form-group">
                      <label className="form-label">{tr('quantity')}</label>
                      <input
                        type="number"
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
                        step="0.01"
                        className="form-input"
                        value={item.price}
                        onChange={(event) => updateItem(index, 'price', event.target.value)}
                      />
                    </div>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ color: 'var(--color-text-muted)' }}>
                      {tr('amount')}: {formatInteger((item.quantity || 0) * (item.price || 0))}
                    </div>
                    <button type="button" className="btn btn-sm btn-danger" onClick={() => removeItem(index)}>
                      {tr('delete')}
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: '0.75rem' }}>
              <button type="button" className="btn btn-secondary" onClick={addItem}>
                {tr('addItem')}
              </button>
            </div>
            <div className="form-group" style={{ marginTop: '1rem' }}>
              <label className="form-label">{tr('note')}</label>
              <textarea
                className="form-input"
                value={form.note}
                onChange={(event) => setForm({ ...form, note: event.target.value })}
                rows={3}
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
        ) : null}
      </Modal>
    </>
  )
}
