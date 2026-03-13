import { useState, useEffect, useMemo } from 'react'
import { api } from '../api'
import { tr } from '../i18n'
import SearchInput from '../components/SearchInput'

export default function Clients() {
  const [items, setItems] = useState([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [sortCol, setSortCol] = useState('name')
  const [sortAsc, setSortAsc] = useState(true)
  const [modal, setModal] = useState(null)
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
    api.clients.list({ search, archived: false }).then(setItems).finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [search])

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

  const handleDelete = async (id) => {
    if (!confirm(tr('archiveClient'))) return
    try {
      await api.clients.delete(id)
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

  const toggleSort = (col) => {
    if (sortCol === col) setSortAsc((value) => !value)
    else {
      setSortCol(col)
      setSortAsc(true)
    }
  }

  const SortIcon = ({ col }) => {
    if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 4 }}>{'\u2195'}</span>
    return <span style={{ marginLeft: 4 }}>{sortAsc ? '\u2191' : '\u2193'}</span>
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('clients')}</h1>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <SearchInput
            placeholder={tr('search')}
            value={search}
            onChange={setSearch}
            style={{ width: 200 }}
          />
          <button className="btn btn-primary" onClick={openAdd}>
            {tr('add')}
          </button>
        </div>
      </div>

      <div className="page-body">
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('name')}>{tr('name')} <SortIcon col="name" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('address')}>{tr('address')} <SortIcon col="address" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('pib')}>{tr('pib')} <SortIcon col="pib" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('maticni_broj')}>{tr('maticniBroj')} <SortIcon col="maticni_broj" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('client_type')}>{tr('type')} <SortIcon col="client_type" /></th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6}>{tr('loading')}</td></tr>
                ) : items.length === 0 ? (
                  <tr><td colSpan={6} style={{ color: 'var(--color-text-muted)' }}>{tr('noClients')}</td></tr>
                ) : (
                  sorted.map((client) => (
                    <tr key={client.id}>
                      <td>{client.name}</td>
                      <td>{(client.address || '').slice(0, 40)}</td>
                      <td>{client.pib || '-'}</td>
                      <td>{client.maticni_broj || '-'}</td>
                      <td>{client.client_type === 'legal' ? tr('legalEntity') : tr('individualEntity')}</td>
                      <td>
                        <button className="btn btn-sm btn-secondary" onClick={() => openEdit(client)}>{tr('edit')}</button>
                        <button className="btn btn-sm btn-danger" style={{ marginLeft: '0.5rem' }} onClick={() => handleDelete(client.id)}>
                          {tr('delete')}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {modal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">{modal === 'add' ? tr('add') : tr('edit')} {tr('clientForm')}</h2>
              <button className="modal-close" onClick={() => setModal(null)}>{'\u00D7'}</button>
            </div>
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
                <button type="submit" className="btn btn-primary">{tr('save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
