import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts'
import { api } from '../api'
import { tr } from '../i18n'

function fmt(n) {
  return (n ?? 0).toLocaleString('sr-RS')
}

function formatObligationDays(daysUntil, tr) {
  if (daysUntil === 0) return tr('obligationToday')
  if (daysUntil === 1) return tr('obligationTomorrow')
  if (daysUntil < 0) {
    const fn = tr('obligationDaysOverdue')
    return typeof fn === 'function' ? fn(Math.abs(daysUntil)) : `${Math.abs(daysUntil)} дн.`
  }
  const fn = tr('obligationDaysLeft')
  return typeof fn === 'function' ? fn(daysUntil) : `${daysUntil} дн.`
}

function IncomeExpensePie({ title, income, expenses, onExpensesClick }) {
  const data = [
    { name: tr('income'), value: income ?? 0, color: 'var(--color-success)' },
    { name: tr('expenses'), value: expenses ?? 0, color: 'var(--color-danger)' },
  ].filter((d) => d.value > 0)

  if (data.length === 0) {
    return (
      <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
        <div className="card-title">{title}</div>
        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>{tr('noData')}</div>
      </div>
    )
  }

  return (
    <div className="card" style={{ minHeight: 200 }}>
      <div className="card-title">{title}</div>
      <ResponsiveContainer width="100%" height={160}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={40}
            outerRadius={65}
            paddingAngle={2}
            dataKey="value"
          >
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.color} stroke="var(--color-surface)" strokeWidth={1} />
            ))}
          </Pie>
          <Tooltip formatter={(v) => fmt(v) + ' RSD'} />
          <Legend formatter={(value, entry) => `${value}: ${fmt(entry?.payload?.value ?? 0)} RSD`} />
        </PieChart>
      </ResponsiveContainer>
      {onExpensesClick && (
        <Link to="/expenses" style={{ fontSize: '0.8rem', display: 'inline-block', marginTop: '-0.5rem' }}>
          {tr('allExpenses')} →
        </Link>
      )}
    </div>
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.dashboard()
      .then((d) => { setData(d); setError(null) })
      .catch((e) => { setError(e.message); console.error(e) })
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
        {/* Главный блок: баланс и планируемые расходы */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
        }}>
          <div className="card" style={{ borderLeft: '4px solid var(--color-accent)' }}>
            <div className="card-title">{tr('balanceMonth')}</div>
            <div style={{
              fontSize: '1.75rem',
              fontWeight: 700,
              color: data.balance_month >= 0 ? 'var(--color-success)' : 'var(--color-danger)',
            }}>
              {fmt(data.balance_month)} RSD
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
              {tr('monthIncome')}: {fmt(data.month_income)} — {tr('monthExpenses')}: {fmt(data.month_expenses)}
            </div>
          </div>
          <div className="card">
            <div className="card-title">{tr('balanceYear')}</div>
            <div style={{
              fontSize: '1.5rem',
              fontWeight: 600,
              color: data.balance_year >= 0 ? 'var(--color-success)' : 'var(--color-danger)',
            }}>
              {fmt(data.balance_year)} RSD
            </div>
          </div>
          <div className="card">
            <div className="card-title">{tr('plannedUntilMonthEnd')}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>
              {tr('plannedExpenses')} + {tr('payments')}
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--color-warning)' }}>
              {fmt(data.planned_expenses_until_month_end)} RSD
            </div>
            <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
              <Link to="/planned-expenses" style={{ fontSize: '0.875rem', display: 'inline-block' }}>
                {tr('plannedExpenses')} →
              </Link>
              <Link to="/payments" style={{ fontSize: '0.875rem', display: 'inline-block' }}>
                {tr('goToPayments')} →
              </Link>
            </div>
          </div>
        </div>

        {/* Доходы и расходы — круговые диаграммы */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
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

        {/* Лимиты паушального режима */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
        }}>
          <div className="card">
            <div className="card-title">{tr('limit6m')} (6M RSD)</div>
            <div style={{ marginBottom: '0.5rem' }}>
              <div className="progress-bar">
                <div
                  className={`progress-bar-fill ${lim.exceeded_6m ? 'danger' : lim.warning_6m ? 'warning' : ''}`}
                  style={{ width: `${Math.min(lim.percent_6m, 100)}%` }}
                />
              </div>
            </div>
            <div style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>
              {lim.percent_6m.toFixed(1)}% {lim.exceeded_6m && tr('exceeded')}
            </div>
          </div>
          <div className="card">
            <div className="card-title">{tr('limit8m')} ({tr('limitMonths12')})</div>
            <div style={{ marginBottom: '0.5rem' }}>
              <div className="progress-bar">
                <div
                  className={`progress-bar-fill ${lim.exceeded_8m ? 'danger' : lim.warning_8m ? 'warning' : ''}`}
                  style={{ width: `${Math.min(lim.percent_8m, 100)}%` }}
                />
              </div>
            </div>
            <div style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>
              {lim.percent_8m.toFixed(1)}%
            </div>
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
              borderColor: data.upcoming_planned_expenses.some((p) => p.status === 'overdue')
                ? 'var(--color-danger)'
                : 'var(--color-warning)',
              borderWidth: 1,
              borderStyle: 'solid',
            }}
          >
            <div className="card-title" style={{ color: data.upcoming_planned_expenses.some((p) => p.status === 'overdue') ? 'var(--color-danger)' : 'var(--color-warning)' }}>
              {data.upcoming_planned_expenses.some((p) => p.status === 'overdue')
                ? `⚠ ${tr('obligationsOverdue')} — ${tr('plannedExpenses')}`
                : `⚠ ${tr('obligationsDueSoon')} — ${tr('plannedExpenses')}`}
            </div>
            <div style={{ marginBottom: '0.75rem' }}>
              {data.upcoming_planned_expenses.map((p, idx) => (
                <div key={`${p.planned_expense_id}-${p.due_date}-${idx}`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
                  <span>
                    <strong>{p.name}</strong> — {fmt(p.amount)} {p.currency}
                    <span style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem', marginLeft: '0.5rem' }}>
                      ({p.due_date.split('-').reverse().join('.')})
                    </span>
                  </span>
                  <span style={{ color: p.status === 'overdue' ? 'var(--color-danger)' : 'var(--color-warning)', fontWeight: 600, fontSize: '0.9rem' }}>
                    {p.status === 'overdue' ? tr('obligationsOverdue') + ' ' : ''}{formatObligationDays(p.days_until, tr)}
                  </span>
                </div>
              ))}
            </div>
            <Link to="/planned-expenses" className="btn btn-primary btn-sm">
              {tr('plannedExpenses')} →
            </Link>
          </div>
        )}

        {data.upcoming_unpaid_obligations && data.upcoming_unpaid_obligations.length > 0 && (
          <div
            className="card"
            style={{
              marginBottom: '2rem',
              borderColor: data.upcoming_unpaid_obligations.some((o) => o.status === 'overdue')
                ? 'var(--color-danger)'
                : 'var(--color-warning)',
              borderWidth: 1,
              borderStyle: 'solid',
            }}
          >
            <div className="card-title" style={{ color: data.upcoming_unpaid_obligations.some((o) => o.status === 'overdue') ? 'var(--color-danger)' : 'var(--color-warning)' }}>
              {data.upcoming_unpaid_obligations.some((o) => o.status === 'overdue')
                ? `⚠ ${tr('obligationsOverdue')}`
                : `⚠ ${tr('obligationsDueSoon')}`}
            </div>
            <div style={{ marginBottom: '0.75rem' }}>
              {data.upcoming_unpaid_obligations.map((o) => (
                <div key={o.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
                  <span>
                    <strong>{o.payment_type_name}</strong> — {fmt(o.amount)} RSD
                    <span style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem', marginLeft: '0.5rem' }}>
                      ({o.deadline.split('-').reverse().join('.')})
                    </span>
                  </span>
                  <span style={{ color: o.status === 'overdue' ? 'var(--color-danger)' : 'var(--color-warning)', fontWeight: 600, fontSize: '0.9rem' }}>
                    {o.status === 'overdue' ? tr('obligationsOverdue') + ' ' : ''}{formatObligationDays(o.days_until, tr)}
                  </span>
                </div>
              ))}
            </div>
            <Link to="/payments" className="btn btn-primary btn-sm">
              {tr('goToPayments')} →
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
                  data.recent_incomes.map((i) => (
                    <tr key={i.id}>
                      <td>{i.date}</td>
                      <td>{i.invoice_number}</td>
                      <td>{i.client_name || '-'}</td>
                      <td>{i.amount_rsd.toLocaleString('sr-RS')}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <Link to="/income" style={{ marginTop: '1rem', display: 'inline-block' }}>{tr('income')} →</Link>
        </div>
      </div>
    </>
  )
}
