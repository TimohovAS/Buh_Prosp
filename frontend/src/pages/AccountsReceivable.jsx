import { useState, useEffect } from 'react'
import { api } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'

function fmt(n) {
  return (n ?? 0).toLocaleString('sr-RS')
}

function formatDate(s) {
  if (!s) return '—'
  const d = new Date(s + 'T12:00:00')
  return d.toLocaleDateString('sr-RS', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export default function AccountsReceivable() {
  const [items, setItems] = useState([])
  const [totals, setTotals] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [onlyOverdue, setOnlyOverdue] = useState(false)

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

  useEffect(load, [])

  const filtered = onlyOverdue ? items.filter((i) => (i.days_overdue ?? 0) > 0) : items

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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.5rem' }}>
        <h1>{tr('financeAR')}</h1>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={onlyOverdue}
            onChange={(e) => setOnlyOverdue(e.target.checked)}
          />
          <span>{tr('arFilterOverdue')}</span>
        </label>
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
                <th>{tr('invoiceNumber')}</th>
                <th>{tr('client')}</th>
                <th>{tr('date')}</th>
                <th>{tr('valuta')}</th>
                <th>{tr('amount')}</th>
                <th>{tr('financeDaysOverdue')}</th>
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
                    <td>{i.client_name || '—'}</td>
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
                        🔗 {tr('bankTransactions')}
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
