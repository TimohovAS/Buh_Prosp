import { useState, useEffect, useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import SearchInput from '../components/SearchInput'

function fmt(n) {
  return (n ?? 0).toLocaleString('sr-RS')
}

function formatDate(s) {
  if (!s) return '\u2014'
  const d = new Date(s + 'T12:00:00')
  return d.toLocaleDateString('sr-RS', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export default function AccountsReceivable() {
  const location = useLocation()
  const isActivePage = location.pathname === '/finance/ar'
  const [items, setItems] = useState([])
  const [totals, setTotals] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [onlyOverdue, setOnlyOverdue] = useState(false)
  const [search, setSearch] = useState('')
  const [sortCol, setSortCol] = useState('days_overdue')
  const [sortAsc, setSortAsc] = useState(false)

  const load = () => {
    setLoading(true)
    api.finance.ar()
      .then((data) => {
        setItems(data.items || [])
        setTotals(data.totals || null)
        setError(null)
      })
      .catch((e) => {
        setError(e.message)
        setItems([])
        setTotals(null)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return
    load()
  }, [isActivePage])

  const filtered = useMemo(() => {
    const s = (search || '').trim().toLowerCase()
    let rows = onlyOverdue ? items.filter((i) => (i.days_overdue ?? 0) > 0) : items
    if (s) rows = rows.filter(i =>
      (i.invoice_number || '').toLowerCase().includes(s) ||
      (i.client_name || '\u2014').toLowerCase().includes(s)
    )
    return [...rows].sort((a, b) => {
      const valA = a[sortCol] ?? 0
      const valB = b[sortCol] ?? 0
      if (valA < valB) return sortAsc ? -1 : 1
      if (valA > valB) return sortAsc ? 1 : -1
      return 0
    })
  }, [items, onlyOverdue, search, sortCol, sortAsc])

  const toggleSort = (col) => {
    if (sortCol === col) setSortAsc(v => !v)
    else { setSortCol(col); setSortAsc(true) }
  }
  const SortIcon = ({ col }) => {
    if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 4 }}>{'\u2195'}</span>
    return <span style={{ marginLeft: 4 }}>{sortAsc ? '\u2191' : '\u2193'}</span>
  }

  if (loading && items.length === 0) {
    return (
      <div className="page">
        <h1>{tr('financeAR')}</h1>
        <p>{tr('loading')}</p>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">{tr('financeAR')}</h1>
        </div>
        <div className="page-header-actions">
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={onlyOverdue}
              onChange={(e) => setOnlyOverdue(e.target.checked)}
            />
            <span>{tr('arFilterOverdue')}</span>
          </label>
          <SearchInput
            placeholder={tr('search')}
            value={search}
            onChange={setSearch}
            style={{ width: 200 }}
          />
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>{error}</div>
      )}

      {totals && (
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
          <div className="card" style={{ minWidth: 140 }}>
            <div className="card-title">{tr('total')}</div>
            <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.ar_total)} RSD</div>
          </div>
          <div className="card" style={{ minWidth: 140, borderLeft: '4px solid var(--color-danger)' }}>
            <div className="card-title">{tr('financeAROverdue')}</div>
            <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{fmt(totals.ar_overdue)} RSD</div>
          </div>
        </div>
      )}

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('invoice_number')}>{tr('invoiceNumber')} <SortIcon col="invoice_number" /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('client_name')}>{tr('client')} <SortIcon col="client_name" /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('issued_date')}>{tr('date')} <SortIcon col="issued_date" /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('due_date')}>{tr('valuta')} <SortIcon col="due_date" /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')} <SortIcon col="amount" /></th>
                <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('days_overdue')}>{tr('financeDaysOverdue')} <SortIcon col="days_overdue" /></th>
                <th style={{ width: 140 }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>
                    {onlyOverdue ? tr('financeNoOverdue') : tr('noData')}
                  </td>
                </tr>
              ) : (
                filtered.map((i) => (
                  <tr key={i.income_id}>
                    <td>{i.invoice_number}</td>
                    <td>{i.client_name || '\u2014'}</td>
                    <td>{formatDate(i.issued_date)}</td>
                    <td>{formatDate(i.due_date)}</td>
                    <td>{fmt(i.amount)} RSD</td>
                    <td style={{ color: (i.days_overdue ?? 0) > 0 ? 'var(--color-danger)' : undefined }}>
                      {Math.max(0, i.days_overdue ?? 0)} {tr('days')}
                    </td>
                    <td>
                      <a
                        href="/bank"
                        className="btn btn-sm btn-primary"
                        style={{ textDecoration: 'none' }}
                      >
                        {'\uD83D\uDD17'} {tr('bankTransactions')}
                      </a>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
