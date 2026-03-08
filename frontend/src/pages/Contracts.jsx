import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { tr } from '../i18n'

const CONTRACT_TYPE_KEYS = { service: 'service', supply: 'supply', rent: 'rent', commission: 'commission' }
const STATUS_KEYS = { active: 'active', completed: 'completed', cancelled: 'cancelled' }
const UI_DASH = '\u2014'
const UI_CLOSE = '\u00D7'
const UI_SORT_BOTH = '\u2195'
const UI_SORT_ASC = '\u2191'
const UI_SORT_DESC = '\u2193'

export default function Contracts() {
  const [items, setItems] = useState([])
  const [clients, setClients] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [clientFilter, setClientFilter] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [sortCol, setSortCol] = useState('date')
  const [sortAsc, setSortAsc] = useState(false)
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
    api.contracts.list({ ...params, limit: 500 }).then(setItems).finally(() => setLoading(false))
  }

  useEffect(load, [statusFilter, clientFilter])
  useEffect(() => { api.clients.listBrief().then(setClients) }, [])

  const openAdd = () => {
    const currentYear = new Date().getFullYear()
    const fallbackNumber = `${currentYear}-0001`
    api.contracts.nextNumber()
      .then((response) => {
        setForm({
          number: response.number || fallbackNumber,
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
        setItemsForm([{ description: '', quantity: 1, unit: '\u0448\u0442', price: 0 }])
        setModal('add')
      })
      .catch(() => {
        setForm({
          number: fallbackNumber,
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
        setItemsForm([{ description: '', quantity: 1, unit: '\u0448\u0442', price: 0 }])
        setModal('add')
      })
  }

  const openEdit = (contract) => {
    setForm({
      number: contract.number,
      date: contract.date,
      client_id: contract.client_id,
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
        ? contract.items.map((item) => ({ description: item.description, quantity: item.quantity, unit: item.unit, price: item.price }))
        : []
    )
    setModal({ type: 'edit', id: contract.id })
  }

  const addItem = () => {
    setItemsForm([...itemsForm, { description: '', quantity: 1, unit: '\u0448\u0442', price: 0 }])
  }

  const removeItem = (index) => {
    setItemsForm(itemsForm.filter((_, itemIndex) => itemIndex !== index))
  }

  const updateItem = (index, field, value) => {
    const next = [...itemsForm]
    next[index] = { ...next[index], [field]: value }
    if (field === 'quantity' || field === 'price') {
      next[index].amount = (field === 'quantity' ? parseFloat(value) || 0 : next[index].quantity) * (field === 'price' ? parseFloat(value) || 0 : next[index].price)
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
        amount: itemsForm.filter((item) => item.description?.trim()).length ? 0 : (parseFloat(form.amount) || 0),
        validity_start: form.validity_start || null,
        validity_end: form.validity_end || null,
        items: modal === 'add'
          ? (itemsForm.filter((item) => item.description.trim()).length
            ? itemsForm.filter((item) => item.description.trim()).map((item) => ({
              description: item.description,
              quantity: parseFloat(item.quantity) || 1,
              unit: item.unit || '\u0448\u0442',
              price: parseFloat(item.price) || 0,
            }))
            : null)
          : itemsForm.filter((item) => item.description.trim()).map((item) => ({
            description: item.description,
            quantity: parseFloat(item.quantity) || 1,
            unit: item.unit || '\u0448\u0442',
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
      rows = items.filter((contract) =>
        (contract.number || '').toLowerCase().includes(normalizedSearch) ||
        (contract.subject || '').toLowerCase().includes(normalizedSearch) ||
        (contract.client_name || '').toLowerCase().includes(normalizedSearch)
      )
    }
    return [...rows].sort((left, right) => {
      const leftValue = left[sortCol] ?? ''
      const rightValue = right[sortCol] ?? ''
      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
  }, [items, search, sortCol, sortAsc])

  const toggleSort = (column) => {
    if (sortCol === column) setSortAsc((value) => !value)
    else {
      setSortCol(column)
      setSortAsc(true)
    }
  }

  const SortIcon = ({ col }) => {
    if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 4 }}>{UI_SORT_BOTH}</span>
    return <span style={{ marginLeft: 4 }}>{sortAsc ? UI_SORT_ASC : UI_SORT_DESC}</span>
  }

  const handleDelete = async (id) => {
    if (!confirm(tr('deleteContract'))) return
    try {
      await api.contracts.delete(id)
      load()
    } catch (error) {
      console.error(error)
    }
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('contracts')}</h1>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <select className="form-input" style={{ width: 'auto' }} value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">{tr('statusFilterAll')}</option>
            <option value="active">{tr('active')}</option>
            <option value="completed">{tr('completed')}</option>
            <option value="cancelled">{tr('cancelled')}</option>
          </select>
          <select className="form-input" style={{ width: 180 }} value={clientFilter} onChange={(event) => setClientFilter(event.target.value)}>
            <option value="">{tr('filterAll')}</option>
            {clients.map((client) => (
              <option key={client.id} value={client.id}>{client.name}</option>
            ))}
          </select>
          <input
            type="text"
            className="form-input"
            placeholder={tr('search')}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            style={{ width: 180 }}
          />
          <button className="btn btn-primary" onClick={openAdd}>{tr('add')}</button>
        </div>
      </div>

      <div className="page-body">
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('number')}>{'\u2116'} <SortIcon col="number" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIcon col="date" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('client_name')}>{tr('client')} <SortIcon col="client_name" /></th>
                  <th>{tr('type')}</th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('subject')}>{tr('contractSubject')} <SortIcon col="subject" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')} <SortIcon col="amount" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('total_received')}>{tr('contractReceived')} <SortIcon col="total_received" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('total_expenses')}>{tr('contractExpenses')} <SortIcon col="total_expenses" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('profit')}>{tr('contractProfit')} <SortIcon col="profit" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('status')}>{tr('status')} <SortIcon col="status" /></th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={11}>{tr('loading')}</td></tr>
                ) : filteredItems.length === 0 ? (
                  <tr><td colSpan={11} style={{ color: 'var(--color-text-muted)' }}>{tr('noContracts')}</td></tr>
                ) : (
                  filteredItems.map((contract) => (
                    <tr key={contract.id}>
                      <td>{contract.number}</td>
                      <td>{contract.date}</td>
                      <td>{contract.client_name || UI_DASH}</td>
                      <td>{tr(CONTRACT_TYPE_KEYS[contract.contract_type] || 'service')}</td>
                      <td>{(contract.subject || '').slice(0, 36)}</td>
                      <td>{Number(contract.amount || 0).toLocaleString('sr-RS')}</td>
                      <td title={`${tr('contractPaymentAdvance')}: ${(contract.advance_sum || 0).toLocaleString('sr-RS')}, ${tr('contractPaymentIntermediate')}: ${(contract.intermediate_sum || 0).toLocaleString('sr-RS')}, ${tr('contractPaymentClosing')}: ${(contract.closing_sum || 0).toLocaleString('sr-RS')}`}>
                        {Number(contract.total_received || 0).toLocaleString('sr-RS')}
                        {(contract.total_received || 0) > 0 && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                            {'\u0410:'}{Number(contract.advance_sum || 0).toLocaleString('sr-RS')} {'\u041F:'}{Number(contract.intermediate_sum || 0).toLocaleString('sr-RS')} {'\u0417:'}{Number(contract.closing_sum || 0).toLocaleString('sr-RS')}
                          </div>
                        )}
                      </td>
                      <td>{Number(contract.total_expenses || 0).toLocaleString('sr-RS')}</td>
                      <td style={{ color: (contract.profit || 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)', fontWeight: 700 }}>
                        {Number(contract.profit || 0).toLocaleString('sr-RS')}
                      </td>
                      <td>
                        <span className={`badge ${contract.status === 'active' ? 'badge-success' : contract.status === 'cancelled' ? 'badge-danger' : 'badge-warning'}`}>
                          {tr(STATUS_KEYS[contract.status] || 'active')}
                        </span>
                      </td>
                      <td>
                        <button className="btn btn-sm btn-secondary" onClick={() => openEdit(contract)}>{tr('edit')}</button>
                        <button className="btn btn-sm btn-danger" style={{ marginLeft: '0.5rem' }} onClick={() => handleDelete(contract.id)}>{tr('delete')}</button>
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
          <div className="modal" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 600 }}>
            <div className="modal-header">
              <h2 className="modal-title">{modal === 'add' ? tr('add') : tr('edit')} {tr('contractForm')}</h2>
              <button className="modal-close" onClick={() => setModal(null)}>{UI_CLOSE}</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('contractNumber')}</label>
                <input type="text" className="form-input" value={form.number} onChange={(event) => setForm({ ...form, number: event.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('date')}</label>
                <input type="date" className="form-input" value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('client')}</label>
                <select className="form-input" value={form.client_id} onChange={(event) => setForm({ ...form, client_id: event.target.value })} required>
                  <option value="">{UI_DASH} {tr('selectClient')} {UI_DASH}</option>
                  {clients.map((client) => (
                    <option key={client.id} value={client.id}>{client.name}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('contractType')}</label>
                <select className="form-input" value={form.contract_type} onChange={(event) => setForm({ ...form, contract_type: event.target.value })}>
                  {Object.entries(CONTRACT_TYPE_KEYS).map(([value, key]) => (
                    <option key={value} value={value}>{tr(key)}</option>
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
                <label className="form-label">{tr('amount')} {tr('amountIfNoItems')}</label>
                <input type="number" step="0.01" className="form-input" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('validFrom')}</label>
                <input type="date" className="form-input" value={form.validity_start} onChange={(event) => setForm({ ...form, validity_start: event.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('validTo')}</label>
                <input type="date" className="form-input" value={form.validity_end} onChange={(event) => setForm({ ...form, validity_end: event.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('status')}</label>
                <select className="form-input" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
                  <option value="active">{tr('active')}</option>
                  <option value="completed">{tr('completed')}</option>
                  <option value="cancelled">{tr('cancelled')}</option>
                </select>
              </div>
              <div className="card-title" style={{ marginTop: '1rem' }}>{tr('contractItems')}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.75rem' }}>
                {itemsForm.map((item, index) => (
                  <div key={index} className="card" style={{ padding: '0.75rem' }}>
                    <div className="form-group">
                      <label className="form-label">{tr('description')}</label>
                      <input type="text" className="form-input" value={item.description} onChange={(event) => updateItem(index, 'description', event.target.value)} />
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
                      <div className="form-group">
                        <label className="form-label">{tr('quantity')}</label>
                        <input type="number" step="0.01" className="form-input" value={item.quantity} onChange={(event) => updateItem(index, 'quantity', event.target.value)} />
                      </div>
                      <div className="form-group">
                        <label className="form-label">{tr('unit')}</label>
                        <input type="text" className="form-input" value={item.unit} onChange={(event) => updateItem(index, 'unit', event.target.value)} />
                      </div>
                      <div className="form-group">
                        <label className="form-label">{tr('price')}</label>
                        <input type="number" step="0.01" className="form-input" value={item.price} onChange={(event) => updateItem(index, 'price', event.target.value)} />
                      </div>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ color: 'var(--color-text-muted)' }}>{tr('amount')}: {Number((item.quantity || 0) * (item.price || 0)).toLocaleString('sr-RS')}</div>
                      <button type="button" className="btn btn-sm btn-danger" onClick={() => removeItem(index)}>{tr('delete')}</button>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: '0.75rem' }}>
                <button type="button" className="btn btn-secondary" onClick={addItem}>{tr('addItem')}</button>
              </div>
              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label className="form-label">{tr('note')}</label>
                <textarea className="form-input" value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} rows={3} />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>{tr('cancel')}</button>
                <button type="submit" className="btn btn-primary">{tr('save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
