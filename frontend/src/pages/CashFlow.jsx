import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
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

export default function CashFlow() {
  const [periodQuick, setPeriodQuick] = useState('year')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const { from, to } = getPeriodRange(periodQuick, customFrom, customTo)

  useEffect(() => {
    setLoading(true)
    api.finance.cashflow({ from, to, group_by: 'month' })
      .then(setData)
      .catch((e) => {
        setError(e.message)
        setData(null)
      })
      .finally(() => setLoading(false))
  }, [from, to])

  const series = data?.series || []

  return (
    <div className="page">
      <h1>{tr('cashflowTitle')}</h1>

      {/* Фильтр периода */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end' }}>
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
                value={customFrom}
                onChange={setCustomFrom}
                placeholder={tr('periodFrom')}
                className="form-input"
              />
              <span>—</span>
              <DatePicker
                value={customTo}
                onChange={setCustomTo}
                placeholder={tr('periodTo')}
                className="form-input"
              />
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>{error}</div>
      )}

      {loading ? (
        <p>{tr('loading')}</p>
      ) : (
        <>
          {data?.opening_cash_balance != null && (
            <div style={{ marginBottom: '1rem', color: 'var(--color-text-muted)' }}>
              {tr('cashflowOpening')}: {fmt(data.opening_cash_balance)} RSD
            </div>
          )}

          {/* Таблица по месяцам */}
          <div className="card" style={{ marginBottom: '2rem' }}>
            <div className="card-title">{tr('cashflowTable')}</div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{tr('financePeriod')}</th>
                    <th>{tr('cashflowOpening')}</th>
                    <th>{tr('cashflowInflow')}</th>
                    <th>{tr('cashflowOutflow')}</th>
                    <th>{tr('cashflowClosing')}</th>
                  </tr>
                </thead>
                <tbody>
                  {series.length === 0 ? (
                    <tr>
                      <td colSpan={5} style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>
                        {tr('noData')}
                      </td>
                    </tr>
                  ) : (
                    series.map((s) => (
                      <tr key={s.period}>
                        <td>{s.period}</td>
                        <td>{fmt(s.opening)} RSD</td>
                        <td style={{ color: 'var(--color-success)' }}>{fmt(s.inflow)} RSD</td>
                        <td style={{ color: 'var(--color-danger)' }}>{fmt(s.outflow)} RSD</td>
                        <td style={{ fontWeight: 600 }}>{fmt(s.closing)} RSD</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* График closing_cash */}
          <div className="card" style={{ minHeight: 300 }}>
            <div className="card-title">{tr('cashflowChart')}</div>
            {series.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={series} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" />
                  <YAxis tickFormatter={(v) => fmt(v)} />
                  <Tooltip formatter={(v) => fmt(v) + ' RSD'} />
                  <Line
                    type="monotone"
                    dataKey="closing"
                    stroke="var(--color-accent)"
                    strokeWidth={2}
                    name={tr('cashflowClosing')}
                    dot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                {tr('noData')}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
