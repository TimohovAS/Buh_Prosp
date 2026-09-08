import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import SortIndicator from '../components/SortIndicator'
import { formatDateSr, formatMoney2, localDateIso } from '../utils/formatters'
import { selectReceivables, receivablesTotal } from '../utils/receivables'
import useFinanceData from '../hooks/useFinanceData'
import {
  FinanceFrame,
  FinanceMetric,
  FinanceStatus,
  FinanceSection,
  FinanceNote,
  InvoiceLink,
} from '../components/finance/FinanceUI'

const AGING = {
  not_due: 'reportNotDue',
  '1_30': 'reportAge1',
  '31_60': 'reportAge31',
  '61_90': 'reportAge61',
  over_90: 'reportAge90',
  no_due: 'reportNoDue',
}
const COLUMNS = {
  invoice_number: 'invoiceNumber',
  client_name: 'client',
  due_date: 'reportDueDate',
  amount_full: 'reportInvoiceAmount',
  amount_paid: 'reportPaidToDate',
  amount: 'reportRemaining',
  days_overdue: 'financeDaysOverdue',
}

export default function AccountsReceivable() {
  const location = useLocation()
  const today = localDateIso()
  const [asOf, setAsOf] = useState(location.state?.asOf || today)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState({ column: 'days_overdue', ascending: false })
  useEffect(() => {
    if (location.state?.asOf) setAsOf(location.state.asOf)
  }, [location.key, location.state?.asOf])
  const validation = !asOf ? 'reportChooseAsOf' : asOf > today ? 'cashflowFutureRange' : ''
  const load = useCallback(() => api.finance.ar({ as_of: asOf }), [asOf])
  const report = useFinanceData(location.pathname === '/finance/ar' && !validation, asOf, load)
  const data = report.data
  const rows = useMemo(
    () => selectReceivables(data?.items || [], filter, search, sort.column, sort.ascending),
    [data, filter, search, sort]
  )
  const totals = data?.totals
  const toggleSort = (column) =>
    setSort((value) => ({
      column,
      ascending:
        value.column === column
          ? !value.ascending
          : !['amount', 'amount_full', 'amount_paid', 'days_overdue'].includes(column),
    }))
  return (
    <FinanceFrame title={tr('financeAR')} subtitle={tr('reportArSubtitle')} badge={tr('reportDebtRegister')}>
      <div className="card finance-control-row">
        <div className="finance-as-of">
          <label htmlFor="ar-as-of">{tr('reportAsOf')}</label>
          <DatePicker id="ar-as-of" value={asOf} onChange={setAsOf} maxDate={new Date(`${today}T12:00:00`)} />
        </div>
        <div className="finance-buttons">
          <button className="btn btn-secondary btn-sm" onClick={() => setAsOf(today)}>
            {tr('reportToday')}
          </button>
          <button
            className="btn btn-secondary btn-sm"
            disabled={report.pending || !!validation}
            onClick={report.reload}
          >
            {tr('reportRefresh')}
          </button>
        </div>
        <span className="finance-muted">{tr('reportDebtDateHint')}</span>
      </div>
      <FinanceStatus {...report} validation={validation} />
      {!validation && !report.pending && data && (
        <>
          <div className="finance-metrics">
            <FinanceMetric
              title={tr('reportOutstanding')}
              value={totals.ar_total}
              note={tr('reportInvoiceCount', { count: totals.invoice_count })}
            />
            <FinanceMetric
              title={tr('reportOverdue')}
              value={totals.ar_overdue}
              tone={totals.ar_overdue > 0 ? 'negative' : ''}
              note={tr('reportOverdueCount', { count: totals.overdue_count })}
            />
            <FinanceMetric
              title={tr('reportNotDue')}
              value={totals.ar_not_due}
              tone="positive"
              note={tr('reportNotDueHint')}
            />
            <FinanceMetric
              title={tr('reportNoDue')}
              value={totals.ar_without_due_date}
              tone={totals.ar_without_due_date > 0 ? 'warning' : ''}
              note={tr('reportNoDueHint')}
            />
          </div>
          {data.missing_payment_dates > 0 && (
            <FinanceNote warning>
              {tr('reportUndatedPayments', { count: data.missing_payment_dates })}
            </FinanceNote>
          )}
          {data.items.length > 0 ? (
            <>
              <FinanceSection title={tr('reportAgingTitle')} note={tr('reportAgingHint')}>
                <div className="finance-aging">
                  {data.aging.map((bucket) => (
                    <button
                      key={bucket.key}
                      aria-pressed={filter === bucket.key}
                      onClick={() => setFilter((value) => (value === bucket.key ? 'all' : bucket.key))}
                    >
                      <span className="finance-muted">{tr(AGING[bucket.key])}</span>
                      <strong
                        className={
                          ['1_30', '31_60', '61_90', 'over_90'].includes(bucket.key) &&
                          Number(bucket.amount) > 0
                            ? 'negative'
                            : ''
                        }
                      >
                        {formatMoney2(bucket.amount)} <small>RSD</small>
                      </strong>
                      <span className="finance-muted">
                        {tr('reportInvoiceCount', { count: bucket.count })}
                      </span>
                    </button>
                  ))}
                </div>
              </FinanceSection>
              <FinanceSection
                title={tr('reportInvoicesToCollect')}
                note={tr('reportArTableNote', { date: formatDateSr(asOf) })}
              >
                <div className="finance-ar-toolbar">
                  <div className="finance-buttons">
                    {['all', 'overdue'].map((key) => (
                      <button
                        className={`btn btn-sm ${filter === key ? 'btn-primary' : 'btn-secondary'}`}
                        key={key}
                        aria-pressed={filter === key}
                        onClick={() => setFilter(key)}
                      >
                        {tr(key === 'all' ? 'reportAllInvoices' : 'arFilterOverdue')}
                      </button>
                    ))}
                    {!['all', 'overdue'].includes(filter) && (
                      <span className="finance-tag">{tr(AGING[filter])}</span>
                    )}
                  </div>
                  <input
                    className="form-input finance-search"
                    aria-label={tr('reportSearchInvoices')}
                    placeholder={tr('reportSearchInvoices')}
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <p className="finance-muted">
                  {tr('reportFilteredTotal', {
                    count: rows.length,
                    amount: `${formatMoney2(receivablesTotal(rows))} RSD`,
                  })}
                </p>
                <div className="table-wrap finance-table">
                  <table>
                    <thead>
                      <tr>
                        {Object.entries(COLUMNS).map(([key, title]) => (
                          <th
                            key={key}
                            scope="col"
                            className={key.startsWith('amount') || key === 'days_overdue' ? 'numeric' : ''}
                            aria-sort={
                              sort.column === key ? (sort.ascending ? 'ascending' : 'descending') : 'none'
                            }
                          >
                            <button className="finance-sort" onClick={() => toggleSort(key)}>
                              {tr(title)}
                              <SortIndicator active={sort.column === key} asc={sort.ascending} />
                            </button>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.length === 0 ? (
                        <tr>
                          <td colSpan={7}>
                            <div className="finance-empty">
                              {tr('reportNoMatches')}
                              <p>
                                <button
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => {
                                    setFilter('all')
                                    setSearch('')
                                  }}
                                >
                                  {tr('reportResetFilters')}
                                </button>
                              </p>
                            </div>
                          </td>
                        </tr>
                      ) : (
                        rows.map((item) => (
                          <tr key={item.income_id}>
                            <td>
                              <InvoiceLink item={item} />
                              <small className="finance-muted">{formatDateSr(item.issued_date)}</small>
                            </td>
                            <td>
                              {item.client_name || '—'}
                              {item.status === 'partial' && (
                                <small className="finance-muted">{tr('reportPartPaid')}</small>
                              )}
                            </td>
                            <td>
                              {item.due_date ? (
                                formatDateSr(item.due_date)
                              ) : (
                                <span className="warning">{tr('reportNoDue')}</span>
                              )}
                            </td>
                            <td className="numeric">{formatMoney2(item.amount_full)}</td>
                            <td className="numeric">{formatMoney2(item.amount_paid)}</td>
                            <td className={`numeric ${Number(item.days_overdue) > 0 ? 'negative' : ''}`}>
                              <strong>{formatMoney2(item.amount)}</strong>
                            </td>
                            <td className={`numeric ${Number(item.days_overdue) > 0 ? 'negative' : ''}`}>
                              {item.days_overdue == null
                                ? '—'
                                : item.days_overdue > 0
                                  ? `${item.days_overdue} ${tr('days')}`
                                  : tr('reportOnTime')}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                    {rows.length > 0 && (
                      <tfoot>
                        <tr>
                          <th scope="row" colSpan={5}>
                            {tr('reportFilteredFooter')}
                          </th>
                          <td className="numeric">{formatMoney2(receivablesTotal(rows))}</td>
                          <td />
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
              </FinanceSection>
            </>
          ) : (
            <div className="card finance-empty">
              <strong>{tr('reportNoDebt')}</strong>
              <p>{tr('reportNoDebtHint', { date: formatDateSr(asOf) })}</p>
            </div>
          )}
          <details className="finance-method">
            <summary>{tr('reportArHowCalculated')}</summary>
            <p>{tr('reportArMethod')}</p>
          </details>
        </>
      )}
    </FinanceFrame>
  )
}
