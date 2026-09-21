import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { getMonthNamesFull, getMonthNamesShort, tr } from '../i18n'
import { formatDateSr } from '../utils/formatters'
import {
  PAYOUT_SERIES_COLORS,
  TRIP_PAYOUT_TYPES,
  groupPayoutsByDate,
  payoutChartSeries,
  payoutEarned,
  payoutNonTrip,
  payoutMoney as money,
  payoutTypeChipLabel,
  payoutTypeLabel,
  sumPayoutEarned,
  sumPayoutMoney as sumMoney,
  visiblePayoutNote,
} from '../utils/workerPayouts'
import { FinanceChart } from './finance/FinanceUI'
import Modal from './Modal'
import './WorkerStatisticsModal.css'

const PAGE_SIZE = 50
const monthLabel = (month) => `${getMonthNamesFull()[Number(month.slice(5)) - 1]} ${month.slice(0, 4)}`
const monthRange = (month) => {
  const [year, index] = month.split('-').map(Number)
  const lastDay = new Date(year, index, 0).getDate()
  return { date_from: `${month}-01`, date_to: `${month}-${String(lastDay).padStart(2, '0')}` }
}

export default function WorkerStatisticsModal({ worker, onClose, onEdit }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [reload, setReload] = useState(0)
  const [year, setYear] = useState('')
  // Список годов берём из ответа за всё время: при выбранном годе сервер
  // присылает только его месяцы, и выпадающий список схлопнулся бы до одного.
  const [years, setYears] = useState([])
  // История показывается за один месяц — по умолчанию за последний с выплатами.
  const [month, setMonth] = useState('')
  const [history, setHistory] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState(false)
  const [page, setPage] = useState(0)
  // Доля высоты, отданная верхней таблице; двигается разделителем.
  const [splitRatio, setSplitRatio] = useState(0.5)
  const panesRef = useRef(null)
  const draggingRef = useRef(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(false)
    const params = { worker_id: worker.id, limit: 1 }
    if (year) {
      params.date_from = `${year}-01-01`
      params.date_to = `${year}-12-31`
    }
    api.workers
      .payoutReport(params)
      .then((data) => {
        if (!active) return
        setSummary(data)
        if (!year) setYears([...new Set(data.months.map((item) => item.month.slice(0, 4)))])
        const available = data.months.map((item) => item.month)
        setMonth((current) => (current && available.includes(current) ? current : available[0] || ''))
        setPage(0)
      })
      .catch(() => {
        if (active) setError(true)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [worker.id, reload, year])

  useEffect(() => {
    if (!month) {
      setHistory(null)
      return
    }
    let active = true
    setHistoryLoading(true)
    setHistoryError(false)
    api.workers
      .payoutReport({
        worker_id: worker.id,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        ...monthRange(month),
      })
      .then((data) => {
        if (active) setHistory(data)
      })
      .catch(() => {
        if (active) setHistoryError(true)
      })
      .finally(() => {
        if (active) setHistoryLoading(false)
      })
    return () => {
      active = false
    }
  }, [worker.id, month, page, reload])

  useEffect(() => {
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  const months = summary?.months || []
  // Карточка тоже про заработок; жильё показано отдельной справочной строкой.
  const totalPaid = sumPayoutEarned(months)
  const regularPaid = sumMoney(months, 'regular_paid')
  const purchasePaid = sumMoney(months, 'purchase_paid')
  const moneyPaid = sumMoney(months, 'money_paid')
  const tripPaid = sumMoney(months, 'trip_paid')
  const lodgingPaid = sumMoney(months, 'lodging_paid')
  const nonTripPaid = months.reduce((sum, item) => sum + payoutNonTrip(item), 0)
  const payoutCount = months.reduce((sum, item) => sum + item.payout_count, 0)
  const sharePercent = (value) => (totalPaid > 0 ? Math.round((value / totalPaid) * 100) : 0)
  const chartData = [...months].reverse().map((item) => ({
    label: `${getMonthNamesShort()[Number(item.month.slice(5)) - 1]} ${item.month.slice(2, 4)}`,
    regular: Number(item.regular_paid),
    purchase: Number(item.purchase_paid),
    trip: Number(item.trip_paid),
  }))
  const historyGroups = groupPayoutsByDate(history?.items)
  const historyCount = history?.payout_count || 0
  const selectMonth = (value) => {
    setMonth(value)
    setPage(0)
  }
  // Выплату правят в «Наличке» — открываем там же, а не заводим вторую форму.
  const openPayout = (payoutId) => {
    onClose()
    navigate(`/cash?payout=${payoutId}`, {
      state: { fromWorker: { id: worker.id, name: worker.name }, fromPath: location.pathname },
    })
  }
  const clampRatio = (value) => Math.min(0.8, Math.max(0.2, value))
  const startResize = (event) => {
    draggingRef.current = true
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  const doResize = (event) => {
    if (!draggingRef.current || !panesRef.current) return
    const rect = panesRef.current.getBoundingClientRect()
    setSplitRatio(clampRatio((event.clientY - rect.top) / rect.height))
  }
  const stopResize = (event) => {
    draggingRef.current = false
    event.currentTarget.releasePointerCapture(event.pointerId)
  }
  const nudgeResize = (event) => {
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return
    event.preventDefault()
    setSplitRatio((value) => clampRatio(value + (event.key === 'ArrowDown' ? 0.05 : -0.05)))
  }

  return (
    <div role="dialog" aria-modal="true" aria-label={`${tr('workerStatisticsTitle')}: ${worker.name}`}>
      <Modal
        isOpen
        onClose={onClose}
        title={worker.name}
        maxWidth="1040px"
        className="worker-statistics-modal"
        bodyClassName="worker-statistics"
        headerExtra={
          <>
            <select
              className="form-input worker-statistics-year"
              aria-label={tr('year')}
              value={year}
              onChange={(event) => setYear(event.target.value)}
              disabled={loading || error}
            >
              <option value="">{tr('allTime')}</option>
              {years.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
            {onEdit && (
              <button className="btn btn-secondary btn-sm" onClick={onEdit}>
                {tr('edit')}
              </button>
            )}
          </>
        }
      >
        {loading ? (
          <p role="status">{tr('loading')}</p>
        ) : error ? (
          <div className="alert alert-danger" role="alert">
            <p>{tr('workerPayoutsLoadError')}</p>
            <button className="btn btn-secondary btn-sm" onClick={() => setReload((value) => value + 1)}>
              {tr('retry')}
            </button>
          </div>
        ) : (
          <>
            <div className="worker-statistics-top">
              <section aria-labelledby="worker-statistics-chart-title">
                <h2 id="worker-statistics-chart-title">{tr('workerPayoutsMonthly')}</h2>
                {chartData.length === 0 ? (
                  <p className="worker-statistics-hint">{tr('workerPayoutsEmpty')}</p>
                ) : (
                  <FinanceChart data={chartData} series={payoutChartSeries()} />
                )}
              </section>

              <section className="worker-statistics-kpi" aria-labelledby="worker-statistics-total-title">
                <h2 id="worker-statistics-total-title">{tr('workerPayoutsEarned')}</h2>
                <strong className="worker-statistics-hero">{money(totalPaid)}</strong>
                <p className="worker-statistics-hero-note">
                  {tr('workerPayoutsCountNote', { payouts: payoutCount })}
                </p>
                <div className="worker-statistics-split">
                  <i
                    style={{
                      background: PAYOUT_SERIES_COLORS.regular,
                      width: `${sharePercent(regularPaid)}%`,
                    }}
                  />
                  <i
                    style={{
                      background: PAYOUT_SERIES_COLORS.purchase,
                      width: `${sharePercent(purchasePaid)}%`,
                    }}
                  />
                  <i
                    style={{
                      background: PAYOUT_SERIES_COLORS.trip,
                      width: `${sharePercent(tripPaid)}%`,
                    }}
                  />
                </div>
                <dl className="worker-statistics-kv">
                  <dt>
                    <i style={{ background: PAYOUT_SERIES_COLORS.regular }} />
                    {tr('workerPayoutsRegular')}
                  </dt>
                  <dd>
                    {money(regularPaid)} · {sharePercent(regularPaid)}%
                  </dd>
                  <dt>
                    <i style={{ background: PAYOUT_SERIES_COLORS.purchase }} />
                    {tr('workerPayoutsPurchases')}
                  </dt>
                  <dd>
                    {money(purchasePaid)} · {sharePercent(purchasePaid)}%
                  </dd>
                  <dt>
                    <i style={{ background: PAYOUT_SERIES_COLORS.trip }} />
                    {tr('workerPayoutsTrips')}
                  </dt>
                  <dd>
                    {money(tripPaid)} · {sharePercent(tripPaid)}%
                  </dd>
                </dl>
                {lodgingPaid > 0 && (
                  <p className="worker-statistics-hero-note">
                    {tr('workerPayoutsLodgingNote')}: {money(lodgingPaid)}
                  </p>
                )}
                <p className="worker-statistics-hint">{tr('workerStatisticsDateHint')}</p>
              </section>
            </div>

            <div className="worker-statistics-panes" ref={panesRef}>
              <section
                className="worker-statistics-pane"
                style={{ flexGrow: splitRatio }}
                aria-labelledby="worker-statistics-months-title"
              >
                <h2 id="worker-statistics-months-title">{tr('workerPayoutsByMonth')}</h2>
                <div className="table-wrap worker-statistics-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>{tr('workerPayoutMonthly')}</th>
                        <th className="worker-statistics-number">{tr('workerPayoutsMoney')}</th>
                        <th className="worker-statistics-number">{tr('workerPayoutsPurchases')}</th>
                        <th className="worker-statistics-number">{tr('workerPayoutsNonTrip')}</th>
                        <th className="worker-statistics-number">{tr('workerPayoutsTrips')}</th>
                        <th className="worker-statistics-number">{tr('workerPayoutsReceived')}</th>
                        <th className="worker-statistics-number worker-statistics-hint">
                          {tr('workerPayoutsLodgingNote')}
                        </th>
                        <th className="worker-statistics-number">{tr('workerPayoutsCount')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {months.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="worker-statistics-hint">
                            {tr('workerPayoutsEmpty')}
                          </td>
                        </tr>
                      ) : (
                        months.map((item) => (
                          <tr
                            key={item.month}
                            className={`worker-statistics-row${item.month === month ? ' is-selected' : ''}`}
                            aria-selected={item.month === month}
                            tabIndex={0}
                            onClick={() => selectMonth(item.month)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault()
                                selectMonth(item.month)
                              }
                            }}
                          >
                            <td className="worker-statistics-month">{monthLabel(item.month)}</td>
                            <td className="worker-statistics-number">{money(item.money_paid)}</td>
                            <td className="worker-statistics-number">{money(item.purchase_paid)}</td>
                            <td className="worker-statistics-number">{money(payoutNonTrip(item))}</td>
                            <td className="worker-statistics-number">{money(item.trip_paid)}</td>
                            <td className="worker-statistics-number">
                              <strong>{money(payoutEarned(item))}</strong>
                            </td>
                            <td className="worker-statistics-number worker-statistics-hint">
                              {money(item.lodging_paid)}
                            </td>
                            <td className="worker-statistics-number">{item.payout_count}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                    {months.length > 0 && (
                      <tfoot>
                        <tr>
                          <th>{tr('total')}</th>
                          <th className="worker-statistics-number">{money(moneyPaid)}</th>
                          <th className="worker-statistics-number">{money(purchasePaid)}</th>
                          <th className="worker-statistics-number">{money(nonTripPaid)}</th>
                          <th className="worker-statistics-number">{money(tripPaid)}</th>
                          <th className="worker-statistics-number">{money(totalPaid)}</th>
                          <th className="worker-statistics-number worker-statistics-hint">
                            {money(lodgingPaid)}
                          </th>
                          <th className="worker-statistics-number">{payoutCount}</th>
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
              </section>

              <div
                className="worker-statistics-splitter"
                role="separator"
                aria-orientation="horizontal"
                aria-label={tr('workerPayoutsResizeTables')}
                aria-valuenow={Math.round(splitRatio * 100)}
                aria-valuemin={20}
                aria-valuemax={80}
                tabIndex={0}
                onPointerDown={startResize}
                onPointerMove={doResize}
                onPointerUp={stopResize}
                onKeyDown={nudgeResize}
              />

              <section
                className="worker-statistics-pane"
                style={{ flexGrow: 1 - splitRatio }}
                aria-labelledby="worker-statistics-history-title"
              >
                <h2 id="worker-statistics-history-title">
                  {tr('workerPayoutsHistory')}
                  {month && <span className="worker-statistics-hint"> · {monthLabel(month)}</span>}
                </h2>
                <div className="table-wrap worker-statistics-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>{tr('workerPayoutType')}</th>
                        <th className="worker-statistics-number">{tr('workerPayoutsPaid')}</th>
                      </tr>
                    </thead>
                    {historyLoading || historyError || historyGroups.length === 0 ? (
                      <tbody>
                        <tr>
                          <td colSpan={2} className="worker-statistics-hint">
                            {historyLoading
                              ? tr('loading')
                              : historyError
                                ? tr('workerPayoutsLoadError')
                                : tr('workerPayoutsEmpty')}
                          </td>
                        </tr>
                      </tbody>
                    ) : (
                      historyGroups.map((group) => (
                        <tbody key={group.date}>
                          <tr className="worker-statistics-day">
                            <th colSpan={2} scope="colgroup">
                              {formatDateSr(group.date)}
                              <span className="worker-statistics-hint">
                                {' · '}
                                {group.items.length}
                                {' · '}
                                {money(sumMoney(group.items, 'cash_paid_amount'))}
                              </span>
                            </th>
                          </tr>
                          {group.items.map((payout) => {
                            const note = visiblePayoutNote(payout.note)
                            const period =
                              payout.period_start || payout.period_end
                                ? `${formatDateSr(payout.period_start)} — ${formatDateSr(payout.period_end)}`
                                : ''
                            return (
                              <tr
                                key={payout.id}
                                className="worker-statistics-payout"
                                tabIndex={0}
                                title={tr('workerPayoutsOpenInCash')}
                                onClick={() => openPayout(payout.id)}
                                onKeyDown={(event) => {
                                  if (event.key === 'Enter' || event.key === ' ') {
                                    event.preventDefault()
                                    openPayout(payout.id)
                                  }
                                }}
                              >
                                <td>
                                  <span
                                    className={`worker-statistics-chip${
                                      TRIP_PAYOUT_TYPES.has(payout.payout_type) ? ' is-trip' : ''
                                    }`}
                                    title={payoutTypeLabel(payout.payout_type)}
                                  >
                                    {payoutTypeChipLabel(payout.payout_type)}
                                  </span>
                                  {period && <span className="worker-statistics-period">{period}</span>}
                                  {note && <span className="worker-statistics-note">{note}</span>}
                                </td>
                                <td className="worker-statistics-number">
                                  <strong>{money(payout.cash_paid_amount)}</strong>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      ))
                    )}
                  </table>
                </div>
                {historyCount > PAGE_SIZE && (
                  <div className="worker-statistics-pagination">
                    <span className="worker-statistics-hint">
                      {tr('workerPayoutsPage', {
                        from: page * PAGE_SIZE + 1,
                        to: Math.min((page + 1) * PAGE_SIZE, historyCount),
                        total: historyCount,
                      })}
                    </span>
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={page === 0}
                      onClick={() => setPage((value) => value - 1)}
                    >
                      {tr('workerPayoutsPrevious')}
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={(page + 1) * PAGE_SIZE >= historyCount}
                      onClick={() => setPage((value) => value + 1)}
                    >
                      {tr('workerPayoutsNext')}
                    </button>
                  </div>
                )}
              </section>
            </div>
          </>
        )}
      </Modal>
    </div>
  )
}
