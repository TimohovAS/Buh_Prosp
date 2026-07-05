import { useState, useEffect, useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import EntityDetailModal from '../components/EntityDetailModal'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import useListPageState from '../hooks/useListPageState'
import { UI_DASH } from '../utils/formatters'

export default function Clients() {
  const location = useLocation()
  const isActivePage = location.pathname === '/clients'
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [detailModal, setDetailModal] = useState(null)
  const [modal, setModal] = useState(null)
  const { search, setSearch, sortCol, sortAsc, toggleSort } = useListPageState({
    initialSortCol: 'name',
    initialSortAsc: true,
  })
  const [form, setForm] = useState({
    name: '',
    address: '',
    pib: '',
    maticni_broj: '',
    contact: '',
    client_type: 'legal',
  })

  const load = () => {
    setLoading(true)
    api.clients
      .list({ search, archived: false })
      .then(setItems)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, isActivePage])

  const openAdd = () => {
    setForm({ name: '', address: '', pib: '', maticni_broj: '', contact: '', client_type: 'legal' })
    setModal('add')
  }

  const openEdit = (item) => {
    setForm({
      name: item.name,
      address: item.address || '',
      pib: item.pib || '',
      maticni_broj: item.maticni_broj || '',
      contact: item.contact || '',
      client_type: item.client_type || 'legal',
    })
    setModal({ type: 'edit', id: item.id })
  }

  const openDetail = (item) => {
    setDetailModal(item)
  }

  const openEditFromDetail = (item) => {
    setDetailModal(null)
    openEdit(item)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    try {
      if (modal === 'add') {
        await api.clients.create(form)
      } else {
        await api.clients.update(modal.id, form)
      }
      setModal(null)
      load()
    } catch (err) {
      console.error(err)
    }
  }

  const handleDeleteFromDetail = async (item) => {
    if (!confirm(tr('archiveClient'))) return
    try {
      await api.clients.delete(item.id)
      setDetailModal(null)
      load()
    } catch (err) {
      console.error(err)
    }
  }

  const sorted = useMemo(() => {
    return [...items].sort((left, right) => {
      const leftValue = left[sortCol] ?? ''
      const rightValue = right[sortCol] ?? ''
      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
  }, [items, sortCol, sortAsc])

  const getClientTypeLabel = (client) =>
    client.client_type === 'legal' ? tr('legalEntity') : tr('individualEntity')

  return (
    <>
      <PageHeader
        title={tr('clients')}
        actions={
          <>
            <SearchInput
              placeholder={tr('search')}
              value={search}
              onChange={setSearch}
              style={{ width: 200 }}
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
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('name')}>
                    {tr('name')} <SortIndicator active={sortCol === 'name'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('address')}>
                    {tr('address')} <SortIndicator active={sortCol === 'address'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('pib')}>
                    {tr('pib')} <SortIndicator active={sortCol === 'pib'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('maticni_broj')}>
                    {tr('maticniBroj')} <SortIndicator active={sortCol === 'maticni_broj'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('client_type')}>
                    {tr('type')} <SortIndicator active={sortCol === 'client_type'} asc={sortAsc} />
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={5}>{tr('loading')}</td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ color: 'var(--color-text-muted)' }}>
                      {tr('noClients')}
                    </td>
                  </tr>
                ) : (
                  sorted.map((client) => (
                    <tr
                      key={client.id}
                      className="record-row"
                      onClick={() => openDetail(client)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          openDetail(client)
                        }
                      }}
                      tabIndex={0}
                    >
                      <td>{client.name}</td>
                      <td>
                        <span className="record-cell-ellipsis">{client.address || UI_DASH}</span>
                      </td>
                      <td>{client.pib || UI_DASH}</td>
                      <td>{client.maticni_broj || UI_DASH}</td>
                      <td>{getClientTypeLabel(client)}</td>
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
            ? `${tr('client')} ${UI_DASH} ${detailModal.name || `#${detailModal.id}`}`
            : tr('client')
        }
        maxWidth="860px"
        details={
          detailModal ? (
            <div className="record-field-grid">
              <div className="record-field full">
                <span className="record-field-label">{tr('name')}</span>
                <span className="record-field-value">{detailModal.name || UI_DASH}</span>
              </div>
              <div className="record-field full">
                <span className="record-field-label">{tr('address')}</span>
                <div className="record-field-text">{detailModal.address || UI_DASH}</div>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('pib')}</span>
                <span className="record-field-value">{detailModal.pib || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('maticniBroj')}</span>
                <span className="record-field-value">{detailModal.maticni_broj || UI_DASH}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('type')}</span>
                <span className="record-field-value">{getClientTypeLabel(detailModal)}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('contact')}</span>
                <span className="record-field-value">{detailModal.contact || UI_DASH}</span>
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
      />

      <Modal
        isOpen={!!modal}
        onClose={() => setModal(null)}
        title={`${modal === 'add' ? tr('add') : tr('edit')} ${tr('clientForm')}`}
      >
        {modal ? (
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">{tr('name')}</label>
              <input
                type="text"
                className="form-input"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">{tr('address')}</label>
              <input
                type="text"
                className="form-input"
                value={form.address}
                onChange={(event) => setForm({ ...form, address: event.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">{tr('pib')}</label>
              <input
                type="text"
                className="form-input"
                value={form.pib}
                onChange={(event) => setForm({ ...form, pib: event.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">{tr('maticniBroj')}</label>
              <input
                type="text"
                className="form-input"
                value={form.maticni_broj}
                onChange={(event) => setForm({ ...form, maticni_broj: event.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">{tr('contact')}</label>
              <input
                type="text"
                className="form-input"
                value={form.contact}
                onChange={(event) => setForm({ ...form, contact: event.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">{tr('type')}</label>
              <select
                className="form-input"
                value={form.client_type}
                onChange={(event) => setForm({ ...form, client_type: event.target.value })}
              >
                <option value="legal">{tr('legalEntity')}</option>
                <option value="individual">{tr('individualEntity')}</option>
              </select>
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
