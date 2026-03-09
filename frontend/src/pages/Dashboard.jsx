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

function SummaryCard({ title, value, subtitle, accentColor = 'var(--color-border)', valueColor }) {
  return (
    <div className="card" style={{ marginBottom: 0, borderLeft: `4px solid ${accentColor}` }}>
      <div className="card-title">{title}</div>
      <div style={{ fontSize: '1.6rem', fontWeight: 700, color: valueColor || 'var(--color-text)' }}>
        {fmtCurrency(value)}
      </div>
      {subtitle ? (
        <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)', marginTop: '0.35rem' }}>
          {subtitle}
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
      <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 240, marginBottom: 0 }}>
        <div className="card-title">{title}</div>
        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>{tr('noData')}</div>
      </div>
    )
  }

  return (
    <div className="card" style={{ minHeight: 240, marginBottom: 0, display: 'flex', flexDirection: 'column' }}>
      <div className="card-title">{title}</div>
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
      {onExpensesClick ? (
        <Link to="/expenses" style={{ fontSize: '0.85rem', display: 'inline-block', marginTop: '0.25rem' }}>
          {tr('allExpenses')} {UI_ARROW}
        </Link>
      ) : null}
    </div>
  )
}

function LimitCard({ title, current, limit, percent, warning, exceeded }) {
  const fillClass = exceeded ? 'danger' : warning ? 'warning' : ''

  return (
    <div className="card" style={{ marginBottom: 0 }}>
      <div className="card-title">{title}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'baseline', marginBottom: '0.65rem', flexWrap: 'wrap' }}>
        <div style={{ fontSize: '0.95rem', fontWeight: 600 }}>{fmt(current)} / {fmt(limit)} RSD</div>
        <div style={{ fontSize: '0.9rem', color: exceeded ? 'var(--color-danger)' : warning ? 'var(--color-warning)' : 'var(--color-text-muted)' }}>
          {percent.toFixed(1)}% {exceeded ? tr('exceeded') : ''}
        </div>
      </div>
      <div className="progress-bar">
        <div
          className={`progress-bar-fill ${fillClass}`.trim()}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.dashboard()
      .then((response) => {
        setData(response)
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

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('dashboard')}</h1>
      </div>

      <div className="page-body">
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
        }}>
          <SummaryCard
            title={tr('balanceMonth')}
            value={data.balance_month}
            valueColor={getMetricColor(data.balance_month)}
            accentColor="var(--color-accent)"
            subtitle={`${tr('monthIncome')}: ${fmtCurrency(data.month_income)}${UI_SEPARATOR}${tr('monthExpenses')}: ${fmtCurrency(data.month_expenses)}`}
          />
          <SummaryCard
            title={tr('balanceYear')}
            value={data.balance_year}
            valueColor={getMetricColor(data.balance_year)}
            accentColor="var(--color-success)"
            subtitle={`${tr('yearIncome')}: ${fmtCurrency(data.year_income)}${UI_SEPARATOR}${tr('yearExpenses')}: ${fmtCurrency(data.year_expenses)}`}
          />
          <SummaryCard
            title={tr('balanceAllTime')}
            value={data.balance_all_time}
            valueColor={getMetricColor(data.balance_all_time)}
            accentColor="var(--color-text-muted)"
          />
          <div className="card" style={{ marginBottom: 0, borderLeft: '4px solid var(--color-warning)' }}>
            <div className="card-title">{tr('plannedUntilMonthEnd')}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>
              {tr('plannedExpenses')} + {tr('payments')}
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-warning)' }}>
              {fmtCurrency(data.planned_expenses_until_month_end)}
            </div>
            <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
              <Link to="/planned-expenses" style={{ fontSize: '0.875rem', display: 'inline-block' }}>
                {tr('plannedExpenses')} {UI_ARROW}
              </Link>
              <Link to="/payments" style={{ fontSize: '0.875rem', display: 'inline-block' }}>
                {tr('goToPayments')} {UI_ARROW}
              </Link>
            </div>
          </div>
        </div>

        <div style={{
          display: 'flex',
          gap: '1rem',
          flexWrap: 'wrap',
          marginBottom: '2rem',
          alignItems: 'stretch',
        }}>
          <div style={{
            flex: '2 1 680px',
            minWidth: 0,
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: '1rem',
          }}>
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

          <div style={{
            flex: '1 1 340px',
            minWidth: 0,
            maxWidth: 420,
            display: 'grid',
            gap: '1rem',
            alignContent: 'start',
          }}>
            <LimitCard
              title={`${tr('limit6m')} (6M RSD)`}
              current={lim.year_income}
              limit={lim.limit_6m}
              percent={lim.percent_6m}
              warning={lim.warning_6m}
              exceeded={lim.exceeded_6m}
            />
            <LimitCard
              title={`${tr('limit8m')} (${tr('limitMonths12')})`}
              current={lim.income_12m}
              limit={lim.limit_8m}
              percent={lim.percent_8m}
              warning={lim.warning_8m}
              exceeded={lim.exceeded_8m}
            />
          </div>
        </div>

        {(lim.warning_6m || lim.warning_8m || lim.exceeded_6m || lim.exceeded_8m) && (
          <div
            className="card"
            style={{
              borderColor: lim.exceeded_6m || lim.exceeded_8m ? 'var(--color-danger)' : 'var(--color-warning)',
              marginBottom: '2rem',
            }}
          >
            {(lim.exceeded_6m || lim.exceeded_8m) ? (
              <p style={{ margin: 0, color: 'var(--color-danger)' }}>
                {tr('limitExceeded')}
              </p>
            ) : (
              <p style={{ margin: 0, color: 'var(--color-warning)' }}>
                {tr('limitWarning')}
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
          <Link to="/income" style={{ marginTop: '1rem', display: 'inline-block' }}>{tr('income')} {UI_ARROW}</Link>
        </div>
      </div>
    </>
  )
}

