import { useState, useEffect, useMemo } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import FileInput from '../components/FileInput'
import PageHeader from '../components/PageHeader'
import PageTabs from '../components/PageTabs'
import SelectionSummary from '../components/SelectionSummary'
import SortIndicator from '../components/SortIndicator'
import { UI_DASH, formatDateTimeSr, formatMoney2 as fmtMoney } from '../utils/formatters'

export default function BankImport() {
  const location = useLocation()
  const isActivePage = location.pathname === '/bank-import'
  const [files, setFiles] = useState([])
  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [result, setResult] = useState(null)
  const [pageError, setPageError] = useState('')
  const [_clients, setClients] = useState([])
  const [selections, setSelections] = useState({}) // idx -> { selected, type }
  const [parseMeta, setParseMeta] = useState([])
  const [skippedFiles, setSkippedFiles] = useState([])
  const [recentFiles, setRecentFiles] = useState([])
  const [recentSort, setRecentSort] = useState({ col: 'imported_at', asc: false })

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
    setPageError('')
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
    } catch (error) {
      // Молчаливый console.error оставлял пользователя без единого признака сбоя
      setPageError(error?.message || tr('loadError'))
      setFiles([])
    } finally {
      setLoading(false)
    }
  }

  const handleApply = async () => {
    const items = transactions
      .map((tx, i) => ({ tx, i, sel: selections[i] }))
      .filter(({ sel }) => sel?.selected)
    if (items.length === 0) {
      setPageError(tr('selectAtLeastOne'))
      return
    }
    setApplying(true)
    setResult(null)
    setPageError('')
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
    } catch (error) {
      setPageError(error?.message || tr('loadError'))
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

  const clearSelectedTransactions = () => {
    setSelections((current) => {
      const next = { ...current }
      transactions.forEach((transaction, index) => {
        next[index] = {
          ...(next[index] || {}),
          selected: false,
          type: next[index]?.type ?? transaction.type,
        }
      })
      return next
    })
  }

  const selectedTransactions = useMemo(
    () => transactions.filter((_, index) => selections[index]?.selected ?? true),
    [transactions, selections]
  )
  const selectedTotal = useMemo(
    () => selectedTransactions.reduce((sum, tx) => sum + Number(tx.amount || 0), 0),
    [selectedTransactions]
  )

  const toggleRecentSort = (column) => {
    if (recentSort.col === column) {
      setRecentSort({ col: column, asc: !recentSort.asc })
    } else {
      setRecentSort({ col: column, asc: column === 'file_name' })
    }
  }

  const sortedRecentFiles = useMemo(() => {
    const accessor = {
      file_name: (file) => file.file_name || '',
      imported_at: (file) => file.imported_at || '',
      transaction_count: (file) => Number(file.transaction_count ?? 0),
      created: (file) => Number(file.created_income ?? 0) + Number(file.created_expense ?? 0),
    }[recentSort.col]
    if (!accessor) return recentFiles
    const sorted = [...recentFiles].sort((left, right) => {
      const leftValue = accessor(left)
      const rightValue = accessor(right)
      if (typeof leftValue === 'number' && typeof rightValue === 'number') {
        return leftValue - rightValue
      }
      return String(leftValue).localeCompare(String(rightValue))
    })
    return recentSort.asc ? sorted : sorted.reverse()
  }, [recentFiles, recentSort])

  const recentFileTh = (column, label, alignRight = false) => (
    <th
      style={{ cursor: 'pointer', ...(alignRight ? { textAlign: 'right' } : {}) }}
      onClick={() => toggleRecentSort(column)}
    >
      {label} <SortIndicator active={recentSort.col === column} asc={recentSort.asc} />
    </th>
  )

  return (
    <>
      <PageHeader
        title={tr('bankImport')}
        actions={
          <FileInput
            label={loading ? `${tr('loading')}...` : tr('selectFile')}
            accept=".xls,.xlsx"
            multiple
            disabled={loading}
            onChange={handleFileChange}
            selectedName={files.map((file) => file.name).join(', ')}
          />
        }
      />

      <PageTabs group="bank" />

      <div className="page-body">
        {pageError ? <div className="alert alert-danger">{pageError}</div> : null}

        {skippedFiles.length > 0 && (
          <div className="alert alert-warning">
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

        {transactions.length > 0 && (
          <div className="card">
            <div className="card-title">
              {tr('bankImportTransactions')} ({transactions.length})
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
                    <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
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
                      <td style={{ textAlign: 'right' }}>{fmtMoney(tx.amount)} RSD</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="card">
          <div className="card-title">{tr('bankImportRecentFiles')}</div>
          {recentFiles.length === 0 ? (
            <div style={{ color: 'var(--color-text-muted)' }}>{tr('noRecords')}</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {recentFileTh('file_name', tr('bankImportRecentFileName'))}
                    {recentFileTh('imported_at', tr('bankImportRecentAt'))}
                    {recentFileTh('transaction_count', tr('bankImportRecentRows'), true)}
                    {recentFileTh('created', tr('bankImportRecentCreated'), true)}
                  </tr>
                </thead>
                <tbody>
                  {sortedRecentFiles.map((f) => (
                    <tr key={f.id || f.file_hash}>
                      <td>{f.file_name || UI_DASH}</td>
                      <td>{formatDateTimeSr(f.imported_at)}</td>
                      <td style={{ textAlign: 'right' }}>{f.transaction_count ?? 0}</td>
                      <td style={{ textAlign: 'right' }}>
                        {`${f.created_income ?? 0} / ${f.created_expense ?? 0}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {result && (
          <div className="alert alert-success">
            <div>
              {tr('bankImportCreated')
                .replace('{income}', result.created_income)
                .replace('{expense}', result.created_expense)}
              {!!result.matched_income_paid &&
                ` ${tr('bankImportMatchedPaid').replace('{count}', result.matched_income_paid)}`}
            </div>
            {result.errors?.length > 0 && (
              <div style={{ marginTop: '0.35rem' }}>
                {tr('bankImportWarnings')}: {result.errors.join('; ')}
              </div>
            )}
            <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem' }}>
              <Link to="/income" className="dashboard-link">
                {tr('bankImportToIncome')}
              </Link>
              <Link to="/expenses" className="dashboard-link">
                {tr('bankImportToExpenses')}
              </Link>
            </div>
          </div>
        )}
      </div>

      <SelectionSummary
        count={selectedTransactions.length}
        items={[{ label: tr('selectedAmount'), value: `${fmtMoney(selectedTotal)} RSD` }]}
        actions={
          <button type="button" className="btn btn-sm btn-primary" onClick={handleApply} disabled={applying}>
            {applying ? tr('importing') : tr('importSelected')}
          </button>
        }
        onClear={clearSelectedTransactions}
      />
    </>
  )
}
