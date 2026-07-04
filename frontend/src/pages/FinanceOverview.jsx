import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import { formatInteger as fmt, localDateIso } from '../utils/formatters'
import { getPeriodRange } from '../utils/periods'

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

function getRiskColor(risk) {
  if (risk === 'high') return 'var(--color-danger)'
  if (risk === 'medium') return 'var(--color-warning)'
  return 'var(--color-success)'
}

function getOverallRisk(...risks) {
  if (risks.includes('high')) return 'high'
  if (risks.includes('medium')) return 'medium'
  return 'low'
}

export default function FinanceOverview() {
  const location = useLocation()
  const isActivePage = location.pathname === '/finance'
  const [periodQuick, setPeriodQuick] = useState('year')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [mode, setMode] = useState('both')
  const [summary, setSummary] = useState(null)
  const [ar, setAr] = useState(null)
  const [limits, setLimits] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const { from, to } = getPeriodRange(periodQuick, customFrom, customTo)
  const todayIso = localDateIso()
  const overviewAsOf = to > todayIso ? todayIso : to

  useEffect(() => {
    if (!isActivePage) return
    setLoading(true)
    const modeVal = mode === 'both' ? 'both' : mode
    Promise.all([
      api.finance.summary({ from, to, group_by: 'month', mode: modeVal }),
      api.finance.ar({ as_of: overviewAsOf }),
      api.finance.limits({ as_of: overviewAsOf }),
    ])
      .then(([s, a, l]) => {
        setSummary(s)
        setAr(a)
        setLimits(l)
        setError(null)
      })
      .catch((e) => {
        setError(e.message)
      })
      .finally(() => setLoading(false))
  }, [from, to, mode, overviewAsOf, isActivePage])

  const totals = summary?.totals || {}
  const series = summary?.series || []
  const arItems = ar?.items || []
  const arTotals = ar?.totals || {}
  const limitsData = limits
  const annualRisk = limitsData
    ? getAnnualLimitRisk(
        limitsData.annual_total,
        limitsData.annual_limit,
        limitsData.annual_percent,
        limitsData.forecast_year_end ?? limitsData.annual_total,
      )
    : 'low'
  const rollingRisk = limitsData
    ? getRollingLimitRisk(
        limitsData.rolling_12_total,
        limitsData.vat_limit,
        limitsData.vat_percent,
      )
    : 'low'
  const limitsRisk = getOverallRisk(annualRisk, rollingRisk)

  const overdueItems = arItems
    .filter((i) => (i.days_overdue ?? 0) > 0)
    .sort((a, b) => (b.days_overdue ?? 0) - (a.days_overdue ?? 0))
    .slice(0, 5)

  const getModeLabel = (value) => tr(`financeMode${value.charAt(0).toUpperCase() + value.slice(1)}`)
  const getInlineModeLabel = (value) => {
    const label = getModeLabel(value)
    return label ? label.charAt(0).toLowerCase() + label.slice(1) : value
  }
  const accrualModeLabel = getInlineModeLabel('accrual')
  const cashModeLabel = getInlineModeLabel('cash')
  const chartSeriesNames = {
    revenue_accrual: `${tr('income')} (${accrualModeLabel})`,
    expense_accrual: `${tr('expenses')} (${accrualModeLabel})`,
    revenue_cash: `${tr('income')} (${cashModeLabel})`,
    expense_cash: `${tr('expenses')} (${cashModeLabel})`,
  }

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
          gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
        }}>
          {limitsData && (
            <>
              <div className="card" style={{ borderLeft: `4px solid ${getRiskColor(annualRisk)}` }}>
                <div className="card-title">{tr('limit6m')}</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(limitsData.annual_total)} / {fmt(limitsData.annual_limit)} RSD</div>
                <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', marginTop: '0.35rem' }}>
                  {limitsData.annual_percent.toFixed(1)}% | {tr('forecastYearEnd')}: {fmt(limitsData.forecast_year_end)} RSD
                </div>
              </div>
              <div className="card" style={{ borderLeft: `4px solid ${getRiskColor(rollingRisk)}` }}>
                <div className="card-title">{tr('limit8m')}</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(limitsData.rolling_12_total)} / {fmt(limitsData.vat_limit)} RSD</div>
                <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', marginTop: '0.35rem' }}>
                  {limitsData.vat_percent.toFixed(1)}% | {tr(`risk${rollingRisk.charAt(0).toUpperCase() + rollingRisk.slice(1)}`)}
                </div>
              </div>
            </>
          )}
          {(mode === 'accrual' || mode === 'both') && (
            <>
              <div className="card" style={{ borderLeft: '4px solid var(--color-success)' }}>
                <div className="card-title">{tr('income')} ({accrualModeLabel})</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.revenue_accrual)} RSD</div>
              </div>
              <div className="card" style={{ borderLeft: '4px solid var(--color-danger)' }}>
                <div className="card-title">{tr('expenses')} ({accrualModeLabel})</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.expense_accrual)} RSD</div>
              </div>
              <div className="card">
                <div className="card-title">{tr('financeNetProfit')} ({accrualModeLabel})</div>
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
                <div className="card-title">{tr('income')} ({cashModeLabel})</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.revenue_cash)} RSD</div>
              </div>
              <div className="card" style={{ borderLeft: '4px solid var(--color-danger)' }}>
                <div className="card-title">{tr('expenses')} ({cashModeLabel})</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.expense_cash)} RSD</div>
              </div>
              <div className="card">
                <div className="card-title">{tr('financeNetProfit')} ({cashModeLabel})</div>
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

        {limitsData && (
          <div className="card" style={{ marginBottom: '2rem', borderColor: limitsRisk === 'high' ? 'var(--color-danger)' : limitsRisk === 'medium' ? 'var(--color-warning)' : 'var(--color-border)' }}>
            <div className="card-title">{tr('financeLimits')}</div>
            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem', marginBottom: '0.4rem' }}>
              {tr('limit6m')} (6M RSD): {fmt(limitsData.annual_total)} / {fmt(limitsData.annual_limit)} RSD
            </div>
            <div className="progress-bar" style={{ marginBottom: '0.75rem' }}>
              <div
                className={`progress-bar-fill ${annualRisk === 'high' ? 'danger' : annualRisk === 'medium' ? 'warning' : ''}`.trim()}
                style={{ width: `${Math.min(limitsData.annual_percent, 100)}%` }}
              />
            </div>
            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem', marginBottom: '0.4rem' }}>
              {tr('limit8m')} ({tr('limitMonths12')}): {fmt(limitsData.rolling_12_total)} / {fmt(limitsData.vat_limit)} RSD
            </div>
            <div className="progress-bar" style={{ marginBottom: '0.75rem' }}>
              <div
                className={`progress-bar-fill ${rollingRisk === 'high' ? 'danger' : rollingRisk === 'medium' ? 'warning' : ''}`.trim()}
                style={{ width: `${Math.min(limitsData.vat_percent, 100)}%` }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem', color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
              <div>{tr('averageMonthlyIncome')}: <strong style={{ color: 'var(--color-text)' }}>{fmt(limitsData.average_monthly_income)} RSD</strong></div>
              <div>{tr('forecastYearEnd')}: <strong style={{ color: 'var(--color-text)' }}>{fmt(limitsData.forecast_year_end)} RSD</strong></div>
              <div>{tr('estimatedLimitDate')}: <strong style={{ color: 'var(--color-text)' }}>{limitsData.estimated_limit_date || tr('notAvailable')}</strong></div>
              <div>{tr('limit6m')}: <strong style={{ color: getRiskColor(annualRisk) }}>{tr(`risk${annualRisk.charAt(0).toUpperCase() + annualRisk.slice(1)}`)}</strong></div>
              <div>{tr('limit8m')}: <strong style={{ color: getRiskColor(rollingRisk) }}>{tr(`risk${rollingRisk.charAt(0).toUpperCase() + rollingRisk.slice(1)}`)}</strong></div>
            </div>
          </div>
        )}

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
                <Legend formatter={(_, entry) => chartSeriesNames[entry?.dataKey] || entry?.value || ''} />
                {mode === 'both' ? (
                  <>
                    <Bar dataKey="revenue_accrual" fill="var(--color-success)" name={chartSeriesNames.revenue_accrual} />
                    <Bar dataKey="expense_accrual" fill="var(--color-danger)" name={chartSeriesNames.expense_accrual} />
                    <Bar dataKey="revenue_cash" fill="rgba(76,175,80,0.6)" name={chartSeriesNames.revenue_cash} />
                    <Bar dataKey="expense_cash" fill="rgba(244,67,54,0.6)" name={chartSeriesNames.expense_cash} />
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
                    <th>{tr('valuta')}</th>
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
                      <td>{i.due_date || '—'}</td>
                      <td>{fmt(i.amount)} RSD</td>
                      <td style={{ color: 'var(--color-danger)' }}>{Math.max(0, i.days_overdue ?? 0)} {tr('financeDaysShort')}</td>
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
