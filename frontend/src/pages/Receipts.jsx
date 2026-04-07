import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import ProjectSelect from '../components/ProjectSelect'
import SearchInput from '../components/SearchInput'

const UI_DASH = '\u2014'
const UI_CLOSE = '\u00D7'

function fmtMoney(value) {
  return Number(value || 0).toLocaleString('sr-RS', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtDateTime(value) {
  if (!value) return UI_DASH
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('sr-RS')
}

function buildContractLabel(contract) {
  if (!contract) return ''
  const parts = []
  if (contract.number) parts.push(contract.number)
  if (contract.subject) parts.push(contract.subject)
  return parts.join(` ${UI_DASH} `) || contract.number || contract.subject || ''
}

function getReceiptStatusMeta(status) {
  switch (status) {
    case 'linked_expense':
      return { label: tr('receiptStatusLinkedExpense'), background: 'rgba(59,130,246,0.18)', color: '#93c5fd' }
    case 'waiting_bank':
      return { label: tr('receiptStatusWaitingBank'), background: 'rgba(245,158,11,0.18)', color: '#fbbf24' }
    case 'matched_bank':
      return { label: tr('receiptStatusMatchedBank'), background: 'rgba(34,197,94,0.18)', color: '#4ade80' }
    case 'cash_expense':
      return { label: tr('receiptStatusCashExpense'), background: 'rgba(20,184,166,0.18)', color: '#2dd4bf' }
    case 'error':
      return { label: tr('receiptStatusError'), background: 'rgba(239,68,68,0.18)', color: '#f87171' }
    default:
      return { label: tr('receiptStatusNew'), background: 'rgba(148,163,184,0.18)', color: '#cbd5e1' }
  }
}

function ReceiptStatusBadge({ status }) {
  const meta = getReceiptStatusMeta(status)
  return (
    <span
      className="badge"
      style={{
        background: meta.background,
        color: meta.color,
        borderRadius: 999,
        padding: '0.25rem 0.55rem',
      }}
    >
      {meta.label}
    </span>
  )
}

export default function Receipts() {
  const location = useLocation()
  const isActivePage = location.pathname === '/receipts'
  const videoRef = useRef(null)
  const scanTimerRef = useRef(null)
  const streamRef = useRef(null)

  const [receipts, setReceipts] = useState([])
  const [projects, setProjects] = useState([])
  const [categories, setCategories] = useState([])
  const [contracts, setContracts] = useState([])
  const [loading, setLoading] = useState(true)
  const [lookupLoading, setLookupLoading] = useState(false)
  const [pageError, setPageError] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [projectFilter, setProjectFilter] = useState('')
  const [search, setSearch] = useState('')

  const [importModalOpen, setImportModalOpen] = useState(false)
  const [importUrl, setImportUrl] = useState('')
  const [importing, setImporting] = useState(false)
  const [scannerOpen, setScannerOpen] = useState(false)
  const [scanSupported, setScanSupported] = useState(false)
  const [scanError, setScanError] = useState('')

  const [detailReceipt, setDetailReceipt] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [detailAction, setDetailAction] = useState('')
  const [assignProjectId, setAssignProjectId] = useState('')
  const [assigningProject, setAssigningProject] = useState(false)
  const [expenseCandidates, setExpenseCandidates] = useState([])
  const [expenseCandidatesLoading, setExpenseCandidatesLoading] = useState(false)
  const [createExpenseSaving, setCreateExpenseSaving] = useState(false)
  const [unlinkingExpense, setUnlinkingExpense] = useState(false)
  const [deletingReceipt, setDeletingReceipt] = useState(false)
  const [createForm, setCreateForm] = useState({
    project_id: '',
    category_id: '',
    contract_id: '',
    description: '',
    note: '',
    payment_mode: 'auto',
  })

  const scannerRequiresHttps =
    typeof window !== 'undefined' &&
    !window.isSecureContext &&
    window.location.hostname !== 'localhost'
  const canUseScanner = scanSupported && !scannerRequiresHttps

  const statusOptions = useMemo(() => ([
    { value: 'all', label: tr('receiptStatusAll') },
    { value: 'new', label: tr('receiptStatusNew') },
    { value: 'linked_expense', label: tr('receiptStatusLinkedExpense') },
    { value: 'waiting_bank', label: tr('receiptStatusWaitingBank') },
    { value: 'matched_bank', label: tr('receiptStatusMatchedBank') },
    { value: 'cash_expense', label: tr('receiptStatusCashExpense') },
    { value: 'error', label: tr('receiptStatusError') },
  ]), [])

  const filteredContracts = useMemo(() => {
    if (!createForm.project_id) return contracts
    return contracts.filter((contract) => contract.project_id == null || String(contract.project_id) === String(createForm.project_id))
  }, [contracts, createForm.project_id])

  const receiptRows = useMemo(
    () => receipts.map((receipt) => ({ ...receipt, statusMeta: getReceiptStatusMeta(receipt.status) })),
    [receipts],
  )

  const getCategoryLabel = (categoryId) => {
    const category = categories.find((item) => String(item.id) === String(categoryId))
    return category ? category.name_ru : UI_DASH
  }

  const loadReceipts = async () => {
    setLoading(true)
    setPageError('')
    try {
      const payload = await api.receipts.list({
        ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
        ...(projectFilter ? { project_id: projectFilter } : {}),
        ...(search.trim() ? { search: search.trim() } : {}),
      })
      setReceipts(payload || [])
    } catch (error) {
      setReceipts([])
      setPageError(error.message || tr('loadError'))
    } finally {
      setLoading(false)
    }
  }

  const loadLookups = async () => {
    setLookupLoading(true)
    try {
      const [projectList, categoryList, contractList] = await Promise.all([
        api.projects.list({ show_archived: true }),
        api.categories.list({ category_type: 'expense' }),
        api.contracts.list({ limit: 500 }),
      ])
      setProjects(projectList || [])
      setCategories(categoryList || [])
      setContracts(contractList || [])
    } catch (error) {
      setPageError((previous) => previous || error.message || tr('loadError'))
    } finally {
      setLookupLoading(false)
    }
  }

  useEffect(() => {
    if (!isActivePage) return
    loadReceipts()
  }, [isActivePage, statusFilter, projectFilter, search])

  useEffect(() => {
    if (!isActivePage) return
    loadLookups()
  }, [isActivePage])

  useEffect(() => {
    if (typeof window === 'undefined') return
    setScanSupported(Boolean(window.BarcodeDetector) && Boolean(navigator.mediaDevices?.getUserMedia))
  }, [])

  useEffect(() => {
    if (!importModalOpen || !scannerOpen) return undefined

    let cancelled = false

    const stopScanner = () => {
      if (scanTimerRef.current) {
        clearTimeout(scanTimerRef.current)
        scanTimerRef.current = null
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop())
        streamRef.current = null
      }
      if (videoRef.current) {
        videoRef.current.srcObject = null
      }
    }

    const startScanner = async () => {
      try {
        setScanError('')
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } },
          audio: false,
        })
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play()
        }
        const detector = new window.BarcodeDetector({ formats: ['qr_code'] })
        const tick = async () => {
          if (cancelled || !videoRef.current) return
          try {
            const codes = await detector.detect(videoRef.current)
            const qrCode = codes.find((entry) => entry?.rawValue)
            if (qrCode?.rawValue) {
              setImportUrl(qrCode.rawValue)
              setScannerOpen(false)
              stopScanner()
              return
            }
          } catch {
          }
          scanTimerRef.current = setTimeout(tick, 350)
        }
        tick()
      } catch (error) {
        setScanError(error.message || tr('receiptScannerUnavailable'))
      }
    }

    startScanner()

    return () => {
      cancelled = true
      stopScanner()
    }
  }, [importModalOpen, scannerOpen, scanSupported])

  const resetImportState = () => {
    setImportUrl('')
    setImporting(false)
    setScannerOpen(false)
    setScanError('')
  }

  const openImportModal = () => {
    resetImportState()
    setImportModalOpen(true)
  }

  const closeImportModal = () => {
    resetImportState()
    setImportModalOpen(false)
  }

  const handleToggleScanner = () => {
    if (scannerOpen) {
      setScannerOpen(false)
      setScanError('')
      return
    }
    if (!scanSupported) {
      setScanError(tr('receiptScannerUnavailable'))
      return
    }
    if (scannerRequiresHttps) {
      setScanError(tr('receiptScanRequiresHttps'))
      return
    }
    setScanError('')
    setScannerOpen(true)
  }

  const hydrateDetailState = (receipt) => {
    setDetailReceipt(receipt)
    setDetailError('')
    setDetailAction('')
    setAssignProjectId(receipt?.project_id ? String(receipt.project_id) : '')
    setExpenseCandidates([])
    setCreateForm({
      project_id: receipt?.project_id ? String(receipt.project_id) : '',
      category_id: receipt?.category_id ? String(receipt.category_id) : '',
      contract_id: '',
      description: '',
      note: '',
      payment_mode: receipt?.payment_kind === 'cash' ? 'cash' : 'auto',
    })
  }

  const openReceiptDetail = async (receiptId) => {
    setDetailLoading(true)
    setDetailError('')
    try {
      const receipt = await api.receipts.get(receiptId)
      hydrateDetailState(receipt)
    } catch (error) {
      setDetailReceipt(null)
      setDetailError(error.message || tr('loadError'))
    } finally {
      setDetailLoading(false)
    }
  }

  const handleImportReceipt = async () => {
    if (!importUrl.trim()) return
    setImporting(true)
    setPageError('')
    try {
      const payload = await api.receipts.importFromQr({ verification_url: importUrl.trim() })
      closeImportModal()
      await loadReceipts()
      hydrateDetailState(payload.receipt)
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setImporting(false)
    }
  }

  const handleAssignProject = async () => {
    if (!detailReceipt) return
    setAssigningProject(true)
    try {
      const receipt = await api.receipts.assignProject(detailReceipt.id, {
        project_id: assignProjectId || null,
      })
      hydrateDetailState(receipt)
      await loadReceipts()
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
    } finally {
      setAssigningProject(false)
    }
  }

  const openExpenseCandidates = async () => {
    if (!detailReceipt) return
    setDetailAction('link')
    setExpenseCandidatesLoading(true)
    try {
      const items = await api.receipts.expenseCandidates(detailReceipt.id)
      setExpenseCandidates(items || [])
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
      setExpenseCandidates([])
    } finally {
      setExpenseCandidatesLoading(false)
    }
  }

  const handleLinkExpense = async (expenseId) => {
    if (!detailReceipt) return
    setExpenseCandidatesLoading(true)
    try {
      const receipt = await api.receipts.linkExpense(detailReceipt.id, { expense_id: expenseId })
      hydrateDetailState(receipt)
      await loadReceipts()
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
    } finally {
      setExpenseCandidatesLoading(false)
    }
  }

  const handleCreateExpense = async (event) => {
    event.preventDefault()
    if (!detailReceipt) return
    setCreateExpenseSaving(true)
    try {
      const receipt = await api.receipts.createExpense(detailReceipt.id, {
        project_id: createForm.project_id || null,
        category_id: createForm.category_id || null,
        contract_id: createForm.contract_id || null,
        description: createForm.description || null,
        note: createForm.note || null,
        payment_mode: createForm.payment_mode || 'auto',
      })
      hydrateDetailState(receipt)
      await loadReceipts()
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
    } finally {
      setCreateExpenseSaving(false)
    }
  }

  const handleUnlinkExpense = async () => {
    if (!detailReceipt) return
    setUnlinkingExpense(true)
    try {
      const receipt = await api.receipts.unlinkExpense(detailReceipt.id)
      hydrateDetailState(receipt)
      await loadReceipts()
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
    } finally {
      setUnlinkingExpense(false)
    }
  }

  const handleDeleteReceipt = async () => {
    if (!detailReceipt || deletingReceipt) return
    if (typeof window !== 'undefined' && !window.confirm(tr('receiptDeleteConfirm'))) return
    setDeletingReceipt(true)
    try {
      await api.receipts.delete(detailReceipt.id)
      setDetailReceipt(null)
      setDetailError('')
      setDetailAction('')
      await loadReceipts()
    } catch (error) {
      setDetailError(error.message || tr('loadError'))
    } finally {
      setDeletingReceipt(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">{tr('receipts')}</h1>
        </div>
        <div className="page-header-actions">
          <select className="form-input" style={{ width: 180 }} value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <select className="form-input" style={{ width: 220 }} value={projectFilter} onChange={(event) => setProjectFilter(event.target.value)}>
            <option value="">{tr('receiptProjectFilterAll')}</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>{project.name}</option>
            ))}
          </select>
          <SearchInput placeholder={tr('search')} value={search} onChange={setSearch} style={{ width: 220 }} />
          <button type="button" className="btn btn-primary" onClick={openImportModal}>
            {tr('receiptImportButton')}
          </button>
        </div>
      </div>

      {pageError ? <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>{pageError}</div> : null}

      <div className="card">
        <div className="card-title">{tr('receipts')}</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{tr('date')}</th>
                <th>{tr('receiptSeller')}</th>
                <th>{tr('invoiceNumber')}</th>
                <th>{tr('receiptPaymentType')}</th>
                <th>{tr('project')}</th>
                <th>{tr('amount')}</th>
                <th>{tr('status')}</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7}>{tr('loading')}</td></tr>
              ) : receiptRows.length === 0 ? (
                <tr><td colSpan={7} style={{ color: 'var(--color-text-muted)' }}>{tr('noRecords')}</td></tr>
              ) : (
                receiptRows.map((receipt) => (
                  <tr
                    key={receipt.id}
                    className="record-row"
                    onClick={() => openReceiptDetail(receipt.id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        openReceiptDetail(receipt.id)
                      }
                    }}
                    tabIndex={0}
                  >
                    <td className="date-cell">{fmtDateTime(receipt.receipt_datetime)}</td>
                    <td>
                      <div style={{ fontWeight: 700 }}>{receipt.seller_name || UI_DASH}</div>
                      <div style={{ color: 'var(--color-text-muted)', fontSize: '0.82rem' }}>{receipt.seller_tax_id || UI_DASH}</div>
                    </td>
                    <td>{receipt.invoice_number || UI_DASH}</td>
                    <td>{receipt.payment_type || UI_DASH}</td>
                    <td>{receipt.project_name || UI_DASH}</td>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap', fontWeight: 700 }}>{fmtMoney(receipt.total_amount)} {receipt.currency || 'RSD'}</td>
                    <td><ReceiptStatusBadge status={receipt.status} /></td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {importModalOpen && (
        <div className="modal-overlay" onClick={closeImportModal}>
          <div className="modal receipt-import-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">{tr('receiptImportTitle')}</h2>
              <button className="modal-close" onClick={closeImportModal}>{UI_CLOSE}</button>
            </div>
            <div className="modal-body">
              <div className="receipt-import-layout">
                <div className="record-detail-card receipt-import-card">
                  <div className="form-group">
                    <label className="form-label">{tr('receiptQrUrl')}</label>
                    <textarea
                      className="form-input"
                      rows={5}
                      value={importUrl}
                      onChange={(event) => setImportUrl(event.target.value)}
                      placeholder="https://suf.purs.gov.rs/v/?vl=..."
                      style={{ resize: 'vertical' }}
                    />
                  </div>
                  <div className="receipt-import-actions">
                    <button type="button" className="btn btn-secondary" onClick={handleToggleScanner}>
                      {scannerOpen ? tr('receiptScanStop') : tr('receiptScanStart')}
                    </button>
                    <button type="button" className="btn btn-primary" onClick={handleImportReceipt} disabled={importing || !importUrl.trim()}>
                      {importing ? tr('receiptImporting') : tr('receiptImportButton')}
                    </button>
                  </div>
                  <div className="receipt-import-help">
                    {canUseScanner ? tr('receiptScanHint') : (scannerRequiresHttps ? tr('receiptScanRequiresHttps') : tr('receiptScannerUnavailable'))}
                  </div>
                  {scanError ? (
                    <div className="alert alert-danger" style={{ marginTop: '0.75rem' }}>{scanError}</div>
                  ) : null}
                </div>
                <div className="record-detail-card receipt-camera-card">
                  <div className="record-field-label">{tr('receiptScanCamera')}</div>
                  {scannerOpen && canUseScanner ? (
                    <video
                      ref={videoRef}
                      autoPlay
                      playsInline
                      muted
                      className="receipt-camera-preview"
                    />
                  ) : (
                    <div className="receipt-camera-placeholder">
                      <strong style={{ display: 'block', marginBottom: '0.35rem' }}>
                        {canUseScanner ? tr('receiptScanCameraIdle') : tr('receiptScanCamera')}
                      </strong>
                      <span>
                        {canUseScanner ? tr('receiptScanHint') : (scannerRequiresHttps ? tr('receiptScanRequiresHttps') : tr('receiptScannerUnavailable'))}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {(detailReceipt || detailLoading || detailError) && (
        <div className="modal-overlay" onClick={() => { setDetailReceipt(null); setDetailError(''); setDetailAction('') }}>
          <div className="modal receipt-detail-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">
                {tr('receiptDetailTitle')} {UI_DASH} {detailReceipt?.invoice_number || (detailReceipt ? `#${detailReceipt.id}` : UI_DASH)}
              </h2>
              <button className="modal-close" onClick={() => { setDetailReceipt(null); setDetailError(''); setDetailAction('') }}>{UI_CLOSE}</button>
            </div>
            <div className="modal-body">
              {detailLoading ? (
                <div>{tr('loading')}</div>
              ) : detailError && !detailReceipt ? (
                <div className="alert alert-danger">{detailError}</div>
              ) : detailReceipt ? (
                <>
                  {detailError ? <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>{detailError}</div> : null}
                  <div className="record-detail-grid" style={{ alignItems: 'start' }}>
                    <div className="record-detail-card">
                      <div className="record-field-grid">
                        <div className="record-field">
                          <span className="record-field-label">{tr('receiptSeller')}</span>
                          <span className="record-field-value">{detailReceipt.seller_name || UI_DASH}</span>
                        </div>
                        <div className="record-field">
                          <span className="record-field-label">{tr('invoiceNumber')}</span>
                          <span className="record-field-value">{detailReceipt.invoice_number || UI_DASH}</span>
                        </div>
                        <div className="record-field">
                          <span className="record-field-label">{tr('date')}</span>
                          <span className="record-field-value">{fmtDateTime(detailReceipt.receipt_datetime)}</span>
                        </div>
                        <div className="record-field">
                          <span className="record-field-label">{tr('status')}</span>
                          <span className="record-field-value"><ReceiptStatusBadge status={detailReceipt.status} /></span>
                        </div>
                        <div className="record-field">
                          <span className="record-field-label">{tr('receiptPaymentType')}</span>
                          <span className="record-field-value">{detailReceipt.payment_type || UI_DASH}</span>
                        </div>
                        <div className="record-field">
                          <span className="record-field-label">{tr('amount')}</span>
                          <span className="record-field-value">{fmtMoney(detailReceipt.total_amount)} {detailReceipt.currency || 'RSD'}</span>
                        </div>
                        <div className="record-field">
                          <span className="record-field-label">{tr('project')}</span>
                          <span className="record-field-value">{detailReceipt.project_name || UI_DASH}</span>
                        </div>
                        <div className="record-field">
                          <span className="record-field-label">{tr('category')}</span>
                          <span className="record-field-value">{getCategoryLabel(detailReceipt.category_id)}</span>
                        </div>
                        <div className="record-field full">
                          <span className="record-field-label">{tr('address')}</span>
                          <div className="record-field-text">
                            {[detailReceipt.seller_address, detailReceipt.seller_city].filter(Boolean).join(', ') || UI_DASH}
                          </div>
                        </div>
                        <div className="record-field full">
                          <span className="record-field-label">{tr('receiptItems')}</span>
                          <div className="table-wrap table-wrap-scroll" style={{ maxHeight: 360 }}>
                            <table>
                              <thead>
                                <tr>
                                  <th>#</th>
                                  <th>{tr('name')}</th>
                                  <th style={{ textAlign: 'right' }}>{tr('receiptQuantity')}</th>
                                  <th style={{ textAlign: 'right' }}>{tr('receiptUnitPrice')}</th>
                                  <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {detailReceipt.items?.length ? detailReceipt.items.map((item) => (
                                  <tr key={item.id}>
                                    <td>{item.line_no}</td>
                                    <td>{item.name}</td>
                                    <td style={{ textAlign: 'right' }}>{fmtMoney(item.quantity)}</td>
                                    <td style={{ textAlign: 'right' }}>{fmtMoney(item.unit_price)} RSD</td>
                                    <td style={{ textAlign: 'right' }}>{fmtMoney(item.total_amount)} RSD</td>
                                  </tr>
                                )) : (
                                  <tr><td colSpan={5} style={{ color: 'var(--color-text-muted)' }}>{tr('noRecords')}</td></tr>
                                )}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="record-detail-card">
                    <div className="record-actions-grid" style={{ marginBottom: '1rem' }}>
                      {!detailReceipt.expense_id ? (
                        <>
                          <button type="button" className="btn btn-primary" onClick={() => setDetailAction('create')}>
                            {tr('receiptCreateExpense')}
                            </button>
                            <button type="button" className="btn btn-secondary" onClick={openExpenseCandidates}>
                              {tr('receiptLinkExpense')}
                            </button>
                          </>
                        ) : (
                          <button type="button" className="btn btn-danger" onClick={handleUnlinkExpense} disabled={unlinkingExpense}>
                            {unlinkingExpense ? tr('loading') : tr('receiptUnlinkExpense')}
                          </button>
                        )}
                        <button type="button" className="btn btn-danger" onClick={handleDeleteReceipt} disabled={deletingReceipt || unlinkingExpense || createExpenseSaving || assigningProject}>
                          {deletingReceipt ? tr('loading') : tr('receiptDelete')}
                        </button>
                      </div>

                      <div className="form-group">
                        <label className="form-label">{tr('project')}</label>
                        <ProjectSelect
                          projects={projects}
                          value={assignProjectId}
                          onChange={setAssignProjectId}
                          allowEmpty
                          emptyLabel={tr('receiptProjectFilterAll')}
                        />
                      </div>
                      <button type="button" className="btn btn-secondary" onClick={handleAssignProject} disabled={assigningProject || lookupLoading}>
                        {assigningProject ? tr('loading') : tr('receiptAssignProject')}
                      </button>

                      <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
                        <div className="record-field">
                          <span className="record-field-label">{tr('receiptLinkedExpense')}</span>
                          <span className="record-field-value">
                            {detailReceipt.expense_id
                              ? `#${detailReceipt.expense_id} ${UI_DASH} ${(detailReceipt.expense_source || '').trim() || UI_DASH} ${UI_DASH} ${(detailReceipt.expense_status || '').trim() || UI_DASH}`
                              : UI_DASH}
                          </span>
                        </div>
                        <div className="record-field" style={{ marginTop: '0.75rem' }}>
                          <span className="record-field-label">{tr('receiptLinkedBank')}</span>
                          <span className="record-field-value">{detailReceipt.bank_transaction_id ? `#${detailReceipt.bank_transaction_id}` : UI_DASH}</span>
                        </div>
                        <div className="record-field" style={{ marginTop: '0.75rem' }}>
                          <span className="record-field-label">{tr('cashRegister')}</span>
                          <span className="record-field-value">{detailReceipt.cash_entry_id ? `#${detailReceipt.cash_entry_id}` : UI_DASH}</span>
                        </div>
                      </div>

                      {detailAction === 'link' ? (
                        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
                          <div className="record-field-label" style={{ marginBottom: '0.75rem' }}>{tr('receiptExpenseCandidates')}</div>
                          {expenseCandidatesLoading ? (
                            <div>{tr('loading')}</div>
                          ) : expenseCandidates.length === 0 ? (
                            <div style={{ color: 'var(--color-text-muted)' }}>{tr('receiptNoCandidates')}</div>
                          ) : (
                            <div style={{ display: 'grid', gap: '0.75rem', maxHeight: 360, overflowY: 'auto' }}>
                              {expenseCandidates.map((candidate) => (
                                <div key={candidate.id} className="record-detail-card" style={{ padding: '0.85rem' }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}>
                                    <div>
                                      <div style={{ fontWeight: 700 }}>{candidate.description || UI_DASH}</div>
                                      <div style={{ color: 'var(--color-text-muted)', fontSize: '0.84rem', marginTop: '0.25rem' }}>
                                        {candidate.date} {UI_DASH} {candidate.project_name || UI_DASH}
                                      </div>
                                      <div style={{ color: 'var(--color-text-muted)', fontSize: '0.84rem', marginTop: '0.25rem' }}>
                                        {candidate.contract_number || UI_DASH}
                                      </div>
                                    </div>
                                    <div style={{ textAlign: 'right' }}>
                                      <div style={{ fontWeight: 700 }}>{fmtMoney(candidate.amount)} {candidate.currency || 'RSD'}</div>
                                      <button type="button" className="btn btn-sm btn-primary" style={{ marginTop: '0.5rem' }} onClick={() => handleLinkExpense(candidate.id)}>
                                        {tr('receiptLinkExpense')}
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ) : null}

                      {detailAction === 'create' ? (
                        <form onSubmit={handleCreateExpense} style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
                          <div className="form-group">
                            <label className="form-label">{tr('receiptCreateMode')}</label>
                            <select
                              className="form-input"
                              value={createForm.payment_mode}
                              onChange={(event) => setCreateForm((prev) => ({ ...prev, payment_mode: event.target.value }))}
                            >
                              <option value="auto">{tr('receiptCreateModeAuto')}</option>
                              <option value="bank">{tr('receiptCreateModeBank')}</option>
                              <option value="cash">{tr('receiptCreateModeCash')}</option>
                            </select>
                          </div>
                          <div className="form-group">
                            <label className="form-label">{tr('project')}</label>
                            <ProjectSelect
                              projects={projects}
                              value={createForm.project_id}
                              onChange={(value) => setCreateForm((prev) => ({ ...prev, project_id: value, contract_id: '' }))}
                              allowEmpty
                              emptyLabel={tr('receiptProjectFilterAll')}
                            />
                          </div>
                          <div className="form-group">
                            <label className="form-label">{tr('category')}</label>
                            <select
                              className="form-input"
                              value={createForm.category_id}
                              onChange={(event) => setCreateForm((prev) => ({ ...prev, category_id: event.target.value }))}
                            >
                              <option value="">{UI_DASH}</option>
                              {categories.map((category) => (
                                <option key={category.id} value={category.id}>{category.name_ru}</option>
                              ))}
                            </select>
                          </div>
                          <div className="form-group">
                            <label className="form-label">{tr('contracts')}</label>
                            <select
                              className="form-input"
                              value={createForm.contract_id}
                              onChange={(event) => setCreateForm((prev) => ({ ...prev, contract_id: event.target.value }))}
                            >
                              <option value="">{UI_DASH}</option>
                              {filteredContracts.map((contract) => (
                                <option key={contract.id} value={contract.id}>{buildContractLabel(contract)}</option>
                              ))}
                            </select>
                          </div>
                          <div className="form-group">
                            <label className="form-label">{tr('description')}</label>
                            <input
                              className="form-input"
                              value={createForm.description}
                              onChange={(event) => setCreateForm((prev) => ({ ...prev, description: event.target.value }))}
                            />
                          </div>
                          <div className="form-group">
                            <label className="form-label">{tr('note')}</label>
                            <textarea
                              className="form-input"
                              rows={3}
                              value={createForm.note}
                              onChange={(event) => setCreateForm((prev) => ({ ...prev, note: event.target.value }))}
                            />
                          </div>
                          <button type="submit" className="btn btn-primary" disabled={createExpenseSaving}>
                            {createExpenseSaving ? tr('loading') : tr('receiptCreateExpense')}
                          </button>
                        </form>
                      ) : null}
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
