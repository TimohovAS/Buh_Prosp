import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ArrowDownLeft, ArrowUpRight, ChevronLeft, ChevronRight, Info, Wallet } from 'lucide-react'
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { api } from '../api'
import { tr, getLang, getMonthNamesFull, getMonthNamesShort } from '../i18n'
import DatePicker from '../components/DatePicker'
import PageTabs from '../components/PageTabs'
import { formatMoney2, formatDateSr, localDateIso } from '../utils/formatters'
import { cashflowRange, shiftCashflowPeriod, cashflowDayCount, cashflowGrouping } from '../utils/cashflow'
import './CashFlow.css'

const PERIODS = {
  month: 'financePeriodMonth',
  quarter: 'financePeriodQuarter',
  year: 'financePeriodYear',
  custom: 'financePeriodCustom',
}
const GROUPS = {
  auto: 'cashflowGroupAuto',
  day: 'cashflowGroupDay',
  month: 'cashflowGroupMonth',
  year: 'cashflowGroupYear',
}
const tone = (value) => (value > 0 ? 'positive' : value < 0 ? 'negative' : '')
const signed = (value) => `${value > 0 ? '+' : value < 0 ? '−' : ''}${formatMoney2(Math.abs(value))}`
const money = (value) => `${formatMoney2(value)} RSD`

function periodLabel(value, full = false) {
  if (value.length === 4) return value
  if (value.length === 7) {
    const [year, month] = value.split('-')
    return `${(full ? getMonthNamesFull() : getMonthNamesShort())[Number(month) - 1]} ${year}`
  }
  return formatDateSr(value)
}

function Metric({ title, value, detail, icon: Icon, color = '', signedValue = false }) {
  return (
    <div className={`card cashflow-metric ${color}`}>
      <div className="cashflow-metric-label">
        <span>{title}</span>
        <Icon size={18} aria-hidden="true" />
      </div>
      <div className="cashflow-metric-value">
        {signedValue ? signed(value) : formatMoney2(value)} <small>RSD</small>
      </div>
      <div className="cashflow-muted">{detail}</div>
    </div>
  )
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="cashflow-tooltip">
      <strong>{label}</strong>
      {payload.map((item) => (
        <div key={item.dataKey}>
          <span style={{ color: item.color }}>{item.name}</span>
          <b>{money(item.value)}</b>
        </div>
      ))}
    </div>
  )
}

function FlowChart({ data, balance = false }) {
  const compactNumber = (value) =>
    new Intl.NumberFormat(getLang() === 'ru' ? 'ru-RU' : 'sr-RS', {
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value)
  const Chart = balance ? LineChart : BarChart
  return (
    <div className="cashflow-chart">
      <ResponsiveContainer width="100%" height={265} minWidth={0}>
        <Chart data={data} margin={{ top: 12, right: 16, left: 0, bottom: 8 }} accessibilityLayer>
          <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 5" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
            minTickGap={35}
            tickLine={false}
          />
          <YAxis
            tickFormatter={compactNumber}
            width={68}
            tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            content={<ChartTooltip />}
            cursor={balance ? undefined : { fill: 'var(--color-surface-hover)' }}
          />
          <ReferenceLine y={0} stroke="var(--color-text-muted)" ifOverflow="extendDomain" />
          {balance ? (
            <Line
              type="linear"
              dataKey="closing"
              name={tr('cashflowCalculatedClosing')}
              stroke="#60a5fa"
              strokeWidth={2.5}
              dot={data.length <= 32 ? { r: 3, fill: '#60a5fa', strokeWidth: 0 } : false}
              activeDot={{ r: 5 }}
            />
          ) : (
            <>
              <Bar
                dataKey="receipts"
                name={tr('cashflowTotalIn')}
                fill="#34d399"
                radius={[3, 3, 0, 0]}
                maxBarSize={32}
              />
              <Bar
                dataKey="payments"
                name={tr('cashflowTotalOut')}
                fill="#fb7185"
                radius={[3, 3, 0, 0]}
                maxBarSize={32}
              />
            </>
          )}
        </Chart>
      </ResponsiveContainer>
    </div>
  )
}

export default function CashFlow() {
  const location = useLocation()
  const isActivePage = location.pathname === '/finance/cashflow'
  const today = localDateIso()
  const [period, setPeriod] = useState('year')
  const [anchor, setAnchor] = useState(today)
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [grouping, setGrouping] = useState('auto')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [retry, setRetry] = useState(0)

  const { from, to } = cashflowRange(period, anchor, customFrom, customTo)
  const effectiveTo = to > today ? today : to
  const validation =
    !from || !to
      ? tr('cashflowChooseDates')
      : from > to
        ? tr('cashflowInvalidRange')
        : from > today
          ? tr('cashflowFutureRange')
          : ''
  const groupBy = cashflowGrouping(from, effectiveTo, grouping)
  const requestKey = `${from}/${to}/${groupBy}/${retry}`
  const data = result?.key === requestKey ? result.data : null
  const error = result?.key === requestKey ? result.error : null
  const pending = !validation && (loading || result?.key !== requestKey)

  useEffect(() => {
    if (!isActivePage || validation) return
    let active = true
    setLoading(true)
    api.finance
      .cashflow({ from, to, group_by: groupBy })
      .then((response) => {
        if (active) setResult({ key: requestKey, data: response })
      })
      .catch((e) => {
        if (active) setResult({ key: requestKey, error: e.message })
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [from, to, groupBy, requestKey, isActivePage, validation])

  const choosePeriod = (next) => {
    if (period === 'custom' && from && from <= today) setAnchor(from)
    if (next === 'custom') {
      setCustomFrom(from)
      setCustomTo(effectiveTo)
    }
    setPeriod(next)
    setGrouping('auto')
  }
  const changeDate = (field, value) => {
    setCustomFrom(field === 'from' ? value : from)
    setCustomTo(field === 'to' ? value : effectiveTo)
    setPeriod('custom')
  }
  const nextAnchor = shiftCashflowPeriod(anchor, period, 1)
  const nextFrom = cashflowRange(period === 'custom' ? 'month' : period, nextAnchor).from
  const rangeTitle =
    period === 'year'
      ? anchor.slice(0, 4)
      : period === 'month'
        ? periodLabel(anchor.slice(0, 7), true)
        : period === 'quarter'
          ? tr('cashflowQuarterLabel', {
              quarter: Math.ceil(Number(anchor.slice(5, 7)) / 3),
              year: anchor.slice(0, 4),
            })
          : tr('financePeriodCustom')
  const series = data?.series || []
  const totals = data?.totals || {}
  const inflow = Number(totals.inflow || 0) + Number(totals.financing_inflow || 0)
  const outflow = Number(totals.outflow || 0) + Number(totals.financing_outflow || 0)
  const hasMovements = series.some((row) =>
    ['inflow', 'outflow', 'financing_inflow', 'financing_outflow'].some((key) => Number(row[key]) !== 0)
  )
  const hasFinancing = series.some(
    (row) => Number(row.financing_inflow) !== 0 || Number(row.financing_outflow) !== 0
  )
  const chartSeries = series.map((row) => ({
    ...row,
    label: periodLabel(row.period),
    receipts: Number(row.inflow) + Number(row.financing_inflow),
    payments: Number(row.outflow) + Number(row.financing_outflow),
  }))
  const balanceSeries = data
    ? [{ label: tr('cashflowAtStart'), closing: data.opening_cash_balance }, ...chartSeries]
    : []
  const minimum = series.reduce(
    (min, row) => (Number(row.closing) < Number(min?.closing ?? Infinity) ? row : min),
    null
  )

  return (
    <div className="page cashflow-page">
      <h1>{tr('cashflowTitle')}</h1>
      <PageTabs group="finance" />
      <div className="cashflow-content">
        <div className="cashflow-heading">
          <p>{tr('cashflowSubtitle')}</p>
          <span className="cashflow-badge">{tr('cashflowActualOnly')} · RSD</span>
        </div>
        <section className="card cashflow-filters" aria-label={tr('financePeriod')}>
          <div className="cashflow-filter-row">
            <div className="cashflow-segmented" aria-label={tr('financePeriod')}>
              {Object.entries(PERIODS).map(([key, label]) => (
                <button
                  type="button"
                  key={key}
                  className={`btn btn-sm ${period === key ? 'btn-primary' : 'btn-secondary'}`}
                  aria-pressed={period === key}
                  onClick={() => choosePeriod(key)}
                >
                  {tr(label)}
                </button>
              ))}
            </div>
            <div className="cashflow-period-nav">
              {period !== 'custom' && (
                <button
                  type="button"
                  className="btn btn-secondary cashflow-icon-button"
                  aria-label={tr('cashflowPreviousPeriod')}
                  onClick={() => setAnchor(shiftCashflowPeriod(anchor, period, -1))}
                >
                  <ChevronLeft size={18} />
                </button>
              )}
              <strong>{rangeTitle}</strong>
              {period !== 'custom' && (
                <button
                  type="button"
                  className="btn btn-secondary cashflow-icon-button"
                  aria-label={tr('cashflowNextPeriod')}
                  disabled={nextFrom > today}
                  onClick={() => setAnchor(nextAnchor)}
                >
                  <ChevronRight size={18} />
                </button>
              )}
              {period !== 'custom' && (
                <button type="button" className="btn btn-sm btn-secondary" onClick={() => setAnchor(today)}>
                  {tr('cashflowCurrentPeriod')}
                </button>
              )}
            </div>
          </div>
          <div className="cashflow-filter-row cashflow-date-row">
            <div className="cashflow-date-fields">
              <div>
                <label htmlFor="cashflow-from">{tr('periodFrom')}</label>
                <DatePicker
                  id="cashflow-from"
                  value={from}
                  onChange={(value) => changeDate('from', value)}
                  maxDate={new Date(`${today}T12:00:00`)}
                />
              </div>
              <div>
                <label htmlFor="cashflow-to">{tr('periodTo')}</label>
                <DatePicker
                  id="cashflow-to"
                  value={effectiveTo}
                  onChange={(value) => changeDate('to', value)}
                  maxDate={new Date(`${today}T12:00:00`)}
                />
              </div>
            </div>
            <div className="cashflow-group-field">
              <label htmlFor="cashflow-group">{tr('cashflowDetail')}</label>
              <select
                id="cashflow-group"
                className="form-input"
                value={grouping === 'day' && groupBy !== 'day' ? groupBy : grouping}
                onChange={(e) => setGrouping(e.target.value)}
              >
                {Object.entries(GROUPS).map(([key, label]) => (
                  <option
                    key={key}
                    value={key}
                    disabled={key === 'day' && cashflowDayCount(from, effectiveTo) > 366}
                  >
                    {tr(label)}
                    {key === 'auto' ? ` · ${tr(GROUPS[groupBy]).toLowerCase()}` : ''}
                  </option>
                ))}
              </select>
            </div>
            <p className="cashflow-range-note">
              {to > today
                ? tr('cashflowThroughToday', { date: formatDateSr(today) })
                : tr('cashflowFullPeriod')}
            </p>
          </div>
        </section>
        {validation && (
          <div className="alert alert-danger" role="alert">
            {validation}
          </div>
        )}
        {!validation && error && (
          <div className="alert alert-danger cashflow-error" role="alert">
            <span>{error}</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setRetry((n) => n + 1)}>
              {tr('cashflowRetry')}
            </button>
          </div>
        )}
        {pending && (
          <div className="card cashflow-loading" role="status">
            {tr('loading')}
          </div>
        )}
        {!validation && !pending && data && (
          <>
            <div className="cashflow-metrics">
              <Metric
                title={tr('cashflowTotalIn')}
                value={inflow}
                detail={tr('cashflowIncludingFinanceIn', { amount: money(totals.financing_inflow) })}
                icon={ArrowDownLeft}
                color="positive"
              />
              <Metric
                title={tr('cashflowTotalOut')}
                value={outflow}
                detail={tr('cashflowIncludingFinanceOut', { amount: money(totals.financing_outflow) })}
                icon={ArrowUpRight}
                color="negative"
              />
              <Metric
                title={tr('cashflowNetChange')}
                value={Number(totals.net)}
                detail={tr('cashflowOperatingResult', { amount: money(totals.operating_net) })}
                icon={ArrowUpRight}
                color={tone(Number(totals.net))}
                signedValue
              />
              <Metric
                title={tr('cashflowCalculatedClosing')}
                value={data.closing_cash_balance}
                detail={tr('cashflowOpeningAmount', { amount: money(data.opening_cash_balance) })}
                icon={Wallet}
                color={tone(Number(data.closing_cash_balance))}
              />
            </div>
            <div className="cashflow-context">
              <Info size={17} aria-hidden="true" />
              <div>
                <span>{tr('cashflowBalanceNote')}</span>
                {Number(data.closing_cash_balance) < 0 && (
                  <span className="cashflow-warning"> {tr('cashflowNegativeNote')}</span>
                )}
                {data.unmatched_bank_count > 0 && (
                  <span className="cashflow-warning">
                    {' '}
                    {tr('cashflowUnmatchedNote', { count: data.unmatched_bank_count })}{' '}
                    <Link to="/bank">{tr('cashflowOpenBank')}</Link>
                  </span>
                )}
              </div>
            </div>
            {!hasMovements && (
              <div className="card cashflow-empty">
                <Wallet size={24} aria-hidden="true" />
                <div>
                  <strong>{tr('cashflowNoMovements')}</strong>
                  <p>{tr('cashflowNoMovementsHint')}</p>
                </div>
              </div>
            )}
            {hasMovements && (
              <div className="cashflow-charts">
                <section className="card cashflow-chart-card">
                  <div className="cashflow-section-heading">
                    <h2>{tr('cashflowMovementChart')}</h2>
                    <span className="cashflow-muted">RSD</span>
                  </div>
                  <div className="cashflow-legend">
                    <span>
                      <i className="positive" />
                      {tr('cashflowTotalIn')}
                    </span>
                    <span>
                      <i className="negative" />
                      {tr('cashflowTotalOut')}
                    </span>
                  </div>
                  <FlowChart data={chartSeries} />
                </section>
                <section className="card cashflow-chart-card">
                  <div className="cashflow-section-heading">
                    <h2>{tr('cashflowBalanceChart')}</h2>
                    <span className="cashflow-muted">RSD</span>
                  </div>
                  <p className="cashflow-chart-note">
                    {minimum &&
                      tr('cashflowMinimum', {
                        amount: money(minimum.closing),
                        period: periodLabel(minimum.period),
                      })}
                  </p>
                  <FlowChart data={balanceSeries} balance />
                </section>
              </div>
            )}
            <section className="card cashflow-table-card">
              <div className="cashflow-section-heading">
                <div>
                  <h2>{tr('cashflowBreakdown')}</h2>
                  <p className="cashflow-muted">
                    {tr(GROUPS[groupBy])} · {formatDateSr(data.range.from)} — {formatDateSr(data.range.to)} ·
                    RSD
                  </p>
                </div>
                <span className="cashflow-badge">{tr('cashflowRows', { count: series.length })}</span>
              </div>
              <div className="table-wrap cashflow-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{tr('financePeriod')}</th>
                      <th scope="col">{tr('cashflowAtStart')}</th>
                      <th scope="col">{tr('cashflowOperatingIn')}</th>
                      <th scope="col">{tr('cashflowOperatingOut')}</th>
                      {hasFinancing && (
                        <>
                          <th scope="col">{tr('cashflowFinancingInflow')}</th>
                          <th scope="col">{tr('cashflowFinancingOutflow')}</th>
                        </>
                      )}
                      <th scope="col">{tr('cashflowNetChange')}</th>
                      <th scope="col">{tr('cashflowAtEnd')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {series.map((row) => (
                      <tr key={row.period}>
                        <th scope="row">
                          {periodLabel(row.period)}
                          {to > data.range.to && row === series[series.length - 1] && (
                            <small className="cashflow-partial">{tr('cashflowPartialPeriod')}</small>
                          )}
                        </th>
                        <td>{formatMoney2(row.opening)}</td>
                        <td className={Number(row.inflow) ? 'positive' : 'cashflow-muted'}>
                          {Number(row.inflow) ? formatMoney2(row.inflow) : '—'}
                        </td>
                        <td className={Number(row.outflow) ? 'negative' : 'cashflow-muted'}>
                          {Number(row.outflow) ? formatMoney2(row.outflow) : '—'}
                        </td>
                        {hasFinancing && (
                          <>
                            <td>{Number(row.financing_inflow) ? formatMoney2(row.financing_inflow) : '—'}</td>
                            <td>
                              {Number(row.financing_outflow) ? formatMoney2(row.financing_outflow) : '—'}
                            </td>
                          </>
                        )}
                        <td className={tone(Number(row.net))}>{signed(Number(row.net))}</td>
                        <td className={`cashflow-closing ${tone(Number(row.closing))}`}>
                          {formatMoney2(row.closing)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <th scope="row">{tr('cashflowPeriodTotal')}</th>
                      <td>{formatMoney2(data.opening_cash_balance)}</td>
                      <td className="positive">{formatMoney2(totals.inflow)}</td>
                      <td className="negative">{formatMoney2(totals.outflow)}</td>
                      {hasFinancing && (
                        <>
                          <td>{formatMoney2(totals.financing_inflow)}</td>
                          <td>{formatMoney2(totals.financing_outflow)}</td>
                        </>
                      )}
                      <td className={tone(Number(totals.net))}>{signed(Number(totals.net))}</td>
                      <td className={tone(Number(data.closing_cash_balance))}>
                        {formatMoney2(data.closing_cash_balance)}
                      </td>
                    </tr>
                    <tr className="cashflow-formula">
                      <td colSpan={hasFinancing ? 8 : 6}>{tr('cashflowFormula')}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </section>
            <details className="cashflow-method">
              <summary>{tr('cashflowHowCalculated')}</summary>
              <p>{tr('cashflowMethod')}</p>
              <p>
                {data.opening_reference.date
                  ? tr('cashflowReference', {
                      date: formatDateSr(data.opening_reference.date),
                      amount: money(data.opening_reference.amount),
                    })
                  : tr('cashflowNoReference', { amount: money(data.opening_reference.amount) })}{' '}
                <Link to="/settings">{tr('cashflowOpeningSettings')}</Link>
              </p>
            </details>
          </>
        )}
      </div>
    </div>
  )
}
