import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import SearchInput from '../components/SearchInput'
import StatusBadge from '../components/StatusBadge'
import SortIndicator from '../components/SortIndicator'
import { UI_DASH, formatDateSr as fmtDate, formatMoney2OrDash as fmt } from '../utils/formatters'

function LoanStatus({ status }) {
  const label = status === 'open' ? tr('loanOpen') : status === 'repaid' ? tr('loanRepaidComplete') : tr('statusCancelled')
  const tone = status === 'open' ? 'warning' : status === 'repaid' ? 'success' : 'muted'
  return <StatusBadge tone={tone}>{label}</StatusBadge>
}

function typeLabel(type) {
  if (type === 'owner_funds') return tr('bankTxOwnerFundsLabel')
  return type === 'borrowed' ? tr('loanBorrowed') : tr('loanIssued')
}

function ownerFundsLabel(movement) {
  return movement.direction === 'in' ? tr('bankTxOwnerFundsInStatus') : tr('bankTxOwnerFundsOutStatus')
}

function ownerFundsAmount(value, currency = 'RSD') {
  return `${fmt(value)} ${currency}`
}

function ownerFundsDescription(movement) {
  const cleaned = String(movement.purpose || '')
    .replace(/\[[^\]]+\]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return cleaned || ownerFundsLabel(movement)
}

function ownerFundsTooltip(movement) {
  return [
    `${tr('counterpartyName')}: ${movement.counterparty_name || UI_DASH}`,
    `${tr('bankTxReference')}: ${movement.bank_reference || UI_DASH}`,
    movement.purpose ? `${tr('description')}: ${movement.purpose}` : null,
  ].filter(Boolean).join('\n')
}

function ownerFundsCounterpartyName(movements) {
  const rawName = movements.find((movement) => movement.counterparty_name)?.counterparty_name || ''
  return rawName.replace(/\b\d{10,}\b/g, '').replace(/\s+/g, ' ').trim() || tr('bankTxOwnerFundsLabel')
}

function movementLabel(loan, movement) {
  if (movement.movement_type === 'disbursement') {
    return loan.loan_type === 'borrowed' ? tr('loanReceivedStatus') : tr('loanIssuedStatus')
  }
  return loan.loan_type === 'borrowed' ? tr('loanRepaidStatus') : tr('loanReturnedStatus')
}

export default function CounterpartyLoans() {
  const location = useLocation()
  const isActivePage = location.pathname === '/counterparty-loans'
  const [items, setItems] = useState([])
  const [ownerFundsItems, setOwnerFundsItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('open')
  const [sortCol, setSortCol] = useState('start_date')
  const [sortAsc, setSortAsc] = useState(false)
  const [detail, setDetail] = useState(null)
  const [noteDraft, setNoteDraft] = useState('')
  const [savingNote, setSavingNote] = useState(false)
  const [ownerFundsDetail, setOwnerFundsDetail] = useState(null)
  const [ownerFundsSummaryOpen, setOwnerFundsSummaryOpen] = useState(false)

  const openLoanDetail = (loan) => {
    setDetail(loan)
    setNoteDraft(loan?.note || '')
  }

  const load = async () => {
    setLoading(true)
    try {
      const includeLoans = typeFilter !== 'owner_funds'
      const includeOwnerFunds = typeFilter === '' || typeFilter === 'owner_funds'
      const params = {}
      if (typeFilter && includeLoans) params.loan_type = typeFilter
      if (statusFilter) params.status = statusFilter
      const [loans, ownerFunds] = await Promise.all([
        includeLoans ? api.counterpartyLoans.list(params) : Promise.resolve([]),
        includeOwnerFunds ? api.counterpartyLoans.ownerFunds({ limit: 500 }) : Promise.resolve([]),
      ])
      setItems(loans)
      setOwnerFundsItems(ownerFunds)
      const openId = new URLSearchParams(location.search).get('open')
      if (openId && includeLoans) {
        const selected = loans.find((loan) => String(loan.id) === openId) || await api.counterpartyLoans.get(openId)
        openLoanDetail(selected)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!isActivePage) return
    load().catch(() => {
      setItems([])
      setOwnerFundsItems([])
    })
  }, [isActivePage, typeFilter, statusFilter, location.search])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    let rows = q
      ? items.filter((loan) =>
          (loan.counterparty_name || '').toLowerCase().includes(q) ||
          (loan.agreement_number || '').toLowerCase().includes(q))
      : items
    return [...rows].sort((left, right) => {
      const a = left[sortCol] ?? ''
      const b = right[sortCol] ?? ''
      if (typeof a === 'number' || typeof b === 'number') return sortAsc ? Number(a) - Number(b) : Number(b) - Number(a)
      return sortAsc ? String(a).localeCompare(String(b)) : String(b).localeCompare(String(a))
    })
  }, [items, search, sortAsc, sortCol])

  const filteredOwnerFunds = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return ownerFundsItems
    return ownerFundsItems.filter((movement) =>
      (movement.counterparty_name || '').toLowerCase().includes(q) ||
      (movement.purpose || '').toLowerCase().includes(q) ||
      (movement.bank_reference || '').toLowerCase().includes(q))
  }, [ownerFundsItems, search])

  const ownerFundsTotals = useMemo(() => {
    const totals = filteredOwnerFunds.reduce((acc, movement) => {
      const amount = Number(movement.amount || 0)
      if (movement.direction === 'in') acc.in += amount
      if (movement.direction === 'out') acc.out += amount
      return acc
    }, { in: 0, out: 0 })
    return { ...totals, balance: totals.in - totals.out }
  }, [filteredOwnerFunds])

  const ownerFundsBalanceById = useMemo(() => {
    let balance = 0
    return [...ownerFundsItems]
      .sort((left, right) => {
        const byDate = String(left.date || '').localeCompare(String(right.date || ''))
        return byDate || Number(left.id || 0) - Number(right.id || 0)
      })
      .reduce((acc, movement) => {
        const amount = Number(movement.amount || 0)
        balance += movement.direction === 'in' ? amount : -amount
        acc[movement.id] = balance
        return acc
      }, {})
  }, [ownerFundsItems])

  const ownerFundsSummary = useMemo(() => {
    if (filteredOwnerFunds.length === 0) return null
    const sorted = [...filteredOwnerFunds].sort((left, right) => {
      const byDate = String(left.date || '').localeCompare(String(right.date || ''))
      return byDate || Number(left.id || 0) - Number(right.id || 0)
    })
    const firstMovement = sorted[0]
    return {
      start_date: firstMovement?.date,
      counterparty_name: ownerFundsCounterpartyName(filteredOwnerFunds),
      disbursed_amount: ownerFundsTotals.in,
      repaid_amount: ownerFundsTotals.out,
      outstanding_amount: ownerFundsTotals.balance,
      currency: firstMovement?.currency || 'RSD',
      status: ownerFundsTotals.balance === 0 ? 'repaid' : 'open',
    }
  }, [filteredOwnerFunds, ownerFundsTotals])

  const toggleSort = (column) => {
    if (column === sortCol) setSortAsc((current) => !current)
    else {
      setSortCol(column)
      setSortAsc(false)
    }
  }

  const saveLoanNote = async () => {
    if (!detail) return
    setSavingNote(true)
    try {
      const updated = await api.counterpartyLoans.update(detail.id, { note: noteDraft })
      setDetail(updated)
      setNoteDraft(updated.note || '')
      setItems((current) => current.map((loan) => (loan.id === updated.id ? updated : loan)))
    } finally {
      setSavingNote(false)
    }
  }

  return (
    <div className="page">
      <PageHeader
        title={tr('counterpartyLoans')}
        actions={(
          <>
            <select className="form-input" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} style={{ width: 150 }}>
              <option value="">{tr('filterAll')}</option>
              <option value="borrowed">{tr('loanBorrowed')}</option>
              <option value="issued">{tr('loanIssued')}</option>
              <option value="owner_funds">{tr('bankTxOwnerFundsLabel')}</option>
            </select>
            <select className="form-input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} style={{ width: 145 }} disabled={typeFilter === 'owner_funds'}>
              <option value="">{tr('filterAll')}</option>
              <option value="open">{tr('loanOpen')}</option>
              <option value="repaid">{tr('loanRepaidComplete')}</option>
            </select>
            <SearchInput placeholder={tr('search')} value={search} onChange={setSearch} style={{ width: 230 }} />
          </>
        )}
      />
      <div className="page-body">
        {typeFilter !== 'owner_funds' ? (
        <div className="card">
          <div className="table-wrap">
            <table className="loan-list-table">
              <thead>
                <tr>
                  <th onClick={() => toggleSort('start_date')}>{tr('date')} <SortIndicator active={sortCol === 'start_date'} asc={sortAsc} /></th>
                  <th onClick={() => toggleSort('counterparty_name')}>{tr('counterpartyName')} <SortIndicator active={sortCol === 'counterparty_name'} asc={sortAsc} /></th>
                  <th>{tr('loanType')}</th>
                  <th>{tr('loanAgreementNumber')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('loanDisbursed')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('loanRepaid')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('loanOutstanding')}</th>
                  <th>{tr('status')}</th>
                </tr>
              </thead>
              <tbody>
                {loading ? <tr><td colSpan={8}>{tr('loading')}</td></tr>
                  : filtered.length === 0 ? <tr><td colSpan={8}>{tr('noRecords')}</td></tr>
                    : filtered.map((loan) => (
                      <tr key={loan.id} className="record-row" tabIndex={0} onClick={() => openLoanDetail(loan)} onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          openLoanDetail(loan)
                        }
                      }}>
                        <td>{fmtDate(loan.start_date)}</td>
                        <td>{loan.counterparty_name}</td>
                        <td>{typeLabel(loan.loan_type)}</td>
                        <td>{loan.agreement_number || UI_DASH}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(loan.disbursed_amount)}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(loan.repaid_amount)}</td>
                        <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmt(loan.outstanding_amount)}</td>
                        <td><LoanStatus status={loan.status} /></td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
        </div>
        ) : null}
        {typeFilter === '' || typeFilter === 'owner_funds' ? (
        <div className="card loan-owner-funds-card">
          <div className="loan-section-header">
            <h3>{tr('bankTxOwnerFundsLabel')}</h3>
          </div>
          <div className="table-wrap">
            <table className="loan-list-table loan-owner-funds-table">
              <thead>
                <tr>
                  <th>{tr('date')}</th>
                  <th>{tr('counterpartyName')}</th>
                  <th>{tr('loanType')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('ownerFundsIn')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('ownerFundsOut')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('loanOutstanding')}</th>
                  <th>{tr('status')}</th>
                </tr>
              </thead>
              <tbody>
                {loading ? <tr><td colSpan={7}>{tr('loading')}</td></tr>
                  : !ownerFundsSummary ? <tr><td colSpan={7}>{tr('noRecords')}</td></tr>
                    : (
                      <tr className="record-row" tabIndex={0} onClick={() => setOwnerFundsSummaryOpen(true)} onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          setOwnerFundsSummaryOpen(true)
                        }
                      }}>
                        <td>{fmtDate(ownerFundsSummary.start_date)}</td>
                        <td>{ownerFundsSummary.counterparty_name}</td>
                        <td>{tr('bankTxOwnerFundsLabel')}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(ownerFundsSummary.disbursed_amount)}</td>
                        <td style={{ textAlign: 'right' }}>{fmt(ownerFundsSummary.repaid_amount)}</td>
                        <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmt(ownerFundsSummary.outstanding_amount)}</td>
                        <td><LoanStatus status={ownerFundsSummary.status} /></td>
                      </tr>
                    )}
              </tbody>
            </table>
          </div>
        </div>
        ) : null}
      </div>
      <Modal
        isOpen={!!detail}
        onClose={() => setDetail(null)}
        title={detail ? `${tr('counterpartyLoans')} #${detail.id}` : tr('counterpartyLoans')}
        className="loan-detail-modal"
        maxWidth="1040px"
      >
        {detail ? (
          <div className="loan-detail-layout">
            <div className="loan-detail-summary">
              <div><span>{tr('counterpartyName')}</span><strong>{detail.counterparty_name}</strong></div>
              <div><span>{tr('loanType')}</span><strong>{typeLabel(detail.loan_type)}</strong></div>
              <div><span>{tr('loanAgreementNumber')}</span><strong>{detail.agreement_number || UI_DASH}</strong></div>
              <div><span>{tr('loanDueDate')}</span><strong>{fmtDate(detail.due_date)}</strong></div>
              <div><span>{tr('loanOutstanding')}</span><strong>{fmt(detail.outstanding_amount)} {detail.currency}</strong></div>
              <div><span>{tr('status')}</span><LoanStatus status={detail.status} /></div>
              <div className="loan-detail-note">
                <span>{tr('note')}</span>
                <textarea
                  className="form-input"
                  rows={3}
                  value={noteDraft}
                  onChange={(event) => setNoteDraft(event.target.value)}
                />
                <div className="loan-note-actions">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={savingNote || noteDraft === (detail.note || '')}
                    onClick={saveLoanNote}
                  >
                    {savingNote ? tr('loading') : tr('save')}
                  </button>
                </div>
              </div>
            </div>
            <div className="table-wrap">
              <table className="loan-movement-table">
                <thead>
                  <tr>
                    <th>{tr('date')}</th>
                    <th>{tr('type')}</th>
                    <th>{tr('bankTxReference')}</th>
                    <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.movements.map((movement) => (
                    <tr key={movement.id}>
                      <td>{fmtDate(movement.date)}</td>
                      <td>
                        {movementLabel(detail, movement)}
                        {movement.note ? <div className="loan-movement-note">{movement.note}</div> : null}
                      </td>
                      <td>
                        {movement.bank_reference || UI_DASH}
                        {movement.bank_purpose ? <div className="loan-movement-note">{movement.bank_purpose}</div> : null}
                      </td>
                      <td style={{ textAlign: 'right' }}>{fmt(movement.amount)} {movement.currency}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </Modal>
      <Modal
        isOpen={ownerFundsSummaryOpen}
        onClose={() => setOwnerFundsSummaryOpen(false)}
        title={tr('bankTxOwnerFundsLabel')}
        className="loan-detail-modal"
        maxWidth="1040px"
      >
        {ownerFundsSummary ? (
          <div className="loan-detail-layout">
            <div className="loan-detail-summary">
              <div><span>{tr('counterpartyName')}</span><strong>{ownerFundsSummary.counterparty_name}</strong></div>
              <div><span>{tr('loanType')}</span><strong>{tr('bankTxOwnerFundsLabel')}</strong></div>
              <div><span>{tr('date')}</span><strong>{fmtDate(ownerFundsSummary.start_date)}</strong></div>
              <div><span>{tr('ownerFundsIn')}</span><strong>{ownerFundsAmount(ownerFundsSummary.disbursed_amount, ownerFundsSummary.currency)}</strong></div>
              <div><span>{tr('ownerFundsOut')}</span><strong>{ownerFundsAmount(ownerFundsSummary.repaid_amount, ownerFundsSummary.currency)}</strong></div>
              <div><span>{tr('ownerFundsCompanyOwes')}</span><strong className={ownerFundsSummary.outstanding_amount >= 0 ? 'amount-positive' : 'amount-negative'}>{ownerFundsAmount(ownerFundsSummary.outstanding_amount, ownerFundsSummary.currency)}</strong></div>
            </div>
            <div className="table-wrap">
              <table className="loan-movement-table">
                <thead>
                  <tr>
                    <th>{tr('date')}</th>
                    <th>{tr('type')}</th>
                    <th>{tr('description')}</th>
                    <th style={{ textAlign: 'right' }}>{tr('ownerFundsIn')}</th>
                    <th style={{ textAlign: 'right' }}>{tr('ownerFundsOut')}</th>
                    <th style={{ textAlign: 'right' }}>{tr('loanOutstanding')}</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOwnerFunds.map((movement) => (
                    <tr key={movement.id} className="record-row" tabIndex={0} title={ownerFundsTooltip(movement)} onClick={() => setOwnerFundsDetail(movement)} onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        setOwnerFundsDetail(movement)
                      }
                    }}>
                      <td>{fmtDate(movement.date)}</td>
                      <td>{ownerFundsLabel(movement)}</td>
                      <td className="loan-owner-funds-description">{ownerFundsDescription(movement)}</td>
                      <td style={{ textAlign: 'right' }}>{movement.direction === 'in' ? ownerFundsAmount(movement.amount, movement.currency) : UI_DASH}</td>
                      <td style={{ textAlign: 'right' }}>{movement.direction === 'out' ? ownerFundsAmount(movement.amount, movement.currency) : UI_DASH}</td>
                      <td style={{ textAlign: 'right', fontWeight: 700 }}>{ownerFundsAmount(ownerFundsBalanceById[movement.id] || 0, movement.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </Modal>
      <Modal
        isOpen={!!ownerFundsDetail}
        onClose={() => setOwnerFundsDetail(null)}
        title={ownerFundsDetail ? `${tr('bankTxOwnerFundsLabel')} #${ownerFundsDetail.id}` : tr('bankTxOwnerFundsLabel')}
        className="loan-detail-modal"
        maxWidth="900px"
      >
        {ownerFundsDetail ? (
          <div className="loan-detail-layout">
            <div className="loan-detail-summary">
              <div><span>{tr('counterpartyName')}</span><strong>{ownerFundsDetail.counterparty_name || UI_DASH}</strong></div>
              <div><span>{tr('type')}</span><strong>{ownerFundsLabel(ownerFundsDetail)}</strong></div>
              <div><span>{tr('date')}</span><strong>{fmtDate(ownerFundsDetail.date)}</strong></div>
              <div><span>{tr('amount')}</span><strong>{fmt(ownerFundsDetail.amount)} {ownerFundsDetail.currency}</strong></div>
              <div><span>{tr('bankTxReference')}</span><strong>{ownerFundsDetail.bank_reference || UI_DASH}</strong></div>
              <div className="loan-detail-note"><span>{tr('description')}</span><div className="record-field-text">{ownerFundsDetail.purpose || UI_DASH}</div></div>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => api.reports.downloadOwnerFundsPdf(ownerFundsDetail.id)}>
                {tr('bankTxOwnerFundsDocument')}
              </button>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
