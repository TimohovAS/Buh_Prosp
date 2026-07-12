import { useEffect, useState } from 'react'
import { api } from '../../api'
import { tr } from '../../i18n'
import { money } from './workDiaryUtils'

// Затраты по объекту: расходы из модуля Расходы + труд/надбавки/складские материалы из дневника
export default function WorkDiaryCostsTab({ projectId, dateFrom, dateTo }) {
  const [costs, setCosts] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!projectId) {
      setCosts(null)
      return
    }
    setLoading(true)
    const params = { project_id: projectId }
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    api.workDiaries
      .projectCosts(params)
      .then(setCosts)
      .finally(() => setLoading(false))
  }, [projectId, dateFrom, dateTo])

  if (!projectId) {
    return <div className="card work-diaries-empty-state no-print">{tr('workDiariesSelectProjectCosts')}</div>
  }
  if (loading || !costs) {
    return <div className="card work-diaries-empty-state no-print">{tr('loading')}</div>
  }

  const rows = [
    [tr('workDiariesCostsExpenses'), costs.expenses_amount],
    [tr('workDiariesCostsLabor'), costs.labor_amount],
    [tr('workDiariesCostsAllowances'), costs.allowance_amount],
    [tr('workDiariesCostsStockMaterials'), costs.stock_material_amount],
  ]

  return (
    <div className="card work-diaries-costs no-print">
      <h3>
        {tr('workDiariesCostsTitle')}
        {costs.project_name ? ` — ${costs.project_name}` : ''}
      </h3>
      <table className="work-diaries-costs-table">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <td>{label}</td>
              <td className="work-diaries-costs-amount">{money(value)}</td>
            </tr>
          ))}
          {costs.linked_material_amount > 0 ? (
            <tr className="work-diaries-costs-muted">
              <td>{tr('workDiariesCostsLinkedMaterials')}</td>
              <td className="work-diaries-costs-amount">{money(costs.linked_material_amount)}</td>
            </tr>
          ) : null}
        </tbody>
        <tfoot>
          <tr>
            <td>{tr('workDiariesCostsTotal')}</td>
            <td className="work-diaries-costs-amount">{money(costs.total_cost_amount)}</td>
          </tr>
        </tfoot>
      </table>
      <div className="work-diaries-costs-extra">
        <span>
          {tr('workDiariesBillable')}: <strong>{money(costs.billable_amount)}</strong>
        </span>
        <span>
          {tr('workDiariesEntries')}: <strong>{costs.entries_count}</strong>
        </span>
        {costs.entries_count > 0 ? null : (
          <span className="work-diaries-costs-muted">{tr('workDiariesEmpty')}</span>
        )}
      </div>
      <p className="work-diaries-costs-hint">{tr('workDiariesCostsHint')}</p>
    </div>
  )
}
