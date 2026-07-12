import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { BarChart, Bar, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { tr } from '../i18n'
import PageTabs from '../components/PageTabs'
import YearFilterSelect from '../components/YearFilterSelect'
import useAvailableYears from '../hooks/useAvailableYears'
import { formatInteger as fmt } from '../utils/formatters'

const MONTH_LABELS = ['', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']

export default function ProfitAndLoss() {
  const location = useLocation()
  const isActivePage = location.pathname === '/finance/pnl'
  const { year, setYear, availableYears, applyAvailableYears, resetAvailableYears } = useAvailableYears({
    initialYear: new Date().getFullYear(),
    includeAllTime: false,
  })
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!isActivePage) return
    setLoading(true)
    Promise.all([api.finance.pnl(year), api.finance.pnlYears()])
      .then(([response, years]) => {
        setData(response)
        applyAvailableYears(years)
        setError(null)
      })
      .catch((e) => {
        resetAvailableYears()
        setError(e.message)
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, isActivePage])

  const items = data?.items || []
  const totals = data?.totals || {}
  const chartData = items.map((item) => ({
    month: MONTH_LABELS[item.month] || String(item.month),
    revenue: item.revenue ?? 0,
    expenses: item.expenses ?? 0,
    profit: item.profit ?? 0,
  }))

  return (
    <>
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">{tr('pnlTitle')}</h1>
        </div>
        <div className="page-header-actions">
          <YearFilterSelect
            value={year}
            availableYears={availableYears}
            onChange={setYear}
            includeAllTime={false}
          />
        </div>
      </div>

      <PageTabs group="finance" />

      <div className="page-body">
        {loading && !data ? (
          <div className="card">{tr('loading')}</div>
        ) : error ? (
          <div className="card" style={{ color: 'var(--color-danger)' }}>
            {tr('loadError')}: {error}
          </div>
        ) : (
          <>
            <div className="card" style={{ marginBottom: '1.5rem' }}>
              <div className="card-title">{tr('pnlExplanation')}</div>
              <div style={{ color: 'var(--color-text-muted)' }}>{tr('pnlAccrualNote')}</div>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: '1rem',
                marginBottom: '1.5rem',
              }}
            >
              <div className="card">
                <div className="card-title">{tr('income')}</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.revenue)} RSD</div>
              </div>
              <div className="card">
                <div className="card-title">{tr('expenses')}</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.expenses)} RSD</div>
              </div>
              <div className="card">
                <div className="card-title">{tr('taxes')}</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.taxes)} RSD</div>
              </div>
              <div className="card">
                <div className="card-title">{tr('profit')}</div>
                <div
                  style={{
                    fontSize: '1.25rem',
                    fontWeight: 600,
                    color: (totals.profit ?? 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)',
                  }}
                >
                  {fmt(totals.profit)} RSD
                </div>
              </div>
            </div>

            <div className="card" style={{ minHeight: 320, marginBottom: '1.5rem' }}>
              <div className="card-title">{tr('pnlChart')}</div>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="month" />
                    <YAxis tickFormatter={(v) => fmt(v)} />
                    <Tooltip formatter={(v) => `${fmt(v)} RSD`} />
                    <Legend />
                    <Bar dataKey="revenue" fill="var(--color-success)" name={tr('income')} />
                    <Bar dataKey="expenses" fill="var(--color-warning)" name={tr('expenses')} />
                    <Bar dataKey="profit" fill="var(--color-accent)" name={tr('profit')} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                  {tr('noData')}
                </div>
              )}
            </div>

            <div className="card">
              <div className="card-title">{tr('pnlTable')}</div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>{tr('month')}</th>
                      <th>{tr('income')}</th>
                      <th>{tr('expenses')}</th>
                      <th>{tr('taxes')}</th>
                      <th>{tr('profit')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.length === 0 ? (
                      <tr>
                        <td colSpan={5} style={{ color: 'var(--color-text-muted)' }}>
                          {tr('noData')}
                        </td>
                      </tr>
                    ) : (
                      items.map((item) => (
                        <tr key={item.month}>
                          <td>{MONTH_LABELS[item.month] || item.month}</td>
                          <td>{fmt(item.revenue)} RSD</td>
                          <td>{fmt(item.expenses)} RSD</td>
                          <td>{fmt(item.taxes)} RSD</td>
                          <td
                            style={{
                              color: item.profit >= 0 ? 'var(--color-success)' : 'var(--color-danger)',
                            }}
                          >
                            {fmt(item.profit)} RSD
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                  <tfoot>
                    <tr>
                      <th>{tr('total')}</th>
                      <th>{fmt(totals.revenue)} RSD</th>
                      <th>{fmt(totals.expenses)} RSD</th>
                      <th>{fmt(totals.taxes)} RSD</th>
                      <th>{fmt(totals.profit)} RSD</th>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  )
}
