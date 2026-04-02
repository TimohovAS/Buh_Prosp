import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import SearchInput from '../components/SearchInput'

const UI_CLOSE = '\u2715'
const UI_DASH = '\u2014'
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

function LinkedInvoiceSummary({ invoice }) {
  if (!invoice) return <span className="record-field-value">{UI_DASH}</span>
  return (
    <div className="record-field-text">
      <div style={{ fontWeight: 600 }}>{invoice.invoice_number || UI_DASH}</div>
      <div style={{ color: 'var(--color-text-muted)' }}>
        {[fmtDate(invoice.date), `${fmt(invoice.amount)} ${invoice.currency || 'RSD'}`, invoice.counterparty_name].filter(Boolean).join(' • ')}
      </div>
      {invoice.project_code || invoice.project_name ? (
        <div style={{ color: 'var(--color-text-muted)' }}>{[invoice.project_code, invoice.project_name].filter(Boolean).join(' / ')}</div>
      ) : null}
      {invoice.description ? <div>{compactText(invoice.description, 120)}</div> : null}
      <div style={{ marginTop: 4 }}><StatusBadge status={invoice.status} /></div>
    </div>
  )
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
  const [linkModal, setLinkModal] = useState(null)
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

  const openEditFromDetail = async item => {
    setDetailModal(null)
    await openEdit(item)
  }

  const openSettlementFromDetail = item => type => {
    setDetailModal(null)
    setSettleModal({ invoice: item, type })
  }

  const openInvoiceLinkFromDetail = item => mode => {
    setDetailModal(null)
    setLinkModal({ invoice: item, mode })
  }

  const handleCancelFromDetail = async item => {
    await handleCancel(item.id)
    openDetail(item.id)
  }

  const handleRestoreFromDetail = async item => {
    await api.incomingInvoices.restore(item.id).catch(() => {})
    load()
    openDetail(item.id)
  }

  const handleUnlinkFromDetail = async item => {
    await api.incomingInvoices.unlinkAdvance(item.id).catch(() => {})
    load()
    openDetail(item.id)
  }

  const totalAmount = useMemo(() => filtered.reduce((sum, item) => sum + Number(item.amount || 0), 0), [filtered])
  const totalRemaining = useMemo(() => filtered.reduce((sum, item) => sum + Number(item.remaining_amount || 0), 0), [filtered])
  const getProjectLabel = item => (
    [item?.project_code, item?.project_name].filter(Boolean).join(' / ')
    || projects.find(project => project.id === item?.project_id)?.name
    || ''
  )
  const detailAmount = Number(detailModal?.amount || 0)
  const canEditDetail = !!detailModal && detailModal.status !== 'paid' && detailModal.status !== 'cancelled'
  const canRestoreDetail = detailModal?.status === 'cancelled'
  const canCancelDetail = !!detailModal && detailModal.status !== 'paid' && detailModal.status !== 'cancelled'
  const canLinkAdvanceDetail = !!detailModal && detailAmount === 0 && !detailModal.advance_invoice && !detailModal.closing_invoice
  const canLinkClosingDetail = !!detailModal && detailAmount > 0 && detailModal.status === 'paid' && !detailModal.closing_invoice
  const canUnlinkAdvanceDetail = !!detailModal?.advance_invoice
  const canUnlinkClosingDetail = !!detailModal?.closing_invoice
  const canSettleDetail = canEditDetail && detailAmount > 0 && !detailModal?.advance_invoice
  const showDetailActions = canEditDetail || canRestoreDetail || canCancelDetail || canLinkAdvanceDetail || canLinkClosingDetail || canUnlinkAdvanceDetail || canUnlinkClosingDetail || canSettleDetail

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">{tr('incomingInvoices')}</h1>
        </div>
        <div className="page-header-actions">
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
          <SearchInput placeholder={tr('search')} value={search} onChange={setSearch} style={{ width: 200 }} />
          <button className="btn btn-primary" onClick={openAdd}>{tr('createIncomingInvoice')}</button>
        </div>
      </div>

      {pageError && <div className="alert alert-danger">{pageError}</div>}

      <div className="page-body">
        <div className="card">
          <div className="table-wrap">
            <table className="incoming-invoices-list-table">
              <thead>
                <tr>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')}<SortIcon col="date" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('invoice_number')}>{tr('invoiceNumber')}<SortIcon col="invoice_number" /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('counterparty_name')}>{tr('counterpartyName')}<SortIcon col="counterparty_name" /></th>
                  <th>{tr('description')}</th>
                  <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')}<SortIcon col="amount" /></th>
                </tr>
              </thead>
              <tbody>
                {loading ? <tr><td colSpan={5}>{tr('loading')}</td></tr>
                  : filtered.length === 0 ? <tr><td colSpan={5}>{tr('noRecords')}</td></tr>
                    : filtered.map(inv => (
                      <tr
                        key={inv.id}
                        className={`record-row ${inv.status === 'cancelled' ? 'row-reversal' : ''}`.trim()}
                        onClick={() => openDetail(inv.id)}
                        onKeyDown={event => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            openDetail(inv.id)
                          }
                        }}
                        tabIndex={0}
                      >
                        <td className="incoming-invoice-date-cell">
                          <div className="incoming-invoice-date-primary">{fmtDate(inv.date)}</div>
                          <div className="incoming-invoice-date-secondary">
                            {getProjectLabel(inv) || UI_DASH}
                          </div>
                        </td>
                        <td className="incoming-invoice-document-cell">
                          <div className="incoming-invoice-number">{inv.invoice_number || UI_DASH}</div>
                          <div className="incoming-invoice-document-meta">
                            {inv.currency || 'RSD'}
                          </div>
                        </td>
                        <td className="incoming-invoice-party-cell">
                          <div className="incoming-invoice-party-name" title={inv.counterparty_name || inv.client_name || UI_DASH}>
                            {inv.counterparty_name || inv.client_name || UI_DASH}
                          </div>
                          {inv.client_name && inv.client_name !== inv.counterparty_name ? (
                            <div className="incoming-invoice-party-meta" title={inv.client_name}>
                              {tr('client')}: {inv.client_name}
                            </div>
                          ) : null}
                        </td>
                        <td className="incoming-invoice-description-cell">
                          <div className="incoming-invoice-description" title={inv.description || UI_DASH}>
                            {inv.description || UI_DASH}
                          </div>
                          {inv.note ? <div className="incoming-invoice-note">{inv.note}</div> : null}
                        </td>
                        <td className="incoming-invoice-amount-cell">
                          <div className="incoming-invoice-amount-primary">{fmt(inv.amount)} {inv.currency || 'RSD'}</div>
                          <div className="incoming-invoice-status-inline"><StatusBadge status={inv.status} /></div>
                          <div className="incoming-invoice-amount-meta">
                            {tr('settledAmount')}: {fmt(inv.settled_amount)}
                          </div>
                          <div className="incoming-invoice-amount-meta">
                            {tr('remainingAmount')}: {fmt(inv.remaining_amount)}
                          </div>
                        </td>
                      </tr>
                    ))}
              </tbody>
              {filtered.length > 0 && (
                <tfoot>
                  <tr style={{ fontWeight: 'bold' }}>
                    <td colSpan={4}>{tr('total') || 'Total'}: {filtered.length}</td>
                    <td style={{ textAlign: 'right' }}>
                      <div>{fmt(totalAmount)}</div>
                      <div className="incoming-invoice-amount-meta">{tr('remainingAmount')}: {fmt(totalRemaining)}</div>
                    </td>
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

      {settleModal && <SettleModal data={settleModal} clients={clients} onClose={() => setSettleModal(null)} onDone={() => { const current = settleModal.invoice; setSettleModal(null); load(); openDetail(current.id) }} />}

      {linkModal && <LinkInvoiceModal data={linkModal} onClose={() => setLinkModal(null)} onDone={() => { const current = linkModal.invoice; setLinkModal(null); load(); openDetail(current.id) }} />}

      {detailModal && (
        <div className="modal-overlay" onClick={() => setDetailModal(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 920 }}>
            <div className="modal-header">
              <h2 className="modal-title">{tr('incomingInvoice')} {detailModal.invoice_number}</h2>
              <button className="modal-close" onClick={() => setDetailModal(null)}>{UI_CLOSE}</button>
            </div>
            <div className="modal-body">
              <div className="record-detail-grid">
                <div className="record-detail-card" style={showDetailActions ? undefined : { gridColumn: '1 / -1' }}>
                  <div className="record-field-grid">
                    <div className="record-field">
                      <span className="record-field-label">{tr('date')}</span>
                      <span className="record-field-value">{fmtDate(detailModal.date)}</span>
                    </div>
                    <div className="record-field">
                      <span className="record-field-label">{tr('status')}</span>
                      <div><StatusBadge status={detailModal.status} /></div>
                    </div>
                    <div className="record-field">
                      <span className="record-field-label">{tr('amount')}</span>
                      <span className="record-field-value">{fmt(detailModal.amount)} {detailModal.currency}</span>
                    </div>
                    <div className="record-field">
                      <span className="record-field-label">{tr('settledAmount')}</span>
                      <span className="record-field-value">{fmt(detailModal.settled_amount)}</span>
                    </div>
                    <div className="record-field">
                      <span className="record-field-label">{tr('remainingAmount')}</span>
                      <span className="record-field-value">{fmt(detailModal.remaining_amount)}</span>
                    </div>
                    <div className="record-field">
                      <span className="record-field-label">{tr('project')}</span>
                      <span className="record-field-value">{getProjectLabel(detailModal) || UI_DASH}</span>
                    </div>
                    <div className="record-field full">
                      <span className="record-field-label">{tr('counterpartyName')}</span>
                      <span className="record-field-value">{detailModal.counterparty_name || detailModal.client_name || UI_DASH}</span>
                    </div>
                    {detailModal.client_name && detailModal.client_name !== detailModal.counterparty_name ? (
                      <div className="record-field full">
                        <span className="record-field-label">{tr('client')}</span>
                        <span className="record-field-value">{detailModal.client_name}</span>
                      </div>
                    ) : null}
                    {detailModal.status === 'paid' && detailModal.expense_id && (!detailModal.settlements || detailModal.settlements.length === 0) && (
                      <div className="record-field full">
                        <span className="record-field-label">{tr('linkedExpense')}</span>
                        <span className="record-field-value">#{detailModal.expense_id}</span>
                      </div>
                    )}
                    {detailModal.advance_invoice ? (
                      <div className="record-field full">
                        <span className="record-field-label">{tr('advanceInvoice')}</span>
                        <LinkedInvoiceSummary invoice={detailModal.advance_invoice} />
                      </div>
                    ) : null}
                    {detailModal.closing_invoice ? (
                      <div className="record-field full">
                        <span className="record-field-label">{tr('closingInvoice')}</span>
                        <LinkedInvoiceSummary invoice={detailModal.closing_invoice} />
                      </div>
                    ) : null}
                    {detailModal.advance_invoice && detailAmount === 0 ? (
                      <div className="record-field full">
                        <span className="record-field-label">{tr('note')}</span>
                        <div className="record-field-text">{tr('linkedInvoiceAmountZeroHint')}</div>
                      </div>
                    ) : null}
                    <div className="record-field full">
                      <span className="record-field-label">{tr('description')}</span>
                      <div className="record-field-text">{detailModal.description || UI_DASH}</div>
                    </div>
                    <div className="record-field full">
                      <span className="record-field-label">{tr('note')}</span>
                      <div className="record-field-text">{detailModal.note || UI_DASH}</div>
                    </div>
                  </div>
                </div>
                {showDetailActions ? (
                  <div className="record-detail-card">
                    <div className="record-actions-grid">
                      {canEditDetail ? <button type="button" className="btn btn-secondary" onClick={() => openEditFromDetail(detailModal)}>{tr('edit')}</button> : null}
                      {canSettleDetail ? <button type="button" className="btn btn-secondary" onClick={() => openSettlementFromDetail(detailModal)('expense')}>{tr('attachExpense')}</button> : null}
                      {canSettleDetail ? <button type="button" className="btn btn-primary" onClick={() => openSettlementFromDetail(detailModal)('bank')}>{tr('settleViaBank')}</button> : null}
                      {canSettleDetail ? <button type="button" className="btn btn-secondary" onClick={() => openSettlementFromDetail(detailModal)('cash')}>{tr('settleViaCash')}</button> : null}
                      {canSettleDetail ? <button type="button" className="btn btn-secondary" onClick={() => openSettlementFromDetail(detailModal)('offset')}>{tr('settleViaOffset')}</button> : null}
                      {canLinkAdvanceDetail ? <button type="button" className="btn btn-primary" onClick={() => openInvoiceLinkFromDetail(detailModal)('advance')}>{tr('linkAdvanceInvoice')}</button> : null}
                      {canLinkClosingDetail ? <button type="button" className="btn btn-primary" onClick={() => openInvoiceLinkFromDetail(detailModal)('closing')}>{tr('linkClosingInvoice')}</button> : null}
                      {canUnlinkAdvanceDetail ? <button type="button" className="btn btn-secondary" onClick={() => handleUnlinkFromDetail(detailModal)}>{tr('unlinkAdvanceInvoice')}</button> : null}
                      {canUnlinkClosingDetail ? <button type="button" className="btn btn-secondary" onClick={() => handleUnlinkFromDetail(detailModal)}>{tr('unlinkClosingInvoice')}</button> : null}
                      {canRestoreDetail ? <button type="button" className="btn btn-secondary" onClick={() => handleRestoreFromDetail(detailModal)}>{tr('restoreIncomingInvoice')}</button> : null}
                      {canCancelDetail ? <button type="button" className="btn btn-danger" onClick={() => handleCancelFromDetail(detailModal)}>{tr('cancelIncomingInvoice')}</button> : null}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="record-detail-card" style={{ marginTop: '1rem' }}>
                <div className="record-field-label" style={{ marginBottom: '0.8rem' }}>{tr('settlementHistory')}</div>
                {(!detailModal.settlements || detailModal.settlements.length === 0) ? <p>{tr('noSettlements')}</p> : (
                  <div className="table-wrap">
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
                  </div>
                )}
              </div>
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

function LinkInvoiceModal({ data, onClose, onDone }) {
  const { invoice, mode } = data
  const [candidates, setCandidates] = useState([])
  const [loading, setLoading] = useState(true)
  const [submittingId, setSubmittingId] = useState(null)

  useEffect(() => {
    let active = true
    const loader = mode === 'advance' ? api.incomingInvoices.advanceCandidates : api.incomingInvoices.closingCandidates
    loader(invoice.id)
      .then(items => { if (active) setCandidates(items || []) })
      .catch(() => { if (active) setCandidates([]) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [invoice.id, mode])

  const handleLink = async candidateId => {
    setSubmittingId(candidateId)
    try {
      if (mode === 'advance') {
        await api.incomingInvoices.linkAdvance(invoice.id, { advance_invoice_id: candidateId })
      } else {
        await api.incomingInvoices.linkClosing(invoice.id, { closing_invoice_id: candidateId })
      }
      onDone()
    } catch {
      setSubmittingId(null)
    }
  }

  const title = mode === 'advance' ? tr('selectAdvanceInvoice') : tr('selectClosingInvoice')
  const emptyLabel = mode === 'advance' ? tr('noAdvanceInvoiceCandidates') : tr('noClosingInvoiceCandidates')
  const currentProjectLabel = [invoice.project_code, invoice.project_name].filter(Boolean).join(' / ')

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 840 }}>
        <div className="modal-header">
          <h2 className="modal-title">{title}: {invoice.invoice_number}</h2>
          <button className="modal-close" onClick={onClose}>{UI_CLOSE}</button>
        </div>
        <div className="modal-body">
          <div className="record-detail-card" style={{ marginBottom: '1rem' }}>
            <div className="record-field-grid">
              <div className="record-field">
                <span className="record-field-label">{tr('invoiceNumber')}</span>
                <span className="record-field-value">{invoice.invoice_number}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('date')}</span>
                <span className="record-field-value">{fmtDate(invoice.date)}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('amount')}</span>
                <span className="record-field-value">{fmt(invoice.amount)} {invoice.currency || 'RSD'}</span>
              </div>
              <div className="record-field">
                <span className="record-field-label">{tr('status')}</span>
                <div><StatusBadge status={invoice.status} /></div>
              </div>
              <div className="record-field full">
                <span className="record-field-label">{tr('counterpartyName')}</span>
                <span className="record-field-value">{invoice.counterparty_name || invoice.client_name || UI_DASH}</span>
              </div>
              {currentProjectLabel ? (
                <div className="record-field full">
                  <span className="record-field-label">{tr('project')}</span>
                  <span className="record-field-value">{currentProjectLabel}</span>
                </div>
              ) : null}
            </div>
          </div>

          <div className="record-detail-card">
            <div className="record-field-label" style={{ marginBottom: '0.8rem' }}>{title}</div>
            {loading ? <p>{tr('loading')}</p> : candidates.length === 0 ? <p>{emptyLabel}</p> : (
              <div style={{ display: 'grid', gap: '0.75rem' }}>
                {candidates.map(candidate => {
                  const candidateProjectLabel = [candidate.project_code, candidate.project_name].filter(Boolean).join(' / ')
                  return (
                    <div key={candidate.id} className="record-detail-card" style={{ margin: 0 }}>
                      <div className="record-detail-grid" style={{ gridTemplateColumns: '1fr auto', gap: '1rem' }}>
                        <div className="record-field-text">
                          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                            <strong>{candidate.invoice_number}</strong>
                            <span style={{ color: 'var(--color-text-muted)' }}>{fmtDate(candidate.date)}</span>
                            <StatusBadge status={candidate.status} />
                          </div>
                          <div style={{ marginTop: 6 }}>{candidate.counterparty_name || candidate.client_name || UI_DASH}</div>
                          {candidateProjectLabel ? <div style={{ color: 'var(--color-text-muted)', marginTop: 4 }}>{candidateProjectLabel}</div> : null}
                          {candidate.description ? <div style={{ marginTop: 6 }}>{compactText(candidate.description, 140)}</div> : null}
                        </div>
                        <div style={{ display: 'grid', gap: '0.75rem', justifyItems: 'end', alignContent: 'start' }}>
                          <div style={{ fontWeight: 700 }}>{fmt(candidate.amount)} {candidate.currency || 'RSD'}</div>
                          <button type="button" className="btn btn-primary" disabled={submittingId === candidate.id} onClick={() => handleLink(candidate.id)}>
                            {tr(mode === 'advance' ? 'linkAdvanceInvoice' : 'linkClosingInvoice')}
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
