import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { getMonthNamesShort, tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import PageHeader from '../components/PageHeader'
import PageTabs from '../components/PageTabs'
import WorkerStatisticsModal from '../components/WorkerStatisticsModal'
import { FinanceChart, FinanceTooltipCard } from '../components/finance/FinanceUI'
import { formatDateSr } from '../utils/formatters'
import {
  PAYOUT_SERIES_COLORS,
  payoutChartSeries,
  payoutEarned,
  payoutMoney as money,
  sumPayoutEarned,
  sumPayoutMoney as sumMoney,
} from '../utils/workerPayouts'
import './WorkerPayouts.css'

// История выплат живёт в карточке работника, поэтому странице нужны только
// сводные числа — записи запрашиваем по минимуму, который допускает API.
const ITEMS_LIMIT = 1

const isoDate = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`

const PERIOD_PRESETS = [
  {
    id: 'month',
    label: 'workerPayoutsPeriodMonth',
    range: (now) => [
      new Date(now.getFullYear(), now.getMonth(), 1),
      new Date(now.getFullYear(), now.getMonth() + 1, 0),
    ],
  },
  {
    id: 'quarter',
    label: 'workerPayoutsPeriodQuarter',
    range: (now) => {
      const first = Math.floor(now.getMonth() / 3) * 3
      return [new Date(now.getFullYear(), first, 1), new Date(now.getFullYear(), first + 3, 0)]
    },
  },
  {
    id: 'year',
    label: 'year',
    range: (now) => [new Date(now.getFullYear(), 0, 1), new Date(now.getFullYear(), 11, 31)],
  },
]

export default function WorkerPayouts() {
  const location = useLocation()
  const isActivePage = location.pathname === '/workers/payouts'
  const [workers, setWorkers] = useState([])
  const [workerId, setWorkerId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [report, setReport] = useState(null)
  const [statisticsWorker, setStatisticsWorker] = useState(null)
  // Возврат из «Налички»: открываем карточку работника, из которой ушли.
  // Сравниваем сам объект state: у каждого перехода он свой, поэтому к одному
  // и тому же работнику можно вернуться повторно.
  const restoredStateRef = useRef(null)
  useEffect(() => {
    const restored = location.state?.openWorker
    if (!restored || restoredStateRef.current === location.state) return
    restoredStateRef.current = location.state
    setStatisticsWorker(restored)
  }, [location.state])
  const [barTooltip, setBarTooltip] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [reload, setReload] = useState(0)
  const invalidDates = Boolean(dateFrom && dateTo && dateFrom > dateTo)

  useEffect(() => {
    if (!isActivePage || invalidDates) return
    let active = true
    setLoading(true)
    setError(false)
    const params = { limit: ITEMS_LIMIT }
    if (workerId) params.worker_id = workerId
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo

    Promise.all([api.workers.list(), api.workers.payoutReport(params)])
      .then(([workerItems, data]) => {
        if (!active) return
        setWorkers(workerItems)
        setReport(data)
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
  }, [isActivePage, workerId, dateFrom, dateTo, reload, invalidDates])

  const changeFilter = (setter, value) => setter(value)
  const resetFilters = () => {
    setWorkerId('')
    setDateFrom('')
    setDateTo('')
  }
  const applyPreset = (preset) => {
    if (preset) {
      const [from, to] = preset.range(new Date())
      setDateFrom(isoDate(from))
      setDateTo(isoDate(to))
    } else {
      setDateFrom('')
      setDateTo('')
    }
  }
  const activePreset = (() => {
    if (!dateFrom && !dateTo) return 'all'
    const now = new Date()
    const preset = PERIOD_PRESETS.find((item) => {
      const [from, to] = item.range(now)
      return isoDate(from) === dateFrom && isoDate(to) === dateTo
    })
    return preset ? preset.id : ''
  })()
  const hasFilters = Boolean(workerId || dateFrom || dateTo)
  // Подсказка у полосы повторяет подсказку графика и так же следует за курсором.
  const showBarTooltip = (event, worker) =>
    setBarTooltip({
      x: event.clientX,
      y: event.clientY,
      // У правого края окна подсказка раскрывается влево, чтобы не уезжать за экран.
      flipX: event.clientX > window.innerWidth - 260,
      label: worker.worker_name,
      rows: [
        {
          key: 'regular',
          name: tr('workerPayoutsRegular'),
          color: PAYOUT_SERIES_COLORS.regular,
          value: money(worker.regular_paid),
        },
        {
          key: 'purchase',
          name: tr('workerPayoutsPurchases'),
          color: PAYOUT_SERIES_COLORS.purchase,
          value: money(worker.purchase_paid),
        },
        {
          key: 'trip',
          name: tr('workerPayoutsTrips'),
          color: PAYOUT_SERIES_COLORS.trip,
          value: money(worker.trip_paid),
        },
      ],
    })

  const summary = report?.workers || []
  const regularPaid = sumMoney(summary, 'regular_paid')
  const purchasePaid = sumMoney(summary, 'purchase_paid')
  const tripPaid = sumMoney(summary, 'trip_paid')
  // Вкладка отвечает на вопрос «сколько работник заработал», поэтому стоимость
  // жилья сюда не входит — она справочно показана в карточке работника.
  const totalPaid = sumPayoutEarned(summary)
  const sharePercent = (value) => (totalPaid > 0 ? Math.round((value / totalPaid) * 100) : 0)
  const maxWorkerPaid = summary.reduce((max, item) => Math.max(max, payoutEarned(item)), 0)
  const lastPayoutDate = summary.reduce(
    (latest, item) => (item.last_payout_date > latest ? item.last_payout_date : latest),
    ''
  )
  const chartData = [...(report?.months || [])].reverse().map((item) => ({
    label: `${getMonthNamesShort()[Number(item.month.slice(5)) - 1]} ${item.month.slice(2, 4)}`,
    regular: Number(item.regular_paid),
    purchase: Number(item.purchase_paid),
    trip: Number(item.trip_paid),
  }))

  return (
    <>
      <PageHeader title={tr('workersTitle')} subtitle={tr('workerPayoutsSubtitle')} />
      <PageTabs
        group="workers"
        actions={
          <>
            <select
              id="payout-worker"
              className="form-input worker-payouts-worker"
              aria-label={tr('worker')}
              value={workerId}
              onChange={(event) => changeFilter(setWorkerId, event.target.value)}
            >
              <option value="">{tr('allWorkers')}</option>
              {workers.map((worker) => (
                <option key={worker.id} value={worker.id}>
                  {worker.name}
                  {worker.is_active ? '' : ` (${tr('archive')})`}
                </option>
              ))}
            </select>
            <div className="worker-payouts-presets" role="group" aria-label={tr('workerPayoutsPeriod')}>
              {PERIOD_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  aria-pressed={activePreset === preset.id}
                  onClick={() => applyPreset(preset)}
                >
                  {tr(preset.label)}
                </button>
              ))}
              <button type="button" aria-pressed={activePreset === 'all'} onClick={() => applyPreset(null)}>
                {tr('allTime')}
              </button>
            </div>
            <span className="worker-payouts-date-field">
              <DatePicker
                id="payout-date-from"
                value={dateFrom}
                onChange={(value) => changeFilter(setDateFrom, value)}
                placeholder={tr('dateFrom')}
                aria-label={tr('dateFrom')}
              />
            </span>
            <span className="worker-payouts-date-field">
              <DatePicker
                id="payout-date-to"
                value={dateTo}
                onChange={(value) => changeFilter(setDateTo, value)}
                placeholder={tr('dateTo')}
                aria-label={tr('dateTo')}
              />
            </span>
            <button className="btn btn-secondary btn-sm" onClick={resetFilters} disabled={!hasFilters}>
              {tr('workerPayoutsReset')}
            </button>
          </>
        }
      />
      <div className="page-body worker-payouts">
        {invalidDates ? (
          <div className="alert alert-danger" role="alert">
            {tr('workerPayoutsInvalidDates')}
          </div>
        ) : error ? (
          <div className="alert alert-danger worker-payouts-error" role="alert">
            {tr('workerPayoutsLoadError')}
            <button className="btn btn-secondary btn-sm" onClick={() => setReload((value) => value + 1)}>
              {tr('retry')}
            </button>
          </div>
        ) : loading ? (
          <div className="card" role="status">
            {tr('loading')}
          </div>
        ) : report ? (
          <>
            <div className="worker-payouts-top">
              <section className="card" aria-labelledby="payout-chart-title">
                <h2 id="payout-chart-title" className="worker-payouts-heading">
                  {tr('workerPayoutsMonthly')}
                </h2>
                {chartData.length === 0 ? (
                  <p className="worker-payouts-muted">{tr('workerPayoutsEmpty')}</p>
                ) : (
                  <FinanceChart data={chartData} series={payoutChartSeries()} />
                )}
              </section>

              <section className="card worker-payouts-kpi" aria-labelledby="payout-total-title">
                <h2 id="payout-total-title" className="worker-payouts-heading">
                  {tr('workerPayoutsEarned')}
                </h2>
                <strong className="worker-payouts-hero">{money(totalPaid)}</strong>
                <p className="worker-payouts-hero-note worker-payouts-muted">
                  {tr('workerPayoutsHeroNote', {
                    payouts: report.payout_count,
                    workers: report.worker_count,
                  })}
                </p>
                <div
                  className="worker-payouts-split"
                  title={`${tr('workerPayoutsRegular')}: ${money(regularPaid)} · ${tr('workerPayoutsPurchases')}: ${money(purchasePaid)} · ${tr('workerPayoutsTrips')}: ${money(tripPaid)}`}
                >
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
                  <i style={{ background: PAYOUT_SERIES_COLORS.trip, width: `${sharePercent(tripPaid)}%` }} />
                </div>
                <dl className="worker-payouts-kv">
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

                  {lastPayoutDate && (
                    <>
                      <dt className="worker-payouts-kv-split">{tr('workerPayoutsLastDate')}</dt>
                      <dd className="worker-payouts-kv-split">{formatDateSr(lastPayoutDate)}</dd>
                    </>
                  )}
                </dl>
                <p className="worker-payouts-hint">{tr('workerPayoutsDateHint')}</p>
              </section>
            </div>

            <section className="card" aria-labelledby="payout-summary-title">
              <h2 id="payout-summary-title" className="worker-payouts-heading">
                {tr('workerPayoutsSummary')}
              </h2>
              <div className="table-wrap">
                <table className="worker-payouts-table">
                  <thead>
                    <tr>
                      <th>{tr('worker')}</th>
                      <th className="worker-payouts-split-col">{tr('workerPayoutsSplit')}</th>
                      <th className="worker-payouts-number">{tr('workerPayoutsEarned')}</th>
                      <th className="worker-payouts-number">{tr('workerPayoutsCount')}</th>
                      <th className="worker-payouts-number">{tr('workerPayoutsLastDate')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="worker-payouts-muted">
                          {tr('workerPayoutsEmpty')}
                        </td>
                      </tr>
                    ) : (
                      summary.map((worker) => {
                        const total = payoutEarned(worker)
                        const regular = Number(worker.regular_paid)
                        const purchase = Number(worker.purchase_paid)
                        const trip = Number(worker.trip_paid)
                        return (
                          <tr key={worker.worker_id}>
                            <td>
                              <button
                                className="worker-payouts-name"
                                onClick={() =>
                                  setStatisticsWorker({
                                    id: worker.worker_id,
                                    name: worker.worker_name,
                                  })
                                }
                              >
                                {worker.worker_name}
                              </button>
                              {!worker.is_active && (
                                <span className="worker-payouts-muted"> ({tr('archive')})</span>
                              )}
                            </td>
                            <td
                              className="worker-payouts-split-col"
                              onMouseEnter={(event) => showBarTooltip(event, worker)}
                              onMouseMove={(event) => showBarTooltip(event, worker)}
                              onMouseLeave={() => setBarTooltip(null)}
                            >
                              <span
                                className="worker-payouts-track"
                                style={{
                                  width: maxWorkerPaid > 0 ? `${(total / maxWorkerPaid) * 100}%` : 0,
                                }}
                                role="img"
                                aria-label={`${tr('workerPayoutsRegular')}: ${money(regular)} · ${tr('workerPayoutsPurchases')}: ${money(purchase)} · ${tr('workerPayoutsTrips')}: ${money(trip)}`}
                              >
                                {regular > 0 && (
                                  <i
                                    style={{
                                      background: PAYOUT_SERIES_COLORS.regular,
                                      width: total > 0 ? `${(regular / total) * 100}%` : 0,
                                    }}
                                  />
                                )}
                                {purchase > 0 && (
                                  <i
                                    style={{
                                      background: PAYOUT_SERIES_COLORS.purchase,
                                      width: total > 0 ? `${(purchase / total) * 100}%` : 0,
                                    }}
                                  />
                                )}
                                {trip > 0 && (
                                  <i
                                    style={{
                                      background: PAYOUT_SERIES_COLORS.trip,
                                      width: total > 0 ? `${(trip / total) * 100}%` : 0,
                                    }}
                                  />
                                )}
                              </span>
                            </td>
                            <td className="worker-payouts-number">
                              <strong>{money(total)}</strong>
                            </td>
                            <td className="worker-payouts-number worker-payouts-muted">
                              {worker.payout_count}
                            </td>
                            <td className="worker-payouts-number worker-payouts-muted">
                              {formatDateSr(worker.last_payout_date)}
                            </td>
                          </tr>
                        )
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        ) : null}
      </div>
      {barTooltip && (
        <div
          className={`worker-payouts-tooltip${barTooltip.flipX ? ' is-flipped' : ''}`}
          style={{ left: barTooltip.x, top: barTooltip.y }}
          role="presentation"
        >
          <FinanceTooltipCard label={barTooltip.label} rows={barTooltip.rows} />
        </div>
      )}
      {statisticsWorker && isActivePage && (
        <WorkerStatisticsModal
          key={statisticsWorker.id}
          worker={statisticsWorker}
          onClose={() => setStatisticsWorker(null)}
        />
      )}
    </>
  )
}
