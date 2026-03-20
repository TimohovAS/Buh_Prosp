import { useEffect, useRef, useState } from 'react'
import { api, getUser } from '../api'
import { tr } from '../i18n'
import {
  DEFAULT_EFAKTURA_API_BASE_URL,
  isEfakturaApiConfigured,
  usesEfakturaDefaultRoutes,
} from '../efakturaDefaults'

function formatAmount(value) {
  if (typeof value === 'number') return `${value.toLocaleString('sr-RS')} RSD`
  if (value === null || value === undefined || value === '') return '—'
  return `${value} RSD`
}

function ResultSummary({ result }) {
  if (!result) return null

  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <h3 style={{ marginTop: 0, marginBottom: '0.75rem' }}>{tr('efakturaResultTitle')}</h3>
      <div className="stats-grid" style={{ marginBottom: '1rem' }}>
        <div className="stat-card">
          <div className="stat-label">{tr('efakturaCreatedDocuments')}</div>
          <div className="stat-value">{result.created_count || 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">{tr('efakturaCreatedIncome')}</div>
          <div className="stat-value">{result.created_income_count || 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">{tr('efakturaCreatedExpenses')}</div>
          <div className="stat-value">{result.created_expense_count || 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">{tr('efakturaSkipped')}</div>
          <div className="stat-value">{result.skipped_count || 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">{tr('efakturaErrors')}</div>
          <div className="stat-value" style={{ color: result.error_count ? 'var(--color-danger)' : undefined }}>
            {result.error_count || 0}
          </div>
        </div>
        {'fetched_count' in result ? (
          <div className="stat-card">
            <div className="stat-label">{tr('efakturaFetchedFromApi')}</div>
            <div className="stat-value">{result.fetched_count || 0}</div>
          </div>
        ) : null}
      </div>

      {(result.errors || []).length > 0 ? (
        <div className="settings-callout" style={{ borderColor: 'rgba(239, 68, 68, 0.35)' }}>
          <strong>{tr('efakturaImportErrorsTitle')}</strong>
          <ul style={{ margin: '0.5rem 0 0 1rem' }}>
            {result.errors.slice(0, 10).map((item, index) => (
              <li key={`${item.file_name || item.invoice_number || 'error'}-${index}`}>
                {item.file_name || item.invoice_number || tr('efakturaDocument')}: {item.error || tr('efakturaUnknownError')}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

export default function Efaktura() {
  const fileInputRef = useRef(null)
  const currentUser = getUser()
  const isAdmin = currentUser?.role === 'admin'

  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [lastResult, setLastResult] = useState(null)
  const [settingsInfo, setSettingsInfo] = useState(null)
  const [pageError, setPageError] = useState('')

  const loadHistory = async () => {
    setHistoryLoading(true)
    try {
      const [historyItems, settings] = await Promise.all([
        api.efaktura.history(200),
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
    loadHistory()
  }, [])

  const handleImportClick = () => {
    if (importing) return
    fileInputRef.current?.click()
  }

  const handleImportFiles = async (event) => {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    if (files.length === 0) return
    setImporting(true)
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
    setSyncing(true)
    try {
      const result = await api.efaktura.sync()
      setLastResult(result)
      await loadHistory()
    } catch (err) {
      setPageError(err.message || tr('efakturaSyncError'))
    } finally {
      setSyncing(false)
    }
  }

  const apiConfigured = isEfakturaApiConfigured(settingsInfo)
  const usingDefaultRoutes = usesEfakturaDefaultRoutes(settingsInfo)
  const effectiveBaseUrl = settingsInfo?.efaktura_api_base_url || DEFAULT_EFAKTURA_API_BASE_URL

  return (
    <>
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">{tr('efakturaTitle')}</h1>
          <div className="page-subtitle">{tr('efakturaSubtitle')}</div>
        </div>
        <div className="page-header-actions">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xml,text/xml,application/xml"
            multiple
            style={{ display: 'none' }}
            onChange={handleImportFiles}
          />
          <button className="btn btn-secondary" onClick={handleImportClick} disabled={importing}>
            {importing ? tr('efakturaImporting') : tr('efakturaImportXml')}
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSync}
            disabled={syncing || (isAdmin && !apiConfigured)}
            title={isAdmin && !apiConfigured ? tr('efakturaSyncSettingsHint') : ''}
          >
            {syncing ? tr('efakturaSyncing') : tr('efakturaSyncApi')}
          </button>
        </div>
      </div>

      <div className="page-body">
        {pageError ? (
          <div className="settings-callout" style={{ marginBottom: '1rem', borderColor: 'rgba(239, 68, 68, 0.35)' }}>
            <strong>{tr('loadError')}</strong>
            <div>{pageError}</div>
          </div>
        ) : null}

        {isAdmin ? (
          <div className="card" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
              <div>
                <div className="settings-field-label">{tr('efakturaApiSettingsTitle')}</div>
                <div style={{ fontSize: '0.95rem', color: 'var(--color-text-muted)' }}>
                  {apiConfigured ? tr('efakturaApiConfigured') : tr('efakturaApiNotConfigured')}
                </div>
                {apiConfigured && usingDefaultRoutes ? (
                  <div style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginTop: '0.35rem' }}>
                    {tr('efakturaUsingDefaultRoutes')}
                  </div>
                ) : null}
              </div>
              {settingsInfo ? (
                <div style={{ fontSize: '0.95rem', color: 'var(--color-text-muted)' }}>
                  <div>{tr('efakturaBaseUrl')}: {effectiveBaseUrl}</div>
                  <div>{tr('efakturaIncomingLabel')}: {settingsInfo.efaktura_sync_incoming ? tr('yes') : tr('no')}</div>
                  <div>{tr('efakturaOutgoingLabel')}: {settingsInfo.efaktura_sync_outgoing ? tr('yes') : tr('no')}</div>
                  <div>{tr('efakturaLookbackLabel')}: {settingsInfo.efaktura_sync_lookback_days || 0} {tr('efakturaDaysShort')}</div>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        <ResultSummary result={lastResult} />

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
            <h3 style={{ margin: 0 }}>{tr('efakturaHistoryTitle')}</h3>
            <button className="btn btn-secondary btn-sm" onClick={loadHistory} disabled={historyLoading}>
              {tr('serviceBackupsRefresh')}
            </button>
          </div>

          {historyLoading ? (
            <div>{tr('loading')}</div>
          ) : history.length === 0 ? (
            <div className="settings-empty-text">{tr('efakturaNoImportedDocuments')}</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{tr('efakturaImportedAt')}</th>
                    <th>{tr('efakturaDirection')}</th>
                    <th>{tr('efakturaDocument')}</th>
                    <th>{tr('efakturaCounterparty')}</th>
                    <th>{tr('amount')}</th>
                    <th>{tr('efakturaImportedAs')}</th>
                    <th>{tr('efakturaRecord')}</th>
                    <th>{tr('efakturaSource')}</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((item) => (
                    <tr key={item.id}>
                      <td>{item.created_at ? new Date(item.created_at).toLocaleString() : '—'}</td>
                      <td>{item.direction === 'incoming' ? tr('efakturaIncoming') : tr('efakturaOutgoing')}</td>
                      <td>
                        <div>{item.invoice_number || '—'}</div>
                        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>{item.issued_date || '—'}</div>
                      </td>
                      <td>{item.direction === 'incoming' ? (item.supplier_name || '—') : (item.customer_name || '—')}</td>
                      <td>{formatAmount(item.amount_rsd)}</td>
                      <td>{item.imported_as === 'expense' ? tr('efakturaImportedAsExpense') : tr('efakturaImportedAsIncome')}</td>
                      <td>{item.imported_record_id || '—'}</td>
                      <td>{item.source || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
