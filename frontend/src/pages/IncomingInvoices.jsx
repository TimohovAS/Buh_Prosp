import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import EntityDetailModal from '../components/EntityDetailModal'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import SharedStatusBadge from '../components/StatusBadge'
import YearFilterSelect from '../components/YearFilterSelect'
import useAvailableYears from '../hooks/useAvailableYears'
import useListPageState from '../hooks/useListPageState'
import { UI_CLOSE, UI_DASH, formatDateSr as fmtDate, formatMoney2OrDash as fmt, todayIso } from '../utils/formatters'

const STATUSES = ['unpaid', 'partial', 'paid', 'cancelled']
const STATUS_LABELS = { unpaid: 'statusUnpaid', partial: 'statusPartial', paid: 'statusPaid', cancelled: 'statusCancelled' }

function compactText(value, max = 80) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 3)}...` : text
}

function StatusBadge({ status }) {
  const tone = { unpaid: 'warning', partial: 'info', paid: 'success', cancelled: 'danger' }
  return <SharedStatusBadge tone={tone[status] || 'muted'}>{tr(STATUS_LABELS[status] || status)}</SharedStatusBadge>
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
  const { year, setYear, availableYears, applyAvailableYears, resetAvailableYears } = useAvailableYears({
    initialYear: new Date().getFullYear(),
  })
  const [month, setMonth] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(null)
  const [settleModal, setSettleModal] = useState(null)
  const [linkModal, setLinkModal] = useState(null)
  const [detailModal, setDetailModal] = useState(null)
  const [form, setForm] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [pageError, setPageError] = useState('')
  const {
    search,
    setSearch,
    sortCol,
    sortAsc,
    toggleSort,
  } = useListPageState({ initialSortCol: 'date', initialSortAsc: false })

  const defaultForm = { invoice_number: '', date: todayIso(), client_id: '', counterparty_name: '', project_id: '', amount: '', currency: 'RSD', description: '', note: '' }

  const load = () => {
    setLoading(true)
    setPageError('')
    const params = {}
    if (year) params.year = year
    if (month && year) params.month = month
    if (filterStatus) params.status = filterStatus
    Promise.all([api.incomingInvoices.list(params), api.incomingInvoices.years()])
      .then(([invoiceItems, years]) => {
        setItems(invoiceItems)
        applyAvailableYears(years)
      })
      .catch(() => {
        setItems([])
        resetAvailableYears()
      })
      .finally(() => setLoading(false))
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
  const renderProjectLabel = item => getProjectLabel(item) || tr('unassigned')
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
      <PageHeader
        title={tr('incomingInvoices')}
        actions={(
          <>
          {filtered.length > 0 ? (
            <div
              style={{
                alignSelf: 'center',
                display: 'flex',
                alignItems: 'center',
                gap: '1rem',
                flexWrap: 'wrap',
                marginRight: '0.5rem',
              }}
            >
              <span style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>
                {tr('total')}: {filtered.length}
              </span>
              <span style={{ fontWeight: 700, color: 'var(--color-text)' }}>
                {fmt(totalAmount)}
              </span>
              <span style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>
                {tr('remainingAmount')}: {fmt(totalRemaining)}
              </span>
            </div>
          ) : null}
          <YearFilterSelect
            value={year}
            availableYears={availableYears}
            onChange={nextYear => {
              setYear(nextYear)
              if (nextYear === '') setMonth('')
            }}
            style={{ width: 120 }}
          />
          <select className="form-input" value={month} onChange={e => setMonth(e.target.value)} style={{ width: 80 }} disabled={!year}>
            <option value="">-</option>
            {Array.from({ length: 12 }, (_, i) => i + 1).map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <select className="form-input" value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={{ width: 130 }}>
            <option value="">{tr('all') || 'All'}</option>
            {STATUSES.map(status => <option key={status} value={status}>{tr(STATUS_LABELS[status])}</option>)}
          </select>
          <SearchInput placeholder={tr('search')} value={search} onChange={setSearch} style={{ width: 200 }} />
          <button className="btn btn-primary" onClick={openAdd}>{tr('createIncomingInvoice')}</button>
          </>
        )}
      />

      {pageError && <div className="alert alert-danger">{pageError}</div>}

      <div className="page-body">
        <div className="card">
          <div className="table-wrap">
            <table className="incoming-invoices-list-table">
              <thead>
                <tr>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIndicator active={sortCol === 'date'} asc={sortAsc} /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('invoice_number')}>{tr('invoiceNumber')} <SortIndicator active={sortCol === 'invoice_number'} asc={sortAsc} /></th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('counterparty_name')}>{tr('counterpartyName')} <SortIndicator active={sortCol === 'counterparty_name'} asc={sortAsc} /></th>
                  <th>{tr('description')}</th>
                  <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')} <SortIndicator active={sortCol === 'amount'} asc={sortAsc} /></th>
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
                          <div className="income-meta-chips">
                            <span
                              className="income-meta-chip income-meta-chip-accent"
                              title={renderProjectLabel(inv)}
                            >
                              {renderProjectLabel(inv)}
                            </span>
                            {inv.client_name && inv.client_name !== inv.counterparty_name ? (
                              <span className="income-meta-chip" title={inv.client_name}>
                                {tr('client')}: {inv.client_name}
                              </span>
                            ) : null}
                          </div>
                        </td>
                        <td className="incoming-invoice-description-cell">
                          <div className="incoming-invoice-description" title={inv.description || UI_DASH}>
                            {inv.description || UI_DASH}
                          </div>
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
            </table>
          </div>
        </div>
      </div>

      <Modal
        isOpen={!!modal}
        onClose={() => setModal(null)}
        title={modal === 'add' ? tr('createIncomingInvoice') : tr('edit')}
        closeOnOverlay
      >
        {modal ? (
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
        ) : null}
      </Modal>

      {settleModal && <SettleModal data={settleModal} clients={clients} projects={projects} onClose={() => setSettleModal(null)} onDone={() => { const current = settleModal.invoice; setSettleModal(null); load(); openDetail(current.id) }} />}

      {linkModal && <LinkInvoiceModal data={linkModal} onClose={() => setLinkModal(null)} onDone={() => { const current = linkModal.invoice; setLinkModal(null); load(); openDetail(current.id) }} />}

      <EntityDetailModal
        isOpen={!!detailModal}
        onClose={() => setDetailModal(null)}
        title={detailModal ? `${tr('incomingInvoice')} ${detailModal.invoice_number}` : ''}
        maxWidth="920px"
        details={detailModal ? (
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
        ) : null}
        actions={detailModal && showDetailActions ? (
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
        ) : null}
      >
        {detailModal ? (
          <div className="record-detail-card">
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
        ) : null}
      </EntityDetailModal>
    </div>
  )
}

function SettleModal({ data, clients, projects, onClose, onDone }) {
  const { invoice, type } = data
  const [form, setForm] = useState({ amount: Number(invoice.remaining_amount || 0), date: invoice.date || todayIso(), note: '', bank_transaction_id: '', income_id: '', expense_id: '' })
  const [bankTxs, setBankTxs] = useState([])
  const [openIncomes, setOpenIncomes] = useState([])
  const [expenseCandidates, setExpenseCandidates] = useState([])
  const [bankSearch, setBankSearch] = useState('')
  const [expenseSearch, setExpenseSearch] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const selectedBankTx = bankTxs.find(i => i.id === Number(form.bank_transaction_id)) || null
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
  const showInvoiceSummary = true
  const isWideSideLayout = type === 'expense' || type === 'bank'
  const getProjectNameById = projectId => projects.find(project => project.id === projectId)?.name || ''
  const toDateOnly = value => {
    if (!value) return null
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? null : new Date(date.getFullYear(), date.getMonth(), date.getDate())
  }
  const getDateDelta = (left, right) => {
    const leftDate = toDateOnly(left)
    const rightDate = toDateOnly(right)
    if (!leftDate || !rightDate) return Number.MAX_SAFE_INTEGER
    return Math.abs(Math.round((leftDate - rightDate) / 86400000))
  }
  const normalizedInvoiceCounterparty = String(invoice.client_name || invoice.counterparty_name || '').toLowerCase().trim()
  const invoiceCounterpartyTokens = normalizedInvoiceCounterparty.split(/\s+/).filter(token => token.length >= 4)
  const targetAmount = Math.abs(Number(invoice.remaining_amount || invoice.amount || 0))
  const bankTxCandidates = useMemo(() => {
    const query = bankSearch.trim().toLowerCase()
    return bankTxs
      .map(tx => {
        const amount = Math.abs(Number(tx.amount || 0))
        const searchText = [
          tx.counterparty_name,
          tx.purpose,
          tx.bank_reference,
          tx.date,
          tx.project_name,
          getProjectNameById(tx.project_id),
          String(tx.amount || ''),
        ].filter(Boolean).join(' ').toLowerCase()
        const amountDelta = Math.abs(amount - targetAmount)
        const dateDelta = getDateDelta(tx.date, invoice.date)
        const counterpartyMatch = invoiceCounterpartyTokens.length > 0
          && invoiceCounterpartyTokens.some(token => searchText.includes(token))
        return {
          ...tx,
          amountDelta,
          dateDelta,
          counterpartyMatch,
          projectLabel: tx.project_name || getProjectNameById(tx.project_id) || '',
          searchText,
        }
      })
      .filter(tx => !query || tx.searchText.includes(query))
      .sort((a, b) => {
        if (a.amountDelta !== b.amountDelta) return a.amountDelta - b.amountDelta
        if (a.dateDelta !== b.dateDelta) return a.dateDelta - b.dateDelta
        if (a.counterpartyMatch !== b.counterpartyMatch) return a.counterpartyMatch ? -1 : 1
        return String(a.date || '').localeCompare(String(b.date || '')) * -1
      })
  }, [bankSearch, bankTxs, invoice.date, invoiceCounterpartyTokens, projects, targetAmount])
  const suggestedBankTxs = bankTxCandidates.filter(tx => tx.amountDelta < 0.01 || tx.counterpartyMatch).slice(0, 6)
  const suggestedBankTxIds = new Set(suggestedBankTxs.map(tx => tx.id))
  const allBankTxs = bankTxCandidates.filter(tx => !suggestedBankTxIds.has(tx.id))
  const formatOffsetIncomeLabel = income => {
    const parts = [income.invoice_number || '']
    if (income.date) parts.push(fmtDate(income.date))
    if (income.client_name) parts.push(income.client_name)
    if (income.project_code || income.project_name) parts.push([income.project_code, income.project_name].filter(Boolean).join(' / '))
    if (income.description) parts.push(compactText(income.description, 60))
    parts.push(`${tr('remainingAmount')}: ${fmt(income.remaining)}`)
    return parts.filter(Boolean).join(' | ')
  }
  const expenseCandidatesView = useMemo(() => {
    const query = expenseSearch.trim().toLowerCase()
    const normalizedInvoiceDescription = String(invoice.description || '').toLowerCase().trim()
    const descriptionTokens = normalizedInvoiceDescription.split(/\s+/).filter(token => token.length >= 5)
    return expenseCandidates
      .map(expense => {
        const candidateDate = expense.paid_date || expense.date
        const description = expense.description || ''
        const projectLabel = [expense.project_code, expense.project_name].filter(Boolean).join(' / ')
        const searchText = [
          expense.id,
          expense.date,
          expense.paid_date,
          description,
          projectLabel,
          expense.contract_number,
          expense.category,
          expense.bank_reference,
          expense.note,
          expense.bank_counterparty_name,
          expense.bank_purpose,
        ].filter(Boolean).join(' ').toLowerCase()
        const descriptionMatch = descriptionTokens.length > 0
          && descriptionTokens.some(token => searchText.includes(token))
        return {
          ...expense,
          candidateDate,
          projectLabel,
          searchText,
          dateDelta: getDateDelta(candidateDate, invoice.date),
          descriptionMatch,
        }
      })
      .filter(expense => !query || expense.searchText.includes(query))
      .sort((a, b) => {
        if (a.descriptionMatch !== b.descriptionMatch) return a.descriptionMatch ? -1 : 1
        if (a.dateDelta !== b.dateDelta) return a.dateDelta - b.dateDelta
        return String(b.candidateDate || '').localeCompare(String(a.candidateDate || ''))
      })
  }, [expenseCandidates, expenseSearch, getDateDelta, invoice.date, invoice.description])
  const suggestedExpenseCandidates = expenseCandidatesView.filter(expense => expense.descriptionMatch || expense.dateDelta <= 10).slice(0, 6)
  const suggestedExpenseIds = new Set(suggestedExpenseCandidates.map(expense => expense.id))
  const allExpenseCandidates = expenseCandidatesView.filter(expense => !suggestedExpenseIds.has(expense.id))
  const renderBankTxCard = tx => {
    const isSelected = selectedBankTx?.id === tx.id
    return (
      <div
        key={tx.id}
        className="record-detail-card"
        role="button"
        tabIndex={0}
        onClick={() => setForm(previous => ({ ...previous, bank_transaction_id: String(tx.id), amount: Number(tx.amount || previous.amount) }))}
        onKeyDown={event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            setForm(previous => ({ ...previous, bank_transaction_id: String(tx.id), amount: Number(tx.amount || previous.amount) }))
          }
        }}
        style={{
          margin: 0,
          cursor: 'pointer',
          borderColor: isSelected ? 'var(--color-primary)' : undefined,
          boxShadow: isSelected ? '0 0 0 1px var(--color-primary) inset' : undefined,
          background: isSelected ? 'rgba(78, 134, 255, 0.08)' : undefined,
        }}
      >
        <div className="record-detail-grid" style={{ gridTemplateColumns: '1fr auto', gap: '1rem' }}>
          <div className="record-field-text">
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <strong>{tx.counterparty_name || UI_DASH}</strong>
              <span style={{ color: 'var(--color-text-muted)' }}>{fmtDate(tx.date)}</span>
            </div>
            {tx.purpose ? <div style={{ marginTop: 6 }}>{compactText(tx.purpose, 140)}</div> : null}
            <div style={{ marginTop: 6, color: 'var(--color-text-muted)' }}>
              {[tx.projectLabel, tx.bank_reference ? `${tr('paymentReference')}: ${tx.bank_reference}` : ''].filter(Boolean).join(` ${UI_DASH} `) || UI_DASH}
            </div>
          </div>
          <div style={{ display: 'grid', gap: '0.5rem', justifyItems: 'end', alignContent: 'start' }}>
            <div style={{ fontWeight: 700 }}>{fmt(tx.amount)} {tx.currency || 'RSD'}</div>
            {tx.amountDelta > 0.009 ? (
              <div style={{ color: 'var(--color-warning)', fontSize: '0.82rem', textAlign: 'right' }}>
                {tr('receiptAmountDelta')}: {fmt(tx.amountDelta)}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    )
  }
  const renderExpenseCandidateCard = expense => {
    const isSelected = selectedExpense?.id === expense.id
    return (
      <div
        key={expense.id}
        className="record-detail-card"
        role="button"
        tabIndex={0}
        onClick={() => setForm(previous => ({ ...previous, expense_id: String(expense.id) }))}
        onKeyDown={event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            setForm(previous => ({ ...previous, expense_id: String(expense.id) }))
          }
        }}
        style={{
          margin: 0,
          cursor: 'pointer',
          borderColor: isSelected ? 'var(--color-primary)' : undefined,
          boxShadow: isSelected ? '0 0 0 1px var(--color-primary) inset' : undefined,
          background: isSelected ? 'rgba(78, 134, 255, 0.08)' : undefined,
        }}
      >
        <div className="record-detail-grid" style={{ gridTemplateColumns: '1fr auto', gap: '1rem' }}>
          <div className="record-field-text">
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <strong>{expense.description || `#${expense.id}`}</strong>
              <span style={{ color: 'var(--color-text-muted)' }}>{fmtDate(expense.date)}</span>
              {expense.paid_date ? <span style={{ color: 'var(--color-text-muted)' }}>{tr('dateOfPayment')}: {fmtDate(expense.paid_date)}</span> : null}
            </div>
            <div style={{ marginTop: 6, color: 'var(--color-text-muted)' }}>
              {[
                expense.projectLabel,
                expense.contract_number ? `${tr('contractNumber')}: ${expense.contract_number}` : '',
                expense.category,
              ].filter(Boolean).join(` ${UI_DASH} `) || UI_DASH}
            </div>
            {expense.bank_reference ? (
              <div style={{ marginTop: 6, color: 'var(--color-text-muted)' }}>
                {tr('paymentReference')}: {expense.bank_reference}
              </div>
            ) : null}
            {expense.bank_counterparty_name || expense.bank_purpose ? (
              <div style={{ marginTop: 6 }}>
                {compactText([expense.bank_counterparty_name, expense.bank_purpose].filter(Boolean).join(` ${UI_DASH} `), 140)}
              </div>
            ) : null}
          </div>
          <div style={{ display: 'grid', gap: '0.5rem', justifyItems: 'end', alignContent: 'start' }}>
            <div style={{ fontWeight: 700 }}>{fmt(expense.amount)} {expense.currency || 'RSD'}</div>
            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.82rem' }}>#{expense.id}</div>
          </div>
        </div>
      </div>
    )
  }
  const renderInvoiceSummaryCard = () => (
    <div className="record-detail-card">
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
          <span className="record-field-label">{tr('remainingAmount')}</span>
          <span className="record-field-value">{fmt(invoice.remaining_amount)}</span>
        </div>
        <div className="record-field full">
          <span className="record-field-label">{tr('counterpartyName')}</span>
          <span className="record-field-value">{invoice.client_name || invoice.counterparty_name || UI_DASH}</span>
        </div>
        {invoiceProjectLabel ? (
          <div className="record-field full">
            <span className="record-field-label">{tr('project')}</span>
            <span className="record-field-value">{invoiceProjectLabel}</span>
          </div>
        ) : null}
        {invoice.description ? (
          <div className="record-field full">
            <span className="record-field-label">{tr('description')}</span>
            <div className="record-field-text">{invoice.description}</div>
          </div>
        ) : null}
        {invoice.note ? (
          <div className="record-field full">
            <span className="record-field-label">{tr('note')}</span>
            <div className="record-field-text">{invoice.note}</div>
          </div>
        ) : null}
      </div>
    </div>
  )
  const renderExpenseSelectionPanel = () => (
    expenseCandidates.length === 0 ? <p style={{ color: 'var(--color-text-muted)' }}>{tr('noExpenseCandidates')}</p> : (
      <div className="record-detail-card">
        <div className="record-field-label" style={{ marginBottom: '0.8rem' }}>{tr('selectExpense')}</div>
        <SearchInput
          placeholder={tr('search')}
          value={expenseSearch}
          onChange={setExpenseSearch}
          style={{ width: '100%', marginBottom: '0.75rem' }}
        />
        <div style={{ display: 'grid', gap: '0.75rem' }}>
          {suggestedExpenseCandidates.length > 0 ? (
            <div>
              <div className="record-field-label" style={{ marginBottom: '0.75rem' }}>{tr('bankTxAutoFound')}</div>
              <div style={{ display: 'grid', gap: '0.75rem' }}>
                {suggestedExpenseCandidates.map(renderExpenseCandidateCard)}
              </div>
            </div>
          ) : null}
          <div>
            <div className="record-field-label" style={{ marginBottom: '0.75rem' }}>{tr('bankTxAll')}</div>
            <div style={{ display: 'grid', gap: '0.75rem', maxHeight: 420, overflowY: 'auto', paddingRight: '0.2rem' }}>
              {expenseCandidatesView.length === 0 ? (
                <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', textAlign: 'center' }}>{tr('bankTxNoInvoicesFound')}</p>
              ) : (
                (suggestedExpenseCandidates.length > 0 ? allExpenseCandidates : expenseCandidatesView).map(renderExpenseCandidateCard)
              )}
            </div>
          </div>
        </div>
      </div>
    )
  )
  const renderBankSelectionPanel = () => (
    <div className="record-detail-card">
      <div className="record-field-label" style={{ marginBottom: '0.8rem' }}>{tr('selectBankTx')}</div>
      <SearchInput
        placeholder={tr('bankTxSearchObligations')}
        value={bankSearch}
        onChange={setBankSearch}
        style={{ width: '100%', marginBottom: '0.75rem' }}
      />
      <div style={{ display: 'grid', gap: '0.75rem' }}>
        {suggestedBankTxs.length > 0 ? (
          <div>
            <div className="record-field-label" style={{ marginBottom: '0.75rem' }}>{tr('bankTxAutoFound')}</div>
            <div style={{ display: 'grid', gap: '0.75rem' }}>
              {suggestedBankTxs.map(renderBankTxCard)}
            </div>
          </div>
        ) : null}
        <div>
          <div className="record-field-label" style={{ marginBottom: '0.75rem' }}>{tr('bankTxAll')}</div>
          <div style={{ display: 'grid', gap: '0.75rem', maxHeight: 320, overflowY: 'auto', paddingRight: '0.2rem' }}>
            {bankTxCandidates.length === 0 ? (
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', textAlign: 'center' }}>{tr('bankTxNoInvoicesFound')}</p>
            ) : (
              (suggestedBankTxs.length > 0 ? allBankTxs : bankTxCandidates).map(renderBankTxCard)
            )}
          </div>
        </div>
      </div>
    </div>
  )
  const renderSettlementFields = () => (
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
  )

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={`${titles[type]}: ${invoice.invoice_number}`}
      maxWidth={isWideSideLayout ? '1280px' : undefined}
      bodyClassName={isWideSideLayout ? 'incoming-invoice-settle-modal-body' : ''}
      closeOnOverlay
    >
        <form onSubmit={handleSubmit}>
          {isWideSideLayout ? (
            <div className="incoming-invoice-settle-layout">
              <div className="incoming-invoice-settle-column">
                {showInvoiceSummary && (
                  <div className="form-group">
                    {renderInvoiceSummaryCard()}
                  </div>
                )}
              </div>
              <div className="incoming-invoice-settle-column">
                <div className="form-group">
                  {type === 'expense' ? renderExpenseSelectionPanel() : renderBankSelectionPanel()}
                </div>
                {type === 'bank' ? (
                  <div className="record-detail-card" style={{ marginBottom: '1rem' }}>
                    {renderSettlementFields()}
                  </div>
                ) : null}
                <div className="modal-actions">
                  <button type="button" className="btn" onClick={onClose}>{tr('cancel')}</button>
                  <button type="submit" className="btn btn-primary" disabled={submitting || (type === 'expense' && !form.expense_id) || (type === 'bank' && !form.bank_transaction_id)}>{tr('save')}</button>
                </div>
              </div>
            </div>
          ) : (
            <>
          {showInvoiceSummary && (
            <div className="form-group">
              {renderInvoiceSummaryCard()}
            </div>
          )}
          {type === 'bank' && (
            <div className="form-group">
              {renderBankSelectionPanel()}
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
              {renderExpenseSelectionPanel()}
            </div>
          )}
          {type !== 'expense' && (
            renderSettlementFields()
          )}
          <div className="modal-actions">
            <button type="button" className="btn" onClick={onClose}>{tr('cancel')}</button>
            <button type="submit" className="btn btn-primary" disabled={submitting || (type === 'expense' && !form.expense_id) || (type === 'bank' && !form.bank_transaction_id)}>{tr('save')}</button>
          </div>
            </>
          )}
        </form>
    </Modal>
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
    <Modal
      isOpen
      onClose={onClose}
      title={`${title}: ${invoice.invoice_number}`}
      maxWidth="840px"
      closeOnOverlay
    >
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
    </Modal>
  )
}
