import { FileText, Plus, RotateCcw, Search } from 'lucide-react'
import { getMonthNamesFull, tr } from '../../i18n'
import PageHeader from '../PageHeader'
import SearchInput from '../SearchInput'
import SortIndicator from '../SortIndicator'
import StatusBadge from '../StatusBadge'
import YearFilterSelect from '../YearFilterSelect'
import { UI_DASH, formatDateSr, formatMoney2OrDash as fmt } from '../../utils/formatters'
import './invoice-register.css'

const STATUSES = {
  unpaid: ['statusUnpaid', 'warning'],
  partial: ['statusPartial', 'info'],
  paid: ['statusPaid', 'success'],
  cancelled: ['statusCancelled', 'muted'],
}

function Totals({ items, field }) {
  const currencies = new Map()
  for (const item of items) {
    const currency = item.currency || 'RSD'
    currencies.set(currency, (currencies.get(currency) || 0) + Number(item[field] || 0))
  }
  if (!currencies.size) return <span>{UI_DASH}</span>
  return [...currencies].map(([currency, amount]) => (
    <span key={currency} className="invoice-register-total">
      {fmt(amount)} <small>{currency}</small>
    </span>
  ))
}

export default function InvoiceRegister({
  items,
  loading,
  error,
  year,
  availableYears,
  onYearChange,
  month,
  onMonthChange,
  status,
  onStatusChange,
  search,
  onSearchChange,
  sortCol,
  sortAsc,
  onSort,
  onAdd,
  onOpen,
  onRetry,
  projectLabel,
}) {
  const hasFilters = year !== '' || month || status || search
  const resetFilters = () => {
    onYearChange('')
    onMonthChange('')
    onStatusChange('')
    onSearchChange('')
  }
  const sortHeader = (key, label, className = '') => (
    <th
      scope="col"
      className={className}
      aria-sort={sortCol === key ? (sortAsc ? 'ascending' : 'descending') : 'none'}
    >
      <button type="button" onClick={() => onSort(key)}>
        {tr(label)} <SortIndicator active={sortCol === key} asc={sortAsc} />
      </button>
    </th>
  )

  return (
    <>
      <PageHeader
        title={tr('incomingInvoices')}
        subtitle={tr('invoiceRegisterSubtitle')}
        actions={
          <button type="button" className="btn btn-primary" onClick={onAdd}>
            <Plus size={16} aria-hidden="true" />
            {tr('createIncomingInvoice')}
          </button>
        }
      />
      <div className="page-body">
        <div className="invoice-register-overview" aria-label={tr('invoiceRegisterSelection')}>
          <div className="invoice-register-metric">
            <span>{tr('invoiceRegisterCount')}</span>
            <strong>{loading || error ? UI_DASH : items.length}</strong>
          </div>
          <div className="invoice-register-metric">
            <span>{tr('invoiceRegisterTotal')}</span>
            <strong>{loading || error ? UI_DASH : <Totals items={items} field="amount" />}</strong>
          </div>
          <div className="invoice-register-metric invoice-register-outstanding">
            <span>{tr('invoiceRegisterRemaining')}</span>
            <strong>{loading || error ? UI_DASH : <Totals items={items} field="remaining_amount" />}</strong>
          </div>
          <span className="invoice-register-selection">{tr('invoiceRegisterSelection')}</span>
        </div>

        <div className="card invoice-register-card">
          <div className="invoice-register-toolbar">
            <div className="invoice-register-search">
              <Search size={17} aria-hidden="true" />
              <SearchInput
                value={search}
                onChange={onSearchChange}
                placeholder={tr('invoiceRegisterSearch')}
                aria-label={tr('search')}
              />
            </div>
            <label className="invoice-register-filter">
              <span>{tr('filterYear')}</span>
              <YearFilterSelect
                value={year}
                availableYears={availableYears}
                onChange={onYearChange}
                style={{ width: '100%' }}
              />
            </label>
            <label className="invoice-register-filter">
              <span>{tr('month')}</span>
              <select
                className="form-input"
                value={month}
                onChange={(e) => onMonthChange(e.target.value)}
                disabled={!year}
              >
                <option value="">{tr('allMonths')}</option>
                {getMonthNamesFull().map((name, i) => (
                  <option key={i} value={i + 1}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="invoice-register-filter">
              <span>{tr('filterStatus')}</span>
              <select className="form-input" value={status} onChange={(e) => onStatusChange(e.target.value)}>
                <option value="">{tr('allStatuses')}</option>
                {Object.entries(STATUSES).map(([value, [label]]) => (
                  <option key={value} value={value}>
                    {tr(label)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="btn btn-secondary invoice-register-reset"
              onClick={resetFilters}
              disabled={!hasFilters}
              title={tr('invoiceRegisterReset')}
              aria-label={tr('invoiceRegisterReset')}
            >
              <RotateCcw size={16} aria-hidden="true" />
            </button>
          </div>
          <div className="table-wrap" aria-busy={loading}>
            <table className="invoice-register-table">
              <thead>
                <tr>
                  {sortHeader('date', 'date')}
                  {sortHeader('invoice_number', 'invoiceNumber')}
                  {sortHeader('counterparty_name', 'counterpartyName')}
                  <th scope="col">{tr('description')}</th>
                  {sortHeader('amount', 'invoiceRegisterAmount', 'invoice-register-numeric')}
                  {sortHeader('status', 'filterStatus')}
                </tr>
              </thead>
              <tbody>
                {loading || error || items.length === 0 ? (
                  <tr>
                    <td colSpan={6}>
                      <div className="invoice-register-empty" role="status">
                        <FileText size={28} aria-hidden="true" />
                        <strong>{tr(loading ? 'loading' : error ? 'loadError' : 'noRecords')}</strong>
                        {!loading && <span>{error || tr('invoiceRegisterEmptyHint')}</span>}
                        {!loading &&
                          (error ? (
                            <button type="button" className="btn btn-secondary" onClick={onRetry}>
                              {tr('retry')}
                            </button>
                          ) : hasFilters ? (
                            <button type="button" className="btn btn-secondary" onClick={resetFilters}>
                              {tr('invoiceRegisterReset')}
                            </button>
                          ) : null)}
                      </div>
                    </td>
                  </tr>
                ) : (
                  items.map((invoice) => {
                    const [label, tone] = STATUSES[invoice.status] || [invoice.status, 'muted']
                    const party = invoice.counterparty_name || invoice.client_name || UI_DASH
                    const remaining = Number(invoice.remaining_amount || 0)
                    const project =
                      invoice.project_code === 'INT-UNASSIGNED' ? tr('unassigned') : projectLabel(invoice)
                    return (
                      <tr
                        key={invoice.id}
                        className={`record-row ${invoice.status === 'cancelled' ? 'row-reversal' : ''}`}
                        onClick={() => onOpen(invoice.id)}
                      >
                        <td className="invoice-register-date">{formatDateSr(invoice.date)}</td>
                        <td>
                          <button
                            type="button"
                            className="invoice-register-number"
                            onClick={(event) => {
                              event.stopPropagation()
                              onOpen(invoice.id)
                            }}
                          >
                            {invoice.invoice_number || UI_DASH}
                          </button>
                          {Number(invoice.amount) === 0 && invoice.status === 'paid' && (
                            <span className="invoice-register-meta">{tr('invoiceRegisterNoPayment')}</span>
                          )}
                        </td>
                        <td>
                          <div className="invoice-register-party" title={party}>
                            {party}
                          </div>
                          <div className="invoice-register-meta" title={projectLabel(invoice)}>
                            {project}
                          </div>
                          {invoice.client_name && invoice.client_name !== invoice.counterparty_name && (
                            <div className="invoice-register-meta" title={invoice.client_name}>
                              {tr('client')}: {invoice.client_name}
                            </div>
                          )}
                        </td>
                        <td>
                          <div className="invoice-register-description" title={invoice.description || ''}>
                            {invoice.description || UI_DASH}
                          </div>
                        </td>
                        <td className="invoice-register-numeric">
                          <div className="invoice-register-money">
                            {fmt(invoice.amount)} <small>{invoice.currency || 'RSD'}</small>
                          </div>
                          {remaining > 0 && ['unpaid', 'partial'].includes(invoice.status) && (
                            <div className="invoice-register-payment-progress">
                              <div>
                                {tr('settledAmount')}: {fmt(invoice.settled_amount)}
                              </div>
                              <div className="invoice-register-balance">
                                {tr('remainingAmount')}: {fmt(remaining)}
                              </div>
                            </div>
                          )}
                        </td>
                        <td>
                          <StatusBadge tone={tone}>{tr(label)}</StatusBadge>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
          <div className="invoice-register-footer">
            <span>{tr('invoiceRegisterOpenHint')}</span>
            <span aria-live="polite">
              {!loading && !error && `${tr('invoiceRegisterCount')}: ${items.length}`}
            </span>
          </div>
        </div>
      </div>
    </>
  )
}
