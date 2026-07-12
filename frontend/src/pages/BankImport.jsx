import { useState, useEffect, useMemo } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import PageTabs from '../components/PageTabs'
import SelectionSummary from '../components/SelectionSummary'
import { formatMoney2 as fmtMoney } from '../utils/formatters'

export default function BankImport() {
  const location = useLocation()
  const isActivePage = location.pathname === '/bank-import'
  const [_files, setFiles] = useState([])
  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [result, setResult] = useState(null)
  const [_clients, setClients] = useState([])
  const [selections, setSelections] = useState({}) // idx -> { selected, type }
  const [parseMeta, setParseMeta] = useState([])
  const [skippedFiles, setSkippedFiles] = useState([])
  const [recentFiles, setRecentFiles] = useState([])

  useEffect(() => {
    if (!isActivePage) return
    api.clients.listBrief().then(setClients)
  }, [isActivePage])
  useEffect(() => {
    if (!isActivePage) return
    api.bankImport
      .recentFiles(10)
      .then((r) => setRecentFiles(r.items || []))
      .catch(() => setRecentFiles([]))
  }, [isActivePage])

  const handleFileChange = async (e) => {
    const selectedFiles = e.target.files || []
    if (selectedFiles.length === 0) return
    setFiles(Array.from(selectedFiles))
    setTransactions([])
    setSelections({})
    setParseMeta([])
    setSkippedFiles([])
    setResult(null)
    setLoading(true)
    try {
      const parsed = await api.bankImport.parse(selectedFiles)
      const tx = parsed.transactions || []
      const parsedFiles = parsed.parsed_files || []

      // Набор хэшей файлов, которые были ранее импортированы
      const previouslyImportedHashes = new Set(
        parsedFiles.filter((f) => f.previously_imported).map((f) => f.file_hash)
      )

      setTransactions(tx)
      const sel = {}
      tx.forEach((t, i) => {
        // Отмечаем только транзакции из новых (ранее не импортированных) файлов
        const isNew = !previouslyImportedHashes.has(t.file_hash)
        sel[i] = { selected: isNew, type: t.type }
      })
      setSelections(sel)
      setParseMeta(parsedFiles)
      setSkippedFiles(parsed.skipped_files || [])
      if (Array.isArray(parsed.recent_files)) setRecentFiles(parsed.recent_files)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleApply = async () => {
    const items = transactions
      .map((tx, i) => ({ tx, i, sel: selections[i] }))
      .filter(({ sel }) => sel?.selected)
    if (items.length === 0) {
      console.error(tr('selectAtLeastOne'))
      return
    }
    setApplying(true)
    setResult(null)
    try {
      const body = {
        transactions: items.map(({ tx, i }) => ({
          type: selections[i].type,
          tx,
          file_hash: tx.file_hash || null,
          client_id: selections[i].client_id || null,
          invoice_number: selections[i].invoice_number || null,
        })),
        files: parseMeta || [],
      }
      const res = await api.bankImport.apply(body)
      setResult(res)
      setTransactions([])
      setFiles([])
      setSelections({})
      setParseMeta([])
      setSkippedFiles([])
      // Всегда перезагружаем список файлов с сервера после применения
      api.bankImport
        .recentFiles(10)
        .then((r) => setRecentFiles(r.items || []))
        .catch(() => {})
    } catch (e) {
      console.error(e)
    } finally {
      setApplying(false)
    }
  }

  const setSelection = (idx, field, value) => {
    setSelections((s) => ({
      ...s,
      [idx]: {
        ...(s[idx] || {}),
        selected: s[idx]?.selected ?? true,
        type: s[idx]?.type ?? transactions[idx]?.type,
        [field]: value,
      },
    }))
  }

  const toggleSelect = (idx) => {
    setSelections((s) => ({
      ...s,
      [idx]: {
        ...(s[idx] || {}),
        selected: !(s[idx]?.selected ?? true),
        type: s[idx]?.type ?? transactions[idx]?.type,
      },
    }))
  }

  const selectedTransactions = useMemo(
    () => transactions.filter((_, index) => selections[index]?.selected ?? true),
    [transactions, selections]
  )
  const selectedTotal = useMemo(
    () => selectedTransactions.reduce((sum, tx) => sum + Number(tx.amount || 0), 0),
    [selectedTransactions]
  )

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('bankImport')}</h1>
      </div>

      <PageTabs group="bank" />

      <div className="page-body">
        <div className="card" style={{ marginBottom: '1rem' }}>
          <div className="form-group">
            <label className="form-label">{tr('bankImportFile')}</label>
            <input type="file" multiple accept=".xls,.xlsx" onChange={handleFileChange} disabled={loading} />
            {loading && (
              <span style={{ marginLeft: '0.5rem', color: 'var(--color-text-muted)' }}>
                {tr('loading')}...
              </span>
            )}
          </div>
          {skippedFiles && skippedFiles.length > 0 && (
            <div style={{ marginTop: '0.75rem', color: 'var(--color-warning)' }}>
              <strong>
                {tr('bankImportSkippedFiles')} ({skippedFiles.length}):
              </strong>
              <ul style={{ margin: '0.25rem 0 0 1.5rem', padding: 0 }}>
                {skippedFiles.map((sf, idx) => (
                  <li key={idx}>
                    {sf.file_name} - {sf.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {transactions.length > 0 && (
          <div className="card" style={{ marginBottom: '1rem' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '1rem',
              }}
            >
              <h3 style={{ margin: 0 }}>
                {tr('bankImportTransactions')} ({transactions.length})
              </h3>
              <button className="btn btn-primary" onClick={handleApply} disabled={applying}>
                {applying ? tr('importing') : tr('importSelected')}
              </button>
            </div>
            <SelectionSummary
              count={selectedTransactions.length}
              items={[{ label: tr('selectedAmount'), value: `${fmtMoney(selectedTotal)} RSD` }]}
            />
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
                    <tr key={i} className={(selections[i]?.selected ?? true) ? 'record-row-selected' : ''}>
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

        <div className="card" style={{ marginBottom: '1rem' }}>
          <h3 style={{ marginTop: 0 }}>{tr('bankImportRecentFiles')}</h3>
          {recentFiles.length === 0 ? (
            <div style={{ color: 'var(--color-text-muted)' }}>{tr('noRecords')}</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{tr('bankImportRecentFileName')}</th>
                    <th>{tr('bankImportRecentAt')}</th>
                    <th>{tr('bankImportRecentRows')}</th>
                    <th>{tr('bankImportRecentCreated')}</th>
                  </tr>
                </thead>
                <tbody>
                  {recentFiles.map((f) => (
                    <tr key={f.id || f.file_hash}>
                      <td>{f.file_name || '-'}</td>
                      <td>{f.imported_at ? new Date(f.imported_at).toLocaleString() : '-'}</td>
                      <td>{f.transaction_count ?? 0}</td>
                      <td>{`${f.created_income ?? 0} / ${f.created_expense ?? 0}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {result && (
          <div className="card" style={{ marginBottom: '1rem', borderColor: 'var(--color-success)' }}>
            <p style={{ margin: 0 }}>
              {tr('bankImportCreated')
                .replace('{income}', result.created_income)
                .replace('{expense}', result.created_expense)}
              {!!result.matched_income_paid && (
                <span style={{ marginLeft: '0.5rem', color: 'var(--color-success)' }}>
                  {tr('bankImportMatchedPaid').replace('{count}', result.matched_income_paid)}
                </span>
              )}
              {result.errors?.length > 0 && (
                <span style={{ color: 'var(--color-warning)', marginLeft: '0.5rem' }}>
                  {tr('bankImportWarnings')}: {result.errors.join('; ')}
                </span>
              )}
            </p>
            <Link to="/income" style={{ marginTop: '0.5rem', display: 'inline-block' }}>
              {tr('bankImportToIncome')}
            </Link>
            <Link to="/expenses" style={{ marginTop: '0.5rem', marginLeft: '1rem', display: 'inline-block' }}>
              {tr('bankImportToExpenses')}
            </Link>
          </div>
        )}
      </div>
    </>
  )
}
