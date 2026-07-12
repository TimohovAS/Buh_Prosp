import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import PageHeader from '../components/PageHeader'
import PageTabs from '../components/PageTabs'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import { formatMoney2OrDash as fmt } from '../utils/formatters'

function BalanceCell({ value }) {
  const n = Number(value || 0)
  const color = n > 0 ? 'var(--color-success, green)' : n < 0 ? 'var(--color-danger, red)' : undefined
  return <td style={{ textAlign: 'right', color, fontWeight: n !== 0 ? 'bold' : undefined }}>{fmt(n)}</td>
}

export default function CounterpartyBalance() {
  const location = useLocation()
  const isActivePage = location.pathname === '/counterparty-balance'
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [sortCol, setSortCol] = useState('net_balance')
  const [sortAsc, setSortAsc] = useState(true)

  useEffect(() => {
    if (!isActivePage) return
    setLoading(true)
    api.incomingInvoices
      .counterpartyBalance()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [isActivePage])

  const items = useMemo(() => {
    if (!data?.items) return []
    const q = (search || '').trim().toLowerCase()
    let rows = data.items
    if (q) rows = rows.filter((item) => (item.client_name || '').toLowerCase().includes(q))
    return [...rows].sort((left, right) => {
      const leftValue = left[sortCol] ?? 0
      const rightValue = right[sortCol] ?? 0
      if (typeof leftValue === 'number' || typeof rightValue === 'number') {
        return sortAsc ? Number(leftValue) - Number(rightValue) : Number(rightValue) - Number(leftValue)
      }
      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
  }, [data, search, sortCol, sortAsc])

  const toggleSort = (column) => {
    if (sortCol === column) {
      setSortAsc((value) => !value)
      return
    }
    setSortCol(column)
    setSortAsc(false)
  }

  return (
    <div className="page">
      <PageHeader
        title={tr('counterpartyBalance')}
        actions={
          <SearchInput
            placeholder={tr('search')}
            value={search}
            onChange={setSearch}
            style={{ width: 220 }}
          />
        }
      />
      <PageTabs group="counterparties" />
      <div className="page-body">
        {data && (
          <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
            <div className="card" style={{ flex: 1, padding: '1rem', textAlign: 'center' }}>
              <div style={{ fontSize: '0.85rem', opacity: 0.7 }}>{tr('receivables')}</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--color-success, green)' }}>
                {fmt(data.total_receivables)}
              </div>
              <div className="balance-summary-breakdown">
                {tr('issuedLoans')}: {fmt(data.total_issued_loans)}
              </div>
            </div>
            <div className="card" style={{ flex: 1, padding: '1rem', textAlign: 'center' }}>
              <div style={{ fontSize: '0.85rem', opacity: 0.7 }}>{tr('payables')}</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--color-danger, red)' }}>
                {fmt(data.total_payables)}
              </div>
              <div className="balance-summary-breakdown">
                {tr('borrowedLoans')}: {fmt(data.total_borrowed_loans)}
              </div>
            </div>
            <div className="card" style={{ flex: 1, padding: '1rem', textAlign: 'center' }}>
              <div style={{ fontSize: '0.85rem', opacity: 0.7 }}>{tr('netBalance')}</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{fmt(data.total_net_balance)}</div>
            </div>
          </div>
        )}
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('client_name')}>
                    {tr('client')} <SortIndicator active={sortCol === 'client_name'} asc={sortAsc} />
                  </th>
                  <th
                    style={{ textAlign: 'right', cursor: 'pointer' }}
                    onClick={() => toggleSort('issued_loans')}
                  >
                    {tr('issuedLoans')} <SortIndicator active={sortCol === 'issued_loans'} asc={sortAsc} />
                  </th>
                  <th
                    style={{ textAlign: 'right', cursor: 'pointer' }}
                    onClick={() => toggleSort('receivables')}
                  >
                    {tr('receivables')} <SortIndicator active={sortCol === 'receivables'} asc={sortAsc} />
                  </th>
                  <th
                    style={{ textAlign: 'right', cursor: 'pointer' }}
                    onClick={() => toggleSort('borrowed_loans')}
                  >
                    {tr('borrowedLoans')}{' '}
                    <SortIndicator active={sortCol === 'borrowed_loans'} asc={sortAsc} />
                  </th>
                  <th
                    style={{ textAlign: 'right', cursor: 'pointer' }}
                    onClick={() => toggleSort('payables')}
                  >
                    {tr('payables')} <SortIndicator active={sortCol === 'payables'} asc={sortAsc} />
                  </th>
                  <th
                    style={{ textAlign: 'right', cursor: 'pointer' }}
                    onClick={() => toggleSort('net_balance')}
                  >
                    {tr('netBalance')} <SortIndicator active={sortCol === 'net_balance'} asc={sortAsc} />
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6}>{tr('loading')}</td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={6}>{tr('noRecords')}</td>
                  </tr>
                ) : (
                  items.map((item, index) => (
                    <tr key={item.client_id || index}>
                      <td>{item.client_name}</td>
                      <td style={{ textAlign: 'right' }}>{fmt(item.issued_loans)}</td>
                      <td style={{ textAlign: 'right' }}>{fmt(item.receivables)}</td>
                      <td style={{ textAlign: 'right' }}>{fmt(item.borrowed_loans)}</td>
                      <td style={{ textAlign: 'right' }}>{fmt(item.payables)}</td>
                      <BalanceCell value={item.net_balance} />
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
