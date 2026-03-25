import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import DatePicker from '../components/DatePicker'
import { api } from '../api'
import { getMonthNamesFull, getMonthNamesShort, tr } from '../i18n'
import SearchInput from '../components/SearchInput'

function formatDate(value) {
  if (!value) return '\u2014'
  const date = new Date(`${value}T12:00:00`)
  return date.toLocaleDateString('sr-RS', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

function emptyValue() {
  const translated = tr('notSet')
  return translated && translated !== 'notSet' ? translated : '\u2014'
}

function defaultRecipientName() {
  const translated = tr('taxAuthority')
  return translated && translated !== 'taxAuthority' ? translated : ''
}

const STATUS_FILTERS = [
  { value: 'all', label: 'statusFilterAll' },
  { value: 'unpaid', label: 'unpaid' },
  { value: 'paid', label: 'paid' },
  { value: 'overdue', label: 'obligationsOverdue' },
]

export default function Obligations() {
  const location = useLocation()
  const isActivePage = location.pathname === '/payments'
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  const [availableYears, setAvailableYears] = useState([currentYear])
  const [statusFilter, setStatusFilter] = useState('all')
  const [paymentTypeFilter, setPaymentTypeFilter] = useState('')
  const [search, setSearch] = useState('')
  const [items, setItems] = useState([])
  const [types, setTypes] = useState([])
  const [decisions, setDecisions] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [paidModal, setPaidModal] = useState(null)
  const [paidForm, setPaidForm] = useState({
    paid_date: new Date().toISOString().slice(0, 10),
    payment_reference: '',
  })
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
        setAvailableYears(years?.length ? years : [currentYear])
      })
      .catch(() => {
        setItems([])
        setTypes([])
        setDecisions([])
        setAvailableYears([currentYear])
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const nextYear = params.get('year')
    const nextSearch = params.get('search')
    if (nextYear) setYear(parseInt(nextYear, 10))
    if (nextSearch) setSearch(nextSearch)
  }, [])

  useEffect(() => {
    if (!isActivePage) return
    load()
  }, [year, paymentTypeFilter, isActivePage])

  useEffect(() => {
    if (!availableYears.length) return
    if (!availableYears.includes(year)) {
      setYear(availableYears[0])
    }
  }, [availableYears, year])

  const getTypeName = (code) => types.find((item) => item.code === code)?.name_sr || code

  const filteredItems = items.filter((obligation) => {
    if (statusFilter !== 'all' && obligation.status !== statusFilter) return false
    const normalizedSearch = search.trim().toLowerCase()
    if (!normalizedSearch) return true

    const typeName = getTypeName(obligation.payment_type_code || '').toLowerCase()
    const haystack = [
      obligation.year,
      obligation.month,
      obligation.amount,
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
      paid_date: new Date().toISOString().slice(0, 10),
      payment_reference: obligation.payment_reference || '',
    })
    setPaidModal(obligation)
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
      period_start: typeof mode.period_start === 'string' ? mode.period_start : mode.period_start?.slice(0, 10) || '',
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
  const empty = emptyValue()

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">{tr('payments')}</h1>
        </div>
        <div className="page-header-actions">
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={year}
            onChange={(event) => setYear(parseInt(event.target.value, 10))}
            title={tr('filterYear')}
          >
            {availableYears.map((optionYear) => (
              <option key={optionYear} value={optionYear}>{optionYear}</option>
            ))}
          </select>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            title={tr('filterStatus')}
          >
            {STATUS_FILTERS.map((filter) => (
              <option key={filter.value} value={filter.value}>{tr(filter.label)}</option>
            ))}
          </select>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={paymentTypeFilter}
            onChange={(event) => setPaymentTypeFilter(event.target.value)}
            title={tr('filterPaymentType')}
          >
            <option value="">{tr('statusFilterAll')}</option>
            {types.map((type) => (
              <option key={type.id} value={type.code}>{type.name_sr}</option>
            ))}
          </select>
          <SearchInput
            placeholder={tr('search')}
            value={search}
            onChange={setSearch}
            style={{ width: 220 }}
          />
          <button className="btn btn-secondary" onClick={() => setSettingsModal(true)}>
            {tr('obligationsSettings')}
          </button>
        </div>
      </div>

      <div className="page-body">
        <div className="card">
          <h3 style={{ margin: 0, marginBottom: '1rem', fontSize: '1rem' }}>{tr('obligationsCalendar')}</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('year')}</th>
                  <th>{tr('month')}</th>
                  <th>{tr('paymentTypeLabel')}</th>
                  <th>{tr('amount')}</th>
                  <th>{tr('deadline')}</th>
                  <th>{tr('status')}</th>
                  <th>{tr('dateOfPayment')}</th>
                  <th>{tr('paymentRef')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={9}>{tr('loading')}</td></tr>
                ) : filteredItems.length === 0 ? (
                  <tr>
                    <td colSpan={9} style={{ color: 'var(--color-text-muted)' }}>
                      {tr('noDataAddDecisions')}
                    </td>
                  </tr>
                ) : (
                  filteredItems.map((obligation) => (
                    <tr key={obligation.id} style={obligation.status === 'paid' ? { opacity: 0.85 } : {}}>
                      <td>{obligation.year}</td>
                      <td>{monthNamesFull[obligation.month - 1] || obligation.month}</td>
                      <td>{getTypeName(obligation.payment_type_code) || obligation.payment_type_code}</td>
                      <td>{obligation.amount?.toLocaleString('sr-RS')} RSD</td>
                      <td>{formatDate(obligation.deadline)}</td>
                      <td>
                        <span
                          className="badge"
                          style={{
                            backgroundColor:
                              obligation.status === 'paid'
                                ? 'var(--color-success)'
                                : obligation.status === 'overdue'
                                  ? 'var(--color-danger)'
                                  : 'var(--color-warning)',
                            color: '#fff',
                            padding: '0.2rem 0.5rem',
                            borderRadius: 4,
                          }}
                        >
                          {obligation.status === 'paid' ? tr('paid') : obligation.status === 'overdue' ? tr('obligationsOverdue') : tr('unpaid')}
                        </span>
                      </td>
                      <td>{obligation.paid_date ? formatDate(obligation.paid_date) : empty}</td>
                      <td style={{ fontSize: '0.85rem', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis' }} title={obligation.payment_reference || empty}>
                        {obligation.payment_reference || empty}
                      </td>
                      <td>
                        {obligation.status === 'paid' ? (
                          <button className="btn btn-sm btn-secondary" onClick={() => markUnpaid(obligation)}>
                            {tr('markUnpaid')}
                          </button>
                        ) : (
                          <button className="btn btn-sm btn-primary" onClick={() => openPaidModal(obligation)}>
                            {tr('markPaid')}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {settingsModal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 800, maxHeight: '90vh', overflow: 'auto' }}>
            <div className="modal-header">
              <h2 className="modal-title">{tr('obligationsSettings')}</h2>
              <button className="modal-close" onClick={() => setSettingsModal(false)}>{'\u00D7'}</button>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
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
                      <td colSpan={6} style={{ color: 'var(--color-text-muted)' }}>{tr('noDecisions')}</td>
                    </tr>
                  ) : (
                    decisions.map((decision) => (
                      <tr key={decision.id}>
                        <td>{decision.year}</td>
                        <td>{decision.payment_type_name || decision.payment_type_code}</td>
                        <td>{decision.monthly_amount?.toLocaleString('sr-RS')} RSD</td>
                        <td style={{ fontSize: '0.85rem' }}>{decision.recipient_account}</td>
                        <td style={{ fontSize: '0.8rem', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }} title={decision.poziv_na_broj}>{decision.poziv_na_broj}</td>
                        <td>
                          <button className="btn btn-sm btn-secondary" onClick={() => openDecisionForm(decision)}>
                            {tr('edit')}
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="modal-actions" style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
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
          </div>
        </div>
      )}

      {paidModal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 400 }}>
            <div className="modal-header">
              <h2 className="modal-title">
                {tr('markPaid')} {'\u2014'} {getTypeName(paidModal.payment_type_code)} {monthNamesShort[paidModal.month - 1]}
              </h2>
              <button className="modal-close" onClick={() => setPaidModal(null)}>{'\u00D7'}</button>
            </div>
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
                <button type="submit" className="btn btn-primary">{tr('save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {decisionFormModal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 520, maxHeight: '90vh', overflow: 'auto' }}>
            <div className="modal-header">
              <h2 className="modal-title">
                {decisionFormModal === 'add' ? tr('add') : tr('edit')} {'\u2014'} {tr('decisionFormTitle')}
              </h2>
              <button className="modal-close" onClick={() => setDecisionFormModal(null)}>{'\u00D7'}</button>
            </div>
            <form onSubmit={handleDecisionFormSubmit}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('yearLabel')} *</label>
                  <input type="number" className="form-input" value={decisionForm.year} onChange={(event) => setDecisionForm({ ...decisionForm, year: event.target.value })} required min={2020} max={2035} />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('paymentTypeLabel')} *</label>
                  <select className="form-input" value={decisionForm.payment_type_id} onChange={(event) => setDecisionForm({ ...decisionForm, payment_type_id: event.target.value })} required disabled={decisionFormModal !== 'add'}>
                    {types.map((type) => (
                      <option key={type.id} value={type.id}>{type.name_sr}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('periodFrom')} *</label>
                  <DatePicker value={decisionForm.period_start} onChange={(value) => setDecisionForm({ ...decisionForm, period_start: value })} required />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('periodTo')} *</label>
                  <DatePicker value={decisionForm.period_end} onChange={(value) => setDecisionForm({ ...decisionForm, period_end: value })} required />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('monthlyAmount')} *</label>
                  <input type="number" step="0.01" className="form-input" value={decisionForm.monthly_amount} onChange={(event) => setDecisionForm({ ...decisionForm, monthly_amount: event.target.value })} required />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('baseAmount')}</label>
                  <input type="number" step="0.01" className="form-input" value={decisionForm.base_amount} onChange={(event) => setDecisionForm({ ...decisionForm, base_amount: event.target.value })} />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('ratePercent')}</label>
                  <input type="number" step="0.01" className="form-input" value={decisionForm.rate_percent} onChange={(event) => setDecisionForm({ ...decisionForm, rate_percent: event.target.value })} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('recipient')}</label>
                <input type="text" className="form-input" value={decisionForm.recipient_name} onChange={(event) => setDecisionForm({ ...decisionForm, recipient_name: event.target.value })} placeholder={tr('taxAuthority')} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('recipientAccount')} *</label>
                  <input type="text" className="form-input" value={decisionForm.recipient_account} onChange={(event) => setDecisionForm({ ...decisionForm, recipient_account: event.target.value })} required placeholder="840-71122843-32" />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('sifraPlacanja')}</label>
                  <input type="text" className="form-input" value={decisionForm.sifra_placanja} onChange={(event) => setDecisionForm({ ...decisionForm, sifra_placanja: event.target.value })} placeholder="253" />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('model')}</label>
                  <input type="text" className="form-input" value={decisionForm.model} onChange={(event) => setDecisionForm({ ...decisionForm, model: event.target.value })} placeholder="97" />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('pozivNaBroj')} *</label>
                  <input type="text" className="form-input" value={decisionForm.poziv_na_broj} onChange={(event) => setDecisionForm({ ...decisionForm, poziv_na_broj: event.target.value })} required placeholder="2624190000007887475" />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('pozivNaBrojNext')}</label>
                <input type="text" className="form-input" value={decisionForm.poziv_na_broj_next} onChange={(event) => setDecisionForm({ ...decisionForm, poziv_na_broj_next: event.target.value })} placeholder="2024190000008031910" />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('paymentPurpose')} *</label>
                <input type="text" className="form-input" value={decisionForm.payment_purpose} onChange={(event) => setDecisionForm({ ...decisionForm, payment_purpose: event.target.value })} required placeholder={tr('paymentPurpose')} />
                <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>{tr('purposeYearHint')}</div>
              </div>
              <div className="form-group">
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input type="checkbox" checked={decisionForm.is_provisional} onChange={(event) => setDecisionForm({ ...decisionForm, is_provisional: event.target.checked })} />
                  {tr('provisional')}
                </label>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setDecisionFormModal(null)}>{tr('cancel')}</button>
                <button type="submit" className="btn btn-primary">{tr('save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
