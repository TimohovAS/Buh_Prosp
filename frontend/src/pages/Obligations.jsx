import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  MoreHorizontal,
  Settings2,
  WalletCards,
} from 'lucide-react'
import { useLocation } from 'react-router-dom'
import DatePicker from '../components/DatePicker'
import { api } from '../api'
import { getLang, getMonthNamesFull, getMonthNamesShort, tr } from '../i18n'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import SearchInput from '../components/SearchInput'
import SharedStatusBadge from '../components/StatusBadge'
import YearFilterSelect from '../components/YearFilterSelect'
import useAvailableYears from '../hooks/useAvailableYears'
import { formatDateSr as formatDate, todayIso } from '../utils/formatters'
import { amountSearchHay } from '../utils/searchUtils'

function defaultRecipientName() {
  const translated = tr('taxAuthority')
  return translated && translated !== 'taxAuthority' ? translated : ''
}

const DUE_SOON_DAYS = 7

function formatRsd(value) {
  return `${Number(value || 0).toLocaleString('sr-RS', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} RSD`
}

function daysUntil(value) {
  if (!value) return null
  const deadline = new Date(`${value}T00:00:00`)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((deadline.getTime() - today.getTime()) / 86400000)
}

function groupByMonth(obligations, descending = false) {
  const groups = new Map()
  obligations.forEach((obligation) => {
    const key = `${obligation.year}-${String(obligation.month).padStart(2, '0')}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(obligation)
  })

  return Array.from(groups.entries())
    .sort(([left], [right]) => (descending ? right.localeCompare(left) : left.localeCompare(right)))
    .map(([key, monthItems]) => ({
      key,
      year: monthItems[0]?.year,
      month: monthItems[0]?.month,
      items: monthItems,
      total: monthItems.reduce((sum, item) => sum + Number(item.amount || 0), 0),
    }))
}

function SummaryCard({ icon: Icon, tone, label, value, note }) {
  return (
    <div className={`obligations-summary-card obligations-summary-card--${tone}`}>
      <span className="obligations-summary-icon" aria-hidden="true">
        <Icon size={19} />
      </span>
      <div className="obligations-summary-content">
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{note}</small>
      </div>
    </div>
  )
}

export default function Obligations() {
  const location = useLocation()
  const isActivePage = location.pathname === '/payments'
  const { currentYear, year, setYear, availableYears, applyAvailableYears, resetAvailableYears } =
    useAvailableYears({
      initialYear: new Date().getFullYear(),
      includeAllTime: false,
    })
  const [paymentTypeFilter, setPaymentTypeFilter] = useState('')
  const [search, setSearch] = useState('')
  const [items, setItems] = useState([])
  const [types, setTypes] = useState([])
  const [decisions, setDecisions] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [paidModal, setPaidModal] = useState(null)
  const [paidForm, setPaidForm] = useState({
    paid_date: todayIso(),
    payment_reference: '',
  })
  const [qrModal, setQrModal] = useState(null)
  const [qrPaymentReference, setQrPaymentReference] = useState('')
  const [confirmingQrPayment, setConfirmingQrPayment] = useState(false)
  const [qrPaymentError, setQrPaymentError] = useState('')
  const [settingsModal, setSettingsModal] = useState(false)
  const [decisionFormModal, setDecisionFormModal] = useState(null)
  const [decisionForm, setDecisionForm] = useState({
    year: new Date().getFullYear(),
    payment_type_id: '',
    period_start: '',
    period_end: '',
    monthly_amount: '',
    base_amount: '',
    rate_percent: '',
    recipient_name: defaultRecipientName(),
    recipient_account: '',
    sifra_placanja: '253',
    model: '97',
    poziv_na_broj: '',
    poziv_na_broj_next: '',
    payment_purpose: '',
    is_provisional: false,
  })

  const load = () => {
    setLoading(true)
    Promise.all([
      api.obligations.types(),
      api.obligations.calendar(year, paymentTypeFilter || undefined),
      api.obligations.decisions(year),
      api.obligations.years(),
    ])
      .then(([paymentTypes, calendarItems, decisionItems, years]) => {
        setTypes(paymentTypes)
        setItems(calendarItems)
        setDecisions(decisionItems)
        applyAvailableYears(years)
      })
      .catch(() => {
        setItems([])
        setTypes([])
        setDecisions([])
        resetAvailableYears()
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return

    const params = new URLSearchParams(location.search || '')
    const hasExplicitQuery = params.toString().length > 0
    if (hasExplicitQuery) {
      const nextYear = params.get('year')
      const resolvedYear = nextYear ? parseInt(nextYear, 10) : currentYear
      const resolvedSearch = params.get('search') || ''
      if (
        year !== resolvedYear ||
        search !== resolvedSearch ||
        paymentTypeFilter !== ''
      ) {
        setYear(resolvedYear)
        setSearch(resolvedSearch)
        setPaymentTypeFilter('')
        return
      }
    }

    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, paymentTypeFilter, search, isActivePage, location.search])

  const getTypeName = (code) => {
    const type = types.find((item) => item.code === code)
    return (getLang() === 'ru' ? type?.name_ru || type?.name_sr : type?.name_sr) || code
  }

  const matchingItems = items.filter((obligation) => {
    const normalizedSearch = search.trim().toLowerCase()
    if (!normalizedSearch) return true

    const typeName = getTypeName(obligation.payment_type_code || '').toLowerCase()
    const haystack = [
      obligation.year,
      obligation.month,
      amountSearchHay(obligation.amount),
      obligation.deadline,
      obligation.paid_date,
      obligation.payment_reference,
      obligation.note,
      typeName,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(normalizedSearch)
  })

  const activeItems = matchingItems.filter((obligation) => obligation.status !== 'paid')
  const paidItems = matchingItems.filter((obligation) => obligation.status === 'paid')
  const activeGroups = groupByMonth(activeItems)
  const paidGroups = groupByMonth(paidItems, true)
  const firstUpcomingGroup = activeGroups.find((group) =>
    group.items.every((obligation) => obligation.status !== 'overdue')
  )
  const expandedActiveGroupKeys = new Set([
    ...activeGroups
      .filter((group) => group.items.some((obligation) => obligation.status === 'overdue'))
      .map((group) => group.key),
    ...(firstUpcomingGroup ? [firstUpcomingGroup.key] : []),
  ])
  const visibleActiveGroups = search.trim()
    ? activeGroups
    : activeGroups.filter((group) => expandedActiveGroupKeys.has(group.key))
  const futureActiveGroups = search.trim()
    ? []
    : activeGroups.filter((group) => !expandedActiveGroupKeys.has(group.key))
  const futureActiveItems = futureActiveGroups.flatMap((group) => group.items)
  const allActiveItems = items.filter((obligation) => obligation.status !== 'paid')
  const overdueItems = allActiveItems.filter((obligation) => obligation.status === 'overdue')
  const dueSoonItems = allActiveItems.filter((obligation) => {
    const days = daysUntil(obligation.deadline)
    return days !== null && days >= 0 && days <= DUE_SOON_DAYS
  })
  const allPaidItems = items.filter((obligation) => obligation.status === 'paid')
  const sumAmounts = (list) => list.reduce((sum, item) => sum + Number(item.amount || 0), 0)

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      await api.obligations.generate(year)
      load()
    } catch (error) {
      console.error(error)
    } finally {
      setGenerating(false)
    }
  }

  const openPaidModal = (obligation) => {
    setPaidForm({
      paid_date: todayIso(),
      payment_reference: obligation.payment_reference || '',
    })
    setPaidModal(obligation)
  }

  const openQrModal = async (obligation) => {
    setQrPaymentReference('')
    setQrPaymentError('')
    setQrModal({ obligation })
    try {
      const data = await api.obligations.ipsQr(obligation.id)
      setQrModal({ obligation, data })
    } catch (error) {
      setQrModal({ obligation, error: error.message || tr('loadError') })
    }
  }

  const handleQrPaymentSubmit = async (event) => {
    event.preventDefault()
    if (!qrModal?.obligation || !qrPaymentReference.trim()) return

    setConfirmingQrPayment(true)
    setQrPaymentError('')
    try {
      await api.obligations.markPaid(qrModal.obligation.id, {
        paid_date: todayIso(),
        payment_reference: qrPaymentReference.trim(),
      })
      setQrModal(null)
      setQrPaymentReference('')
      load()
    } catch (error) {
      setQrPaymentError(error.message || tr('paymentConfirmError'))
    } finally {
      setConfirmingQrPayment(false)
    }
  }

  const handleMarkPaidSubmit = async (event) => {
    event.preventDefault()
    if (!paidModal) return
    try {
      await api.obligations.markPaid(paidModal.id, {
        paid_date: paidForm.paid_date,
        payment_reference: paidForm.payment_reference || null,
      })
      setPaidModal(null)
      load()
    } catch (error) {
      console.error(error)
    }
  }

  const markUnpaid = async (obligation) => {
    if (!confirm(tr('confirmUnpaid'))) return
    try {
      await api.obligations.markUnpaid(obligation.id)
      load()
    } catch (error) {
      console.error(error)
    }
  }

  const openDecisionForm = (mode) => {
    if (mode === 'add') {
      const selectedYear = year
      setDecisionForm({
        year: selectedYear,
        payment_type_id: types[0]?.id || '',
        period_start: `${selectedYear}-01-01`,
        period_end: `${selectedYear}-12-31`,
        monthly_amount: '',
        base_amount: '',
        rate_percent: '',
        recipient_name: defaultRecipientName(),
        recipient_account: '',
        sifra_placanja: '253',
        model: '97',
        poziv_na_broj: '',
        poziv_na_broj_next: '',
        payment_purpose: '',
        is_provisional: false,
      })
      setDecisionFormModal('add')
      return
    }

    setDecisionFormModal({ type: 'edit', id: mode.id })
    setDecisionForm({
      year: mode.year,
      payment_type_id: mode.payment_type_id,
      period_start:
        typeof mode.period_start === 'string' ? mode.period_start : mode.period_start?.slice(0, 10) || '',
      period_end: typeof mode.period_end === 'string' ? mode.period_end : mode.period_end?.slice(0, 10) || '',
      monthly_amount: mode.monthly_amount ?? '',
      base_amount: mode.base_amount ?? '',
      rate_percent: mode.rate_percent ?? '',
      recipient_name: mode.recipient_name || defaultRecipientName(),
      recipient_account: mode.recipient_account || '',
      sifra_placanja: mode.sifra_placanja || '253',
      model: mode.model || '97',
      poziv_na_broj: mode.poziv_na_broj || '',
      poziv_na_broj_next: mode.poziv_na_broj_next || '',
      payment_purpose: mode.payment_purpose || '',
      is_provisional: mode.is_provisional ?? false,
    })
  }

  const handleDecisionFormSubmit = async (event) => {
    event.preventDefault()
    try {
      const payload = {
        year: parseInt(decisionForm.year, 10),
        payment_type_id: parseInt(decisionForm.payment_type_id, 10),
        period_start: decisionForm.period_start,
        period_end: decisionForm.period_end,
        monthly_amount: parseFloat(decisionForm.monthly_amount) || 0,
        base_amount: decisionForm.base_amount ? parseFloat(decisionForm.base_amount) : null,
        rate_percent: decisionForm.rate_percent ? parseFloat(decisionForm.rate_percent) : null,
        recipient_name: decisionForm.recipient_name || defaultRecipientName(),
        recipient_account: decisionForm.recipient_account.trim(),
        sifra_placanja: decisionForm.sifra_placanja || '253',
        model: decisionForm.model || '97',
        poziv_na_broj: decisionForm.poziv_na_broj.trim(),
        poziv_na_broj_next: decisionForm.poziv_na_broj_next?.trim() || null,
        payment_purpose: decisionForm.payment_purpose.trim(),
        is_provisional: decisionForm.is_provisional,
      }
      if (decisionFormModal === 'add') {
        await api.obligations.createDecision(payload)
      } else {
        await api.obligations.updateDecision(decisionFormModal.id, payload)
      }
      setDecisionFormModal(null)
      load()
    } catch (error) {
      console.error(error)
    }
  }

  const applyPreset2026 = async () => {
    if (!confirm(tr('confirmApplyPreset'))) return
    try {
      await api.obligations.applyPreset2026()
      load()
    } catch (error) {
      console.error(error)
    }
  }

  const monthNamesFull = getMonthNamesFull()
  const monthNamesShort = getMonthNamesShort()

  const renderObligation = (obligation) => {
    const isPaid = obligation.status === 'paid'
    const remainingDays = daysUntil(obligation.deadline)
    const isDueSoon = !isPaid && remainingDays !== null && remainingDays >= 0 && remainingDays <= DUE_SOON_DAYS
    const statusTone = isPaid ? 'success' : obligation.status === 'overdue' ? 'danger' : 'warning'
    const statusLabel = isPaid
      ? tr('paid')
      : obligation.status === 'overdue'
        ? tr('obligationsOverdue')
        : isDueSoon
          ? tr('obligationsDueSoon')
          : tr('unpaid')

    return (
      <div
        className={`obligation-row ${isPaid ? 'obligation-row--paid' : 'obligation-row--active'}`}
        key={obligation.id}
      >
        <div className="obligation-row-main">
          <div className="obligation-row-title">
            <strong>{getTypeName(obligation.payment_type_code) || obligation.payment_type_code}</strong>
            <SharedStatusBadge tone={statusTone} className="badge-pill">
              {statusLabel}
            </SharedStatusBadge>
          </div>
          <div className="obligation-row-meta">
            {isPaid ? (
              <>
                <span>
                  {tr('dateOfPayment')}: <strong>{formatDate(obligation.paid_date)}</strong>
                </span>
                {obligation.payment_reference ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <span title={obligation.payment_reference}>
                      {tr('paymentRef')}: <strong>{obligation.payment_reference}</strong>
                    </span>
                  </>
                ) : null}
              </>
            ) : (
              <>
                <span>
                  {tr('deadline')}: <strong>{formatDate(obligation.deadline)}</strong>
                </span>
                {isDueSoon ? (
                  <span className="obligation-due-hint">
                    {remainingDays === 0 ? tr('obligationToday') : tr('obligationDaysLeft')(remainingDays)}
                  </span>
                ) : null}
              </>
            )}
          </div>
        </div>

        <strong className="obligation-row-amount">{formatRsd(obligation.amount)}</strong>

        <div className="obligation-row-actions">
          {!isPaid ? (
            <button className="btn btn-sm btn-primary" onClick={() => openQrModal(obligation)}>
              {tr('payQr')}
            </button>
          ) : null}
          <details className="obligation-actions-menu">
            <summary
              className="obligation-icon-button"
              title={tr('obligationsMoreActions')}
              aria-label={tr('obligationsMoreActions')}
            >
              <MoreHorizontal size={18} />
            </summary>
            <div className="obligation-actions-popover">
              <button
                type="button"
                onClick={() => (isPaid ? markUnpaid(obligation) : openPaidModal(obligation))}
              >
                {isPaid ? tr('markUnpaid') : tr('markPaid')}
              </button>
            </div>
          </details>
        </div>
      </div>
    )
  }

  const renderMonthGroup = (group, isPaid = false) => (
    <section className={`obligation-month-card ${isPaid ? 'obligation-month-card--paid' : ''}`} key={group.key}>
      <header className="obligation-month-header">
        <div>
          <h3>
            {monthNamesFull[group.month - 1] || group.month} {group.year}
          </h3>
          <span>
            {group.items.length} · {tr('deadline')} {formatDate(group.items[0]?.deadline)}
          </span>
        </div>
        <strong>{formatRsd(group.total)}</strong>
      </header>
      <div className="obligation-month-rows">{group.items.map(renderObligation)}</div>
    </section>
  )

  return (
    <div className="page obligations-page">
      <PageHeader
        title={tr('payments')}
        subtitle={tr('obligationsPageSubtitle')}
        actions={
          <button className="btn btn-secondary obligations-settings-button" onClick={() => setSettingsModal(true)}>
            <Settings2 size={17} />
            {tr('obligationsSettings')}
          </button>
        }
      />

      <div className="page-body">
        <div className="obligations-summary-grid">
          <SummaryCard
            icon={AlertTriangle}
            tone="danger"
            label={tr('obligationsOverdue')}
            value={loading ? '—' : overdueItems.length}
            note={loading ? tr('loading') : formatRsd(sumAmounts(overdueItems))}
          />
          <SummaryCard
            icon={CalendarClock}
            tone="warning"
            label={tr('obligationsDueNext7Days')}
            value={loading ? '—' : dueSoonItems.length}
            note={loading ? tr('loading') : formatRsd(sumAmounts(dueSoonItems))}
          />
          <SummaryCard
            icon={WalletCards}
            tone="accent"
            label={tr('obligationsOpenTotal')}
            value={loading ? '—' : formatRsd(sumAmounts(allActiveItems))}
            note={
              loading
                ? tr('loading')
                : tr('obligationsPaymentsCount', { count: allActiveItems.length })
            }
          />
          <SummaryCard
            icon={CheckCircle2}
            tone="success"
            label={tr('obligationsPaidForYear', { year })}
            value={loading ? '—' : formatRsd(sumAmounts(allPaidItems))}
            note={
              loading ? tr('loading') : tr('obligationsPaymentsCount', { count: allPaidItems.length })
            }
          />
        </div>

        <div className="card obligations-toolbar">
          <div className="obligations-filter-field obligations-filter-field--year">
            <label htmlFor="obligations-year">{tr('filterYear')}</label>
            <YearFilterSelect
              id="obligations-year"
              value={year}
              availableYears={availableYears}
              onChange={setYear}
              includeAllTime={false}
              title={tr('filterYear')}
              style={{ width: '100%' }}
            />
          </div>
          <div className="obligations-filter-field">
            <label htmlFor="obligations-payment-type">{tr('filterPaymentType')}</label>
            <select
              id="obligations-payment-type"
              className="form-input"
              value={paymentTypeFilter}
              onChange={(event) => setPaymentTypeFilter(event.target.value)}
            >
              <option value="">{tr('obligationsAllPaymentTypes')}</option>
              {types.map((type) => (
                <option key={type.id} value={type.code}>
                  {(getLang() === 'ru' ? type.name_ru || type.name_sr : type.name_sr) || type.code}
                </option>
              ))}
            </select>
          </div>
          <div className="obligations-filter-field obligations-filter-field--search">
            <label htmlFor="obligations-search">{tr('search')}</label>
            <SearchInput
              id="obligations-search"
              placeholder={tr('obligationsSearchPlaceholder')}
              value={search}
              onChange={setSearch}
            />
          </div>
        </div>

        <section className="obligations-active-section">
          <div className="obligations-section-heading">
            <div>
              <h2>{tr('obligationsNearestPayments')}</h2>
              <p>{tr('obligationsNearestPaymentsHint')}</p>
            </div>
            {!loading ? <span className="obligations-section-count">{activeItems.length}</span> : null}
          </div>

          {loading ? (
            <div className="card obligations-empty-state">{tr('loading')}</div>
          ) : activeGroups.length ? (
            <>
              <div className="obligation-groups">
                {visibleActiveGroups.map((group) => renderMonthGroup(group))}
              </div>
              {futureActiveGroups.length ? (
                <details className="obligations-history obligations-future">
                  <summary>
                    <span className="obligations-history-icon">
                      <CalendarClock size={18} />
                    </span>
                    <span>
                      <strong>{tr('obligationsFutureMonths')}</strong>
                      <small>
                        {tr('obligationsMonthsCount', { count: futureActiveGroups.length })} ·{' '}
                        {tr('obligationsPaymentsCount', { count: futureActiveItems.length })}
                      </small>
                    </span>
                    <span className="obligations-history-total">{formatRsd(sumAmounts(futureActiveItems))}</span>
                    <span className="obligations-history-chevron" aria-hidden="true">⌄</span>
                  </summary>
                  <div className="obligations-history-content">
                    <div className="obligation-groups">
                      {futureActiveGroups.map((group) => renderMonthGroup(group))}
                    </div>
                  </div>
                </details>
              ) : null}
            </>
          ) : (
            <div className="card obligations-empty-state">
              <CheckCircle2 size={24} />
              <strong>{tr('obligationsNoActive')}</strong>
              <span>{search ? tr('obligationsTryAnotherSearch') : tr('obligationsNoActiveHint')}</span>
            </div>
          )}
        </section>

        {!loading ? (
          <details className="obligations-history">
            <summary>
              <span className="obligations-history-icon">
                <CheckCircle2 size={18} />
              </span>
              <span>
                <strong>{tr('obligationsPaidHistory')}</strong>
                <small>{tr('obligationsPaymentsCount', { count: paidItems.length })}</small>
              </span>
              <span className="obligations-history-total">{formatRsd(sumAmounts(paidItems))}</span>
              <span className="obligations-history-chevron" aria-hidden="true">⌄</span>
            </summary>
            <div className="obligations-history-content">
              {paidGroups.length ? (
                <div className="obligation-groups">{paidGroups.map((group) => renderMonthGroup(group, true))}</div>
              ) : (
                <div className="obligations-empty-state obligations-empty-state--compact">
                  {tr('obligationsNoPaid')}
                </div>
              )}
            </div>
          </details>
        ) : null}
      </div>

      <Modal
        isOpen={settingsModal}
        onClose={() => setSettingsModal(false)}
        title={tr('obligationsSettings')}
        maxWidth="1080px"
        style={{ maxHeight: '90vh', overflow: 'auto' }}
      >
        {settingsModal ? (
          <>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                marginBottom: '1rem',
                flexWrap: 'wrap',
                gap: '0.5rem',
              }}
            >
              <button className="btn btn-primary" onClick={() => openDecisionForm('add')}>
                {tr('add')}
              </button>
              <button className="btn btn-secondary" onClick={applyPreset2026}>
                {tr('preset2026')}
              </button>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{tr('yearLabel')}</th>
                    <th>{tr('paymentTypeLabel')}</th>
                    <th>{tr('monthlySum')}</th>
                    <th>{tr('recipientAccount')}</th>
                    <th>{tr('pozivNaBroj')}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {decisions.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ color: 'var(--color-text-muted)' }}>
                        {tr('noDecisions')}
                      </td>
                    </tr>
                  ) : (
                    decisions.map((decision) => (
                      <tr key={decision.id}>
                        <td>{decision.year}</td>
                        <td>{decision.payment_type_name || decision.payment_type_code}</td>
                        <td>{decision.monthly_amount?.toLocaleString('sr-RS')} RSD</td>
                        <td style={{ fontSize: '0.85rem' }}>{decision.recipient_account}</td>
                        <td
                          style={{
                            fontSize: '0.8rem',
                            maxWidth: 120,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                          title={decision.poziv_na_broj}
                        >
                          {decision.poziv_na_broj}
                        </td>
                        <td>
                          <button
                            className="btn btn-sm btn-secondary"
                            onClick={() => openDecisionForm(decision)}
                          >
                            {tr('edit')}
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div
              className="modal-actions"
              style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}
            >
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleGenerate}
                disabled={generating || loading}
              >
                {generating ? tr('loading') : tr('obligationsGenerate')}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setSettingsModal(false)}>
                {tr('close')}
              </button>
            </div>
          </>
        ) : null}
      </Modal>

      <Modal
        isOpen={!!paidModal}
        onClose={() => setPaidModal(null)}
        title={
          paidModal
            ? `${tr('markPaid')} \u2014 ${getTypeName(paidModal.payment_type_code)} ${monthNamesShort[paidModal.month - 1]}`
            : tr('markPaid')
        }
        maxWidth="400px"
      >
        {paidModal ? (
          <form onSubmit={handleMarkPaidSubmit}>
            <div className="form-group">
              <label className="form-label">{tr('date')}</label>
              <DatePicker
                value={paidForm.paid_date}
                onChange={(value) => setPaidForm({ ...paidForm, paid_date: value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">{tr('paymentRef')}</label>
              <input
                type="text"
                className="form-input"
                value={paidForm.payment_reference}
                onChange={(event) => setPaidForm({ ...paidForm, payment_reference: event.target.value })}
                placeholder={tr('paymentRef')}
              />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setPaidModal(null)}>
                {tr('cancel')}
              </button>
              <button type="submit" className="btn btn-primary">
                {tr('save')}
              </button>
            </div>
          </form>
        ) : null}
      </Modal>

      <Modal
        isOpen={!!qrModal}
        onClose={() => setQrModal(null)}
        title={
          qrModal
            ? `${tr('payQrTitle')} — ${getTypeName(qrModal.obligation.payment_type_code)} ${monthNamesShort[qrModal.obligation.month - 1]} ${qrModal.obligation.year}`
            : tr('payQrTitle')
        }
        maxWidth="420px"
      >
        {qrModal?.error ? (
          <div style={{ color: 'var(--color-danger)' }}>{qrModal.error}</div>
        ) : !qrModal?.data ? (
          <div style={{ textAlign: 'center', padding: '1.5rem' }}>{tr('loading')}</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', alignItems: 'center' }}>
            <img
              src={qrModal.data.qr_png}
              alt="NBS IPS QR"
              style={{ width: 240, height: 240, background: '#fff', padding: 10, borderRadius: 8 }}
            />
            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', textAlign: 'center' }}>
              {tr('payQrScanHint')}
            </div>
            <div
              style={{
                width: '100%',
                display: 'grid',
                gridTemplateColumns: 'auto 1fr',
                gap: '0.3rem 0.9rem',
                fontSize: '0.9rem',
              }}
            >
              <span style={{ color: 'var(--color-text-muted)' }}>{tr('recipient')}</span>
              <span>{qrModal.data.recipient}</span>
              <span style={{ color: 'var(--color-text-muted)' }}>{tr('recipientAccount')}</span>
              <span style={{ fontVariantNumeric: 'tabular-nums' }}>{qrModal.data.account}</span>
              <span style={{ color: 'var(--color-text-muted)' }}>{tr('amount')}</span>
              <span style={{ fontWeight: 700 }}>
                {Number(qrModal.data.amount)?.toLocaleString('sr-RS')} {qrModal.data.currency}
              </span>
              <span style={{ color: 'var(--color-text-muted)' }}>{tr('pozivNaBroj')}</span>
              <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                {qrModal.data.model} {qrModal.data.reference}
              </span>
              <span style={{ color: 'var(--color-text-muted)' }}>{tr('paymentPurpose')}</span>
              <span>{qrModal.data.purpose}</span>
            </div>
            <form className="obligation-qr-confirmation" onSubmit={handleQrPaymentSubmit}>
              <div className="obligation-qr-confirmation-heading">
                <strong>{tr('paymentConfirmation')}</strong>
                <span>{tr('transactionNumberHint')}</span>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="obligation-transaction-number">
                  {tr('transactionNumber')} *
                </label>
                <input
                  id="obligation-transaction-number"
                  type="text"
                  className="form-input"
                  value={qrPaymentReference}
                  onChange={(event) => setQrPaymentReference(event.target.value)}
                  placeholder={tr('transactionNumberPlaceholder')}
                  autoComplete="off"
                  required
                />
              </div>
              {qrPaymentError ? <div className="alert alert-danger">{qrPaymentError}</div> : null}
              <button
                type="submit"
                className="btn btn-primary obligation-qr-confirm-button"
                disabled={confirmingQrPayment || !qrPaymentReference.trim()}
              >
                {confirmingQrPayment ? tr('loading') : tr('confirmPayment')}
              </button>
            </form>
          </div>
        )}
      </Modal>

      <Modal
        isOpen={!!decisionFormModal}
        onClose={() => setDecisionFormModal(null)}
        title={`${decisionFormModal === 'add' ? tr('add') : tr('edit')} \u2014 ${tr('decisionFormTitle')}`}
        maxWidth="520px"
        style={{ maxHeight: '90vh', overflow: 'auto' }}
      >
        {decisionFormModal ? (
          <form onSubmit={handleDecisionFormSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">{tr('yearLabel')} *</label>
                <input
                  type="number"
                  className="form-input"
                  value={decisionForm.year}
                  onChange={(event) => setDecisionForm({ ...decisionForm, year: event.target.value })}
                  required
                  min={2020}
                  max={2035}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('paymentTypeLabel')} *</label>
                <select
                  className="form-input"
                  value={decisionForm.payment_type_id}
                  onChange={(event) =>
                    setDecisionForm({ ...decisionForm, payment_type_id: event.target.value })
                  }
                  required
                  disabled={decisionFormModal !== 'add'}
                >
                  {types.map((type) => (
                    <option key={type.id} value={type.id}>
                      {type.name_sr}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">{tr('periodFrom')} *</label>
                <DatePicker
                  value={decisionForm.period_start}
                  onChange={(value) => setDecisionForm({ ...decisionForm, period_start: value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('periodTo')} *</label>
                <DatePicker
                  value={decisionForm.period_end}
                  onChange={(value) => setDecisionForm({ ...decisionForm, period_end: value })}
                  required
                />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">{tr('monthlyAmount')} *</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  value={decisionForm.monthly_amount}
                  onChange={(event) =>
                    setDecisionForm({ ...decisionForm, monthly_amount: event.target.value })
                  }
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('baseAmount')}</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  value={decisionForm.base_amount}
                  onChange={(event) => setDecisionForm({ ...decisionForm, base_amount: event.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('ratePercent')}</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  value={decisionForm.rate_percent}
                  onChange={(event) => setDecisionForm({ ...decisionForm, rate_percent: event.target.value })}
                />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">{tr('recipient')}</label>
              <input
                type="text"
                className="form-input"
                value={decisionForm.recipient_name}
                onChange={(event) => setDecisionForm({ ...decisionForm, recipient_name: event.target.value })}
                placeholder={tr('taxAuthority')}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">{tr('recipientAccount')} *</label>
                <input
                  type="text"
                  className="form-input"
                  value={decisionForm.recipient_account}
                  onChange={(event) =>
                    setDecisionForm({ ...decisionForm, recipient_account: event.target.value })
                  }
                  required
                  placeholder="840-71122843-32"
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('sifraPlacanja')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={decisionForm.sifra_placanja}
                  onChange={(event) =>
                    setDecisionForm({ ...decisionForm, sifra_placanja: event.target.value })
                  }
                  placeholder="253"
                />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">{tr('model')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={decisionForm.model}
                  onChange={(event) => setDecisionForm({ ...decisionForm, model: event.target.value })}
                  placeholder="97"
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('pozivNaBroj')} *</label>
                <input
                  type="text"
                  className="form-input"
                  value={decisionForm.poziv_na_broj}
                  onChange={(event) =>
                    setDecisionForm({ ...decisionForm, poziv_na_broj: event.target.value })
                  }
                  required
                  placeholder="2624190000007887475"
                />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">{tr('pozivNaBrojNext')}</label>
              <input
                type="text"
                className="form-input"
                value={decisionForm.poziv_na_broj_next}
                onChange={(event) =>
                  setDecisionForm({ ...decisionForm, poziv_na_broj_next: event.target.value })
                }
                placeholder="2024190000008031910"
              />
            </div>
            <div className="form-group">
              <label className="form-label">{tr('paymentPurpose')} *</label>
              <input
                type="text"
                className="form-input"
                value={decisionForm.payment_purpose}
                onChange={(event) =>
                  setDecisionForm({ ...decisionForm, payment_purpose: event.target.value })
                }
                required
                placeholder={tr('paymentPurpose')}
              />
              <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
                {tr('purposeYearHint')}
              </div>
            </div>
            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={decisionForm.is_provisional}
                  onChange={(event) =>
                    setDecisionForm({ ...decisionForm, is_provisional: event.target.checked })
                  }
                />
                {tr('provisional')}
              </label>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setDecisionFormModal(null)}>
                {tr('cancel')}
              </button>
              <button type="submit" className="btn btn-primary">
                {tr('save')}
              </button>
            </div>
          </form>
        ) : null}
      </Modal>
    </div>
  )
}
