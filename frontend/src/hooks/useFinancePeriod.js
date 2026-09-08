import { useState } from 'react'
import { localDateIso } from '../utils/formatters'
import { cashflowRange, cashflowGrouping, shiftCashflowPeriod } from '../utils/cashflow'

export default function useFinancePeriod() {
  const today = localDateIso()
  const [period, setPeriod] = useState('year')
  const [anchor, setAnchor] = useState(today)
  const [custom, setCustom] = useState({ from: '', to: '' })
  const [grouping, setGrouping] = useState('auto')
  const range = cashflowRange(period, anchor, custom.from, custom.to)
  const from = range.from
  const to = range.to > today ? today : range.to
  const validation =
    !from || !to
      ? 'cashflowChooseDates'
      : from > to
        ? 'cashflowInvalidRange'
        : from > today
          ? 'cashflowFutureRange'
          : ''
  const groupBy = cashflowGrouping(from, to, grouping)
  return {
    today,
    period,
    anchor,
    from,
    to,
    groupBy,
    validation,
    grouping: grouping === 'day' && groupBy !== 'day' ? groupBy : grouping,
    incomplete: range.to > today,
    canNext:
      period !== 'custom' && cashflowRange(period, shiftCashflowPeriod(anchor, period, 1)).from <= today,
    setGrouping,
    selectPeriod: (next) => {
      if (period === 'custom' && from && from <= today) setAnchor(from)
      if (next === 'custom') setCustom({ from, to })
      setPeriod(next)
      setGrouping('auto')
    },
    move: (direction) => setAnchor(shiftCashflowPeriod(anchor, period, direction)),
    current: () => setAnchor(today),
    changeDate: (field, value) => {
      setCustom({ from, to, [field]: value })
      setPeriod('custom')
    },
  }
}
