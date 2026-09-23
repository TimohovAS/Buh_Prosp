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

function isSchemeActive(scheme, day = todayIso()) {
  return (scheme.periods || []).some(
    (period) => period.period_start <= day && (!period.period_end || period.period_end >= day)
  )
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
  const [schemes, setSchemes] = useState([])
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
  const [settingsError, setSettingsError] = useState('')
  const [typeFormModal, setTypeFormModal] = useState(null)
  const [typeForm, setTypeForm] = useState({
    code: '',
    name_sr: '',
    name_ru: '',
    sort_order: 0,
    is_archived: false,
  })
  const [schemeFormModal, setSchemeFormModal] = useState(null)
  const [schemeForm, setSchemeForm] = useState({ name: '', description: '', is_archived: false })
  const [activationModal, setActivationModal] = useState(null)
  const [activationForm, setActivationForm] = useState({
    effective_from: todayIso(),
    closing_deadline: '',
    note: '',
  })
  const [decisionFormModal, setDecisionFormModal] = useState(null)
  const [decisionForm, setDecisionForm] = useState({
    year: new Date().getFullYear(),
    tax_scheme_id: '',
    payment_type_id: '',
    period_start: '',
    period_end: '',
    monthly_amount: '',
    base_amount: '',
    rate_percent: '',
    recipient_name: '',
    recipient_account: '',
    sifra_placanja: '253',
    model: '97',
    poziv_na_broj: '',
    poziv_na_broj_next: '',
    payment_purpose: '',
    due_day: 15,
    due_month_offset: 1,
    prorate_partial_month: true,
    is_provisional: false,
    is_active: true,
  })

  const load = () => {
    setLoading(true)
    Promise.all([
      api.obligations.types(),
      api.obligations.calendar(year, paymentTypeFilter || undefined),
      api.obligations.decisions(year),
      api.obligations.years(),
    ])
      .then(async ([paymentTypes, calendarItems, decisionItems, years]) => {
        const taxSchemes = await api.obligations.schemes()
        setTypes(paymentTypes)
        setSchemes(taxSchemes)
        setItems(calendarItems)
        setDecisions(decisionItems)
        applyAvailableYears(years)
      })
      .catch(() => {
        setItems([])
        setTypes([])
        setSchemes([])
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
      if (year !== resolvedYear || search !== resolvedSearch || paymentTypeFilter !== '') {
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
      obligation.tax_scheme_name,
      obligation.accrual_period_start,
      obligation.accrual_period_end,
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
        tax_scheme_id: schemes.find((scheme) => isSchemeActive(scheme))?.id || schemes[0]?.id || '',
        payment_type_id: types[0]?.id || '',
        period_start: `${selectedYear}-01-01`,
        period_end: `${selectedYear}-12-31`,
        monthly_amount: '',
        base_amount: '',
        rate_percent: '',
        recipient_name: '',
        recipient_account: '',
        sifra_placanja: '253',
        model: '97',
        poziv_na_broj: '',
        poziv_na_broj_next: '',
        payment_purpose: '',
        due_day: 15,
        due_month_offset: 1,
        prorate_partial_month: true,
        is_provisional: false,
        is_active: true,
      })
      setDecisionFormModal('add')
      return
    }

    setDecisionFormModal({ type: 'edit', id: mode.id })
    setDecisionForm({
      year: mode.year,
      tax_scheme_id: mode.tax_scheme_id || '',
      payment_type_id: mode.payment_type_id,
      period_start:
        typeof mode.period_start === 'string' ? mode.period_start : mode.period_start?.slice(0, 10) || '',
      period_end: typeof mode.period_end === 'string' ? mode.period_end : mode.period_end?.slice(0, 10) || '',
      monthly_amount: mode.monthly_amount ?? '',
      base_amount: mode.base_amount ?? '',
      rate_percent: mode.rate_percent ?? '',
      recipient_name: mode.recipient_name || '',
      recipient_account: mode.recipient_account || '',
      sifra_placanja: mode.sifra_placanja || '253',
      model: mode.model || '97',
      poziv_na_broj: mode.poziv_na_broj || '',
      poziv_na_broj_next: mode.poziv_na_broj_next || '',
      payment_purpose: mode.payment_purpose || '',
      due_day: mode.due_day ?? 15,
      due_month_offset: mode.due_month_offset ?? 1,
      prorate_partial_month: mode.prorate_partial_month ?? true,
      is_provisional: mode.is_provisional ?? false,
      is_active: mode.is_active ?? true,
    })
  }

  const handleDecisionFormSubmit = async (event) => {
    event.preventDefault()
    try {
      const payload = {
        year: parseInt(decisionForm.year, 10),
        tax_scheme_id: parseInt(decisionForm.tax_scheme_id, 10),
        payment_type_id: parseInt(decisionForm.payment_type_id, 10),
        period_start: decisionForm.period_start,
        period_end: decisionForm.period_end,
        monthly_amount: parseFloat(decisionForm.monthly_amount) || 0,
        base_amount: decisionForm.base_amount ? parseFloat(decisionForm.base_amount) : null,
        rate_percent: decisionForm.rate_percent ? parseFloat(decisionForm.rate_percent) : null,
        recipient_name: decisionForm.recipient_name.trim(),
        recipient_account: decisionForm.recipient_account.trim(),
        sifra_placanja: decisionForm.sifra_placanja || '253',
        model: decisionForm.model || '97',
        poziv_na_broj: decisionForm.poziv_na_broj.trim(),
        poziv_na_broj_next: decisionForm.poziv_na_broj_next?.trim() || null,
        payment_purpose: decisionForm.payment_purpose.trim(),
        due_day: parseInt(decisionForm.due_day, 10),
        due_month_offset: parseInt(decisionForm.due_month_offset, 10),
        prorate_partial_month: decisionForm.prorate_partial_month,
        is_provisional: decisionForm.is_provisional,
        is_active: decisionForm.is_active,
      }
      if (decisionFormModal === 'add') delete payload.is_active
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

  const openTypeForm = (paymentType = null) => {
    setSettingsError('')
    setTypeForm({
      code: paymentType?.code || '',
      name_sr: paymentType?.name_sr || '',
      name_ru: paymentType?.name_ru || '',
      sort_order: paymentType?.sort_order ?? types.length + 1,
      is_archived: paymentType?.is_archived ?? false,
    })
    setTypeFormModal(paymentType || 'add')
  }

  const handleTypeFormSubmit = async (event) => {
    event.preventDefault()
    setSettingsError('')
    const payload = {
      code: typeForm.code.trim().toLowerCase(),
      name_sr: typeForm.name_sr.trim(),
      name_ru: typeForm.name_ru.trim() || null,
      sort_order: parseInt(typeForm.sort_order, 10) || 0,
    }
    try {
      if (typeFormModal === 'add') {
        await api.obligations.createType(payload)
      } else {
        await api.obligations.updateType(typeFormModal.id, {
          ...payload,
          is_archived: typeForm.is_archived,
        })
      }
      setTypeFormModal(null)
      load()
    } catch (error) {
      setSettingsError(error.message || tr('saveError'))
    }
  }

  const openSchemeForm = (scheme = null) => {
    setSettingsError('')
    setSchemeForm({
      name: scheme?.name || '',
      description: scheme?.description || '',
      is_archived: scheme?.is_archived ?? false,
    })
    setSchemeFormModal(scheme || 'add')
  }

  const handleSchemeFormSubmit = async (event) => {
    event.preventDefault()
    setSettingsError('')
    try {
      const payload = {
        name: schemeForm.name.trim(),
        description: schemeForm.description.trim() || null,
      }
      if (schemeFormModal === 'add') {
        await api.obligations.createScheme(payload)
      } else {
        await api.obligations.updateScheme(schemeFormModal.id, {
          ...payload,
          is_archived: schemeForm.is_archived,
        })
      }
      setSchemeFormModal(null)
      setSchemeForm({ name: '', description: '', is_archived: false })
      load()
    } catch (error) {
      setSettingsError(error.message || tr('saveError'))
    }
  }

  const openActivationModal = (scheme) => {
    setSettingsError('')
    setActivationForm({ effective_from: todayIso(), closing_deadline: '', note: '' })
    setActivationModal(scheme)
  }

  const handleActivationSubmit = async (event) => {
    event.preventDefault()
    if (!activationModal) return
    setSettingsError('')
    try {
      await api.obligations.activateScheme(activationModal.id, {
        effective_from: activationForm.effective_from,
        closing_deadline: activationForm.closing_deadline || null,
        note: activationForm.note.trim() || null,
      })
      setActivationModal(null)
      load()
    } catch (error) {
      setSettingsError(error.message || tr('saveError'))
    }
  }

  const monthNamesFull = getMonthNamesFull()
  const monthNamesShort = getMonthNamesShort()

  const renderObligation = (obligation) => {
    const isPaid = obligation.status === 'paid'
    const remainingDays = daysUntil(obligation.deadline)
    const isDueSoon =
      !isPaid && remainingDays !== null && remainingDays >= 0 && remainingDays <= DUE_SOON_DAYS
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
            {obligation.tax_scheme_name ? (
              <>
                <span aria-hidden="true">·</span>
                <span>{obligation.tax_scheme_name}</span>
              </>
            ) : null}
            {obligation.accrual_period_start && obligation.accrual_period_end ? (
              <>
                <span aria-hidden="true">·</span>
                <span>
                  {tr('accrualPeriod')}: {formatDate(obligation.accrual_period_start)} —{' '}
                  {formatDate(obligation.accrual_period_end)}
                </span>
              </>
            ) : null}
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
    <section
      className={`obligation-month-card ${isPaid ? 'obligation-month-card--paid' : ''}`}
      key={group.key}
    >
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
          <button
            className="btn btn-secondary obligations-settings-button"
            onClick={() => setSettingsModal(true)}
          >
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
            note={loading ? tr('loading') : tr('obligationsPaymentsCount', { count: allActiveItems.length })}
          />
          <SummaryCard
            icon={CheckCircle2}
            tone="success"
            label={tr('obligationsPaidForYear', { year })}
            value={loading ? '—' : formatRsd(sumAmounts(allPaidItems))}
            note={loading ? tr('loading') : tr('obligationsPaymentsCount', { count: allPaidItems.length })}
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
                    <span className="obligations-history-total">
                      {formatRsd(sumAmounts(futureActiveItems))}
                    </span>
                    <span className="obligations-history-chevron" aria-hidden="true">
                      ⌄
                    </span>
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
              <span className="obligations-history-chevron" aria-hidden="true">
                ⌄
              </span>
            </summary>
            <div className="obligations-history-content">
              {paidGroups.length ? (
                <div className="obligation-groups">
                  {paidGroups.map((group) => renderMonthGroup(group, true))}
                </div>
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
            {settingsError ? <div className="alert alert-danger">{settingsError}</div> : null}
            <div className="tax-settings-guide">
              <strong>{tr('taxSetupGuideTitle')}</strong>
              <span>{tr('taxSetupGuideHint')}</span>
            </div>

            <div className="tax-decision-heading">
              <div>
                <h3>{tr('paymentTypesTitle')}</h3>
                <p>{tr('paymentTypesHint')}</p>
              </div>
              <button className="btn btn-secondary" onClick={() => openTypeForm()}>
                {tr('paymentTypeAdd')}
              </button>
            </div>
            <div className="tax-payment-type-list">
              {types.map((type) => (
                <button
                  type="button"
                  className={`tax-payment-type-chip ${type.is_archived ? 'tax-payment-type-chip--archived' : ''}`}
                  key={type.id}
                  onClick={() => openTypeForm(type)}
                >
                  <strong>{getLang() === 'ru' ? type.name_ru || type.name_sr : type.name_sr}</strong>
                  <span>{type.code}</span>
                  {type.is_archived ? <small>{tr('taxItemArchived')}</small> : null}
                </button>
              ))}
            </div>

            <div className="tax-scheme-heading">
              <div>
                <h3>{tr('taxSchemesTitle')}</h3>
                <p>{tr('taxSchemesHint')}</p>
              </div>
              <div className="tax-scheme-heading-actions">
                <button className="btn btn-secondary" onClick={() => openSchemeForm()}>
                  {tr('taxSchemeAdd')}
                </button>
              </div>
            </div>

            <div className="tax-scheme-grid">
              {schemes.map((scheme) => {
                const active = isSchemeActive(scheme)
                return (
                  <article
                    className={`tax-scheme-card ${active ? 'tax-scheme-card--active' : ''} ${scheme.is_archived ? 'tax-scheme-card--archived' : ''}`}
                    key={scheme.id}
                  >
                    <div className="tax-scheme-card-main">
                      <div className="tax-scheme-card-title">
                        <strong>{scheme.name}</strong>
                        {active ? (
                          <span className="badge badge-success">{tr('taxSchemeCurrent')}</span>
                        ) : null}
                        {scheme.is_archived ? <span className="badge">{tr('taxItemArchived')}</span> : null}
                      </div>
                      {scheme.description ? <p>{scheme.description}</p> : null}
                      <div className="tax-scheme-periods">
                        {(scheme.periods || []).map((period) => (
                          <span key={period.id}>
                            {formatDate(period.period_start)} —{' '}
                            {period.period_end ? formatDate(period.period_end) : tr('taxSchemeNoEndDate')}
                            {period.closing_deadline
                              ? ` · ${tr('deadline')}: ${formatDate(period.closing_deadline)}`
                              : ''}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="tax-scheme-card-actions">
                      <button className="btn btn-sm btn-secondary" onClick={() => openSchemeForm(scheme)}>
                        {tr('edit')}
                      </button>
                      {!scheme.is_archived && !active ? (
                        <button
                          className="btn btn-sm btn-primary"
                          onClick={() => openActivationModal(scheme)}
                        >
                          {tr('taxSchemeActivate')}
                        </button>
                      ) : null}
                    </div>
                  </article>
                )
              })}
            </div>

            <div className="tax-decision-heading">
              <div>
                <h3>{tr('taxDecisionRules')}</h3>
                <p>{tr('taxDecisionRulesHint')}</p>
              </div>
              <div className="tax-scheme-heading-actions">
                <button className="btn btn-primary" onClick={() => openDecisionForm('add')}>
                  {tr('taxDecisionAdd')}
                </button>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{tr('yearLabel')}</th>
                    <th>{tr('taxScheme')}</th>
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
                      <td colSpan={7} style={{ color: 'var(--color-text-muted)' }}>
                        {tr('noDecisions')}
                      </td>
                    </tr>
                  ) : (
                    decisions.map((decision) => (
                      <tr key={decision.id}>
                        <td>{decision.year}</td>
                        <td>{decision.tax_scheme_name || '—'}</td>
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
        isOpen={!!typeFormModal}
        onClose={() => setTypeFormModal(null)}
        title={typeFormModal === 'add' ? tr('paymentTypeAdd') : tr('paymentTypeEdit')}
        maxWidth="520px"
      >
        {typeFormModal ? (
          <form onSubmit={handleTypeFormSubmit}>
            <div className="form-group">
              <label className="form-label">{tr('paymentTypeCode')} *</label>
              <input
                className="form-input"
                value={typeForm.code}
                onChange={(event) =>
                  setTypeForm({ ...typeForm, code: event.target.value.toLowerCase().replace(/\s+/g, '_') })
                }
                pattern="[a-z0-9][a-z0-9_-]*"
                placeholder="property_tax"
                required
              />
              <small className="form-hint">{tr('paymentTypeCodeHint')}</small>
            </div>
            <div className="form-grid-2">
              <div className="form-group">
                <label className="form-label">{tr('paymentTypeNameSr')} *</label>
                <input
                  className="form-input"
                  value={typeForm.name_sr}
                  onChange={(event) => setTypeForm({ ...typeForm, name_sr: event.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('paymentTypeNameRu')}</label>
                <input
                  className="form-input"
                  value={typeForm.name_ru}
                  onChange={(event) => setTypeForm({ ...typeForm, name_ru: event.target.value })}
                />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">{tr('sortOrder')}</label>
              <input
                type="number"
                className="form-input"
                value={typeForm.sort_order}
                onChange={(event) => setTypeForm({ ...typeForm, sort_order: event.target.value })}
              />
            </div>
            {typeFormModal !== 'add' ? (
              <label className="tax-setting-checkbox">
                <input
                  type="checkbox"
                  checked={typeForm.is_archived}
                  onChange={(event) => setTypeForm({ ...typeForm, is_archived: event.target.checked })}
                />
                <span>{tr('taxArchiveItem')}</span>
              </label>
            ) : null}
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setTypeFormModal(null)}>
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
        isOpen={!!schemeFormModal}
        onClose={() => setSchemeFormModal(null)}
        title={schemeFormModal === 'add' ? tr('taxSchemeAdd') : tr('taxSchemeEdit')}
        maxWidth="460px"
      >
        {schemeFormModal ? (
          <form onSubmit={handleSchemeFormSubmit}>
            <div className="form-group">
              <label className="form-label">{tr('name')} *</label>
              <input
                className="form-input"
                value={schemeForm.name}
                onChange={(event) => setSchemeForm({ ...schemeForm, name: event.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">{tr('description')}</label>
              <textarea
                className="form-input"
                rows={3}
                value={schemeForm.description}
                onChange={(event) => setSchemeForm({ ...schemeForm, description: event.target.value })}
              />
            </div>
            {schemeFormModal !== 'add' ? (
              <label className="tax-setting-checkbox">
                <input
                  type="checkbox"
                  checked={schemeForm.is_archived}
                  onChange={(event) => setSchemeForm({ ...schemeForm, is_archived: event.target.checked })}
                />
                <span>{tr('taxArchiveItem')}</span>
              </label>
            ) : null}
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setSchemeFormModal(null)}>
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
        isOpen={!!activationModal}
        onClose={() => setActivationModal(null)}
        title={
          activationModal ? `${tr('taxSchemeActivate')} — ${activationModal.name}` : tr('taxSchemeActivate')
        }
        maxWidth="460px"
      >
        {activationModal ? (
          <form onSubmit={handleActivationSubmit}>
            <div className="alert alert-info">{tr('taxSchemeActivationHint')}</div>
            <div className="form-group">
              <label className="form-label">{tr('effectiveFrom')} *</label>
              <DatePicker
                value={activationForm.effective_from}
                onChange={(value) => setActivationForm({ ...activationForm, effective_from: value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">{tr('closingDeadline')}</label>
              <DatePicker
                value={activationForm.closing_deadline}
                onChange={(value) => setActivationForm({ ...activationForm, closing_deadline: value })}
              />
              <small className="form-hint">{tr('closingDeadlineHint')}</small>
            </div>
            <div className="form-group">
              <label className="form-label">{tr('note')}</label>
              <input
                className="form-input"
                value={activationForm.note}
                onChange={(event) => setActivationForm({ ...activationForm, note: event.target.value })}
              />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setActivationModal(null)}>
                {tr('cancel')}
              </button>
              <button type="submit" className="btn btn-primary">
                {tr('taxSchemeActivate')}
              </button>
            </div>
          </form>
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
            <div className="form-group">
              <label className="form-label">{tr('taxScheme')} *</label>
              <select
                className="form-input"
                value={decisionForm.tax_scheme_id}
                onChange={(event) => setDecisionForm({ ...decisionForm, tax_scheme_id: event.target.value })}
                required
              >
                {schemes
                  .filter((scheme) => !scheme.is_archived || scheme.id === Number(decisionForm.tax_scheme_id))
                  .map((scheme) => (
                    <option key={scheme.id} value={scheme.id}>
                      {scheme.name}
                    </option>
                  ))}
              </select>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">{tr('yearLabel')} *</label>
                <input
                  type="number"
                  className="form-input"
                  value={decisionForm.year}
                  onChange={(event) => setDecisionForm({ ...decisionForm, year: event.target.value })}
                  required
                  min={1900}
                  max={2100}
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
                  {types
                    .filter((type) => !type.is_archived || type.id === Number(decisionForm.payment_type_id))
                    .map((type) => (
                      <option key={type.id} value={type.id}>
                        {getLang() === 'ru' ? type.name_ru || type.name_sr : type.name_sr}
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
            <div className="tax-rule-options">
              <div className="form-group">
                <label className="form-label">{tr('paymentDueDay')} *</label>
                <input
                  type="number"
                  min="1"
                  max="31"
                  className="form-input"
                  value={decisionForm.due_day}
                  onChange={(event) => setDecisionForm({ ...decisionForm, due_day: event.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('paymentDueMonthOffset')} *</label>
                <input
                  type="number"
                  min="0"
                  max="24"
                  className="form-input"
                  value={decisionForm.due_month_offset}
                  onChange={(event) =>
                    setDecisionForm({ ...decisionForm, due_month_offset: event.target.value })
                  }
                  required
                />
              </div>
            </div>
            <label className="tax-setting-checkbox tax-setting-checkbox--panel">
              <input
                type="checkbox"
                checked={decisionForm.prorate_partial_month}
                onChange={(event) =>
                  setDecisionForm({ ...decisionForm, prorate_partial_month: event.target.checked })
                }
              />
              <span>
                <strong>{tr('proratePartialMonth')}</strong>
                <small>{tr('proratePartialMonthHint')}</small>
              </span>
            </label>
            <div className="form-group">
              <label className="form-label">{tr('recipient')} *</label>
              <input
                type="text"
                className="form-input"
                value={decisionForm.recipient_name}
                onChange={(event) => setDecisionForm({ ...decisionForm, recipient_name: event.target.value })}
                placeholder={tr('recipientNamePlaceholder')}
                required
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
                  placeholder={tr('recipientAccountPlaceholder')}
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
                  placeholder={tr('paymentReferencePlaceholder')}
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
                placeholder={tr('paymentReferenceNextPlaceholder')}
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
              <label className="tax-setting-checkbox">
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
            {decisionFormModal !== 'add' ? (
              <div className="form-group">
                <label className="tax-setting-checkbox">
                  <input
                    type="checkbox"
                    checked={decisionForm.is_active}
                    onChange={(event) =>
                      setDecisionForm({ ...decisionForm, is_active: event.target.checked })
                    }
                  />
                  {tr('taxRuleActive')}
                </label>
              </div>
            ) : null}
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
