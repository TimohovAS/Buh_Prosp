export function selectReceivables(items, filter, search, sortColumn, ascending) {
  const query = search.trim().toLocaleLowerCase()
  return items
    .filter((item) => {
      const matchesFilter =
        filter === 'all' ||
        (filter === 'overdue' ? Number(item.days_overdue) > 0 : item.aging_bucket === filter)
      const matchesSearch =
        !query ||
        [item.invoice_number, item.client_name].some((value) =>
          String(value || '')
            .toLocaleLowerCase()
            .includes(query)
        )
      return matchesFilter && matchesSearch
    })
    .sort((a, b) => {
      const left = a[sortColumn]
      const right = b[sortColumn]
      if (left == null || right == null)
        return left == null ? (right == null ? a.income_id - b.income_id : 1) : -1
      const comparison = ['amount', 'amount_full', 'amount_paid', 'days_overdue'].includes(sortColumn)
        ? Number(left) - Number(right)
        : String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: 'base' })
      return comparison ? comparison * (ascending ? 1 : -1) : a.income_id - b.income_id
    })
}

export function receivablesTotal(items) {
  return items.reduce((total, item) => total + Math.round(Number(item.amount) * 100), 0) / 100
}
