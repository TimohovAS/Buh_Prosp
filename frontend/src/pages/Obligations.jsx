import { useState, useEffect } from 'react'
import { api } from '../api'
import { tr, getMonthNamesShort, getMonthNamesFull } from '../i18n'
import DatePicker from '../components/DatePicker'

function formatDate(s) {
  if (!s) return '—'
  const d = new Date(s + 'T12:00:00')
  return d.toLocaleDateString('sr-RS', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

const STATUS_FILTERS = [
  { value: 'all', label: 'statusFilterAll' },
  { value: 'unpaid', label: 'unpaid' },
  { value: 'paid', label: 'paid' },
  { value: 'overdue', label: 'obligationsOverdue' },
]

export default function Obligations() {
  const [year, setYear] = useState(new Date().getFullYear())
  const [statusFilter, setStatusFilter] = useState('all')
  const [paymentTypeFilter, setPaymentTypeFilter] = useState('')
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
    recipient_name: 'Пореска управа Републике Србије',
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
    ])
      .then(([t, cal, dec]) => {
        setTypes(t)
        setItems(cal)
        setDecisions(dec)
      })
      .catch(() => {
        setItems([])
        setTypes([])
        setDecisions([])
      })
      .finally(() => setLoading(false))
  }

  useEffect(load, [year, paymentTypeFilter])

  const filteredItems = items.filter((ob) => {
    if (statusFilter === 'all') return true
    return ob.status === statusFilter
  })

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      await api.obligations.generate(year)
      load()
    } catch (err) {
      alert(err.message)
    } finally {
      setGenerating(false)
    }
  }

  const openPaidModal = (ob) => {
    setPaidForm({
      paid_date: new Date().toISOString().slice(0, 10),
      payment_reference: ob.payment_reference || '',
    })
    setPaidModal(ob)
  }

  const handleMarkPaidSubmit = async (e) => {
    e.preventDefault()
    if (!paidModal) return
    try {
      await api.obligations.markPaid(paidModal.id, {
        paid_date: paidForm.paid_date,
        payment_reference: paidForm.payment_reference || null,
      })
      setPaidModal(null)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const markUnpaid = async (ob) => {
    if (!confirm(tr('confirmUnpaid'))) return
    try {
      await api.obligations.markUnpaid(ob.id)
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const openDecisionForm = (mode) => {
    if (mode === 'add') {
      const y = year
      setDecisionForm({
        year: y,
        payment_type_id: types[0]?.id || '',
        period_start: `${y}-01-01`,
        period_end: `${y}-12-31`,
        monthly_amount: '',
        base_amount: '',
        rate_percent: '',
        recipient_name: 'Пореска управа Републике Србије',
        recipient_account: '',
        sifra_placanja: '253',
        model: '97',
        poziv_na_broj: '',
        poziv_na_broj_next: '',
        payment_purpose: '',
        is_provisional: false,
      })
      setDecisionFormModal('add')
    } else {
      setDecisionFormModal({ type: 'edit', id: mode.id })
      setDecisionForm({
        year: mode.year,
        payment_type_id: mode.payment_type_id,
        period_start: typeof mode.period_start === 'string' ? mode.period_start : mode.period_start?.slice(0, 10) || '',
        period_end: typeof mode.period_end === 'string' ? mode.period_end : mode.period_end?.slice(0, 10) || '',
        monthly_amount: mode.monthly_amount ?? '',
        base_amount: mode.base_amount ?? '',
        rate_percent: mode.rate_percent ?? '',
        recipient_name: mode.recipient_name || 'Пореска управа Републике Србије',
        recipient_account: mode.recipient_account || '',
        sifra_placanja: mode.sifra_placanja || '253',
        model: mode.model || '97',
        poziv_na_broj: mode.poziv_na_broj || '',
        poziv_na_broj_next: mode.poziv_na_broj_next || '',
        payment_purpose: mode.payment_purpose || '',
        is_provisional: mode.is_provisional ?? false,
      })
    }
  }

  const handleDecisionFormSubmit = async (e) => {
    e.preventDefault()
    try {
      const payload = {
        year: parseInt(decisionForm.year),
        payment_type_id: parseInt(decisionForm.payment_type_id),
        period_start: decisionForm.period_start,
        period_end: decisionForm.period_end,
        monthly_amount: parseFloat(decisionForm.monthly_amount) || 0,
        base_amount: decisionForm.base_amount ? parseFloat(decisionForm.base_amount) : null,
        rate_percent: decisionForm.rate_percent ? parseFloat(decisionForm.rate_percent) : null,
        recipient_name: decisionForm.recipient_name || 'Пореска управа Републике Србије',
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
    } catch (err) {
      alert(err.message)
    }
  }

  const applyPreset2026 = async () => {
    if (!confirm(tr('confirmApplyPreset'))) return
    try {
      await api.obligations.applyPreset2026()
      load()
    } catch (err) {
      alert(err.message)
    }
  }

  const getTypeName = (code) => types.find(t => t.code === code)?.name_sr || code
  const monthNamesFull = getMonthNamesFull()
  const monthNamesShort = getMonthNamesShort()

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">{tr('payments')}</h1>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value))}
            title={tr('filterYear')}
          >
            {[year - 2, year - 1, year, year + 1].map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            title={tr('filterStatus')}
          >
            {STATUS_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>{tr(f.label)}</option>
            ))}
          </select>
          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={paymentTypeFilter}
            onChange={(e) => setPaymentTypeFilter(e.target.value)}
            title={tr('filterPaymentType')}
          >
            <option value="">{tr('statusFilterAll')}</option>
            {types.map((t) => (
              <option key={t.id} value={t.code}>{t.name_sr}</option>
            ))}
          </select>
          <button className="btn btn-secondary" onClick={() => setSettingsModal(true)}>
            {tr('obligationsSettings')}
          </button>
        </div>
      </div>

      <div className="page-body">
        {/* Таблица обязательств */}
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
                  filteredItems.map((ob) => (
                    <tr key={ob.id} style={ob.status === 'paid' ? { opacity: 0.85 } : {}}>
                      <td>{ob.year}</td>
                      <td>{monthNamesFull[ob.month - 1] || ob.month}</td>
                      <td>{getTypeName(ob.payment_type_code) || ob.payment_type_code}</td>
                      <td>{ob.amount?.toLocaleString('sr-RS')} RSD</td>
                      <td>{formatDate(ob.deadline)}</td>
                      <td>
                        <span
                          className="badge"
                          style={{
                            backgroundColor:
                              ob.status === 'paid' ? 'var(--color-success)'
                                : ob.status === 'overdue' ? 'var(--color-danger)'
                                  : 'var(--color-warning)',
                            color: '#fff',
                            padding: '0.2rem 0.5rem',
                            borderRadius: 4,
                          }}
                        >
                          {ob.status === 'paid' ? tr('paid') : ob.status === 'overdue' ? tr('obligationsOverdue') : tr('unpaid')}
                        </span>
                      </td>
                      <td>{ob.paid_date ? formatDate(ob.paid_date) : '—'}</td>
                      <td style={{ fontSize: '0.85rem', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis' }} title={ob.payment_reference}>
                        {ob.payment_reference || '—'}
                      </td>
                      <td>
                        {ob.status === 'paid' ? (
                          <button className="btn btn-sm btn-secondary" onClick={() => markUnpaid(ob)}>
                            {tr('markUnpaid')}
                          </button>
                        ) : (
                          <button className="btn btn-sm btn-primary" onClick={() => openPaidModal(ob)}>
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

      {/* Модалка «Настройки обязательств» */}
      {settingsModal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 800, maxHeight: '90vh', overflow: 'auto' }}>
            <div className="modal-header">
              <h2 className="modal-title">{tr('obligationsSettings')}</h2>
              <button className="modal-close" onClick={() => setSettingsModal(false)}>×</button>
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
                    decisions.map((d) => (
                      <tr key={d.id}>
                        <td>{d.year}</td>
                        <td>{d.payment_type_name || d.payment_type_code}</td>
                        <td>{d.monthly_amount?.toLocaleString('sr-RS')} RSD</td>
                        <td style={{ fontSize: '0.85rem' }}>{d.recipient_account}</td>
                        <td style={{ fontSize: '0.8rem', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }} title={d.poziv_na_broj}>{d.poziv_na_broj}</td>
                        <td>
                          <button className="btn btn-sm btn-secondary" onClick={() => openDecisionForm(d)}>
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
                onClick={() => { handleGenerate(); }}
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

      {/* Модалка «Отметить оплаченным» */}
      {paidModal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 400 }}>
            <div className="modal-header">
              <h2 className="modal-title">
                {tr('markPaid')} — {getTypeName(paidModal.payment_type_code)} {monthNamesShort[paidModal.month - 1]}
              </h2>
              <button className="modal-close" onClick={() => setPaidModal(null)}>×</button>
            </div>
            <form onSubmit={handleMarkPaidSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('date')}</label>
                <DatePicker
                  value={paidForm.paid_date}
                  onChange={(v) => setPaidForm({ ...paidForm, paid_date: v })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('paymentRef')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={paidForm.payment_reference}
                  onChange={(e) => setPaidForm({ ...paidForm, payment_reference: e.target.value })}
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

      {/* Модалка формы решения */}
      {decisionFormModal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 520, maxHeight: '90vh', overflow: 'auto' }}>
            <div className="modal-header">
              <h2 className="modal-title">
                {decisionFormModal === 'add' ? tr('add') : tr('edit')} — {tr('decisionFormTitle')}
              </h2>
              <button className="modal-close" onClick={() => setDecisionFormModal(null)}>×</button>
            </div>
            <form onSubmit={handleDecisionFormSubmit}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('yearLabel')} *</label>
                  <input type="number" className="form-input" value={decisionForm.year} onChange={(e) => setDecisionForm({ ...decisionForm, year: e.target.value })} required min={2020} max={2035} />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('paymentTypeLabel')} *</label>
                  <select className="form-input" value={decisionForm.payment_type_id} onChange={(e) => setDecisionForm({ ...decisionForm, payment_type_id: e.target.value })} required disabled={decisionFormModal !== 'add'}>
                    {types.map((t) => (
                      <option key={t.id} value={t.id}>{t.name_sr}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('periodFrom')} *</label>
                  <DatePicker value={decisionForm.period_start} onChange={(v) => setDecisionForm({ ...decisionForm, period_start: v })} required />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('periodTo')} *</label>
                  <DatePicker value={decisionForm.period_end} onChange={(v) => setDecisionForm({ ...decisionForm, period_end: v })} required />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('monthlyAmount')} *</label>
                  <input type="number" step="0.01" className="form-input" value={decisionForm.monthly_amount} onChange={(e) => setDecisionForm({ ...decisionForm, monthly_amount: e.target.value })} required />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('baseAmount')}</label>
                  <input type="number" step="0.01" className="form-input" value={decisionForm.base_amount} onChange={(e) => setDecisionForm({ ...decisionForm, base_amount: e.target.value })} />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('ratePercent')}</label>
                  <input type="number" step="0.01" className="form-input" value={decisionForm.rate_percent} onChange={(e) => setDecisionForm({ ...decisionForm, rate_percent: e.target.value })} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('recipient')}</label>
                <input type="text" className="form-input" value={decisionForm.recipient_name} onChange={(e) => setDecisionForm({ ...decisionForm, recipient_name: e.target.value })} placeholder={tr('taxAuthority')} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('recipientAccount')} *</label>
                  <input type="text" className="form-input" value={decisionForm.recipient_account} onChange={(e) => setDecisionForm({ ...decisionForm, recipient_account: e.target.value })} required placeholder="840-71122843-32" />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('sifraPlacanja')}</label>
                  <input type="text" className="form-input" value={decisionForm.sifra_placanja} onChange={(e) => setDecisionForm({ ...decisionForm, sifra_placanja: e.target.value })} placeholder="253" />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">{tr('model')}</label>
                  <input type="text" className="form-input" value={decisionForm.model} onChange={(e) => setDecisionForm({ ...decisionForm, model: e.target.value })} placeholder="97" />
                </div>
                <div className="form-group">
                  <label className="form-label">{tr('pozivNaBroj')} *</label>
                  <input type="text" className="form-input" value={decisionForm.poziv_na_broj} onChange={(e) => setDecisionForm({ ...decisionForm, poziv_na_broj: e.target.value })} required placeholder="2624190000007887475" />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('pozivNaBrojNext')}</label>
                <input type="text" className="form-input" value={decisionForm.poziv_na_broj_next} onChange={(e) => setDecisionForm({ ...decisionForm, poziv_na_broj_next: e.target.value })} placeholder="2024190000008031910" />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('paymentPurpose')} *</label>
                <input type="text" className="form-input" value={decisionForm.payment_purpose} onChange={(e) => setDecisionForm({ ...decisionForm, payment_purpose: e.target.value })} required placeholder="Porez na paušalni prihod za YYYY. godinu" />
                <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>{tr('purposeYearHint')}</div>
              </div>
              <div className="form-group">
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input type="checkbox" checked={decisionForm.is_provisional} onChange={(e) => setDecisionForm({ ...decisionForm, is_provisional: e.target.checked })} />
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
