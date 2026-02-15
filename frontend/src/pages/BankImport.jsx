import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'

export default function BankImport() {
  const [file, setFile] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [result, setResult] = useState(null)
  const [clients, setClients] = useState([])
  const [selections, setSelections] = useState({}) // idx -> { selected, type }

  useEffect(() => { api.clients.listBrief().then(setClients) }, [])

  const handleFileChange = async (e) => {
    const f = e.target.files?.[0] || null
    setFile(f)
    setTransactions([])
    setSelections({})
    setResult(null)
    if (!f) return
    setLoading(true)
    try {
      const { transactions: tx } = await api.bankImport.parse(f)
      setTransactions(tx)
      const sel = {}
      tx.forEach((t, i) => { sel[i] = { selected: true, type: t.type } })
      setSelections(sel)
    } catch (e) {
      alert(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleApply = async () => {
    const items = transactions
      .map((tx, i) => ({ tx, i, sel: selections[i] }))
      .filter(({ sel }) => sel?.selected)
    if (items.length === 0) return alert(tr('selectAtLeastOne'))
    setApplying(true)
    setResult(null)
    try {
      const body = {
        transactions: items.map(({ tx, i }) => ({
          type: selections[i].type,
          tx,
          client_id: selections[i].client_id || null,
          invoice_number: selections[i].invoice_number || null,
        })),
      }
      const res = await api.bankImport.apply(body)
      setResult(res)
      setTransactions([])
      setFile(null)
      setSelections({})
    } catch (e) {
      alert(e.message)
    } finally {
      setApplying(false)
    }
  }

  const setSelection = (idx, field, value) => {
    setSelections((s) => ({
      ...s,
      [idx]: { ...(s[idx] || {}), selected: s[idx]?.selected ?? true, type: s[idx]?.type ?? transactions[idx]?.type, [field]: value },
    }))
  }

  const toggleSelect = (idx) => {
    setSelections((s) => ({
      ...s,
      [idx]: { ...(s[idx] || {}), selected: !(s[idx]?.selected ?? true), type: s[idx]?.type ?? transactions[idx]?.type },
    }))
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('bankImport')}</h1>
      </div>

      <div className="page-body">
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div className="form-group">
          <label className="form-label">{tr('bankImportFile')}</label>
          <input
            type="file"
            accept=".xls,.xlsx"
            onChange={handleFileChange}
            disabled={loading}
          />
          {loading && <span style={{ marginLeft: '0.5rem', color: 'var(--color-text-muted)' }}>{tr('loading')}...</span>}
        </div>
      </div>

      {result && (
        <div className="card" style={{ marginBottom: '1rem', borderColor: 'var(--color-success)' }}>
          <p style={{ margin: 0 }}>
            {tr('bankImportCreated').replace('{income}', result.created_income).replace('{expense}', result.created_expense)}
            {result.errors?.length > 0 && (
              <span style={{ color: 'var(--color-warning)', marginLeft: '0.5rem' }}>
                {tr('bankImportWarnings')}: {result.errors.join('; ')}
              </span>
            )}
          </p>
          <Link to="/income" style={{ marginTop: '0.5rem', display: 'inline-block' }}>{tr('bankImportToIncome')}</Link>
          <Link to="/expenses" style={{ marginTop: '0.5rem', marginLeft: '1rem', display: 'inline-block' }}>{tr('bankImportToExpenses')}</Link>
        </div>
      )}

      {transactions.length > 0 && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ margin: 0 }}>{tr('bankImportTransactions')} ({transactions.length})</h3>
            <button className="btn btn-primary" onClick={handleApply} disabled={applying}>
              {applying ? tr('importing') : tr('importSelected')}
            </button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 40 }}></th>
                  <th>{tr('date')}</th>
                  <th>{tr('type')}</th>
                  <th>{tr('description')}</th>
                  <th>{tr('client')}</th>
                  <th>{tr('amount')}</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((tx, i) => (
                  <tr key={i}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selections[i]?.selected ?? true}
                        onChange={() => toggleSelect(i)}
                      />
                    </td>
                    <td>{tx.date}</td>
                    <td>
                      <select
                        value={selections[i]?.type ?? tx.type}
                        onChange={(e) => setSelection(i, 'type', e.target.value)}
                        className="form-input"
                        style={{ width: 'auto', minWidth: 100 }}
                      >
                        <option value="income">{tr('incomeLabel')}</option>
                        <option value="expense">{tr('expenseLabel')}</option>
                      </select>
                    </td>
                    <td style={{ maxWidth: 200 }}>{(tx.description || '').slice(0, 50)}</td>
                    <td style={{ maxWidth: 150 }}>{(tx.payer_beneficiary || '').slice(0, 40)}</td>
                    <td>{tx.amount?.toLocaleString?.('sr-RS')} RSD</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      </div>
    </>
  )
}
