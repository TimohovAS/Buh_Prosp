import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Info } from 'lucide-react'
import {
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { tr, getLang, getMonthNamesFull } from '../../i18n'
import { formatDateSr, formatMoney2 } from '../../utils/formatters'
import { cashflowDayCount } from '../../utils/cashflow'
import DatePicker from '../DatePicker'
import PageTabs from '../PageTabs'
import './FinanceUI.css'

export function FinanceHeader({ title, subtitle, badge, actions }) {
  return (
    <header className="finance-header" aria-label={title}>
      <PageTabs group="finance" />
      <div className="finance-header-actions">
        {actions}
        <details className="finance-help">
          <summary aria-label={tr('reportAbout')} title={tr('reportAbout')}>
            <Info size={18} aria-hidden="true" />
          </summary>
          <div className="finance-help-content">
            {badge && <strong>{badge}</strong>}
            <p>{subtitle}</p>
          </div>
        </details>
      </div>
    </header>
  )
}

export function FinanceFrame({ title, subtitle, badge, actions, children }) {
  return (
    <div className="page finance-report">
      <FinanceHeader title={title} subtitle={subtitle} badge={badge} actions={actions} />
      <div className="finance-report-content">{children}</div>
    </div>
  )
}

export function FinanceMetric({ title, value, note, tone = '', unit = 'RSD' }) {
  return (
    <div className={`card finance-metric ${tone}`}>
      <div className="finance-metric-title">{title}</div>
      <div className="finance-metric-value">
        {value == null ? '—' : unit === '%' ? Number(value).toFixed(1) : formatMoney2(value)}{' '}
        <small>{unit}</small>
      </div>
      <div className="finance-muted">{note}</div>
    </div>
  )
}

export function FinanceStatus({ validation, error, pending, reload }) {
  if (validation || error)
    return (
      <div className="alert alert-danger finance-status" role="alert">
        <span>{validation ? tr(validation) : error}</span>
        {!validation && (
          <button className="btn btn-secondary btn-sm" onClick={reload}>
            {tr('cashflowRetry')}
          </button>
        )}
      </div>
    )
  return pending ? (
    <div className="card finance-loading" role="status">
      {tr('loading')}
    </div>
  ) : null
}

export function FinanceNote({ children, warning = false }) {
  return (
    <div className={`finance-note ${warning ? 'warning' : ''}`}>
      <Info size={17} aria-hidden="true" />
      <div>{children}</div>
    </div>
  )
}

export function FinanceSection({ title, note, action, children, className = '' }) {
  return (
    <section className={`card finance-section ${className}`}>
      <div className="finance-section-heading">
        <div>
          <h2>{title}</h2>
          {note && <p className="finance-muted">{note}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

export function InvoiceLink({ item }) {
  return (
    <Link className="finance-invoice-link" to="/income" state={{ openIncomeId: item.income_id }}>
      {item.invoice_number}
    </Link>
  )
}

export function FinancePeriodControls({ value: v, children, idPrefix = 'finance' }) {
  const groups = {
    auto: 'cashflowGroupAuto',
    day: 'cashflowGroupDay',
    month: 'cashflowGroupMonth',
    year: 'cashflowGroupYear',
  }
  const periods = {
    month: 'financePeriodMonth',
    quarter: 'financePeriodQuarter',
    year: 'financePeriodYear',
    custom: 'financePeriodCustom',
  }
  const title =
    v.period === 'year'
      ? v.anchor.slice(0, 4)
      : v.period === 'month'
        ? `${getMonthNamesFull()[Number(v.anchor.slice(5, 7)) - 1]} ${v.anchor.slice(0, 4)}`
        : v.period === 'quarter'
          ? tr('cashflowQuarterLabel', {
              quarter: Math.ceil(Number(v.anchor.slice(5, 7)) / 3),
              year: v.anchor.slice(0, 4),
            })
          : tr('financePeriodCustom')
  return (
    <section
      className={`card finance-controls ${children ? '' : 'finance-controls-only'}`}
      aria-label={tr('financePeriod')}
    >
      <div className="finance-control-primary">
        <div className="finance-buttons">
          {Object.entries(periods).map(([key, label]) => (
            <button
              key={key}
              className={`btn btn-sm ${v.period === key ? 'btn-primary' : 'btn-secondary'}`}
              aria-pressed={v.period === key}
              onClick={() => v.selectPeriod(key)}
            >
              {tr(label)}
            </button>
          ))}
        </div>
        <div className="finance-period-nav">
          {v.period !== 'custom' && (
            <button
              className="btn btn-secondary"
              aria-label={tr('cashflowPreviousPeriod')}
              onClick={() => v.move(-1)}
            >
              <ChevronLeft size={17} />
            </button>
          )}
          <strong>{title}</strong>
          {v.period !== 'custom' && (
            <>
              <button
                className="btn btn-secondary"
                disabled={!v.canNext}
                aria-label={tr('cashflowNextPeriod')}
                onClick={() => v.move(1)}
              >
                <ChevronRight size={17} />
              </button>
              <button className="btn btn-secondary btn-sm" onClick={v.current}>
                {tr('cashflowCurrentPeriod')}
              </button>
            </>
          )}
        </div>
        <div className="finance-date-pair">
          <div>
            <label htmlFor={`${idPrefix}-from`}>{tr('periodFrom')}</label>
            <DatePicker
              id={`${idPrefix}-from`}
              value={v.from}
              onChange={(date) => v.changeDate('from', date)}
              maxDate={new Date(`${v.today}T12:00:00`)}
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-to`}>{tr('periodTo')}</label>
            <DatePicker
              id={`${idPrefix}-to`}
              value={v.to}
              onChange={(date) => v.changeDate('to', date)}
              maxDate={new Date(`${v.today}T12:00:00`)}
            />
          </div>
        </div>
        <div className="finance-group-field">
          <label htmlFor={`${idPrefix}-group`}>{tr('cashflowDetail')}</label>
          <select
            className="form-input"
            id={`${idPrefix}-group`}
            value={v.grouping}
            onChange={(e) => v.setGrouping(e.target.value)}
          >
            {Object.entries(groups).map(([key, label]) => (
              <option key={key} value={key} disabled={key === 'day' && cashflowDayCount(v.from, v.to) > 366}>
                {tr(label)}
                {key === 'auto' ? ` · ${tr(groups[v.groupBy]).toLowerCase()}` : ''}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="finance-control-secondary">
        {children}
        <span className="finance-muted finance-period-note">
          {v.incomplete
            ? tr('cashflowThroughToday', { date: formatDateSr(v.today) })
            : tr('cashflowFullPeriod')}
        </span>
      </div>
    </section>
  )
}

function FinanceTooltip({ active, label, payload }) {
  if (!active || !payload?.length) return null
  return (
    <div className="finance-tooltip">
      <strong>{label}</strong>
      {payload.map((item) => (
        <div key={item.dataKey}>
          <span style={{ color: item.color }}>{item.name}</span>
          <b>{formatMoney2(item.value)} RSD</b>
        </div>
      ))}
    </div>
  )
}

export function FinanceChart({ data, series }) {
  const compact = (value) =>
    new Intl.NumberFormat(getLang() === 'ru' ? 'ru-RU' : 'sr-RS', {
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value)
  return (
    <>
      <div className="finance-chart-legend">
        {series.map((item) => (
          <span key={item.key}>
            <i style={{ background: item.color }} />
            {item.name}
          </span>
        ))}
      </div>
      <div className="finance-chart">
        <ResponsiveContainer width="100%" height={200} minWidth={0}>
          <BarChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 8 }} accessibilityLayer>
            <CartesianGrid vertical={false} stroke="var(--color-border)" strokeDasharray="3 5" />
            <XAxis
              dataKey="label"
              tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
              tickLine={false}
              minTickGap={28}
            />
            <YAxis
              width={68}
              tickFormatter={compact}
              tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip content={<FinanceTooltip />} cursor={{ fill: 'var(--color-surface-hover)' }} />
            <ReferenceLine y={0} stroke="var(--color-text-muted)" />
            {series.map((item) => (
              <Bar
                key={item.key}
                dataKey={item.key}
                name={item.name}
                fill={item.color}
                stackId={item.stack}
                maxBarSize={34}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  )
}
