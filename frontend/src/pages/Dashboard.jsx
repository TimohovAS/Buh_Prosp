import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { PieChart, Pie, Cell, Tooltip } from 'recharts'
import { api } from '../api'
import { tr } from '../i18n'
import { formatInteger as fmt, formatMoney as fmtCurrency } from '../utils/formatters'

const UI_ARROW = '\u2192'
const UI_WARNING = '\u26A0'
const UI_DAYS = ' \u0434\u043d.'
const UI_SEPARATOR = ' | '

function formatObligationDays(daysUntil, translate) {
  if (daysUntil === 0) return translate('obligationToday')
  if (daysUntil === 1) return translate('obligationTomorrow')
  if (daysUntil < 0) {
    const fn = translate('obligationDaysOverdue')
    return typeof fn === 'function' ? fn(Math.abs(daysUntil)) : `${Math.abs(daysUntil)}${UI_DAYS}`
  }
  const fn = translate('obligationDaysLeft')
  return typeof fn === 'function' ? fn(daysUntil) : `${daysUntil}${UI_DAYS}`
}

function getMetricColor(value, positive = 'var(--color-success)', negative = 'var(--color-danger)') {
  return value >= 0 ? positive : negative
}

function SummaryCard({ title, value, subtitle, tone = 'accent', valueColor, chart = null }) {
  return (
    <div className={`card dashboard-summary-card dashboard-summary-card--${tone}`}>
      <div className="dashboard-summary-row">
        <div className="dashboard-summary-main">
          <div className="card-title">{title}</div>
          <div className="dashboard-summary-value" style={{ color: valueColor || 'var(--color-text)' }}>
            {fmtCurrency(value)}
          </div>
          {subtitle ? <div className="dashboard-summary-note">{subtitle}</div> : null}
        </div>
        {chart ? <div className="dashboard-summary-chart">{chart}</div> : null}
      </div>
    </div>
  )
}

function MoneyNowCard({ value, bankAvailable, bankStatement, cashBalance, pendingWithdrawals }) {
  const hasPendingWithdrawals = Number(pendingWithdrawals || 0) > 0
  return (
    <div className="card dashboard-summary-card dashboard-summary-card--muted">
      <div className="dashboard-summary-row">
        <div className="dashboard-summary-main">
          <div className="card-title">{tr('dashboardMoneyNow')}</div>
          <div className="dashboard-summary-value" style={{ color: getMetricColor(value) }}>
            {fmtCurrency(value)}
          </div>
          <div className="dashboard-money-breakdown">
            <span>
              {tr('dashboardBankAvailable')}: {fmtCurrency(bankAvailable)}
            </span>
            <span>
              {tr('cash')}: {fmtCurrency(cashBalance)}
            </span>
            {hasPendingWithdrawals ? (
              <span className="dashboard-money-pending">
                {tr('cashPendingWithdrawalTotal')}: -{fmtCurrency(pendingWithdrawals)}
              </span>
            ) : null}
            {hasPendingWithdrawals ? (
              <span>
                {tr('dashboardBankStatement')}: {fmtCurrency(bankStatement)}
              </span>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}

function MiniIncomeExpenseDonut({ income, expenses }) {
  const data = [
    { name: tr('income'), value: Number(income ?? 0), color: 'var(--color-success)' },
    { name: tr('expenses'), value: Number(expenses ?? 0), color: 'var(--color-danger)' },
  ].filter((item) => item.value > 0)

  if (data.length === 0) return null

  return (
    <PieChart width={96} height={96}>
      <Pie data={data} cx="50%" cy="50%" innerRadius={28} outerRadius={46} paddingAngle={2} dataKey="value">
        {data.map((entry, index) => (
          <Cell key={index} fill={entry.color} stroke="var(--color-surface)" strokeWidth={1} />
        ))}
      </Pie>
      <Tooltip formatter={(value) => `${fmt(value)} RSD`} />
    </PieChart>
  )
}

function getRiskTone(risk) {
  if (risk === 'high') return 'danger'
  if (risk === 'medium') return 'warning'
  return ''
}

function getAnnualLimitRisk(current, limit, percent, forecast) {
  if (current >= limit || forecast >= limit || percent >= 90) return 'high'
  if (forecast >= limit * 0.9 || percent >= 70) return 'medium'
  return 'low'
}

function getRollingLimitRisk(current, limit, percent) {
  if (current >= limit || percent >= 90) return 'high'
  if (percent >= 75) return 'medium'
  return 'low'
}

function LimitForecastCard({ title, current, limit, percent, risk, forecast = null, estimate = null }) {
  const tone = getRiskTone(risk)
  const cardClass = tone
    ? `card dashboard-limit-card dashboard-limit-card--${tone}`
    : 'card dashboard-limit-card'
  const fillClass = tone
  const percentClass = fillClass ? `dashboard-limit-percent ${fillClass}` : 'dashboard-limit-percent'

  return (
    <div className={cardClass}>
      <div className="card-title">{title}</div>
      <div className="dashboard-limit-head">
        <div className="dashboard-limit-current">
          {fmt(current)} / {fmt(limit)} RSD
        </div>
        <div className={percentClass}>{percent.toFixed(1)}%</div>
      </div>
      <div className="progress-bar">
        <div
          className={`progress-bar-fill ${fillClass}`.trim()}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
      {forecast != null ? (
        <div className="dashboard-summary-note" style={{ marginTop: '0.35rem' }}>
          {tr('forecastYearEnd')}: {fmtCurrency(forecast)}
        </div>
      ) : null}
      {estimate ? (
        <div className="dashboard-summary-note" style={{ marginTop: '0.35rem' }}>
          {tr('estimatedLimitDate')}: {estimate}
        </div>
      ) : null}
    </div>
  )
}

function DashboardAlertCard({ title, items, linkTo, linkLabel, isOverdue, renderItem }) {
  const toneClass = isOverdue ? 'dashboard-alert-card--danger' : 'dashboard-alert-card--warning'
  return (
    <section className={`card dashboard-alert-card ${toneClass}`}>
      <div className="dashboard-alert-head">
        <div className="dashboard-alert-title">{title}</div>
        <Link to={linkTo} className="btn btn-primary btn-sm dashboard-alert-link">
          {linkLabel} {UI_ARROW}
        </Link>
      </div>
      <div className="dashboard-alert-list">{items.map(renderItem)}</div>
    </section>
  )
}

export default function Dashboard() {
  const location = useLocation()
  const isActivePage = location.pathname === '/'
  const [data, setData] = useState(null)
  const [limits, setLimits] = useState(null)
  const [receivables, setReceivables] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!isActivePage) return
    Promise.all([api.dashboard(), api.finance.limits(), api.finance.ar()])
      .then(([dashboardResponse, limitsResponse, arResponse]) => {
        setData(dashboardResponse)
        setLimits(limitsResponse)
        setReceivables(arResponse)
        setError(null)
      })
      .catch((err) => {
        setError(err.message)
        console.error(err)
      })
      .finally(() => setLoading(false))
  }, [isActivePage])

  if (loading) return <div style={{ padding: '2rem', textAlign: 'center' }}>{tr('loading')}</div>
  if (!data)
    return (
      <div style={{ padding: '2rem', color: 'var(--color-danger)' }}>
        {tr('loadError')}
        {error ? `: ${error}` : ''}
      </div>
    )

  const lim = data.income_limit_status
  const limitsData = limits || {
    annual_total: lim.year_income,
    annual_limit: lim.limit_6m,
    annual_percent: lim.percent_6m,
    rolling_12_total: lim.income_12m,
    vat_limit: lim.limit_8m,
    vat_percent: lim.percent_8m,
    forecast_year_end: lim.year_income,
    estimated_limit_date: null,
    risk: lim.exceeded_6m || lim.exceeded_8m ? 'high' : lim.warning_6m || lim.warning_8m ? 'medium' : 'low',
  }
  const annualRisk = getAnnualLimitRisk(
    limitsData.annual_total,
    limitsData.annual_limit,
    limitsData.annual_percent,
    limitsData.forecast_year_end ?? limitsData.annual_total
  )
  const rollingRisk = getRollingLimitRisk(
    limitsData.rolling_12_total,
    limitsData.vat_limit,
    limitsData.vat_percent
  )
  const upcomingPlannedExpenses = data.upcoming_planned_expenses || []
  const upcomingUnpaidObligations = data.upcoming_unpaid_obligations || []
  const hasUpcomingPlannedExpenses = upcomingPlannedExpenses.length > 0
  const hasUpcomingUnpaidObligations = upcomingUnpaidObligations.length > 0
  const plannedExpensesOverdue = upcomingPlannedExpenses.some((item) => item.status === 'overdue')
  const obligationsOverdue = upcomingUnpaidObligations.some((item) => item.status === 'overdue')

  const arTotals = receivables?.totals || { ar_total: 0, ar_overdue: 0 }
  // Просроченные сверху (самые старые первыми), затем ближайшие по сроку.
  const topReceivables = [...(receivables?.items || [])]
    .sort((a, b) => {
      const aOverdue = a.days_overdue > 0
      const bOverdue = b.days_overdue > 0
      if (aOverdue !== bOverdue) return aOverdue ? -1 : 1
      if (aOverdue) return b.days_overdue - a.days_overdue
      return (a.due_date || '').localeCompare(b.due_date || '')
    })
    .slice(0, 7)
  const unpaidIncoming = data.unpaid_incoming_invoices || []
  const bankStatementBalance = Number(data.balance_all_time ?? 0)
  const pendingCashWithdrawals = Number(data.pending_cash_withdrawal_total ?? 0)
  const bankAvailableBalance = Number(
    data.available_bank_balance ?? bankStatementBalance - pendingCashWithdrawals
  )
  const cashRegisterBalance = Number(data.cash_register_balance ?? 0)
  const moneyNow = Number(data.available_money_now ?? bankAvailableBalance + cashRegisterBalance)

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('dashboard')}</h1>
      </div>

      <div className="page-body">
        <div className="dashboard-summary-grid">
          <SummaryCard
            title={tr('balanceMonth')}
            value={data.balance_month}
            valueColor={getMetricColor(data.balance_month)}
            tone="accent"
            subtitle={`${tr('monthIncome')}: ${fmtCurrency(data.month_income)}${UI_SEPARATOR}${tr('monthExpenses')}: ${fmtCurrency(data.month_expenses)}`}
            chart={<MiniIncomeExpenseDonut income={data.month_income} expenses={data.month_expenses} />}
          />
          <SummaryCard
            title={tr('balanceYear')}
            value={data.balance_year}
            valueColor={getMetricColor(data.balance_year)}
            tone="success"
            subtitle={`${tr('yearIncome')}: ${fmtCurrency(data.year_income)}${UI_SEPARATOR}${tr('yearExpenses')}: ${fmtCurrency(data.year_expenses)}`}
            chart={<MiniIncomeExpenseDonut income={data.year_income} expenses={data.year_expenses} />}
          />
          <MoneyNowCard
            value={moneyNow}
            bankAvailable={bankAvailableBalance}
            bankStatement={bankStatementBalance}
            cashBalance={cashRegisterBalance}
            pendingWithdrawals={pendingCashWithdrawals}
          />
          <div className="card dashboard-summary-card dashboard-summary-card--warning">
            <div className="card-title">{tr('plannedUntilMonthEnd')}</div>
            <div className="dashboard-summary-label">
              {tr('plannedExpenses')} + {tr('payments')}
            </div>
            <div className="dashboard-summary-value" style={{ color: 'var(--color-warning)' }}>
              {fmtCurrency(data.planned_expenses_until_month_end)}
            </div>
            <div className="dashboard-summary-links">
              <Link to="/planned-expenses" className="dashboard-link">
                {tr('plannedExpenses')} {UI_ARROW}
              </Link>
              <Link to="/payments" className="dashboard-link">
                {tr('goToPayments')} {UI_ARROW}
              </Link>
            </div>
          </div>
        </div>

        <div className="dashboard-limits-grid">
          <LimitForecastCard
            title={`${tr('limit6m')} (6M RSD)`}
            current={limitsData.annual_total}
            limit={limitsData.annual_limit}
            percent={limitsData.annual_percent}
            risk={annualRisk}
            forecast={limitsData.forecast_year_end}
            estimate={limitsData.estimated_limit_date}
          />
          <LimitForecastCard
            title={`${tr('limit8m')} (${tr('limitMonths12')})`}
            current={limitsData.rolling_12_total}
            limit={limitsData.vat_limit}
            percent={limitsData.vat_percent}
            risk={rollingRisk}
          />
        </div>

        {(hasUpcomingPlannedExpenses || hasUpcomingUnpaidObligations) && (
          <div className="dashboard-alert-grid">
            {hasUpcomingPlannedExpenses ? (
              <DashboardAlertCard
                title={
                  plannedExpensesOverdue
                    ? `${UI_WARNING} ${tr('obligationsOverdue')} | ${tr('plannedExpenses')}`
                    : `${UI_WARNING} ${tr('obligationsDueSoon')} | ${tr('plannedExpenses')}`
                }
                items={upcomingPlannedExpenses}
                isOverdue={plannedExpensesOverdue}
                linkTo="/planned-expenses"
                linkLabel={tr('plannedExpenses')}
                renderItem={(item, index) => (
                  <div
                    className="dashboard-alert-row"
                    key={`${item.planned_expense_id}-${item.due_date}-${index}`}
                  >
                    <span className="dashboard-alert-main">
                      <strong>{item.name}</strong> | {fmt(item.amount)} {item.currency}
                      <span className="dashboard-alert-date">
                        ({item.due_date.split('-').reverse().join('.')})
                      </span>
                    </span>
                    <span className={`dashboard-alert-days${item.status === 'overdue' ? ' danger' : ''}`}>
                      {item.status === 'overdue' ? `${tr('obligationsOverdue')} ` : ''}
                      {formatObligationDays(item.days_until, tr)}
                    </span>
                  </div>
                )}
              />
            ) : null}

            {hasUpcomingUnpaidObligations ? (
              <DashboardAlertCard
                title={
                  obligationsOverdue
                    ? `${UI_WARNING} ${tr('obligationsOverdue')}`
                    : `${UI_WARNING} ${tr('obligationsDueSoon')}`
                }
                items={upcomingUnpaidObligations}
                isOverdue={obligationsOverdue}
                linkTo="/payments"
                linkLabel={tr('goToPayments')}
                renderItem={(item) => (
                  <div className="dashboard-alert-row" key={item.id}>
                    <span className="dashboard-alert-main">
                      <strong>{item.payment_type_name}</strong> | {fmt(item.amount)} RSD
                      <span className="dashboard-alert-date">
                        ({item.deadline.split('-').reverse().join('.')})
                      </span>
                    </span>
                    <span className={`dashboard-alert-days${item.status === 'overdue' ? ' danger' : ''}`}>
                      {item.status === 'overdue' ? `${tr('obligationsOverdue')} ` : ''}
                      {formatObligationDays(item.days_until, tr)}
                    </span>
                  </div>
                )}
              />
            ) : null}
          </div>
        )}

        <div className="dashboard-debts-grid">
          <div className="card">
            <div className="dashboard-alert-head">
              <div className="card-title" style={{ marginBottom: 0 }}>
                {tr('dashboardArTitle')}
              </div>
              <Link to="/finance/ar" className="btn btn-primary btn-sm dashboard-alert-link">
                {tr('financeAR')} {UI_ARROW}
              </Link>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{tr('client')}</th>
                    <th>{tr('invoiceNumber')}</th>
                    <th>{tr('dashboardDueDate')}</th>
                    <th style={{ textAlign: 'right' }}>{tr('bankTxAllocationRemaining')}</th>
                    <th style={{ textAlign: 'right' }}>{tr('obligationsOverdue')}</th>
                  </tr>
                </thead>
                <tbody>
                  {topReceivables.length === 0 ? (
                    <tr>
                      <td colSpan={5} style={{ color: 'var(--color-text-muted)' }}>
                        {tr('noRecords')}
                      </td>
                    </tr>
                  ) : (
                    topReceivables.map((item) => (
                      <tr key={item.income_id}>
                        <td>{item.client_name || '-'}</td>
                        <td>{item.invoice_number}</td>
                        <td>{item.due_date ? item.due_date.split('-').reverse().join('.') : '-'}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(item.amount)}</td>
                        <td
                          style={{
                            textAlign: 'right',
                            color: item.days_overdue > 0 ? 'var(--color-danger)' : 'var(--color-text-muted)',
                            fontWeight: item.days_overdue > 0 ? 600 : 400,
                          }}
                        >
                          {item.days_overdue > 0 ? `${item.days_overdue}${UI_DAYS}` : '-'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="dashboard-debts-totals">
              <span>
                {tr('total')}: <strong>{fmtCurrency(arTotals.ar_total)}</strong>
              </span>
              <span style={{ color: arTotals.ar_overdue > 0 ? 'var(--color-danger)' : 'inherit' }}>
                {tr('obligationsOverdue')}: <strong>{fmtCurrency(arTotals.ar_overdue)}</strong>
              </span>
            </div>
          </div>

          <div className="card">
            <div className="dashboard-alert-head">
              <div className="card-title" style={{ marginBottom: 0 }}>
                {tr('dashboardApTitle')}
              </div>
              <Link to="/incoming-invoices" className="btn btn-primary btn-sm dashboard-alert-link">
                {tr('incomingInvoices')} {UI_ARROW}
              </Link>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{tr('counterpartyName')}</th>
                    <th>{tr('invoiceNumber')}</th>
                    <th>{tr('date')}</th>
                    <th style={{ textAlign: 'right' }}>{tr('bankTxAllocationRemaining')}</th>
                  </tr>
                </thead>
                <tbody>
                  {unpaidIncoming.length === 0 ? (
                    <tr>
                      <td colSpan={4} style={{ color: 'var(--color-text-muted)' }}>
                        {tr('noRecords')}
                      </td>
                    </tr>
                  ) : (
                    unpaidIncoming.map((item) => (
                      <tr key={item.id}>
                        <td>{item.counterparty_name}</td>
                        <td>{item.invoice_number}</td>
                        <td>{item.date ? item.date.split('-').reverse().join('.') : '-'}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(item.remaining)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="dashboard-debts-totals">
              <span>
                {tr('total')}: <strong>{fmtCurrency(data.unpaid_incoming_total ?? 0)}</strong>
              </span>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
