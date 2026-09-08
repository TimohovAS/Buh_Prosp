import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr, getMonthNamesFull, getMonthNamesShort } from '../i18n'
import { formatDateSr, formatMoney2 } from '../utils/formatters'
import useFinanceData from '../hooks/useFinanceData'
import {
  FinanceFrame,
  FinanceMetric,
  FinanceStatus,
  FinanceSection,
  FinanceNote,
  FinanceChart,
} from '../components/finance/FinanceUI'

export default function ProfitAndLoss() {
  const { pathname } = useLocation()
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  const [years, setYears] = useState([currentYear])
  const active = pathname === '/finance/pnl'
  useEffect(() => {
    if (!active) return
    let current = true
    api.finance
      .pnlYears()
      .then((values) => {
        if (current)
          setYears(
            [
              ...new Set([currentYear, ...values.filter((value) => value >= 1900 && value <= currentYear)]),
            ].sort((a, b) => b - a)
          )
      })
      .catch(() => {
        /* The report remains usable if year discovery is unavailable. */
      })
    return () => {
      current = false
    }
  }, [active, currentYear])
  const load = useCallback(() => api.finance.pnl(year), [year])
  const report = useFinanceData(active, String(year), load)
  const items =
    report.data?.items.map((item) => ({
      ...item,
      revenue: Number(item.revenue),
      expenses: Number(item.expenses),
      taxes: Number(item.taxes),
      profit: Number(item.profit),
      label: getMonthNamesShort()[item.month - 1],
    })) || []
  const totals = report.data?.totals
  const revenue = Number(totals?.revenue || 0)
  const profit = Number(totals?.profit || 0)
  const margin = revenue > 0 ? (profit / revenue) * 100 : null
  const hasActivity = items.some((item) => item.revenue || item.expenses || item.taxes)
  return (
    <FinanceFrame title={tr('pnlTitle')} subtitle={tr('reportPnlSubtitle')} badge={tr('reportByDocuments')}>
      <div className="card finance-control-row">
        <div className="finance-as-of">
          <label htmlFor="pnl-year">{tr('year')}</label>
          <select
            id="pnl-year"
            className="form-input"
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
          >
            {[...new Set([year, ...years])]
              .sort((a, b) => b - a)
              .map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
          </select>
        </div>
        <p className="finance-muted">
          {year === currentYear ? tr('reportYearToDate') : tr('reportFullYear')}
        </p>
      </div>
      <FinanceStatus {...report} />
      {!report.pending && report.data && (
        <>
          <div className="finance-metrics">
            <FinanceMetric
              title={tr('reportRevenue')}
              value={revenue}
              tone="positive"
              note={tr('reportIssuedInvoices')}
            />
            <FinanceMetric
              title={tr('reportAllExpenses')}
              value={Number(totals.expenses) + Number(totals.taxes)}
              tone="negative"
              note={tr('reportTaxesIncluded', { amount: `${formatMoney2(totals.taxes)} RSD` })}
            />
            <FinanceMetric
              title={tr('reportNetProfit')}
              value={profit}
              tone={profit < 0 ? 'negative' : 'positive'}
              note={tr('reportAfterTaxes')}
            />
            <FinanceMetric
              title={tr('reportMargin')}
              value={margin}
              unit="%"
              note={tr(margin == null ? 'reportMarginUndefined' : 'reportMarginHint')}
            />
          </div>
          <FinanceNote>{tr('reportPnlMethod')}</FinanceNote>
          {hasActivity ? (
            <div className="finance-two-columns">
              <FinanceSection title={tr('reportPnlStructure')} note={tr('reportTaxStackNote')}>
                <FinanceChart
                  data={items}
                  series={[
                    { key: 'revenue', name: tr('reportRevenue'), color: '#34d399' },
                    { key: 'expenses', name: tr('reportExpensesExTax'), color: '#fb7185', stack: 'cost' },
                    { key: 'taxes', name: tr('taxes'), color: '#fbbf24', stack: 'cost' },
                  ]}
                />
              </FinanceSection>
              <FinanceSection title={tr('reportProfitTrend')} note={tr('reportAfterTaxes')}>
                <FinanceChart
                  data={items}
                  series={[{ key: 'profit', name: tr('reportNetProfit'), color: '#60a5fa' }]}
                />
              </FinanceSection>
            </div>
          ) : (
            <div className="card finance-empty">{tr('reportNoActivity')}</div>
          )}
          <FinanceSection
            title={tr('pnlTable')}
            note={`${formatDateSr(report.data.date_from)} — ${formatDateSr(report.data.date_to)} · RSD`}
          >
            <div className="table-wrap finance-table">
              <table>
                <thead>
                  <tr>
                    <th>{tr('month')}</th>
                    <th className="numeric">{tr('reportRevenue')}</th>
                    <th className="numeric">{tr('reportExpensesExTax')}</th>
                    <th className="numeric">{tr('taxes')}</th>
                    <th className="numeric">{tr('reportNetProfit')}</th>
                    <th className="numeric">{tr('reportMargin')}</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.month}>
                      <th scope="row">
                        {getMonthNamesFull()[item.month - 1]}
                        {year === currentYear && item.month === new Date().getMonth() + 1 && (
                          <small className="finance-muted">{tr('cashflowPartialPeriod')}</small>
                        )}
                      </th>
                      <td className="numeric positive">{formatMoney2(item.revenue)}</td>
                      <td className="numeric">{formatMoney2(item.expenses)}</td>
                      <td className="numeric">{formatMoney2(item.taxes)}</td>
                      <td className={`numeric ${item.profit < 0 ? 'negative' : 'positive'}`}>
                        {formatMoney2(item.profit)}
                      </td>
                      <td className="numeric">
                        {item.revenue > 0 ? `${((item.profit / item.revenue) * 100).toFixed(1)}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <th scope="row">{tr('total')}</th>
                    <td className="numeric">{formatMoney2(revenue)}</td>
                    <td className="numeric">{formatMoney2(totals.expenses)}</td>
                    <td className="numeric">{formatMoney2(totals.taxes)}</td>
                    <td className={`numeric ${profit < 0 ? 'negative' : 'positive'}`}>
                      {formatMoney2(profit)}
                    </td>
                    <td className="numeric">{margin == null ? '—' : `${margin.toFixed(1)}%`}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <div className="finance-equation">{tr('reportPnlEquation')}</div>
          </FinanceSection>
        </>
      )}
    </FinanceFrame>
  )
}
