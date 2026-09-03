import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  ArrowDownToLine,
  ArrowUpFromLine,
  CheckCircle2,
  CloudDownload,
  Database,
  FileUp,
  History,
  RefreshCw,
  Server,
  X,
} from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { api, getUser } from '../api'
import PageHeader from '../components/PageHeader'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import StatusBadge from '../components/StatusBadge'
import {
  DEFAULT_EFAKTURA_API_BASE_URL,
  isEfakturaApiConfigured,
  usesEfakturaDefaultRoutes,
} from '../efakturaDefaults'
import useListPageState from '../hooks/useListPageState'
import { tr } from '../i18n'
import { downloadBlobFile } from '../utils/download'
import { formatDateSr, formatDateTimeSr, UI_DASH } from '../utils/formatters'

function formatAmount(value) {
  if (value === null || value === undefined || value === '') return UI_DASH
  const amount = Number(value)
  if (!Number.isFinite(amount)) return `${value} RSD`
  return `${amount.toLocaleString('sr-RS', { maximumFractionDigits: 2 })} RSD`
}

function counterpartyName(item) {
  return item.direction === 'incoming' ? item.supplier_name : item.customer_name
}

function counterpartyPib(item) {
  return item.direction === 'incoming' ? item.supplier_pib : item.customer_pib
}

function getSortValue(item, column) {
  if (column === 'created_at') return new Date(item.created_at || 0).getTime()
  if (column === 'amount_rsd') return Number(item.amount_rsd || 0)
  if (column === 'counterparty') return counterpartyName(item) || ''
  return item[column] || ''
}

function ResultSummary({ result, onDismiss }) {
  if (!result) return null

  const issueCount = Number(result.error_count || 0) + Number(result.download_error_count || 0)
  const metrics = [
    {
      key: 'created',
      label: tr('efakturaCreatedDocuments'),
      value: result.created_count || 0,
      tone: 'success',
    },
    { key: 'income', label: tr('efakturaCreatedIncome'), value: result.created_income_count || 0 },
    {
      key: 'expenses',
      label: tr('efakturaCreatedExpenses'),
      value: result.created_expense_count || 0,
    },
    { key: 'skipped', label: tr('efakturaSkipped'), value: result.skipped_count || 0, tone: 'muted' },
    { key: 'errors', label: tr('efakturaErrors'), value: result.error_count || 0, tone: 'danger' },
    'fetched_count' in result
      ? {
          key: 'fetched',
          label: tr('efakturaFetchedFromApi'),
          value: result.fetched_count || 0,
          tone: 'info',
        }
      : null,
    'pdf_download_count' in result
      ? {
          key: 'pdf',
          label: tr('efakturaPdfDownloads'),
          value: result.pdf_download_count || 0,
          tone: 'info',
        }
      : null,
    'download_error_count' in result
      ? {
          key: 'download-errors',
          label: tr('efakturaDownloadErrors'),
          value: result.download_error_count || 0,
          tone: 'danger',
        }
      : null,
  ].filter(Boolean)

  return (
    <section className="card efaktura-result-card" aria-live="polite">
      <div className="efaktura-section-head">
        <div className="efaktura-section-title">
          <span className={`efaktura-section-icon ${issueCount ? 'is-warning' : 'is-success'}`}>
            {issueCount ? <AlertTriangle size={19} /> : <CheckCircle2 size={19} />}
          </span>
          <div>
            <h2>{tr('efakturaResultTitle')}</h2>
            <p>{issueCount ? tr('efakturaResultWithIssues') : tr('efakturaResultCompleted')}</p>
          </div>
        </div>
        <button
          type="button"
          className="efaktura-icon-button"
          onClick={onDismiss}
          aria-label={tr('efakturaCloseResult')}
          title={tr('efakturaCloseResult')}
        >
          <X size={17} />
        </button>
      </div>

      <div className="efaktura-result-metrics">
        {metrics.map((metric) => (
          <div
            key={metric.key}
            className={`efaktura-result-metric${metric.tone ? ` is-${metric.tone}` : ''}`}
          >
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>

      {(result.errors || []).length > 0 ? (
        <div className="efaktura-result-issues is-danger">
          <strong>{tr('efakturaImportErrorsTitle')}</strong>
          <ul>
            {result.errors.slice(0, 10).map((item, index) => (
              <li key={`${item.file_name || item.invoice_number || 'error'}-${index}`}>
                {item.file_name || item.invoice_number || tr('efakturaDocument')}:{' '}
                {item.error || tr('efakturaUnknownError')}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {(result.download_errors || []).length > 0 ? (
        <div className="efaktura-result-issues is-warning">
          <strong>{tr('efakturaDownloadErrorsTitle')}</strong>
          <ul>
            {result.download_errors.slice(0, 10).map((item, index) => (
              <li key={`${item.file_name || item.invoice_number || 'download'}-${index}`}>
                {item.file_name || item.invoice_number || tr('efakturaDocument')}:{' '}
                {item.error || tr('efakturaUnknownError')}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}

function SyncProgress({ stage, startedAt }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  useEffect(() => {
    const updateElapsed = () => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)))
    }
    updateElapsed()
    const timer = window.setInterval(updateElapsed, 250)
    return () => window.clearInterval(timer)
  }, [startedAt])

  const processingComplete = stage === 'refreshing'
  const steps = [
    {
      key: 'request',
      label: tr('efakturaSyncStepRequest'),
      status: 'complete',
      icon: CloudDownload,
    },
    {
      key: 'processing',
      label: tr('efakturaSyncStepProcessing'),
      status: processingComplete ? 'complete' : 'active',
      icon: Database,
    },
    {
      key: 'history',
      label: tr('efakturaSyncStepHistory'),
      status: processingComplete ? 'active' : 'pending',
      icon: History,
    },
  ]

  return (
    <section className="card efaktura-sync-progress-card" role="status" aria-live="polite">
      <div className="efaktura-section-head">
        <div className="efaktura-section-title">
          <span className="efaktura-section-icon is-active">
            <RefreshCw className="efaktura-button-spinner" size={19} />
          </span>
          <div>
            <h2>{tr('efakturaSyncProgressTitle')}</h2>
            <p>
              {processingComplete
                ? tr('efakturaSyncProgressRefreshing')
                : tr('efakturaSyncProgressProcessing')}
            </p>
          </div>
        </div>
        <span className="efaktura-sync-elapsed">
          {tr('efakturaSyncElapsed', { seconds: elapsedSeconds })}
        </span>
      </div>

      <div className="efaktura-sync-progress-body">
        <div className="efaktura-sync-progress-track" aria-hidden="true">
          <span />
        </div>
        <div className="efaktura-sync-steps">
          {steps.map((step) => {
            const StepIcon = step.icon
            return (
              <div key={step.key} className={`efaktura-sync-step is-${step.status}`}>
                <span className="efaktura-sync-step-icon">
                  {step.status === 'complete' ? (
                    <CheckCircle2 size={18} />
                  ) : step.status === 'active' ? (
                    <RefreshCw className="efaktura-button-spinner" size={17} />
                  ) : (
                    <StepIcon size={17} />
                  )}
                </span>
                <span>{step.label}</span>
              </div>
            )
          })}
        </div>
        <p className="efaktura-sync-wait-hint">{tr('efakturaSyncWaitHint')}</p>
      </div>
    </section>
  )
}

function SortableHeader({ column, activeColumn, ascending, onSort, children, align = 'left' }) {
  return (
    <th style={{ textAlign: align }}>
      <button
        type="button"
        className="efaktura-sort-button"
        onClick={() => onSort(column)}
        style={{ justifyContent: align === 'right' ? 'flex-end' : 'flex-start' }}
      >
        {children}
        <SortIndicator active={activeColumn === column} asc={ascending} />
      </button>
    </th>
  )
}

export default function Efaktura() {
  const location = useLocation()
  const fileInputRef = useRef(null)
  const isActivePage = location.pathname === '/efaktura'
  const currentUser = getUser()
  const isAdmin = currentUser?.role === 'admin'

  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [syncStage, setSyncStage] = useState('')
  const [syncStartedAt, setSyncStartedAt] = useState(null)
  const [importing, setImporting] = useState(false)
  const [lastResult, setLastResult] = useState(null)
  const [settingsInfo, setSettingsInfo] = useState(null)
  const [pageError, setPageError] = useState('')
  const [directionFilter, setDirectionFilter] = useState('')
  const [recordTypeFilter, setRecordTypeFilter] = useState('')
  const { search, setSearch, sortCol, sortAsc, toggleSort } = useListPageState({
    initialSortCol: 'created_at',
    initialSortAsc: false,
  })

  const downloadPdfFiles = (downloads = []) => {
    downloads.forEach((item) => {
      if (!item?.content_base64 || !item?.file_name) return
      const binary = atob(item.content_base64)
      const bytes = new Uint8Array(binary.length)
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index)
      }
      downloadBlobFile(new Blob([bytes], { type: item.content_type || 'application/pdf' }), item.file_name)
    })
  }

  const loadHistory = async () => {
    setHistoryLoading(true)
    try {
      const [historyItems, settings] = await Promise.all([
        api.efaktura.history(),
        isAdmin ? api.efaktura.settings() : Promise.resolve(null),
      ])
      setHistory(historyItems || [])
      setSettingsInfo(settings)
      setPageError('')
    } catch (err) {
      setPageError(err.message || tr('efakturaLoadingError'))
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    if (!isActivePage) return
    loadHistory()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActivePage])

  const handleImportClick = () => {
    if (importing || syncing) return
    fileInputRef.current?.click()
  }

  const handleImportFiles = async (event) => {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    if (files.length === 0) return
    setImporting(true)
    setPageError('')
    try {
      const result = await api.efaktura.importXml(files)
      setLastResult(result)
      await loadHistory()
    } catch (err) {
      setPageError(err.message || tr('efakturaImportError'))
    } finally {
      setImporting(false)
    }
  }

  const handleSync = async () => {
    if (syncing || importing) return
    setSyncing(true)
    setSyncStage('processing')
    setSyncStartedAt(Date.now())
    setLastResult(null)
    setPageError('')
    try {
      const result = await api.efaktura.sync()
      setSyncStage('refreshing')
      downloadPdfFiles(result?.pdf_downloads || [])
      await loadHistory()
      setLastResult(result)
    } catch (err) {
      setPageError(err.message || tr('efakturaSyncError'))
    } finally {
      setSyncStage('')
      setSyncStartedAt(null)
      setSyncing(false)
    }
  }

  const filteredHistory = useMemo(() => {
    const query = search.trim().toLocaleLowerCase()
    const rows = history.filter((item) => {
      if (directionFilter && item.direction !== directionFilter) return false
      if (recordTypeFilter && item.imported_as !== recordTypeFilter) return false
      if (!query) return true

      return [
        item.invoice_number,
        item.external_id,
        item.file_name,
        counterpartyName(item),
        counterpartyPib(item),
        item.imported_record_id,
        item.amount_rsd,
      ].some((value) =>
        String(value ?? '')
          .toLocaleLowerCase()
          .includes(query)
      )
    })

    return [...rows].sort((left, right) => {
      const leftValue = getSortValue(left, sortCol)
      const rightValue = getSortValue(right, sortCol)
      if (typeof leftValue === 'number' && typeof rightValue === 'number') {
        return sortAsc ? leftValue - rightValue : rightValue - leftValue
      }
      const comparison = String(leftValue).localeCompare(String(rightValue), 'sr', {
        numeric: true,
        sensitivity: 'base',
      })
      return sortAsc ? comparison : -comparison
    })
  }, [directionFilter, history, recordTypeFilter, search, sortAsc, sortCol])

  const apiConfigured = isEfakturaApiConfigured(settingsInfo)
  const usingDefaultRoutes = usesEfakturaDefaultRoutes(settingsInfo)
  const effectiveBaseUrl = settingsInfo?.efaktura_api_base_url || DEFAULT_EFAKTURA_API_BASE_URL
  const busy = syncing || importing
  const hasActiveFilters = Boolean(search || directionFilter || recordTypeFilter)

  return (
    <>
      <PageHeader
        title={tr('efakturaTitle')}
        subtitle={tr('efakturaSubtitle')}
        actions={
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xml,text/xml,application/xml"
              multiple
              hidden
              onChange={handleImportFiles}
            />
            <button
              className="btn btn-secondary efaktura-action-button"
              onClick={handleImportClick}
              disabled={busy}
            >
              {importing ? <RefreshCw className="efaktura-button-spinner" size={17} /> : <FileUp size={17} />}
              {importing ? tr('efakturaImporting') : tr('efakturaImportXml')}
            </button>
            <button
              className="btn btn-primary efaktura-action-button"
              onClick={handleSync}
              disabled={busy || (isAdmin && !apiConfigured)}
              title={isAdmin && !apiConfigured ? tr('efakturaSyncSettingsHint') : ''}
            >
              <RefreshCw className={syncing ? 'efaktura-button-spinner' : ''} size={17} />
              {syncing ? tr('efakturaSyncing') : tr('efakturaSyncApi')}
            </button>
          </>
        }
      />

      <div className="page-body efaktura-page-body">
        {pageError ? (
          <div className="alert alert-danger efaktura-page-alert" role="alert">
            <AlertTriangle size={18} />
            <div>
              <strong>{tr('loadError')}</strong>
              <span>{pageError}</span>
            </div>
          </div>
        ) : null}

        {isAdmin ? (
          <section className="card efaktura-api-card">
            <div className="efaktura-api-main">
              <span className={`efaktura-api-icon${apiConfigured ? ' is-connected' : ''}`}>
                <Server size={21} />
              </span>
              <div className="efaktura-api-copy">
                <span>{tr('efakturaApiSettingsTitle')}</span>
                <strong>
                  {apiConfigured ? tr('efakturaApiConfigured') : tr('efakturaApiNotConfigured')}
                </strong>
              </div>
              <StatusBadge tone={apiConfigured ? 'success' : 'warning'} className="badge-pill">
                {apiConfigured ? tr('efakturaConnected') : tr('efakturaNotConnected')}
              </StatusBadge>
            </div>

            <div className="efaktura-api-details">
              <div className="efaktura-api-detail efaktura-api-detail--endpoint">
                <span>{tr('efakturaApiEndpoint')}</span>
                <strong title={effectiveBaseUrl}>{effectiveBaseUrl}</strong>
              </div>
              <div className="efaktura-api-detail">
                <span>{tr('efakturaSyncScope')}</span>
                <strong>
                  {[
                    settingsInfo?.efaktura_sync_incoming ? tr('efakturaIncomingLabel') : '',
                    settingsInfo?.efaktura_sync_outgoing ? tr('efakturaOutgoingLabel') : '',
                  ]
                    .filter(Boolean)
                    .join(' + ') || UI_DASH}
                </strong>
              </div>
              <div className="efaktura-api-detail">
                <span>{tr('efakturaLookbackLabel')}</span>
                <strong>
                  {settingsInfo?.efaktura_sync_lookback_days || 0} {tr('efakturaDaysShort')}
                </strong>
              </div>
              <div className="efaktura-api-detail">
                <span>{tr('efakturaSavePdf')}</span>
                <strong>{settingsInfo?.efaktura_save_pdf ? tr('yes') : tr('no')}</strong>
              </div>
              <div className="efaktura-api-detail">
                <span>{tr('efakturaRoutes')}</span>
                <strong>
                  {usingDefaultRoutes ? tr('efakturaStandardRoutes') : tr('efakturaCustomRoutes')}
                </strong>
              </div>
            </div>
          </section>
        ) : null}

        {syncing && syncStartedAt ? <SyncProgress stage={syncStage} startedAt={syncStartedAt} /> : null}

        <ResultSummary result={lastResult} onDismiss={() => setLastResult(null)} />

        <section className="card efaktura-history-card">
          <div className="efaktura-section-head efaktura-history-head">
            <div>
              <h2>{tr('efakturaHistoryTitle')}</h2>
              <p>{tr('efakturaHistoryDescription')}</p>
            </div>
            <div className="efaktura-history-count">
              {tr('efakturaHistoryCount', {
                shown: filteredHistory.length,
                total: history.length,
              })}
            </div>
          </div>

          <div className="efaktura-history-toolbar">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder={tr('efakturaSearchPlaceholder')}
              aria-label={tr('efakturaSearchPlaceholder')}
            />
            <select
              className="form-input"
              value={directionFilter}
              onChange={(event) => setDirectionFilter(event.target.value)}
              aria-label={tr('efakturaDirection')}
            >
              <option value="">{tr('efakturaAllDirections')}</option>
              <option value="incoming">{tr('efakturaIncoming')}</option>
              <option value="outgoing">{tr('efakturaOutgoing')}</option>
            </select>
            <select
              className="form-input"
              value={recordTypeFilter}
              onChange={(event) => setRecordTypeFilter(event.target.value)}
              aria-label={tr('efakturaImportedAs')}
            >
              <option value="">{tr('efakturaAllRecordTypes')}</option>
              <option value="expense">{tr('efakturaImportedAsExpense')}</option>
              <option value="income">{tr('efakturaImportedAsIncome')}</option>
            </select>
            <button
              type="button"
              className="btn btn-secondary btn-sm efaktura-refresh-button"
              onClick={loadHistory}
              disabled={historyLoading}
            >
              <RefreshCw className={historyLoading ? 'efaktura-button-spinner' : ''} size={15} />
              {tr('serviceBackupsRefresh')}
            </button>
          </div>

          <div className="table-wrap">
            <table className="efaktura-history-table">
              <thead>
                <tr>
                  <SortableHeader
                    column="created_at"
                    activeColumn={sortCol}
                    ascending={sortAsc}
                    onSort={toggleSort}
                  >
                    {tr('efakturaImportedAt')}
                  </SortableHeader>
                  <SortableHeader
                    column="direction"
                    activeColumn={sortCol}
                    ascending={sortAsc}
                    onSort={toggleSort}
                  >
                    {tr('efakturaDirection')}
                  </SortableHeader>
                  <SortableHeader
                    column="invoice_number"
                    activeColumn={sortCol}
                    ascending={sortAsc}
                    onSort={toggleSort}
                  >
                    {tr('efakturaDocument')}
                  </SortableHeader>
                  <SortableHeader
                    column="counterparty"
                    activeColumn={sortCol}
                    ascending={sortAsc}
                    onSort={toggleSort}
                  >
                    {tr('efakturaCounterparty')}
                  </SortableHeader>
                  <SortableHeader
                    column="amount_rsd"
                    activeColumn={sortCol}
                    ascending={sortAsc}
                    onSort={toggleSort}
                    align="right"
                  >
                    {tr('amount')}
                  </SortableHeader>
                  <th>{tr('efakturaImportedAs')}</th>
                  <th>{tr('efakturaSource')}</th>
                </tr>
              </thead>
              <tbody>
                {historyLoading ? (
                  <tr>
                    <td colSpan={7} className="efaktura-table-message">
                      <RefreshCw className="efaktura-button-spinner" size={18} />
                      {tr('loading')}
                    </td>
                  </tr>
                ) : filteredHistory.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="efaktura-table-message">
                      {hasActiveFilters ? tr('efakturaNoSearchResults') : tr('efakturaNoImportedDocuments')}
                    </td>
                  </tr>
                ) : (
                  filteredHistory.map((item) => {
                    const partyName = counterpartyName(item)
                    const partyPib = counterpartyPib(item)
                    const incoming = item.direction === 'incoming'
                    const expense = item.imported_as === 'expense'

                    return (
                      <tr key={item.id}>
                        <td className="efaktura-date-cell">
                          <strong>{formatDateTimeSr(item.created_at)}</strong>
                        </td>
                        <td>
                          <StatusBadge tone={incoming ? 'info' : 'success'} className="badge-pill">
                            {incoming ? <ArrowDownToLine size={13} /> : <ArrowUpFromLine size={13} />}
                            {incoming ? tr('efakturaIncoming') : tr('efakturaOutgoing')}
                          </StatusBadge>
                        </td>
                        <td className="efaktura-document-cell">
                          <strong title={item.invoice_number}>{item.invoice_number || UI_DASH}</strong>
                          <span>{formatDateSr(item.issued_date)}</span>
                        </td>
                        <td className="efaktura-counterparty-cell">
                          <strong title={partyName || ''}>{partyName || UI_DASH}</strong>
                          {partyPib ? <span>PIB {partyPib}</span> : null}
                        </td>
                        <td className="efaktura-amount-cell">{formatAmount(item.amount_rsd)}</td>
                        <td>
                          <div className="efaktura-record-cell">
                            <StatusBadge tone={expense ? 'warning' : 'success'} className="badge-pill">
                              {expense ? tr('efakturaImportedAsExpense') : tr('efakturaImportedAsIncome')}
                            </StatusBadge>
                            <span>#{item.imported_record_id || UI_DASH}</span>
                          </div>
                        </td>
                        <td>
                          <StatusBadge tone={item.source === 'api' ? 'info' : 'muted'} className="badge-pill">
                            {item.source === 'api' ? tr('efakturaSourceApi') : tr('efakturaSourceXml')}
                          </StatusBadge>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  )
}
