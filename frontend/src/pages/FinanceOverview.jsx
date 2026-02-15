import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'

function fmt(n) {
  return (n ?? 0).toLocaleString('sr-RS')
}

function getPeriodRange(quick, customFrom, customTo) {
  const today = new Date()
  const y = today.getFullYear()
  const m = today.getMonth() + 1

  if (quick === 'month') {
    const lastDay = new Date(y, m, 0).getDate()
    return {
      from: `${y}-${String(m).padStart(2, '0')}-01`,
      to: `${y}-${String(m).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
    }
  }
  if (quick === 'quarter') {
    const q = Math.ceil(m / 3)
    const startM = (q - 1) * 3 + 1
    const endM = q * 3
    const lastDay = new Date(y, endM + 1, 0).getDate()
    return {
      from: `${y}-${String(startM).padStart(2, '0')}-01`,
      to: `${y}-${String(endM).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`,
    }
  }
  if (quick === 'year') {
    return { from: `${y}-01-01`, to: `${y}-12-31` }
  }
  return {
    from: customFrom || today.toISOString().slice(0, 10),
    to: customTo || today.toISOString().slice(0, 10),
  }
}

export default function FinanceOverview() {
  const [periodQuick, setPeriodQuick] = useState('month')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [mode, setMode] = useState('both')
  const [summary, setSummary] = useState(null)
  const [ar, setAr] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const { from, to } = getPeriodRange(periodQuick, customFrom, customTo)

  useEffect(() => {
    setLoading(true)
    const modeVal = mode === 'both' ? 'both' : mode
    Promise.all([
      api.finance.summary({ from, to, group_by: 'month', mode: modeVal }),
      api.finance.ar(),
    ])
      .then(([s, a]) => {
        setSummary(s)
        setAr(a)
        setError(null)
      })
      .catch((e) => {
        setError(e.message)
      })
      .finally(() => setLoading(false))
  }, [from, to, mode])

  const totals = summary?.totals || {}
  const series = summary?.series || []
  const arItems = ar?.items || []
  const arTotals = ar?.totals || {}

  const overdueItems = arItems.filter((i) => i.days_outstanding > 30).sort((a, b) => b.days_outstanding - a.days_outstanding).slice(0, 5)

  const revenueKey = mode === 'cash' ? 'revenue_cash' : mode === 'accrual' ? 'revenue_accrual' : 'revenue_cash'
  const expenseKey = mode === 'cash' ? 'expense_cash' : mode === 'accrual' ? 'expense_accrual' : 'expense_cash'

  const revenueLabel = mode === 'both' ? `${tr('income')} (accrual/cash)` : `${tr('income')} (${mode})`
  const expenseLabel = mode === 'both' ? `${tr('expenses')} (accrual/cash)` : `${tr('expenses')} (${mode})`

  const taxLoadPercent = totals.revenue_cash > 0 && totals.taxes_cash != null
    ? ((totals.taxes_cash / totals.revenue_cash) * 100).toFixed(1)
    : null

  const chartData = mode === 'both'
    ? series.map((s) => ({
        period: s.period,
        revenue_accrual: s.revenue_accrual,
        expense_accrual: s.expense_accrual,
        revenue_cash: s.revenue_cash,
        expense_cash: s.expense_cash,
      }))
    : series.map((s) => ({
        period: s.period,
        revenue: s[mode === 'cash' ? 'revenue_cash' : 'revenue_accrual'],
        expense: s[mode === 'cash' ? 'expense_cash' : 'expense_accrual'],
      }))

  if (loading && !summary) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>{tr('loading')}</div>
    )
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('financeOverview')}</h1>
      </div>

      {error && (
        <div style={{ padding: '1rem', color: 'var(--color-danger)' }}>{tr('loadError')}: {error}</div>
      )}

      <div className="page-body">
        {/* Фильтры */}
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>{tr('financePeriod')}</label>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
                {['month', 'quarter', 'year', 'custom'].map((q) => (
                  <button
                    key={q}
                    className={`btn btn-sm ${periodQuick === q ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setPeriodQuick(q)}
                  >
                    {tr(`financePeriod${q.charAt(0).toUpperCase() + q.slice(1)}`)}
                  </button>
                ))}
              </div>
            </div>
            {periodQuick === 'custom' && (
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <DatePicker
                  value={customFrom || from}
                  onChange={(v) => setCustomFrom(v)}
                  placeholder={tr('periodFrom')}
                />
                <span>—</span>
                <DatePicker
                  value={customTo || to}
                  onChange={(v) => setCustomTo(v)}
                  placeholder={tr('periodTo')}
                />
              </div>
            )}
            <div style={{ marginLeft: 'auto' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>{tr('financeMode')}</label>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
                {['accrual', 'cash', 'both'].map((m) => (
                  <button
                    key={m}
                    className={`btn btn-sm ${mode === m ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setMode(m)}
                  >
                    {tr(`financeMode${m.charAt(0).toUpperCase() + m.slice(1)}`)}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* KPI карточки */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
        }}>
          {(mode === 'accrual' || mode === 'both') && (
            <>
              <div className="card" style={{ borderLeft: '4px solid var(--color-success)' }}>
                <div className="card-title">{tr('income')} (accrual)</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.revenue_accrual)} RSD</div>
              </div>
              <div className="card" style={{ borderLeft: '4px solid var(--color-danger)' }}>
                <div className="card-title">{tr('expenses')} (accrual)</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.expense_accrual)} RSD</div>
              </div>
              <div className="card">
                <div className="card-title">{tr('financeNetProfit')} (accrual)</div>
                <div style={{
                  fontSize: '1.25rem',
                  fontWeight: 600,
                  color: (totals.net_profit_accrual ?? 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)',
                }}>
                  {fmt(totals.net_profit_accrual)} RSD
                </div>
              </div>
            </>
          )}
          {(mode === 'cash' || mode === 'both') && (
            <>
              <div className="card" style={{ borderLeft: '4px solid var(--color-success)' }}>
                <div className="card-title">{tr('income')} (cash)</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.revenue_cash)} RSD</div>
              </div>
              <div className="card" style={{ borderLeft: '4px solid var(--color-danger)' }}>
                <div className="card-title">{tr('expenses')} (cash)</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.expense_cash)} RSD</div>
              </div>
              <div className="card">
                <div className="card-title">{tr('financeNetProfit')} (cash)</div>
                <div style={{
                  fontSize: '1.25rem',
                  fontWeight: 600,
                  color: (totals.net_profit_cash ?? 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)',
                }}>
                  {fmt(totals.net_profit_cash)} RSD
                </div>
              </div>
            </>
          )}
          <div className="card" style={{ borderLeft: '4px solid var(--color-accent)' }}>
            <div className="card-title">{tr('financeAR')}</div>
            <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(arTotals.ar_total)} RSD</div>
          </div>
          {mode !== 'accrual' && totals.revenue_cash > 0 && (
            <div className="card">
              <div className="card-title">{tr('financeTaxLoad')}</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{taxLoadPercent ?? 0}%</div>
            </div>
          )}
        </div>

        {/* График */}
        <div className="card" style={{ marginBottom: '2rem', minHeight: 300 }}>
          <div className="card-title">{tr('financeChart')}</div>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="period" />
                <YAxis tickFormatter={(v) => fmt(v)} />
                <Tooltip formatter={(v) => fmt(v) + ' RSD'} />
                <Legend formatter={(_, entry) => (entry.dataKey === 'revenue_accrual' ? tr('income') + ' (accrual)' : entry.dataKey === 'expense_accrual' ? tr('expenses') + ' (accrual)' : entry.dataKey)} />
                {mode === 'both' ? (
                  <>
                    <Bar dataKey="revenue_accrual" fill="var(--color-success)" name={tr('income') + ' accrual'} />
                    <Bar dataKey="expense_accrual" fill="var(--color-danger)" name={tr('expenses') + ' accrual'} />
                    <Bar dataKey="revenue_cash" fill="rgba(76,175,80,0.6)" name={tr('income') + ' cash'} />
                    <Bar dataKey="expense_cash" fill="rgba(244,67,54,0.6)" name={tr('expenses') + ' cash'} />
                  </>
                ) : (
                  <>
                    <Bar dataKey="revenue" fill="var(--color-success)" name={tr('income')} />
                    <Bar dataKey="expense" fill="var(--color-danger)" name={tr('expenses')} />
                  </>
                )}
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>{tr('noData')}</div>
          )}
        </div>

        {/* Дебиторка: 5 самых старых неоплаченных (просрочено >30 дн.) */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div className="card-title">{tr('financeAROverdue')}</div>
            <Link to="/finance/ar" className="btn btn-sm btn-primary">
              {tr('financeGoTo')}
            </Link>
          </div>
          {overdueItems.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{tr('invoiceNumber')}</th>
                    <th>{tr('client')}</th>
                    <th>{tr('date')}</th>
                    <th>{tr('amount')}</th>
                    <th>{tr('financeDaysOverdue')}</th>
                  </tr>
                </thead>
                <tbody>
                  {overdueItems.map((i) => (
                    <tr key={i.income_id}>
                      <td>{i.invoice_number}</td>
                      <td>{i.client_name || '—'}</td>
                      <td>{i.issued_date}</td>
                      <td>{fmt(i.amount)} RSD</td>
                      <td style={{ color: 'var(--color-danger)' }}>{i.days_outstanding} дн.</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ color: 'var(--color-text-muted)' }}>{tr('financeNoOverdue')}</div>
          )}
        </div>
      </div>
    </>
  )
}
