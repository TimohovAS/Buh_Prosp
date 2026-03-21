import { useState, useEffect, useMemo } from 'react'
import { api } from '../api'
import { tr } from '../i18n'

function fmt(n) { return n != null ? Number(n).toLocaleString('sr-RS', { minimumFractionDigits: 2 }) : '—' }

function BalanceCell({ value }) {
  const n = Number(value || 0)
  const color = n > 0 ? 'var(--color-success, green)' : n < 0 ? 'var(--color-danger, red)' : undefined
  return <td style={{ textAlign: 'right', color, fontWeight: n !== 0 ? 'bold' : undefined }}>{fmt(n)}</td>
}

export default function CounterpartyBalance() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [sortCol, setSortCol] = useState('net_balance')
  const [sortAsc, setSortAsc] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.incomingInvoices.counterpartyBalance()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  const items = useMemo(() => {
    if (!data?.items) return []
    const q = (search || '').trim().toLowerCase()
    let rows = data.items
    if (q) rows = rows.filter(i => (i.client_name || '').toLowerCase().includes(q))
    return [...rows].sort((a, b) => {
      const av = a[sortCol] ?? 0, bv = b[sortCol] ?? 0
      if (typeof av === 'number' || typeof bv === 'number') {
        return sortAsc ? Number(av) - Number(bv) : Number(bv) - Number(av)
      }
      if (av < bv) return sortAsc ? -1 : 1
      if (av > bv) return sortAsc ? 1 : -1
      return 0
    })
  }, [data, search, sortCol, sortAsc])

  const toggleSort = col => { if (sortCol === col) setSortAsc(v => !v); else { setSortCol(col); setSortAsc(false) } }
  const SortIcon = ({ col }) => sortCol === col ? (sortAsc ? ' \u25B2' : ' \u25BC') : ''

  return (
    <div className="page">
      <div className="page-header">
        <h1>{tr('counterpartyBalance')}</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input className="form-input" placeholder={tr('search')} value={search} onChange={e => setSearch(e.target.value)} style={{ width: 220 }} />
        </div>
      </div>
      <div className="page-body">
        {data && (
          <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
            <div className="card" style={{ flex: 1, padding: '1rem', textAlign: 'center' }}>
              <div style={{ fontSize: '0.85rem', opacity: 0.7 }}>{tr('receivables')}</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--color-success, green)' }}>{fmt(data.total_receivables)}</div>
            </div>
            <div className="card" style={{ flex: 1, padding: '1rem', textAlign: 'center' }}>
              <div style={{ fontSize: '0.85rem', opacity: 0.7 }}>{tr('payables')}</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--color-danger, red)' }}>{fmt(data.total_payables)}</div>
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
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('client_name')}>{tr('client')}<SortIcon col="client_name" /></th>
                  <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('receivables')}>{tr('receivables')}<SortIcon col="receivables" /></th>
                  <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('payables')}>{tr('payables')}<SortIcon col="payables" /></th>
                  <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('net_balance')}>{tr('netBalance')}<SortIcon col="net_balance" /></th>
                </tr>
              </thead>
              <tbody>
                {loading ? <tr><td colSpan={4}>{tr('loading')}</td></tr>
                  : items.length === 0 ? <tr><td colSpan={4}>{tr('noRecords')}</td></tr>
                    : items.map((item, idx) => (
                      <tr key={item.client_id || idx}>
                        <td>{item.client_name}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(item.receivables)}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(item.payables)}</td>
                        <BalanceCell value={item.net_balance} />
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
