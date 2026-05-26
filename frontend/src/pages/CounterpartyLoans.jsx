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
  return type === 'borrowed' ? tr('loanBorrowed') : tr('loanIssued')
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
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('open')
  const [sortCol, setSortCol] = useState('start_date')
  const [sortAsc, setSortAsc] = useState(false)
  const [detail, setDetail] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const params = {}
      if (typeFilter) params.loan_type = typeFilter
      if (statusFilter) params.status = statusFilter
      const loans = await api.counterpartyLoans.list(params)
      setItems(loans)
      const openId = new URLSearchParams(location.search).get('open')
      if (openId) {
        const selected = loans.find((loan) => String(loan.id) === openId) || await api.counterpartyLoans.get(openId)
        setDetail(selected)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!isActivePage) return
    load().catch(() => setItems([]))
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

  const toggleSort = (column) => {
    if (column === sortCol) setSortAsc((current) => !current)
    else {
      setSortCol(column)
      setSortAsc(false)
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
            </select>
            <select className="form-input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} style={{ width: 145 }}>
              <option value="">{tr('filterAll')}</option>
              <option value="open">{tr('loanOpen')}</option>
              <option value="repaid">{tr('loanRepaidComplete')}</option>
            </select>
            <SearchInput placeholder={tr('search')} value={search} onChange={setSearch} style={{ width: 230 }} />
          </>
        )}
      />
      <div className="page-body">
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
                      <tr key={loan.id} className="record-row" tabIndex={0} onClick={() => setDetail(loan)} onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          setDetail(loan)
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
                      <td>{movementLabel(detail, movement)}</td>
                      <td>{movement.bank_reference || UI_DASH}</td>
                      <td style={{ textAlign: 'right' }}>{fmt(movement.amount)} {movement.currency}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
