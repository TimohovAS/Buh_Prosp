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
  const [modal, setModal] = useState(null) // { income_id, invoice_number }
  const [paidDate, setPaidDate] = useState(new Date().toISOString().slice(0, 10))
  const [submitting, setSubmitting] = useState(false)

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

  const filtered = onlyOverdue ? items.filter((i) => i.days_outstanding > 30) : items

  const openMarkPaid = (item) => {
    setModal({ income_id: item.income_id, invoice_number: item.invoice_number })
    setPaidDate(new Date().toISOString().slice(0, 10))
  }

  const closeModal = () => {
    setModal(null)
    setSubmitting(false)
  }

  const handleMarkPaid = async (e) => {
    e.preventDefault()
    if (!modal?.income_id) return
    setSubmitting(true)
    try {
      await api.income.markPaid(modal.income_id, { paid_date: paidDate })
      closeModal()
      load()
    } catch (err) {
      alert(err.message)
    } finally {
      setSubmitting(false)
    }
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
                <th>{tr('amount')}</th>
                <th>{tr('financeDaysOverdue')}</th>
                <th style={{ width: 140 }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>
                    {onlyOverdue ? tr('financeNoOverdue') : tr('noData')}
                  </td>
                </tr>
              ) : (
                filtered.map((i) => (
                  <tr key={i.income_id}>
                    <td>{i.invoice_number}</td>
                    <td>{i.client_name || '—'}</td>
                    <td>{formatDate(i.issued_date)}</td>
                    <td>{fmt(i.amount)} RSD</td>
                    <td style={{ color: i.days_outstanding > 30 ? 'var(--color-danger)' : undefined }}>
                      {i.days_outstanding} {tr('days')}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-sm btn-primary"
                        onClick={() => openMarkPaid(i)}
                      >
                        {tr('arMarkPaid')}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Модалка: отметка оплаты */}
      {modal && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{tr('arMarkPaid')} — {modal.invoice_number}</h3>
              <button type="button" className="modal-close" onClick={closeModal} aria-label={tr('close')}>×</button>
            </div>
            <form onSubmit={handleMarkPaid}>
              <div className="modal-body">
                <div className="form-group">
                  <label>{tr('arPaidDate')}</label>
                  <DatePicker
                    value={paidDate}
                    onChange={setPaidDate}
                    required
                    className="form-input"
                    style={{ width: '100%' }}
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={closeModal}>
                  {tr('cancel')}
                </button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? tr('loading') : tr('arMarkPaid')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
