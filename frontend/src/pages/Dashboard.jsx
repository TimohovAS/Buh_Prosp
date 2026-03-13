import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts'
import { api } from '../api'
import { tr } from '../i18n'

const UI_ARROW = '\u2192'
const UI_WARNING = '\u26A0'
const UI_DAYS = ' \u0434\u043d.'
const UI_SEPARATOR = ' | '

function fmt(n) {
  return (n ?? 0).toLocaleString('sr-RS')
}

function fmtCurrency(n) {
  return `${fmt(n)} RSD`
}

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

function SummaryCard({ title, value, subtitle, tone = 'accent', valueColor }) {
  return (
    <div className={`card dashboard-summary-card dashboard-summary-card--${tone}`}>
      <div className="card-title">{title}</div>
      <div className="dashboard-summary-value" style={{ color: valueColor || 'var(--color-text)' }}>
        {fmtCurrency(value)}
      </div>
      {subtitle ? <div className="dashboard-summary-note">{subtitle}</div> : null}
    </div>
  )
}

function getRiskTone(risk) {
  if (risk === 'high') return 'danger'
  if (risk === 'medium') return 'warning'
  return ''
}

function LimitForecastCard({ title, current, limit, percent, risk, note, forecast, estimate }) {
  const fillClass = getRiskTone(risk)
  const percentClass = fillClass ? `dashboard-limit-percent ${fillClass}` : 'dashboard-limit-percent'

  return (
    <div className="card dashboard-limit-card">
      <div className="card-title">{title}</div>
      <div className="dashboard-limit-head">
        <div className="dashboard-limit-current">{fmt(current)} / {fmt(limit)} RSD</div>
        <div className={percentClass}>{percent.toFixed(1)}%</div>
      </div>
      <div className="progress-bar">
        <div
          className={`progress-bar-fill ${fillClass}`.trim()}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
      <div className="dashboard-summary-note" style={{ marginTop: '0.75rem' }}>
        {note}
      </div>
      <div className="dashboard-summary-note" style={{ marginTop: '0.35rem' }}>
        {tr('forecastYearEnd')}: {fmtCurrency(forecast)}
      </div>
      {estimate ? (
        <div className="dashboard-summary-note" style={{ marginTop: '0.35rem' }}>
          {tr('estimatedLimitDate')}: {estimate}
        </div>
      ) : null}
    </div>
  )
}

function IncomeExpensePie({ title, income, expenses, onExpensesClick }) {
  const data = [
    { name: tr('income'), value: income ?? 0, color: 'var(--color-success)' },
    { name: tr('expenses'), value: expenses ?? 0, color: 'var(--color-danger)' },
  ].filter((item) => item.value > 0)

  if (data.length === 0) {
    return (
      <section className="dashboard-pie-card" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div className="dashboard-pie-title">{title}</div>
        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>{tr('noData')}</div>
      </section>
    )
  }

  return (
    <section className="dashboard-pie-card">
      <div className="dashboard-pie-title">{title}</div>
      <div style={{ flex: 1, minHeight: 180 }}>
        <ResponsiveContainer width="100%" height={180}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={42}
              outerRadius={70}
              paddingAngle={2}
              dataKey="value"
            >
              {data.map((entry, index) => (
                <Cell key={index} fill={entry.color} stroke="var(--color-surface)" strokeWidth={1} />
              ))}
            </Pie>
            <Tooltip formatter={(value) => `${fmt(value)} RSD`} />
            <Legend formatter={(value, entry) => `${value}: ${fmt(entry?.payload?.value ?? 0)} RSD`} />
          </PieChart>
        </ResponsiveContainer>
      </div>

    </section>
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [limits, setLimits] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([api.dashboard(), api.finance.limits()])
      .then(([dashboardResponse, limitsResponse]) => {
        setData(dashboardResponse)
        setLimits(limitsResponse)
        setError(null)
      })
      .catch((err) => {
        setError(err.message)
        console.error(err)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ padding: '2rem', textAlign: 'center' }}>{tr('loading')}</div>
  if (!data) return <div style={{ padding: '2rem', color: 'var(--color-danger)' }}>{tr('loadError')}{error ? `: ${error}` : ''}</div>

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
          />
          <SummaryCard
            title={tr('balanceYear')}
            value={data.balance_year}
            valueColor={getMetricColor(data.balance_year)}
            tone="success"
            subtitle={`${tr('yearIncome')}: ${fmtCurrency(data.year_income)}${UI_SEPARATOR}${tr('yearExpenses')}: ${fmtCurrency(data.year_expenses)}`}
          />
          <SummaryCard
            title={tr('balanceAllTime')}
            value={data.balance_all_time}
            valueColor={getMetricColor(data.balance_all_time)}
            tone="muted"
            subtitle={`(${tr('financialResult')}: ${fmtCurrency(data.financial_result_all_time)})`}
          />
          <div className="card dashboard-summary-card dashboard-summary-card--warning">
            <div className="card-title">{tr('plannedUntilMonthEnd')}</div>
            <div className="dashboard-summary-label">{tr('plannedExpenses')} + {tr('payments')}</div>
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

        <div className="dashboard-visual-grid">
          <div className="card dashboard-pies-panel">
            <div className="dashboard-pies-grid">
              <IncomeExpensePie
                title={`${tr('monthIncome')} / ${tr('monthExpenses')}`}
                income={data.month_income}
                expenses={data.month_expenses}
              />
              <IncomeExpensePie
                title={`${tr('yearIncome')} / ${tr('yearExpenses')}`}
                income={data.year_income}
                expenses={data.year_expenses}
                onExpensesClick
              />
            </div>
          </div>

          <div className="dashboard-limit-stack">
            <LimitForecastCard
              title={`${tr('limit6m')} (6M RSD)`}
              current={limitsData.annual_total}
              limit={limitsData.annual_limit}
              percent={limitsData.annual_percent}
              risk={limitsData.risk}
              note={tr('limitsAccrualNote')}
              forecast={limitsData.forecast_year_end}
              estimate={limitsData.estimated_limit_date}
            />
            <LimitForecastCard
              title={`${tr('limit8m')} (${tr('limitMonths12')})`}
              current={limitsData.rolling_12_total}
              limit={limitsData.vat_limit}
              percent={limitsData.vat_percent}
              risk={limitsData.risk}
              note={tr('limitsAccrualNote')}
              forecast={limitsData.forecast_year_end}
              estimate={limitsData.estimated_limit_date}
            />
          </div>
        </div>

        {limitsData.risk !== 'low' && (
          <div
            className="card"
            style={{
              borderColor: limitsData.risk === 'high' ? 'var(--color-danger)' : 'var(--color-warning)',
              marginBottom: '2rem',
            }}
          >
            {(limitsData.risk === 'high') ? (
              <p style={{ margin: 0, color: 'var(--color-danger)' }}>
                {tr('limitRiskHigh')}
              </p>
            ) : (
              <p style={{ margin: 0, color: 'var(--color-warning)' }}>
                {tr('limitRiskMedium')}
              </p>
            )}
          </div>
        )}

        {data.upcoming_planned_expenses && data.upcoming_planned_expenses.length > 0 && (
          <div
            className="card"
            style={{
              marginBottom: '2rem',
              borderColor: data.upcoming_planned_expenses.some((item) => item.status === 'overdue')
                ? 'var(--color-danger)'
                : 'var(--color-warning)',
              borderWidth: 1,
              borderStyle: 'solid',
            }}
          >
            <div className="card-title" style={{ color: data.upcoming_planned_expenses.some((item) => item.status === 'overdue') ? 'var(--color-danger)' : 'var(--color-warning)' }}>
              {data.upcoming_planned_expenses.some((item) => item.status === 'overdue')
                ? `${UI_WARNING} ${tr('obligationsOverdue')} | ${tr('plannedExpenses')}`
                : `${UI_WARNING} ${tr('obligationsDueSoon')} | ${tr('plannedExpenses')}`}
            </div>
            <div style={{ marginBottom: '0.75rem' }}>
              {data.upcoming_planned_expenses.map((item, index) => (
                <div key={`${item.planned_expense_id}-${item.due_date}-${index}`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
                  <span>
                    <strong>{item.name}</strong> | {fmt(item.amount)} {item.currency}
                    <span style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem', marginLeft: '0.5rem' }}>
                      ({item.due_date.split('-').reverse().join('.')})
                    </span>
                  </span>
                  <span style={{ color: item.status === 'overdue' ? 'var(--color-danger)' : 'var(--color-warning)', fontWeight: 600, fontSize: '0.9rem' }}>
                    {item.status === 'overdue' ? `${tr('obligationsOverdue')} ` : ''}{formatObligationDays(item.days_until, tr)}
                  </span>
                </div>
              ))}
            </div>
            <Link to="/planned-expenses" className="btn btn-primary btn-sm">
              {tr('plannedExpenses')} {UI_ARROW}
            </Link>
          </div>
        )}

        {data.upcoming_unpaid_obligations && data.upcoming_unpaid_obligations.length > 0 && (
          <div
            className="card"
            style={{
              marginBottom: '2rem',
              borderColor: data.upcoming_unpaid_obligations.some((item) => item.status === 'overdue')
                ? 'var(--color-danger)'
                : 'var(--color-warning)',
              borderWidth: 1,
              borderStyle: 'solid',
            }}
          >
            <div className="card-title" style={{ color: data.upcoming_unpaid_obligations.some((item) => item.status === 'overdue') ? 'var(--color-danger)' : 'var(--color-warning)' }}>
              {data.upcoming_unpaid_obligations.some((item) => item.status === 'overdue')
                ? `${UI_WARNING} ${tr('obligationsOverdue')}`
                : `${UI_WARNING} ${tr('obligationsDueSoon')}`}
            </div>
            <div style={{ marginBottom: '0.75rem' }}>
              {data.upcoming_unpaid_obligations.map((item) => (
                <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
                  <span>
                    <strong>{item.payment_type_name}</strong> | {fmt(item.amount)} RSD
                    <span style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem', marginLeft: '0.5rem' }}>
                      ({item.deadline.split('-').reverse().join('.')})
                    </span>
                  </span>
                  <span style={{ color: item.status === 'overdue' ? 'var(--color-danger)' : 'var(--color-warning)', fontWeight: 600, fontSize: '0.9rem' }}>
                    {item.status === 'overdue' ? `${tr('obligationsOverdue')} ` : ''}{formatObligationDays(item.days_until, tr)}
                  </span>
                </div>
              ))}
            </div>
            <Link to="/payments" className="btn btn-primary btn-sm">
              {tr('goToPayments')} {UI_ARROW}
            </Link>
          </div>
        )}

        <div className="card">
          <div className="card-title">{tr('recentIncomes')}</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('date')}</th>
                  <th>{tr('invoiceNumber')}</th>
                  <th>{tr('client')}</th>
                  <th>{tr('amount')}</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_incomes.length === 0 ? (
                  <tr><td colSpan={4} style={{ color: 'var(--color-text-muted)' }}>{tr('noRecords')}</td></tr>
                ) : (
                  data.recent_incomes.map((item) => (
                    <tr key={item.id}>
                      <td>{item.date}</td>
                      <td>{item.invoice_number}</td>
                      <td>{item.client_name || '-'}</td>
                      <td>{item.amount_rsd.toLocaleString('sr-RS')}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <Link to="/income" className="dashboard-link" style={{ marginTop: '1rem', display: 'inline-block' }}>{tr('income')} {UI_ARROW}</Link>
        </div>
      </div>
    </>
  )
}
