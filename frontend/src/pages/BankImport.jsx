import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  CircleAlert,
  CircleCheck,
  FileSpreadsheet,
  History,
  RefreshCw,
  UploadCloud,
} from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import FileInput from '../components/FileInput'
import PageHeader from '../components/PageHeader'
import PageTabs from '../components/PageTabs'
import SearchInput from '../components/SearchInput'
import SelectionSummary from '../components/SelectionSummary'
import SortIndicator from '../components/SortIndicator'
import StatusBadge from '../components/StatusBadge'
import { UI_DASH, formatDateSr, formatDateTimeSr, formatMoney2 as fmtMoney } from '../utils/formatters'

const HISTORY_LIMIT = 50

function formatFileSize(value) {
  const bytes = Number(value || 0)
  if (!bytes) return UI_DASH
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function getImportStatus(file) {
  const created = Number(file.created_income || 0) + Number(file.created_expense || 0)
  const rows = Number(file.transaction_count || 0)
  const errors = Number(file.errors_count || 0)

  if (errors > 0) return { key: 'attention', tone: 'warning', label: tr('bankImportStatusAttention') }
  if (rows > 0 && created === 0) return { key: 'no-new', tone: 'muted', label: tr('bankImportStatusNoNew') }
  if (created < rows) return { key: 'partial', tone: 'info', label: tr('bankImportStatusPartial') }
  return { key: 'success', tone: 'success', label: tr('bankImportStatusSuccess') }
}

export default function BankImport() {
  const location = useLocation()
  const isActivePage = location.pathname === '/bank-import'
  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(false)
  const [recentLoading, setRecentLoading] = useState(true)
  const [applying, setApplying] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [result, setResult] = useState(null)
  const [pageError, setPageError] = useState('')
  const [selections, setSelections] = useState({})
  const [parseMeta, setParseMeta] = useState([])
  const [skippedFiles, setSkippedFiles] = useState([])
  const [recentFiles, setRecentFiles] = useState([])
  const [recentSort, setRecentSort] = useState({ col: 'imported_at', asc: false })
  const [transactionSearch, setTransactionSearch] = useState('')
  const [directionFilter, setDirectionFilter] = useState('all')
  const [historySearch, setHistorySearch] = useState('')
  const [historyStatus, setHistoryStatus] = useState('all')

  const loadRecentFiles = useCallback(async () => {
    setRecentLoading(true)
    try {
      const response = await api.bankImport.recentFiles(HISTORY_LIMIT)
      setRecentFiles(response.items || [])
    } catch {
      setRecentFiles([])
    } finally {
      setRecentLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!isActivePage) return
    loadRecentFiles()
  }, [isActivePage, loadRecentFiles])

  const parseSelectedFiles = async (selectedFiles) => {
    const nextFiles = Array.from(selectedFiles || [])
    if (nextFiles.length === 0) return

    setTransactions([])
    setSelections({})
    setParseMeta([])
    setSkippedFiles([])
    setResult(null)
    setPageError('')
    setTransactionSearch('')
    setDirectionFilter('all')
    setLoading(true)
    try {
      const parsed = await api.bankImport.parse(nextFiles)
      const parsedTransactions = parsed.transactions || []
      const parsedFiles = parsed.parsed_files || []
      const previouslyImportedHashes = new Set(
        parsedFiles.filter((file) => file.previously_imported).map((file) => file.file_hash)
      )

      setTransactions(parsedTransactions)
      setSelections(
        Object.fromEntries(
          parsedTransactions.map((transaction, index) => [
            index,
            {
              selected: !previouslyImportedHashes.has(transaction.file_hash),
            },
          ])
        )
      )
      setParseMeta(parsedFiles)
      setSkippedFiles(parsed.skipped_files || [])
    } catch (error) {
      setPageError(error?.message || tr('loadError'))
    } finally {
      setLoading(false)
    }
  }

  const handleFileChange = (event) => {
    parseSelectedFiles(event.target.files)
    event.target.value = ''
  }

  const handleDrop = (event) => {
    event.preventDefault()
    setIsDragging(false)
    if (!loading) parseSelectedFiles(event.dataTransfer.files)
  }

  const handleApply = async () => {
    const items = transactions
      .map((transaction, index) => ({ transaction, index, selection: selections[index] }))
      .filter(({ selection }) => selection?.selected)
    if (items.length === 0) {
      setPageError(tr('selectAtLeastOne'))
      return
    }

    setApplying(true)
    setResult(null)
    setPageError('')
    try {
      const body = {
        transactions: items.map(({ transaction }) => ({
          type: transaction.type,
          tx: transaction,
          file_hash: transaction.file_hash || null,
        })),
        files: parseMeta || [],
      }
      const response = await api.bankImport.apply(body)
      setResult(response)
      setTransactions([])
      setSelections({})
      setParseMeta([])
      setSkippedFiles([])
      loadRecentFiles()
    } catch (error) {
      setPageError(error?.message || tr('loadError'))
    } finally {
      setApplying(false)
    }
  }

  const toggleSelect = (index) => {
    setSelections((current) => ({
      ...current,
      [index]: {
        ...(current[index] || {}),
        selected: !(current[index]?.selected ?? true),
      },
    }))
  }

  const selectedRows = useMemo(
    () =>
      transactions
        .map((transaction, index) => ({ transaction, index }))
        .filter(({ index }) => selections[index]?.selected ?? true),
    [transactions, selections]
  )

  const selectedSummary = useMemo(
    () =>
      selectedRows.reduce(
        (summary, { transaction }) => {
          const type = transaction.type
          summary[type].count += 1
          summary[type].amount += Number(transaction.amount || 0)
          return summary
        },
        { income: { count: 0, amount: 0 }, expense: { count: 0, amount: 0 } }
      ),
    [selectedRows]
  )

  const fileNameByHash = useMemo(
    () => new Map(parseMeta.map((file) => [file.file_hash, file.file_name])),
    [parseMeta]
  )

  const visibleTransactions = useMemo(() => {
    const query = transactionSearch.trim().toLocaleLowerCase()
    return transactions
      .map((transaction, index) => ({ transaction, index }))
      .filter(({ transaction }) => {
        if (directionFilter !== 'all' && transaction.type !== directionFilter) return false
        if (!query) return true
        const haystack = [
          transaction.description,
          transaction.payer_beneficiary,
          transaction.reference,
          fileNameByHash.get(transaction.file_hash),
        ]
          .filter(Boolean)
          .join(' ')
          .toLocaleLowerCase()
        return haystack.includes(query)
      })
  }, [transactions, directionFilter, transactionSearch, fileNameByHash])

  const setVisibleSelection = (selected) => {
    setSelections((current) => {
      const next = { ...current }
      visibleTransactions.forEach(({ index }) => {
        next[index] = {
          ...(next[index] || {}),
          selected,
        }
      })
      return next
    })
  }

  const clearAllSelections = () => {
    setSelections((current) => {
      const next = { ...current }
      transactions.forEach((_, index) => {
        next[index] = {
          ...(next[index] || {}),
          selected: false,
        }
      })
      return next
    })
  }

  const historyTotals = useMemo(
    () =>
      recentFiles.reduce(
        (summary, file) => {
          summary.rows += Number(file.transaction_count || 0)
          summary.created += Number(file.created_income || 0) + Number(file.created_expense || 0)
          summary.errors += Number(file.errors_count || 0)
          return summary
        },
        { rows: 0, created: 0, errors: 0 }
      ),
    [recentFiles]
  )

  const toggleRecentSort = (column) => {
    setRecentSort((current) =>
      current.col === column
        ? { col: column, asc: !current.asc }
        : { col: column, asc: column === 'file_name' }
    )
  }

  const filteredRecentFiles = useMemo(() => {
    const query = historySearch.trim().toLocaleLowerCase()
    return recentFiles.filter((file) => {
      const status = getImportStatus(file).key
      const statusMatches =
        historyStatus === 'all' ||
        status === historyStatus ||
        (historyStatus === 'attention' && status === 'partial')
      if (!statusMatches) return false
      if (!query) return true
      return [file.file_name, file.imported_by].filter(Boolean).join(' ').toLocaleLowerCase().includes(query)
    })
  }, [recentFiles, historySearch, historyStatus])

  const sortedRecentFiles = useMemo(() => {
    const accessor = {
      file_name: (file) => file.file_name || '',
      imported_at: (file) => file.imported_at || '',
      transaction_count: (file) => Number(file.transaction_count || 0),
      created: (file) => Number(file.created_income || 0) + Number(file.created_expense || 0),
      statement_amount: (file) => Number(file.income_amount || 0) + Number(file.expense_amount || 0),
      errors_count: (file) => Number(file.errors_count || 0),
    }[recentSort.col]
    const sorted = [...filteredRecentFiles].sort((left, right) => {
      const leftValue = accessor(left)
      const rightValue = accessor(right)
      return typeof leftValue === 'number'
        ? leftValue - rightValue
        : String(leftValue).localeCompare(String(rightValue))
    })
    return recentSort.asc ? sorted : sorted.reverse()
  }, [filteredRecentFiles, recentSort])

  const recentFileTh = (column, label, alignRight = false) => (
    <th className={alignRight ? 'bank-import-number-cell' : ''} onClick={() => toggleRecentSort(column)}>
      {label} <SortIndicator active={recentSort.col === column} asc={recentSort.asc} />
    </th>
  )

  const selectedVisibleCount = visibleTransactions.filter(
    ({ index }) => selections[index]?.selected ?? true
  ).length

  return (
    <>
      <PageHeader
        title={tr('bankImport')}
        subtitle={tr('bankImportSubtitle')}
        actions={
          <section
            className={`bank-import-header-dropzone${isDragging ? ' is-dragging' : ''}${loading ? ' is-loading' : ''}`}
            onDragEnter={(event) => {
              event.preventDefault()
              setIsDragging(true)
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget)) setIsDragging(false)
            }}
            onDrop={handleDrop}
          >
            <div className="bank-import-header-dropzone-icon">
              <UploadCloud size={22} />
            </div>
            <div className="bank-import-header-dropzone-copy">
              <strong>{loading ? tr('loading') : tr('bankImportDropTitle')}</strong>
              <span>{tr('bankImportDropHint')} · XLS / XLSX</span>
            </div>
            <FileInput
              label={
                <>
                  <UploadCloud size={17} />
                  {loading ? `${tr('loading')}...` : tr('bankImportChooseFiles')}
                </>
              }
              accept=".xls,.xlsx"
              multiple
              disabled={loading}
              onChange={handleFileChange}
              buttonClassName="btn btn-primary bank-import-header-upload"
            />
          </section>
        }
      />

      <PageTabs group="bank" />

      <div className="page-body bank-import-page">
        {pageError ? <div className="alert alert-danger">{pageError}</div> : null}

        {result ? (
          <div className="bank-import-result" role="status">
            <div className="bank-import-result-icon">
              <CircleCheck size={24} />
            </div>
            <div className="bank-import-result-main">
              <strong>{tr('bankImportResultTitle')}</strong>
              <span>{tr('bankImportResultHint')}</span>
            </div>
            <div className="bank-import-result-metrics">
              <span>
                <strong>{result.created_income || 0}</strong>
                {tr('incomeLabel')}
              </span>
              <span>
                <strong>{result.created_expense || 0}</strong>
                {tr('expenseLabel')}
              </span>
              <span>
                <strong>{result.skipped_duplicates || 0}</strong>
                {tr('bankImportDuplicatesSkipped')}
              </span>
              <span>
                <strong>{result.errors?.length || 0}</strong>
                {tr('bankImportIssues')}
              </span>
            </div>
            <Link to="/bank" className="btn btn-secondary btn-sm">
              {tr('bankImportOpenBank')} <ArrowRight size={15} />
            </Link>
          </div>
        ) : null}

        {result?.errors?.length ? (
          <div className="alert alert-warning bank-import-attention">
            <CircleAlert size={18} />
            <div>
              <strong>{tr('bankImportWarnings')}</strong>
              <ul>
                {result.errors.map((error, index) => (
                  <li key={`${error}-${index}`}>{error}</li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}

        <section className="bank-import-overview" aria-label={tr('bankImportHistorySummary')}>
          <div className="bank-import-stat">
            <span className="bank-import-stat-icon">
              <History size={18} />
            </span>
            <div>
              <strong>{recentFiles.length}</strong>
              <span>{tr('bankImportFilesProcessed')}</span>
            </div>
          </div>
          <div className="bank-import-stat">
            <span className="bank-import-stat-icon">
              <FileSpreadsheet size={18} />
            </span>
            <div>
              <strong>{historyTotals.rows}</strong>
              <span>{tr('bankImportRowsFound')}</span>
            </div>
          </div>
          <div className="bank-import-stat bank-import-stat--success">
            <span className="bank-import-stat-icon">
              <CircleCheck size={18} />
            </span>
            <div>
              <strong>{historyTotals.created}</strong>
              <span>{tr('bankImportOperationsCreated')}</span>
            </div>
          </div>
          <div className={`bank-import-stat${historyTotals.errors ? ' bank-import-stat--warning' : ''}`}>
            <span className="bank-import-stat-icon">
              <CircleAlert size={18} />
            </span>
            <div>
              <strong>{historyTotals.errors}</strong>
              <span>{tr('bankImportIssues')}</span>
            </div>
          </div>
        </section>

        {skippedFiles.length > 0 ? (
          <div className="alert alert-warning bank-import-attention">
            <CircleAlert size={18} />
            <div>
              <strong>
                {tr('bankImportAttentionFiles')} ({skippedFiles.length})
              </strong>
              <ul>
                {skippedFiles.map((file, index) => (
                  <li key={`${file.file_name}-${index}`}>
                    {file.file_name}: {file.reason}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}

        {transactions.length > 0 ? (
          <section className="card bank-import-preview-card">
            <div className="bank-import-section-head">
              <div>
                <h2>{tr('bankImportReadyReview')}</h2>
                <p>{tr('bankImportReadyHint')}</p>
              </div>
              <StatusBadge tone="info">
                {selectedRows.length} / {transactions.length} {tr('bankImportSelectedCount')}
              </StatusBadge>
            </div>

            <div className="bank-import-preview-summary">
              <div>
                <span>{tr('bankImportLoadedFiles')}</span>
                <strong>{parseMeta.length}</strong>
              </div>
              <div>
                <span>{tr('incomeLabel')}</span>
                <strong className="is-positive">
                  {selectedSummary.income.count} · {fmtMoney(selectedSummary.income.amount)} RSD
                </strong>
              </div>
              <div>
                <span>{tr('expenseLabel')}</span>
                <strong className="is-negative">
                  {selectedSummary.expense.count} · {fmtMoney(selectedSummary.expense.amount)} RSD
                </strong>
              </div>
            </div>

            <div className="bank-import-toolbar">
              <SearchInput
                value={transactionSearch}
                onChange={setTransactionSearch}
                placeholder={tr('bankImportSearchTransactions')}
                style={{ minWidth: 260 }}
              />
              <select
                className="form-input"
                value={directionFilter}
                onChange={(event) => setDirectionFilter(event.target.value)}
              >
                <option value="all">{tr('bankTxAll')}</option>
                <option value="income">{tr('incomeLabel')}</option>
                <option value="expense">{tr('expenseLabel')}</option>
              </select>
              <div className="bank-import-toolbar-actions">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setVisibleSelection(true)}
                  disabled={selectedVisibleCount === visibleTransactions.length}
                >
                  {tr('bankImportSelectVisible')}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setVisibleSelection(false)}
                  disabled={!selectedVisibleCount}
                >
                  {tr('bankImportClearVisible')}
                </button>
              </div>
            </div>

            <div className="table-wrap table-wrap-scroll">
              <table className="bank-import-preview-table">
                <thead>
                  <tr>
                    <th className="bank-import-checkbox-cell"></th>
                    <th>{tr('date')}</th>
                    <th>{tr('type')}</th>
                    <th>{tr('client')}</th>
                    <th>{tr('description')}</th>
                    {parseMeta.length > 1 ? <th>{tr('bankImportSourceFile')}</th> : null}
                    <th className="bank-import-number-cell">{tr('amount')}</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleTransactions.map(({ transaction, index }) => (
                    <tr
                      key={`${transaction.file_hash}-${index}`}
                      className={(selections[index]?.selected ?? true) ? 'record-row-selected' : ''}
                    >
                      <td className="bank-import-checkbox-cell">
                        <input
                          type="checkbox"
                          checked={selections[index]?.selected ?? true}
                          onChange={() => toggleSelect(index)}
                          aria-label={`${tr('selectedRows')} ${index + 1}`}
                        />
                      </td>
                      <td className="date-cell">{formatDateSr(transaction.date)}</td>
                      <td>
                        <StatusBadge tone={transaction.type === 'income' ? 'success' : 'danger'}>
                          {transaction.type === 'income' ? tr('incomeLabel') : tr('expenseLabel')}
                        </StatusBadge>
                      </td>
                      <td>
                        <span className="record-cell-ellipsis" title={transaction.payer_beneficiary || ''}>
                          {transaction.payer_beneficiary || UI_DASH}
                        </span>
                      </td>
                      <td>
                        <span className="record-cell-ellipsis" title={transaction.description || ''}>
                          {transaction.description || UI_DASH}
                        </span>
                      </td>
                      {parseMeta.length > 1 ? (
                        <td>
                          <span
                            className="record-cell-ellipsis"
                            title={fileNameByHash.get(transaction.file_hash)}
                          >
                            {fileNameByHash.get(transaction.file_hash) || UI_DASH}
                          </span>
                        </td>
                      ) : null}
                      <td className="bank-import-number-cell">
                        <strong>{fmtMoney(transaction.amount)}</strong> RSD
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {visibleTransactions.length === 0 ? (
                <div className="bank-import-empty">{tr('noRecords')}</div>
              ) : null}
            </div>
          </section>
        ) : null}

        <section className="card bank-import-history-card">
          <div className="bank-import-section-head">
            <div>
              <h2>{tr('bankImportHistory')}</h2>
              <p>{tr('bankImportHistoryHint')}</p>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={loadRecentFiles}
              disabled={recentLoading}
            >
              <RefreshCw size={15} className={recentLoading ? 'is-spinning' : ''} /> {tr('bankImportReload')}
            </button>
          </div>

          <div className="bank-import-toolbar">
            <SearchInput
              value={historySearch}
              onChange={setHistorySearch}
              placeholder={tr('bankImportSearchFiles')}
              style={{ minWidth: 260 }}
            />
            <select
              className="form-input"
              value={historyStatus}
              onChange={(event) => setHistoryStatus(event.target.value)}
            >
              <option value="all">{tr('allStatuses')}</option>
              <option value="success">{tr('bankImportStatusSuccess')}</option>
              <option value="attention">{tr('bankImportStatusAttention')}</option>
              <option value="no-new">{tr('bankImportStatusNoNew')}</option>
            </select>
            <span className="bank-import-filter-count">
              {sortedRecentFiles.length} / {recentFiles.length}
            </span>
          </div>

          {recentLoading && recentFiles.length === 0 ? (
            <div className="bank-import-empty">{tr('bankImportLoadingHistory')}</div>
          ) : sortedRecentFiles.length === 0 ? (
            <div className="bank-import-empty">
              {historySearch || historyStatus !== 'all' ? tr('bankImportNoMatchingFiles') : tr('noRecords')}
            </div>
          ) : (
            <div className="table-wrap">
              <table className="bank-import-history-table">
                <thead>
                  <tr>
                    {recentFileTh('file_name', tr('bankImportRecentFileName'))}
                    {recentFileTh('imported_at', tr('bankImportRecentAt'))}
                    <th>{tr('bankImportStatus')}</th>
                    {recentFileTh('transaction_count', tr('bankImportRecentRows'), true)}
                    {recentFileTh('statement_amount', tr('bankImportStatementAmount'), true)}
                    {recentFileTh('created', tr('bankImportRecentCreated'), true)}
                    {recentFileTh('errors_count', tr('bankImportIssues'), true)}
                  </tr>
                </thead>
                <tbody>
                  {sortedRecentFiles.map((file) => {
                    const status = getImportStatus(file)
                    return (
                      <tr key={file.id || file.file_hash}>
                        <td>
                          <div className="bank-import-file-cell">
                            <FileSpreadsheet size={17} />
                            <div>
                              <strong title={file.file_name}>{file.file_name || UI_DASH}</strong>
                              <span>{formatFileSize(file.file_size)}</span>
                            </div>
                          </div>
                        </td>
                        <td>
                          <div className="bank-import-date-cell">
                            <strong>{formatDateTimeSr(file.imported_at)}</strong>
                            <span>
                              {file.imported_by ? `${tr('bankImportBy')} ${file.imported_by}` : UI_DASH}
                            </span>
                          </div>
                        </td>
                        <td>
                          <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
                        </td>
                        <td className="bank-import-number-cell">{file.transaction_count ?? 0}</td>
                        <td className="bank-import-number-cell">
                          {file.income_amount != null || file.expense_amount != null ? (
                            <div className="bank-import-statement-amount">
                              <span className="is-positive">↑ {fmtMoney(file.income_amount || 0)} RSD</span>
                              <span className="is-negative">↓ {fmtMoney(file.expense_amount || 0)} RSD</span>
                            </div>
                          ) : (
                            UI_DASH
                          )}
                        </td>
                        <td className="bank-import-number-cell">
                          <span className="bank-import-created-count">
                            <strong>{file.created_income ?? 0}</strong> /{' '}
                            <strong>{file.created_expense ?? 0}</strong>
                          </span>
                        </td>
                        <td className="bank-import-number-cell">
                          <span className={Number(file.errors_count || 0) ? 'bank-import-error-count' : ''}>
                            {file.errors_count ?? 0}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <SelectionSummary
        count={selectedRows.length}
        items={[
          {
            label: tr('incomeLabel'),
            value: `${fmtMoney(selectedSummary.income.amount)} RSD`,
            tone: 'positive',
          },
          {
            label: tr('expenseLabel'),
            value: `${fmtMoney(selectedSummary.expense.amount)} RSD`,
            tone: 'negative',
          },
        ]}
        actions={
          <button type="button" className="btn btn-sm btn-primary" onClick={handleApply} disabled={applying}>
            {applying ? tr('importing') : tr('importSelected')}
          </button>
        }
        onClear={clearAllSelections}
      />
    </>
  )
}
