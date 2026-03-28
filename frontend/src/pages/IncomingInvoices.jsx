import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'

const UI_CLOSE = '\u2715'
const currentYear = new Date().getFullYear()
const STATUSES = ['unpaid', 'partial', 'paid', 'cancelled']
const STATUS_LABELS = { unpaid: 'statusUnpaid', partial: 'statusPartial', paid: 'statusPaid', cancelled: 'statusCancelled' }

function fmt(n) { return n != null ? Number(n).toLocaleString('sr-RS', { minimumFractionDigits: 2 }) : '-' }
function fmtDate(d) { return d ? new Date(d).toLocaleDateString('sr-RS') : '-' }

function compactText(value, max = 80) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 3)}...` : text
}

function StatusBadge({ status }) {
  const cls = { unpaid: 'badge badge-warning', partial: 'badge badge-info', paid: 'badge badge-success', cancelled: 'badge badge-danger' }
  return <span className={cls[status] || 'badge'}>{tr(STATUS_LABELS[status] || status)}</span>
}

export default function IncomingInvoices() {
  const location = useLocation()
  const isActivePage = location.pathname === '/incoming-invoices'
  const [items, setItems] = useState([])
  const [clients, setClients] = useState([])
  const [projects, setProjects] = useState([])
  const [year, setYear] = useState(currentYear)
  const [month, setMonth] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [sortCol, setSortCol] = useState('date')
  const [sortAsc, setSortAsc] = useState(false)
  const [modal, setModal] = useState(null)
  const [settleModal, setSettleModal] = useState(null)
  const [detailModal, setDetailModal] = useState(null)
  const [form, setForm] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [pageError, setPageError] = useState('')

  const defaultForm = { invoice_number: '', date: new Date().toISOString().slice(0, 10), client_id: '', counterparty_name: '', project_id: '', amount: '', currency: 'RSD', description: '', note: '' }

  const load = () => {
    setLoading(true)
    setPageError('')
    const params = {}
    if (year) params.year = year
    if (month && year) params.month = month
    if (filterStatus) params.status = filterStatus
    api.incomingInvoices.list(params).then(setItems).catch(() => setItems([])).finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return
    load()
  }, [year, month, filterStatus, isActivePage])
  useEffect(() => {
    if (!isActivePage) return
    api.clients.list().then(all => setClients(all.filter(c => !c.is_archived))).catch(() => {})
    api.projects.list().then(setProjects).catch(() => {})
  }, [isActivePage])

  const refreshProjects = async () => {
    try {
      const projectList = await api.projects.list()
      setProjects(projectList)
      return projectList
    } catch {
      return projects
    }
  }

  const filtered = useMemo(() => {
    const q = (search || '').trim().toLowerCase()
    let rows = items
    if (q) {
      rows = items.filter(i =>
        (i.invoice_number || '').toLowerCase().includes(q) ||
        (i.counterparty_name || '').toLowerCase().includes(q) ||
        (i.client_name || '').toLowerCase().includes(q) ||
        (i.description || '').toLowerCase().includes(q)
      )
    }
    return [...rows].sort((a, b) => {
      const av = a[sortCol] ?? ''
      const bv = b[sortCol] ?? ''
      if (av < bv) return sortAsc ? -1 : 1
      if (av > bv) return sortAsc ? 1 : -1
      return 0
    })
  }, [items, search, sortCol, sortAsc])

  const toggleSort = col => {
    if (sortCol === col) setSortAsc(v => !v)
    else {
      setSortCol(col)
      setSortAsc(true)
    }
  }
  const SortIcon = ({ col }) => sortCol === col ? (sortAsc ? ' \u25B2' : ' \u25BC') : ''

  const openAdd = async () => {
    await refreshProjects()
    setForm({ ...defaultForm })
    setModal('add')
  }

  const openEdit = async item => {
    await refreshProjects()
    setForm({
      invoice_number: item.invoice_number,
      date: item.date,
      client_id: item.client_id || '',
      counterparty_name: item.counterparty_name,
      project_id: item.project_id || '',
      amount: item.amount,
      currency: item.currency || 'RSD',
      description: item.description || '',
      note: item.note || '',
    })
    setModal({ type: 'edit', id: item.id })
  }

  const handleSubmit = async e => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const payload = { ...form, amount: Number(form.amount), client_id: form.client_id || null, project_id: form.project_id || null }
      if (modal === 'add') await api.incomingInvoices.create(payload)
      else await api.incomingInvoices.update(modal.id, payload)
      setModal(null)
      load()
    } catch { }
    setSubmitting(false)
  }

  const handleCancel = async id => {
    if (!confirm(`${tr('delete')}?`)) return
    await api.incomingInvoices.cancel(id).catch(() => {})
    load()
  }

  const openDetail = async id => {
    try {
      const detail = await api.incomingInvoices.get(id)
      setDetailModal(detail)
    } catch { }
  }

  const handleReverseSettlement = async settlementId => {
    if (!confirm(tr('reverseSettlementConfirm'))) return
    await api.incomingInvoices.reverseSettlement(settlementId).catch(() => {})
    if (detailModal) openDetail(detailModal.id)
    load()
  }

  const totalAmount = useMemo(() => filtered.reduce((sum, item) => sum + Number(item.amount || 0), 0), [filtered])
  const totalRemaining = useMemo(() => filtered.reduce((sum, item) => sum + Number(item.remaining_amount || 0), 0), [filtered])

  return (
    <div className="page">
      <div className="page-header">
        <h1>{tr('incomingInvoices')}</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <select className="form-input" value={year} onChange={e => setYear(Number(e.target.value))} style={{ width: 100 }}>
            {Array.from({ length: 5 }, (_, i) => currentYear - i).map(y => <option key={y} value={y}>{y}</option>)}
          </select>
          <select className="form-input" value={month} onChange={e => setMonth(e.target.value)} style={{ width: 80 }}>
            <option value="">-</option>
            {Array.from({ length: 12 }, (_, i) => i + 1).map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <select className="form-input" value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={{ width: 130 }}>
            <option value="">{tr('all') || 'All'}</option>
            {STATUSES.map(status => <option key={status} value={status}>{tr(STATUS_LABELS[status])}</option>)}
          </select>
          <input className="form-input" placeholder={tr('search')} value={search} onChange={e => setSearch(e.target.value)} style={{ width: 180 }} />
          <button className="btn btn-primary" onClick={openAdd}>{tr('createIncomingInvoice')}</button>
        </div>
      </div>

      {pageError && <div className="alert alert-danger">{pageError}</div>}

      <div className="page-body">
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')}<SortIcon col="date" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('invoice_number')}>{tr('invoiceNumber')}<SortIcon col="invoice_number" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('counterparty_name')}>{tr('counterpartyName')}<SortIcon col="counterparty_name" /></th>
                  <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')}<SortIcon col="amount" /></th>
                  <th style={{ textAlign: 'right' }}>{tr('settledAmount')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('remainingAmount')}</th>
                  <th>{tr('status')}</th>
                  <th>{tr('actions') || ''}</th>
                </tr>
              </thead>
              <tbody>
                {loading ? <tr><td colSpan={8}>{tr('loading')}</td></tr>
                  : filtered.length === 0 ? <tr><td colSpan={8}>{tr('noRecords')}</td></tr>
                    : filtered.map(inv => (
                      <tr key={inv.id}>
                        <td>{fmtDate(inv.date)}</td>
                        <td><a href="#" onClick={e => { e.preventDefault(); openDetail(inv.id) }}>{inv.invoice_number}</a></td>
                        <td>{inv.client_name || inv.counterparty_name}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(inv.amount)}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(inv.settled_amount)}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(inv.remaining_amount)}</td>
                        <td><StatusBadge status={inv.status} /></td>
                        <td>
                          <div style={{ display: 'flex', gap: 4 }}>
                            {inv.status !== 'paid' && inv.status !== 'cancelled' && (
                              <>
                                <button className="btn btn-sm" onClick={() => openEdit(inv)}>{tr('edit')}</button>
                                <button className="btn btn-sm" onClick={() => setSettleModal({ invoice: inv, type: 'expense' })}>{tr('attachExpense')}</button>
                                <button className="btn btn-sm btn-primary" onClick={() => setSettleModal({ invoice: inv, type: 'bank' })}>{tr('settleViaBank')}</button>
                                <button className="btn btn-sm" onClick={() => setSettleModal({ invoice: inv, type: 'cash' })}>{tr('settleViaCash')}</button>
                                <button className="btn btn-sm" onClick={() => setSettleModal({ invoice: inv, type: 'offset' })}>{tr('settleViaOffset')}</button>
                                <button className="btn btn-sm btn-danger" onClick={() => handleCancel(inv.id)}>{tr('cancel')}</button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
              </tbody>
              {filtered.length > 0 && (
                <tfoot>
                  <tr style={{ fontWeight: 'bold' }}>
                    <td colSpan={3}>{tr('total') || 'Total'}: {filtered.length}</td>
                    <td style={{ textAlign: 'right' }}>{fmt(totalAmount)}</td>
                    <td></td>
                    <td style={{ textAlign: 'right' }}>{fmt(totalRemaining)}</td>
                    <td colSpan={2}></td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </div>
      </div>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">{modal === 'add' ? tr('createIncomingInvoice') : tr('edit')}</h2>
              <button className="modal-close" onClick={() => setModal(null)}>{UI_CLOSE}</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('invoiceNumber')}</label>
                <input className="form-input" required value={form.invoice_number} onChange={e => setForm({ ...form, invoice_number: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('date')}</label>
                <DatePicker value={form.date} onChange={value => setForm({ ...form, date: value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('counterpartyName')}</label>
                <input className="form-input" required value={form.counterparty_name} onChange={e => setForm({ ...form, counterparty_name: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('client')}</label>
                <select className="form-input" value={form.client_id} onChange={e => setForm({ ...form, client_id: e.target.value })}>
                  <option value="">-</option>
                  {clients.map(client => <option key={client.id} value={client.id}>{client.name}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('project')}</label>
                <select className="form-input" value={form.project_id} onChange={e => setForm({ ...form, project_id: e.target.value })}>
                  <option value="">-</option>
                  {projects.map(project => <option key={project.id} value={project.id}>{project.code} - {project.name}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('amount')}</label>
                <input className="form-input" type="number" step="0.01" required value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('description')}</label>
                <input className="form-input" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('note')}</label>
                <textarea className="form-input" value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn" onClick={() => setModal(null)}>{tr('cancel')}</button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>{tr('save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {settleModal && <SettleModal data={settleModal} clients={clients} onClose={() => setSettleModal(null)} onDone={() => { setSettleModal(null); load() }} />}

      {detailModal && (
        <div className="modal-overlay" onClick={() => setDetailModal(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 700 }}>
            <div className="modal-header">
              <h2 className="modal-title">{tr('incomingInvoice')} {detailModal.invoice_number}</h2>
              <button className="modal-close" onClick={() => setDetailModal(null)}>{UI_CLOSE}</button>
            </div>
            <div style={{ padding: '1rem' }}>
              <p><strong>{tr('counterpartyName')}:</strong> {detailModal.client_name || detailModal.counterparty_name}</p>
              <p><strong>{tr('date')}:</strong> {fmtDate(detailModal.date)}</p>
              <p><strong>{tr('amount')}:</strong> {fmt(detailModal.amount)} {detailModal.currency}</p>
              <p><strong>{tr('settledAmount')}:</strong> {fmt(detailModal.settled_amount)}</p>
              <p><strong>{tr('remainingAmount')}:</strong> {fmt(detailModal.remaining_amount)}</p>
              <p><strong>{tr('status')}:</strong> <StatusBadge status={detailModal.status} /></p>
              {detailModal.status === 'paid' && detailModal.expense_id && (!detailModal.settlements || detailModal.settlements.length === 0) && (
                <p><strong>{tr('linkedExpense')}:</strong> #{detailModal.expense_id}</p>
              )}
              {detailModal.description && <p><strong>{tr('description')}:</strong> {detailModal.description}</p>}
              <h3 style={{ marginTop: '1rem' }}>{tr('settlementHistory')}</h3>
              {(!detailModal.settlements || detailModal.settlements.length === 0) ? <p>{tr('noSettlements')}</p> : (
                <table>
                  <thead>
                    <tr>
                      <th>{tr('date')}</th>
                      <th>{tr('type')}</th>
                      <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
                      <th>{tr('note')}</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailModal.settlements.map(settlement => (
                      <tr key={settlement.id}>
                        <td>{fmtDate(settlement.date)}</td>
                        <td>{tr(settlement.settlement_type) || settlement.settlement_type}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(settlement.amount)}</td>
                        <td>{settlement.note || ''}</td>
                        <td><button className="btn btn-sm btn-danger" onClick={() => handleReverseSettlement(settlement.id)}>{tr('reverseSettlement')}</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function SettleModal({ data, clients, onClose, onDone }) {
  const { invoice, type } = data
  const [form, setForm] = useState({ amount: Number(invoice.remaining_amount || 0), date: invoice.date || new Date().toISOString().slice(0, 10), note: '', bank_transaction_id: '', income_id: '', expense_id: '' })
  const [bankTxs, setBankTxs] = useState([])
  const [openIncomes, setOpenIncomes] = useState([])
  const [expenseCandidates, setExpenseCandidates] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const selectedIncome = openIncomes.find(i => i.id === Number(form.income_id)) || null
  const selectedExpense = expenseCandidates.find(i => i.id === Number(form.expense_id)) || null

  useEffect(() => {
    if (type === 'bank') {
      api.bankTransactions.list({ status: 'unmatched', direction: 'out' }).then(setBankTxs).catch(() => {})
    }
    if (type === 'offset' && invoice.client_id) {
      api.incomingInvoices.openIncomes(invoice.client_id).then(setOpenIncomes).catch(() => {})
    }
    if (type === 'expense') {
      api.incomingInvoices.expenseCandidates(invoice.id).then(setExpenseCandidates).catch(() => setExpenseCandidates([]))
    }
  }, [type, invoice.client_id, invoice.id])

  const handleSubmit = async e => {
    e.preventDefault()
    setSubmitting(true)
    try {
      if (type === 'expense') {
        await api.incomingInvoices.attachExpense(invoice.id, { expense_id: Number(form.expense_id) })
      } else {
        const payload = { amount: Number(form.amount), date: form.date, note: form.note || null }
        if (type === 'bank') {
          payload.bank_transaction_id = Number(form.bank_transaction_id)
          await api.incomingInvoices.settleBank(invoice.id, payload)
        } else if (type === 'cash') {
          await api.incomingInvoices.settleCash(invoice.id, payload)
        } else if (type === 'offset') {
          payload.income_id = Number(form.income_id)
          await api.incomingInvoices.settleOffset(invoice.id, payload)
        }
      }
      onDone()
    } catch { }
    setSubmitting(false)
  }

  const titles = { bank: tr('settleViaBank'), cash: tr('settleViaCash'), offset: tr('settleViaOffset'), expense: tr('attachExpense') }
  const invoiceProjectLabel = [invoice.project_code, invoice.project_name].filter(Boolean).join(' / ')
  const showInvoiceSummary = type === 'offset' || type === 'expense'
  const formatOffsetIncomeLabel = income => {
    const parts = [income.invoice_number || '']
    if (income.date) parts.push(fmtDate(income.date))
    if (income.client_name) parts.push(income.client_name)
    if (income.project_code || income.project_name) parts.push([income.project_code, income.project_name].filter(Boolean).join(' / '))
    if (income.description) parts.push(compactText(income.description, 60))
    parts.push(`${tr('remainingAmount')}: ${fmt(income.remaining)}`)
    return parts.filter(Boolean).join(' | ')
  }
  const formatExpenseLabel = expense => {
    const parts = [fmtDate(expense.date)]
    if (expense.description) parts.push(compactText(expense.description, 72))
    if (expense.project_code || expense.project_name) parts.push([expense.project_code, expense.project_name].filter(Boolean).join(' / '))
    if (expense.contract_number) parts.push(`${tr('contractNumber')}: ${expense.contract_number}`)
    if (expense.category) parts.push(expense.category)
    if (expense.bank_reference) parts.push(`${tr('paymentReference')}: ${expense.bank_reference}`)
    parts.push(fmt(expense.amount))
    return parts.filter(Boolean).join(' | ')
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{titles[type]}: {invoice.invoice_number}</h2>
          <button className="modal-close" onClick={onClose}>{UI_CLOSE}</button>
        </div>
        <form onSubmit={handleSubmit}>
          {showInvoiceSummary && (
            <div className="form-group">
              <div style={{ marginBottom: 10, padding: '0.75rem', border: '1px solid var(--border-color, rgba(255,255,255,0.12))', borderRadius: 8, display: 'grid', gap: 4 }}>
                <div><strong>{tr('invoiceNumber')}:</strong> {invoice.invoice_number}</div>
                <div><strong>{tr('counterpartyName')}:</strong> {invoice.client_name || invoice.counterparty_name || '-'}</div>
                <div><strong>{tr('date')}:</strong> {fmtDate(invoice.date)}</div>
                {invoiceProjectLabel && <div><strong>{tr('project')}:</strong> {invoiceProjectLabel}</div>}
                {invoice.description && <div><strong>{tr('description')}:</strong> {invoice.description}</div>}
                {invoice.note && <div><strong>{tr('note')}:</strong> {invoice.note}</div>}
                <div><strong>{tr('remainingAmount')}:</strong> {fmt(invoice.remaining_amount)}</div>
              </div>
            </div>
          )}
          {type === 'bank' && (
            <div className="form-group">
              <label className="form-label">{tr('selectBankTx')}</label>
              <select className="form-input" required value={form.bank_transaction_id} onChange={e => {
                const tx = bankTxs.find(item => item.id === Number(e.target.value))
                setForm({ ...form, bank_transaction_id: e.target.value, amount: tx ? Number(tx.amount) : form.amount })
              }}>
                <option value="">-</option>
                {bankTxs.map(tx => <option key={tx.id} value={tx.id}>{fmtDate(tx.date)} | {fmt(tx.amount)} | {tx.counterparty_name || tx.purpose || tx.bank_reference}</option>)}
              </select>
            </div>
          )}
          {type === 'offset' && (
            <div className="form-group">
              <label className="form-label">{tr('selectIncome')}</label>
              {!invoice.client_id ? <p style={{ color: 'var(--color-danger)' }}>Для взаимозачета нужно указать клиента у входящей фактуры.</p> : (
                <div>
                  <select className="form-input" required value={form.income_id} onChange={e => {
                    const income = openIncomes.find(item => item.id === Number(e.target.value))
                    const maxAmount = income ? Math.min(Number(income.remaining), Number(invoice.remaining_amount)) : form.amount
                    setForm({ ...form, income_id: e.target.value, amount: maxAmount })
                  }}>
                    <option value="">-</option>
                    {openIncomes.map(income => <option key={income.id} value={income.id}>{formatOffsetIncomeLabel(income)}</option>)}
                  </select>
                  {selectedIncome && (
                    <div style={{ marginTop: 8, padding: '0.75rem', border: '1px solid var(--border-color, rgba(255,255,255,0.12))', borderRadius: 8, display: 'grid', gap: 4 }}>
                      <div><strong>{tr('counterpartyName')}:</strong> {selectedIncome.client_name || '-'}</div>
                      {(selectedIncome.project_code || selectedIncome.project_name) && <div><strong>{tr('project')}:</strong> {[selectedIncome.project_code, selectedIncome.project_name].filter(Boolean).join(' / ')}</div>}
                      {selectedIncome.description && <div><strong>{tr('description')}:</strong> {selectedIncome.description}</div>}
                      <div><strong>{tr('remainingAmount')}:</strong> {fmt(selectedIncome.remaining)}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          {type === 'expense' && (
            <div className="form-group">
              <label className="form-label">{tr('selectExpense')}</label>
              {expenseCandidates.length === 0 ? <p style={{ color: 'var(--color-text-muted)' }}>{tr('noExpenseCandidates')}</p> : (
                <div>
                  <select className="form-input" required value={form.expense_id} onChange={e => setForm({ ...form, expense_id: e.target.value })}>
                    <option value="">-</option>
                    {expenseCandidates.map(expense => <option key={expense.id} value={expense.id}>{formatExpenseLabel(expense)}</option>)}
                  </select>
                  {selectedExpense && (
                    <div style={{ marginTop: 8, padding: '0.75rem', border: '1px solid var(--border-color, rgba(255,255,255,0.12))', borderRadius: 8, display: 'grid', gap: 4 }}>
                      <div><strong>{tr('linkedExpense')}:</strong> #{selectedExpense.id}</div>
                      <div><strong>{tr('date')}:</strong> {fmtDate(selectedExpense.date)}</div>
                      {selectedExpense.paid_date && <div><strong>{tr('dateOfPayment')}:</strong> {fmtDate(selectedExpense.paid_date)}</div>}
                      <div><strong>{tr('description')}:</strong> {selectedExpense.description}</div>
                      {(selectedExpense.project_code || selectedExpense.project_name) && <div><strong>{tr('project')}:</strong> {[selectedExpense.project_code, selectedExpense.project_name].filter(Boolean).join(' / ')}</div>}
                      {selectedExpense.contract_number && <div><strong>{tr('contractNumber')}:</strong> {selectedExpense.contract_number}</div>}
                      {selectedExpense.category && <div><strong>{tr('category')}:</strong> {selectedExpense.category}</div>}
                      {selectedExpense.bank_reference && <div><strong>{tr('paymentReference')}:</strong> {selectedExpense.bank_reference}</div>}
                      <div><strong>{tr('amount')}:</strong> {fmt(selectedExpense.amount)}</div>
                      {selectedExpense.note && <div><strong>{tr('note')}:</strong> {selectedExpense.note}</div>}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          {type !== 'expense' && (
            <>
              <div className="form-group">
                <label className="form-label">{tr('settlementAmount')}</label>
                <input className="form-input" type="number" step="0.01" required value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('settlementDate')}</label>
                <DatePicker value={form.date} onChange={value => setForm({ ...form, date: value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('note')}</label>
                <input className="form-input" value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} />
              </div>
            </>
          )}
          <div className="modal-actions">
            <button type="button" className="btn" onClick={onClose}>{tr('cancel')}</button>
            <button type="submit" className="btn btn-primary" disabled={submitting || (type === 'expense' && !form.expense_id)}>{tr('save')}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
