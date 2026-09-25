import { useCallback, useEffect, useState } from 'react'
import { Link2, Link2Off } from 'lucide-react'
import { api } from '../../api'
import { tr } from '../../i18n'
import { dateLabel, hours, money } from './workDiaryUtils'

const PAYOUT_TYPE_KEYS = {
  regular: 'workerPayoutRegular',
  weekly: 'workerPayoutWeekly',
  monthly: 'workerPayoutMonthly',
  purchase: 'workerPayoutPurchaseShort',
  trip_advance: 'workerPayoutTripAdvanceShort',
  trip_final: 'workerPayoutTripFinalShort',
}

const payoutTypeLabel = (type) => (PAYOUT_TYPE_KEYS[type] ? tr(PAYOUT_TYPE_KEYS[type]) : type)

function periodLabel(start, end) {
  if (!start || !end) return '—'
  return start === end ? dateLabel(start) : `${dateLabel(start)} – ${dateLabel(end)}`
}

function CostRow({ label, value, muted = false, strong = false }) {
  return (
    <tr className={muted ? 'work-diaries-costs-muted' : undefined}>
      <td>{strong ? <strong>{label}</strong> : label}</td>
      <td className="work-diaries-costs-amount">{strong ? <strong>{money(value)}</strong> : money(value)}</td>
    </tr>
  )
}

// Затраты по объекту: начисления дневника (оценка) + расходы проекта. Выплаты работникам,
// явно сопоставленные с начислениями, повторно не прибавляются.
export default function WorkDiaryCostsTab({ projectId, dateFrom, dateTo }) {
  const [costs, setCosts] = useState(null)
  const [loading, setLoading] = useState(false)
  const [savingPayoutId, setSavingPayoutId] = useState(null)

  const load = useCallback(() => {
    if (!projectId) {
      setCosts(null)
      return Promise.resolve()
    }
    setLoading(true)
    const params = { project_id: projectId }
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    return api.workDiaries
      .projectCosts(params)
      .then(setCosts)
      .finally(() => setLoading(false))
  }, [projectId, dateFrom, dateTo])

  useEffect(() => {
    load()
  }, [load])

  const setReconciled = async (payout, reconciled) => {
    setSavingPayoutId(payout.payout_id)
    try {
      await api.workDiaries.setPayoutReconciliation(payout.payout_id, reconciled)
      await load()
    } finally {
      setSavingPayoutId(null)
    }
  }

  if (!projectId) {
    return <div className="card work-diaries-empty-state no-print">{tr('workDiariesSelectProjectCosts')}</div>
  }
  if (!costs) {
    return <div className="card work-diaries-empty-state no-print">{tr('loading')}</div>
  }

  const unmatchedPayouts = costs.payouts.filter((payout) => !payout.diary_reconciled)
  const reconcileButton = (payout, reconciled) => {
    const disabled = savingPayoutId === payout.payout_id || (reconciled && !payout.can_reconcile)
    return (
      <button
        type="button"
        className="btn btn-sm btn-secondary"
        disabled={disabled}
        title={reconciled && !payout.can_reconcile ? tr('workDiariesCostsNoPeriod') : undefined}
        onClick={() => setReconciled(payout, reconciled)}
      >
        {reconciled ? <Link2 size={14} /> : <Link2Off size={14} />}{' '}
        {tr(reconciled ? 'workDiariesCostsReconcile' : 'workDiariesCostsUnreconcile')}
      </button>
    )
  }

  return (
    <div className={`card work-diaries-costs no-print${loading ? ' is-loading' : ''}`}>
      <h3>
        {tr('workDiariesCostsTitle')}
        {costs.project_name ? ` — ${costs.project_name}` : ''}
      </h3>
      {costs.unmatched_payout_amount > 0 ? (
        <p className="work-diaries-costs-warning" role="status">
          {tr('workDiariesCostsUnmatchedWarning', { amount: money(costs.unmatched_payout_amount) })}
        </p>
      ) : null}
      <table className="work-diaries-costs-table">
        <tbody>
          <tr className="work-diaries-costs-group">
            <td colSpan={2}>{tr('workDiariesCostsAccruedTitle')}</td>
          </tr>
          <CostRow label={tr('workDiariesCostsLabor')} value={costs.labor_amount} />
          {costs.day_labor_amount > 0 ? (
            <CostRow label={tr('workDiariesCostsLaborDayPart')} value={costs.day_labor_amount} muted />
          ) : null}
          <CostRow label={tr('workDiariesCostsAllowances')} value={costs.allowance_amount} />
          <CostRow label={tr('workDiariesCostsStockMaterials')} value={costs.stock_material_amount} />
          <tr className="work-diaries-costs-group">
            <td colSpan={2}>{tr('workDiariesCostsProjectExpensesTitle')}</td>
          </tr>
          <CostRow label={tr('workDiariesCostsOtherExpenses')} value={costs.other_expenses_amount} />
          <CostRow label={tr('workDiariesCostsUnmatchedPayouts')} value={costs.unmatched_payout_amount} />
          {costs.payout_excess_amount > 0 ? (
            <CostRow label={tr('workDiariesCostsPayoutExcess')} value={costs.payout_excess_amount} />
          ) : null}
        </tbody>
        <tfoot>
          <tr>
            <td>{tr('workDiariesCostsTotal')}</td>
            <td className="work-diaries-costs-amount">{money(costs.total_cost_amount)}</td>
          </tr>
        </tfoot>
      </table>
      <table className="work-diaries-costs-table work-diaries-costs-result">
        <tbody>
          <CostRow label={tr('workDiariesBillable')} value={costs.billable_amount} />
          <tr className={costs.margin_amount < 0 ? 'work-diaries-margin-negative' : undefined}>
            <td>
              <strong>{tr('workDiariesCostsMargin')}</strong>
            </td>
            <td className="work-diaries-costs-amount">
              <strong>{money(costs.margin_amount)}</strong>
            </td>
          </tr>
          <tr className="work-diaries-costs-group">
            <td colSpan={2}>{tr('workDiariesCostsReference')}</td>
          </tr>
          <CostRow label={tr('workDiariesCostsMatchedPayouts')} value={costs.matched_payout_amount} muted />
          {costs.linked_material_amount > 0 ? (
            <CostRow
              label={tr('workDiariesCostsLinkedMaterials')}
              value={costs.linked_material_amount}
              muted
            />
          ) : null}
          <CostRow label={tr('workDiariesCostsExpenses')} value={costs.expenses_amount} muted />
        </tbody>
      </table>
      <div className="work-diaries-costs-extra">
        <span>
          {tr('workDiariesEntries')}: <strong>{costs.entries_count}</strong>
        </span>
        <span>
          {tr('workDiariesCostsPersonHoursOnSite')}: <strong>{hours(costs.person_hours)}</strong>
        </span>
        {costs.entries_count > 0 ? null : (
          <span className="work-diaries-costs-muted">{tr('workDiariesEmpty')}</span>
        )}
      </div>
      <p className="work-diaries-costs-hint">{tr('workDiariesCostsHint')}</p>

      {unmatchedPayouts.length ? (
        <section className="work-diaries-costs-section">
          <h4>{tr('workDiariesCostsPayoutsTitle')}</h4>
          <p className="work-diaries-costs-hint">{tr('workDiariesCostsPayoutHint')}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('worker')}</th>
                  <th>{tr('workDiariesCostsPayoutType')}</th>
                  <th>{tr('date')}</th>
                  <th>{tr('workDiariesCostsPeriod')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('workDiariesCostsPaid')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('workDiariesCostsPeriodAccrued')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {unmatchedPayouts.map((payout) => (
                  <tr key={payout.payout_id}>
                    <td>{payout.worker_name}</td>
                    <td>{payoutTypeLabel(payout.payout_type)}</td>
                    <td className="date-cell">{dateLabel(payout.date)}</td>
                    <td>{periodLabel(payout.period_start, payout.period_end)}</td>
                    <td style={{ textAlign: 'right' }}>{money(payout.amount)}</td>
                    <td style={{ textAlign: 'right' }}>
                      {payout.period_accrued_amount == null ? '—' : money(payout.period_accrued_amount)}
                    </td>
                    <td>{reconcileButton(payout, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {costs.reconciliations.length ? (
        <section className="work-diaries-costs-section">
          <h4>{tr('workDiariesCostsReconcileTitle')}</h4>
          <p className="work-diaries-costs-hint">{tr('workDiariesCostsReconcileHint')}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('worker')}</th>
                  <th>{tr('workDiariesCostsPeriod')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('workDiariesCostsAccrued')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('workDiariesCostsAccruedInProject')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('workDiariesCostsPaid')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('workDiariesCostsBalance')}</th>
                  <th>{tr('workDiariesCostsPayoutsColumn')}</th>
                </tr>
              </thead>
              <tbody>
                {costs.reconciliations.map((group) => (
                  <tr key={`${group.worker_id}-${group.period_start}-${group.period_end}`}>
                    <td>{group.worker_name}</td>
                    <td>{periodLabel(group.period_start, group.period_end)}</td>
                    <td style={{ textAlign: 'right' }}>{money(group.accrued_amount)}</td>
                    <td style={{ textAlign: 'right' }}>{money(group.accrued_in_project_amount)}</td>
                    <td style={{ textAlign: 'right' }}>{money(group.paid_amount)}</td>
                    <td style={{ textAlign: 'right' }}>
                      {money(Math.abs(group.balance_amount))}
                      {group.balance_amount !== 0 ? (
                        <small className="work-diaries-costs-balance-note">
                          {tr(
                            group.balance_amount > 0 ? 'workDiariesCostsToPay' : 'workDiariesCostsOverpaid'
                          )}
                        </small>
                      ) : null}
                    </td>
                    <td>
                      <div className="work-diaries-costs-payout-list">
                        {group.payouts.map((payout) => (
                          <div key={payout.payout_id} className="work-diaries-costs-payout">
                            <span>
                              {payoutTypeLabel(payout.payout_type)} {dateLabel(payout.date)} —{' '}
                              {money(payout.amount)}
                              {payout.project_name && payout.project_id !== costs.project_id
                                ? ` (${payout.project_name})`
                                : ''}
                              {payout.excess_amount > 0
                                ? `; ${tr('workDiariesCostsExcess', { amount: money(payout.excess_amount) })}`
                                : ''}
                            </span>
                            {reconcileButton(payout, false)}
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  )
}
