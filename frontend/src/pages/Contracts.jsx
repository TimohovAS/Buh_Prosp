import { useState, useEffect } from 'react'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'

const CONTRACT_TYPE_KEYS = { service: 'service', supply: 'supply', rent: 'rent', commission: 'commission' }
const STATUS_KEYS = { active: 'active', completed: 'completed', cancelled: 'cancelled' }

export default function Contracts() {
  const [items, setItems] = useState([])
  const [clients, setClients] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [clientFilter, setClientFilter] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({
    number: '',
    date: new Date().toISOString().slice(0, 10),
    client_id: '',
    contract_type: 'service',
    subject: '',
    amount: 0,
    validity_start: '',
    validity_end: '',
    status: 'active',
    note: '',
  })
  const [itemsForm, setItemsForm] = useState([])

  const load = () => {
    setLoading(true)
    const params = {}
    if (statusFilter) params.status = statusFilter
    if (clientFilter) params.client_id = clientFilter
    api.contracts.list(params).then(setItems).finally(() => setLoading(false))
  }

  useEffect(load, [statusFilter, clientFilter])
  useEffect(() => { api.clients.listBrief().then(setClients) }, [])

  const openAdd = () => {
    const y = new Date().getFullYear()
    const defaultNumber = `${y}-0001`
    api.contracts.nextNumber()
      .then((r) => {
        setForm({
          number: r.number || defaultNumber,
          date: new Date().toISOString().slice(0, 10),
          client_id: '',
          contract_type: 'service',
          subject: '',
          amount: 0,
          validity_start: '',
          validity_end: '',
          status: 'active',
          note: '',
        })
        setItemsForm([{ description: '', quantity: 1, unit: 'шт', price: 0 }])
        setModal('add')
      })
      .catch(() => {
        setForm({
          number: defaultNumber,
          date: new Date().toISOString().slice(0, 10),
          client_id: '',
          contract_type: 'service',
          subject: '',
          amount: 0,
          validity_start: '',
          validity_end: '',
          status: 'active',
          note: '',
        })
        setItemsForm([{ description: '', quantity: 1, unit: 'шт', price: 0 }])
        setModal('add')
      })
  }

  const openEdit = (c) => {
    setForm({
      number: c.number,
      date: c.date,
      client_id: c.client_id,
      contract_type: c.contract_type,
      subject: c.subject,
      amount: c.amount,
      validity_start: c.validity_start || '',
      validity_end: c.validity_end || '',
      status: c.status,
      note: c.note || '',
    })
    setItemsForm(
      c.items?.length
        ? c.items.map((i) => ({ description: i.description, quantity: i.quantity, unit: i.unit, price: i.price }))
        : []
    )
    setModal({ type: 'edit', id: c.id })
  }

  const addItem = () => {
    setItemsForm([...itemsForm, { description: '', quantity: 1, unit: 'шт', price: 0 }])
  }

  const removeItem = (idx) => {
    setItemsForm(itemsForm.filter((_, i) => i !== idx))
  }

  const updateItem = (idx, field, value) => {
    const next = [...itemsForm]
    next[idx] = { ...next[idx], [field]: value }
    if (field === 'quantity' || field === 'price') {
      next[idx].amount = (field === 'quantity' ? parseFloat(value) || 0 : next[idx].quantity) * (field === 'price' ? parseFloat(value) || 0 : next[idx].price)
    }
    setItemsForm(next)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
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
        amount: itemsForm.filter((i) => i.description?.trim()).length ? 0 : (parseFloat(form.amount) || 0),
        validity_start: form.validity_start || null,
        validity_end: form.validity_end || null,
        items: modal === 'add'
          ? (itemsForm.filter((i) => i.description.trim()).length
              ? itemsForm.filter((i) => i.description.trim()).map((i) => ({
                  description: i.description,
                  quantity: parseFloat(i.quantity) || 1,
                  unit: i.unit || 'шт',
                  price: parseFloat(i.price) || 0,
                }))
              : null)
          : itemsForm.filter((i) => i.description.trim()).map((i) => ({
              description: i.description,
              quantity: parseFloat(i.quantity) || 1,
              unit: i.unit || 'шт',
              price: parseFloat(i.price) || 0,
            })),
      }
      if (modal === 'add') {
        await api.contracts.create(payload)
      } else {
        await api.contracts.update(modal.id, payload)
      }
      setModal(null)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const filteredItems = items.filter((c) => {
    if (!search) return true
    const s = search.toLowerCase()
    return (c.number || '').toLowerCase().includes(s) ||
           (c.subject || '').toLowerCase().includes(s) ||
           (c.client_name || '').toLowerCase().includes(s)
  })

  const handleDelete = async (id) => {
    if (!confirm(tr('deleteContract'))) return
    try {
      await api.contracts.delete(id)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('contracts')}</h1>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
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
            onChange={(e) => setClientFilter(e.target.value)}
          >
            <option value="">{tr('noClients')}</option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <input
            type="text"
            className="form-input"
            placeholder={tr('search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 180 }}
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
                <th>№</th>
                <th>{tr('date')}</th>
                <th>{tr('client')}</th>
                <th>{tr('type')}</th>
                <th>{tr('contractSubject')}</th>
                <th>{tr('amount')}</th>
                <th>{tr('contractReceived')}</th>
                <th>{tr('status')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={9}>{tr('loading')}</td></tr>
              ) : filteredItems.length === 0 ? (
                <tr><td colSpan={9} style={{ color: 'var(--color-text-muted)' }}>{tr('noContracts')}</td></tr>
              ) : (
                filteredItems.map((c) => (
                  <tr key={c.id}>
                    <td>{c.number}</td>
                    <td>{c.date}</td>
                    <td>{c.client_name || '-'}</td>
                    <td>{tr(CONTRACT_TYPE_KEYS[c.contract_type] || 'service')}</td>
                    <td>{(c.subject || '').slice(0, 30)}</td>
                    <td>{c.amount.toLocaleString('sr-RS')}</td>
                    <td title={`${tr('contractPaymentAdvance')}: ${(c.advance_sum || 0).toLocaleString('sr-RS')}, ${tr('contractPaymentIntermediate')}: ${(c.intermediate_sum || 0).toLocaleString('sr-RS')}, ${tr('contractPaymentClosing')}: ${(c.closing_sum || 0).toLocaleString('sr-RS')}`}>
                      {(c.total_received || 0).toLocaleString('sr-RS')}
                      {(c.total_received || 0) > 0 && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                          А:{((c.advance_sum || 0)).toLocaleString('sr-RS')} П:{((c.intermediate_sum || 0)).toLocaleString('sr-RS')} З:{((c.closing_sum || 0)).toLocaleString('sr-RS')}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className={`badge ${c.status === 'active' ? 'badge-success' : c.status === 'cancelled' ? 'badge-danger' : 'badge-warning'}`}>
                        {tr(STATUS_KEYS[c.status] || 'active')}
                      </span>
                    </td>
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
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 600 }}>
            <div className="modal-header">
              <h2 className="modal-title">{modal === 'add' ? tr('add') : tr('edit')} {tr('contractForm')}</h2>
              <button className="modal-close" onClick={() => setModal(null)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('contractNumber')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.number}
                  onChange={(e) => setForm({ ...form, number: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('date')}</label>
                <input
                  type="date"
                  className="form-input"
                  value={form.date}
                  onChange={(e) => setForm({ ...form, date: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('client')}</label>
                <select
                  className="form-input"
                  value={form.client_id}
                  onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                  required
                >
                  <option value="">— {tr('selectClient')} —</option>
                  {clients.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('contractType')}</label>
                <select
                  className="form-input"
                  value={form.contract_type}
                  onChange={(e) => setForm({ ...form, contract_type: e.target.value })}
                >
                {Object.entries(CONTRACT_TYPE_KEYS).map(([k, key]) => (
                  <option key={k} value={k}>{tr(key)}</option>
                ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('contractSubject')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.subject}
                  onChange={(e) => setForm({ ...form, subject: e.target.value })}
                  placeholder={tr('contractSubjectPlaceholder')}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('amount')} {tr('amountIfNoItems')}</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                />
              </div>

              <div className="card-title" style={{ marginTop: '1rem' }}>{tr('contractItems')}</div>
              {itemsForm.map((item, idx) => (
                <div key={idx} style={{ display: 'grid', gridTemplateColumns: '1fr 80px 60px 100px auto', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'end' }}>
                  <input
                    type="text"
                    className="form-input"
                    placeholder={tr('description')}
                    value={item.description}
                    onChange={(e) => updateItem(idx, 'description', e.target.value)}
                  />
                  <input
                    type="number"
                    step="0.01"
                    className="form-input"
                    placeholder={tr('quantity')}
                    value={item.quantity}
                    onChange={(e) => updateItem(idx, 'quantity', e.target.value)}
                  />
                  <input
                    type="text"
                    className="form-input"
                    placeholder={tr('unit')}
                    value={item.unit}
                    onChange={(e) => updateItem(idx, 'unit', e.target.value)}
                  />
                  <input
                    type="number"
                    step="0.01"
                    className="form-input"
                    placeholder={tr('price')}
                    value={item.price}
                    onChange={(e) => updateItem(idx, 'price', e.target.value)}
                  />
                  <button type="button" className="btn btn-sm btn-secondary" onClick={() => removeItem(idx)}>×</button>
                </div>
              ))}
              <button type="button" className="btn btn-sm btn-secondary" onClick={addItem} style={{ marginBottom: '1rem' }}>
                + {tr('addItem')}
              </button>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('validFrom')}</label>
                  <DatePicker
                    value={form.validity_start}
                    onChange={(v) => setForm({ ...form, validity_start: v })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('validTo')}</label>
                  <DatePicker
                    value={form.validity_end}
                    onChange={(v) => setForm({ ...form, validity_end: v })}
                  />
                </div>
              </div>
              {modal !== 'add' && (
                <div className="form-group">
                  <label className="form-label">{tr('status')}</label>
                  <select
                    className="form-input"
                    value={form.status}
                    onChange={(e) => setForm({ ...form, status: e.target.value })}
                  >
                {Object.entries(STATUS_KEYS).map(([k, key]) => (
                  <option key={k} value={k}>{tr(key)}</option>
                ))}
                  </select>
                </div>
              )}
              <div className="form-group">
                <label className="form-label">{tr('note')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.note}
                  onChange={(e) => setForm({ ...form, note: e.target.value })}
                />
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
