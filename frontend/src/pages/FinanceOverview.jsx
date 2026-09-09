import { useCallback, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr, getMonthNamesShort } from '../i18n'
import { formatDateSr, formatMoney2 } from '../utils/formatters'
import useFinanceData from '../hooks/useFinanceData'
import useFinancePeriod from '../hooks/useFinancePeriod'
import {
  FinanceFrame,
  FinancePeriodControls,
  FinanceStatus,
  FinanceSection,
  FinanceNote,
  FinanceChart,
  InvoiceLink,
} from '../components/finance/FinanceUI'

export default function FinanceOverview() {
  const { pathname } = useLocation()
  const period = useFinancePeriod()
  const { from, to, groupBy } = period
  const [mode, setMode] = useState('both')
  const load = useCallback(async () => {
    const [summary, ar, limits] = await Promise.all([
      api.finance.summary({ from, to, group_by: groupBy, mode }),
      api.finance.ar({ as_of: to }),
      api.finance.limits({ as_of: to }),
    ])
    return { summary, ar, limits }
  }, [from, to, groupBy, mode])
  const report = useFinanceData(
    pathname === '/finance' && !period.validation,
    `${from}/${to}/${groupBy}/${mode}`,
    load
  )
  const data = report.data
  const methods = mode === 'both' ? ['accrual', 'cash'] : [mode]
  const methodLabels = { accrual: 'reportByDocuments', cash: 'reportByPayments', both: 'reportCompare' }
  const overdue =
    data?.ar.items
      .filter((item) => Number(item.days_overdue) > 0)
      .sort((a, b) => b.days_overdue - a.days_overdue || Number(b.amount) - Number(a.amount))
      .slice(0, 5) || []
  const periodLabel = (key) =>
    key.length === 7
      ? `${getMonthNamesShort()[Number(key.slice(5, 7)) - 1]} ${key.slice(0, 4)}`
      : key.length === 10
        ? formatDateSr(key)
        : key
  return (
    <FinanceFrame
      title={tr('financeOverview')}
      subtitle={tr('reportOverviewSubtitle')}
      badge={tr('cashflowActualOnly')}
    >
      <FinancePeriodControls value={period}>
        <div className="finance-control-row finance-mode-control">
          <div className="finance-buttons">
            {Object.entries(methodLabels).map(([key, label]) => (
              <button
                key={key}
                className={`btn btn-sm ${mode === key ? 'btn-primary' : 'btn-secondary'}`}
                aria-pressed={mode === key}
                onClick={() => setMode(key)}
              >
                {tr(label)}
              </button>
            ))}
          </div>
        </div>
      </FinancePeriodControls>
      <FinanceStatus {...report} validation={period.validation} />
      {!period.validation && !report.pending && data && (
        <>
          <div
            className={
              methods.length === 2
                ? 'finance-two-columns finance-overview-methods'
                : 'finance-overview-methods'
            }
          >
            {methods.map((method) => {
              const totals = data.summary.totals
              const revenue = Number(totals[`revenue_${method}`])
              const expenses = Number(totals[`expense_${method}`])
              const net = Number(totals[`net_profit_${method}`])
              const rows = data.summary.series.map((row) => ({
                label: periodLabel(row.period),
                revenue: Number(row[`revenue_${method}`]),
                expenses: Number(row[`expense_${method}`]),
              }))
              return (
                <FinanceSection
                  key={method}
                  title={tr(methodLabels[method])}
                  note={tr(method === 'cash' ? 'reportCashBasis' : 'reportAccrualBasis')}
                >
                  <dl className="finance-summary-values">
                    <div>
                      <dt>{tr(method === 'cash' ? 'reportReceived' : 'reportRevenue')}</dt>
                      <dd className="positive">
                        {formatMoney2(revenue)} <small>RSD</small>
                      </dd>
                    </div>
                    <div>
                      <dt>{tr(method === 'cash' ? 'reportPaid' : 'reportAllExpenses')}</dt>
                      <dd className="negative">
                        {formatMoney2(expenses)} <small>RSD</small>
                      </dd>
                    </div>
                    <div className="finance-summary-result">
                      <dt>{tr(method === 'cash' ? 'reportOperatingCash' : 'reportNetProfit')}</dt>
                      <dd className={net < 0 ? 'negative' : 'positive'}>
                        {formatMoney2(net)} <small>RSD</small>
                      </dd>
                    </div>
                  </dl>
                  <p className="finance-muted">
                    {tr('reportTaxesIncluded', { amount: `${formatMoney2(totals[`taxes_${method}`])} RSD` })}
                  </p>
                  {rows.some((row) => row.revenue || row.expenses) ? (
                    <FinanceChart
                      data={rows}
                      series={[
                        {
                          key: 'revenue',
                          name: tr(method === 'cash' ? 'reportReceived' : 'reportRevenue'),
                          color: '#34d399',
                        },
                        {
                          key: 'expenses',
                          name: tr(method === 'cash' ? 'reportPaid' : 'reportAllExpenses'),
                          color: '#fb7185',
                        },
                      ]}
                    />
                  ) : (
                    <div className="finance-empty">{tr('reportNoActivity')}</div>
                  )}
                  <div className="finance-equation">
                    {tr(method === 'cash' ? 'reportCashEquation' : 'reportProfitEquation')}
                  </div>
                </FinanceSection>
              )
            })}
          </div>
          <div className="finance-overview-bottom">
            <FinanceSection
              title={tr('reportDebtSnapshot', { date: formatDateSr(to) })}
              note={tr('reportDebtSnapshotHint')}
              action={
                <Link className="btn btn-secondary btn-sm" to="/finance/ar" state={{ asOf: to }}>
                  {tr('reportAllDebts')}
                </Link>
              }
            >
              <div className="finance-debt-summary">
                <span>
                  {tr('reportOutstanding')}: <strong>{formatMoney2(data.ar.totals.ar_total)} RSD</strong>
                </span>
                <span>
                  {tr('reportOverdue')}:{' '}
                  <strong className="negative">{formatMoney2(data.ar.totals.ar_overdue)} RSD</strong>
                </span>
              </div>
              {overdue.length > 0 ? (
                <div className="table-wrap finance-table">
                  <table>
                    <thead>
                      <tr>
                        <th>{tr('invoiceNumber')}</th>
                        <th>{tr('client')}</th>
                        <th>{tr('reportDueDate')}</th>
                        <th className="numeric">{tr('reportRemaining')}</th>
                        <th className="numeric">{tr('financeDaysOverdue')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overdue.map((item) => (
                        <tr key={item.income_id}>
                          <td>
                            <InvoiceLink item={item} />
                          </td>
                          <td>{item.client_name || '—'}</td>
                          <td>{formatDateSr(item.due_date)}</td>
                          <td className="numeric">{formatMoney2(item.amount)}</td>
                          <td className="numeric negative">
                            {item.days_overdue} {tr('days')}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="finance-muted">{tr('financeNoOverdue')}</p>
              )}
              {data.ar.totals.ar_without_due_date > 0 && (
                <p className="finance-muted">
                  {tr('reportNoDueAmount', {
                    amount: `${formatMoney2(data.ar.totals.ar_without_due_date)} RSD`,
                  })}
                </p>
              )}
              {data.ar.missing_payment_dates > 0 && (
                <FinanceNote warning>
                  {tr('reportUndatedPayments', { count: data.ar.missing_payment_dates })}
                </FinanceNote>
              )}
            </FinanceSection>
            <FinanceSection
              title={tr('financeLimits')}
              note={tr('reportLimitsAsOf', { date: formatDateSr(to) })}
            >
              <div className="finance-two-columns">
                {[
                  {
                    label: 'limit6m',
                    amount: data.limits.annual_total,
                    limit: data.limits.annual_limit,
                    percent: data.limits.annual_percent,
                    note: tr('reportAnnualRange', { year: to.slice(0, 4) }),
                  },
                  {
                    label: 'limit8m',
                    amount: data.limits.rolling_12_total,
                    limit: data.limits.vat_limit,
                    percent: data.limits.vat_percent,
                    note: tr('reportRollingRange'),
                  },
                ].map((limit) => (
                  <div key={limit.label}>
                    <div className="finance-muted">
                      {tr(limit.label)} · {limit.note}
                    </div>
                    <div className="finance-limit-value">
                      {formatMoney2(limit.amount)} <small>/ {formatMoney2(limit.limit)} RSD</small>
                    </div>
                    <div
                      className={`finance-limit-progress ${limit.percent >= 90 ? 'negative' : limit.percent >= 70 ? 'warning' : 'positive'}`}
                      role="progressbar"
                      aria-label={tr(limit.label)}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.min(100, Math.max(0, limit.percent))}
                    >
                      <div style={{ width: `${Math.min(100, Math.max(0, limit.percent))}%` }} />
                    </div>
                    <span className="finance-muted">
                      {Number(limit.percent).toFixed(1)}% ·{' '}
                      {tr(Number(limit.amount) > limit.limit ? 'reportExceededBy' : 'reportRemainingLimit', {
                        amount: `${formatMoney2(Math.abs(limit.limit - Number(limit.amount)))} RSD`,
                      })}
                    </span>
                  </div>
                ))}
              </div>
              <details className="finance-method">
                <summary>{tr('reportForecastTitle')}</summary>
                <p>
                  {tr('reportForecastValue', {
                    average: `${formatMoney2(data.limits.average_monthly_income)} RSD`,
                    forecast: `${formatMoney2(data.limits.forecast_year_end)} RSD`,
                  })}
                </p>
                <p>{tr('reportForecastHint')}</p>
              </details>
            </FinanceSection>
          </div>
          <details className="finance-method">
            <summary>{tr('reportAbout')}</summary>
            <p>
              {tr('reportModeHint')} {tr('reportCompareNote')}{' '}
              <Link to="/finance/cashflow">{tr('cashflowTitle')}</Link>
            </p>
          </details>
        </>
      )}
    </FinanceFrame>
  )
}
