import { useState, useEffect } from 'react'
import { api } from '../api'
import { tr } from '../i18n'

export default function Clients() {
  const [items, setItems] = useState([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({
    name: '',
    address: '',
    pib: '',
    contact: '',
    client_type: 'legal',
  })

  const load = () => {
    setLoading(true)
    api.clients.list({ search, archived: false }).then(setItems).finally(() => setLoading(false))
  }

  useEffect(load, [search])

  const openAdd = () => {
    setForm({ name: '', address: '', pib: '', contact: '', client_type: 'legal' })
    setModal('add')
  }

  const openEdit = (item) => {
    setForm({
      name: item.name,
      address: item.address || '',
      pib: item.pib || '',
      contact: item.contact || '',
      client_type: item.client_type || 'legal',
    })
    setModal({ type: 'edit', id: item.id })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      if (modal === 'add') {
        await api.clients.create(form)
      } else {
        await api.clients.update(modal.id, form)
      }
      setModal(null)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm(tr('archiveClient'))) return
    try {
      await api.clients.delete(id)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('clients')}</h1>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            type="text"
            className="form-input"
            placeholder={tr('search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
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
                <th>{tr('name')}</th>
                <th>{tr('address')}</th>
                <th>{tr('pib')}</th>
                <th>{tr('type')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5}>{tr('loading')}</td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan={5} style={{ color: 'var(--color-text-muted)' }}>{tr('noClients')}</td></tr>
              ) : (
                items.map((c) => (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td>{(c.address || '').slice(0, 40)}</td>
                    <td>{c.pib || '-'}</td>
                    <td>{c.client_type === 'legal' ? tr('legalEntity') : tr('individualEntity')}</td>
                    <td>
                      <button className="btn btn-sm btn-secondary" onClick={() => openEdit(c)}>{tr('edit')}</button>
                      <button className="btn btn-sm btn-danger" style={{ marginLeft: '0.5rem' }} onClick={() => handleDelete(c.id)}>
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
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">{modal === 'add' ? tr('add') : tr('edit')} {tr('clientForm')}</h2>
              <button className="modal-close" onClick={() => setModal(null)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('name')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('address')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.address}
                  onChange={(e) => setForm({ ...form, address: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('pib')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.pib}
                  onChange={(e) => setForm({ ...form, pib: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('contact')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.contact}
                  onChange={(e) => setForm({ ...form, contact: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('type')}</label>
                <select
                  className="form-input"
                  value={form.client_type}
                  onChange={(e) => setForm({ ...form, client_type: e.target.value })}
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
