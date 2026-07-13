import { useMemo } from 'react'
import { tr } from '../../i18n'
import { money, num, unitLabel } from './workDiaryUtils'

// Сводка использованных материалов по загруженным записям (фильтры страницы уже применены).
// Группировка: название + единица + источник; количество суммируется только там, где оно указано.
export default function WorkDiaryMaterialsTab({ entries, loading }) {
  const rows = useMemo(() => {
    const groups = new Map()
    entries.forEach((entry) => {
      ;(entry.materials || []).forEach((material) => {
        const description = (material.description || '').trim()
        if (!description) return
        const key = [description.toLowerCase(), material.unit || '', material.source].join('|')
        let row = groups.get(key)
        if (!row) {
          row = {
            description,
            unit: material.unit || '',
            source: material.source,
            quantity: 0,
            hasQuantity: false,
            amount: 0,
            count: 0,
          }
          groups.set(key, row)
        }
        if (material.quantity != null) {
          row.quantity += num(material.quantity)
          row.hasQuantity = true
        }
        row.amount += num(material.amount)
        row.count += 1
      })
    })
    return [...groups.values()].sort((left, right) => right.amount - left.amount)
  }, [entries])

  const totalAmount = rows.reduce((sum, row) => sum + row.amount, 0)

  return (
    <div className="card">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{tr('workDiariesMaterials')}</th>
              <th>{tr('workDiariesMaterialSource')}</th>
              <th style={{ textAlign: 'right' }}>{tr('quantity')}</th>
              <th>{tr('unit')}</th>
              <th style={{ textAlign: 'right' }}>{tr('workDiariesMaterialsEntriesCount')}</th>
              <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6}>{tr('loading')}</td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ color: 'var(--color-text-muted)' }}>
                  {tr('workDiariesMaterialsEmpty')}
                </td>
              </tr>
            ) : (
              rows.map((row, index) => (
                <tr key={index}>
                  <td>{row.description}</td>
                  <td>
                    {tr(
                      row.source === 'expense'
                        ? 'workDiariesMaterialSourceExpense'
                        : 'workDiariesMaterialSourceStock'
                    )}
                  </td>
                  <td style={{ textAlign: 'right' }}>{row.hasQuantity ? row.quantity : '-'}</td>
                  <td>{row.unit ? unitLabel(row.unit) : '-'}</td>
                  <td style={{ textAlign: 'right' }}>{row.count}</td>
                  <td style={{ textAlign: 'right' }}>{money(row.amount)}</td>
                </tr>
              ))
            )}
          </tbody>
          {rows.length > 0 ? (
            <tfoot>
              <tr>
                <td colSpan={5} style={{ fontWeight: 600 }}>
                  {tr('total')}
                </td>
                <td style={{ textAlign: 'right', fontWeight: 600 }}>{money(totalAmount)}</td>
              </tr>
            </tfoot>
          ) : null}
        </table>
      </div>
    </div>
  )
}
