import { tr } from '../../i18n'
import FieldTooltip from '../FieldTooltip'
import { DAY_PAY_MODES, PAY_MODES, hours, money, payModeLabel } from './workDiaryUtils'

const DAY_RATE_SOURCE_KEYS = {
  card: 'workDiariesDayRateFromCard',
  saved: 'workDiariesDayRateSaved',
  manual: 'workDiariesDayRateManual',
}

function AllowanceInput({ label, value, placeholder, onChange }) {
  return (
    <label className="work-diaries-pay-field">
      <span className="work-diaries-pay-label">{label}</span>
      <input
        className="form-input"
        type="number"
        min="0"
        step="0.01"
        value={value}
        placeholder={placeholder}
        aria-label={label}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}

// Дневница или питание, которые уже входят в фиксированную ставку дня командировки:
// не ноль и не поле ввода, а пометка, что они оплачены внутри ставки.
function IncludedInRate({ label, title }) {
  return (
    <div className="work-diaries-pay-field">
      <span className="work-diaries-pay-label">{label}</span>
      <span className="work-diaries-pay-muted" title={title}>
        {tr('workDiariesIncludedInDayRate')}
      </span>
    </div>
  )
}

// Оплата работников за дату записи. Режим и командировочные — на работника и дату:
// они общие для всех его записей этого дня, а сумма делится между записями по часам.
export default function WorkDiaryWorkerPaySection({
  workers,
  payState,
  savedDays,
  resolved,
  shares,
  duration,
  showAllowances,
  readOnly,
  onChange,
  onApplyAll,
}) {
  if (!workers.length) {
    return <p className="work-diaries-pay-hint">{tr('workDiariesPayNoWorkers')}</p>
  }
  // Дневница и питание — отдельные колонки, только если они хоть у кого-то начисляются
  // отдельно: у фиксированной ставки командировки они уже внутри ставки дня.
  const showMeals = showAllowances && workers.some((worker) => !resolved[worker.id]?.fixedTrip)
  const gridClass = showMeals ? ' with-allowances' : showAllowances ? ' with-lodging' : ''
  return (
    <div className="work-diaries-pay">
      <p className="work-diaries-pay-hint">{tr('workDiariesPayHint')}</p>
      {!readOnly && workers.length > 1 ? (
        <label className="work-diaries-pay-all">
          <span>{tr('workDiariesPayModeAll')}</span>
          <select
            className="form-input"
            value=""
            onChange={(event) => {
              if (event.target.value) onApplyAll(event.target.value)
            }}
          >
            <option value="">{tr('select')}</option>
            {PAY_MODES.map((mode) => (
              <option key={mode} value={mode}>
                {payModeLabel(mode)}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <div className={`work-diaries-pay-grid${gridClass}`}>
        <div className="work-diaries-pay-row work-diaries-pay-header" aria-hidden="true">
          <span>{tr('worker')}</span>
          <span className="field-label-with-tooltip">
            {tr('workDiariesPayMode')}
            <FieldTooltip text={tr('workDiariesPayModeTooltip')} />
          </span>
          <span>{tr('workDiariesDayRate')}</span>
          {showMeals ? (
            <>
              <span>{tr('workDiariesPerDiemDay')}</span>
              <span>{tr('workDiariesFoodDay')}</span>
            </>
          ) : null}
          {showAllowances ? <span>{tr('workDiariesLodgingNight')}</span> : null}
          <span>{tr('workDiariesAccruedInEntry')}</span>
        </div>
        {workers.map((worker) => {
          const state = payState[worker.id] || {
            pay_mode: 'hourly',
            day_rate: '',
            per_diem: '',
            food: '',
            lodging: '',
          }
          const pay = resolved[worker.id]
          const share = shares[worker.id]
          const others = savedDays[worker.id]?.other_entries || []
          const isDay = DAY_PAY_MODES.includes(pay.mode)
          // Между записями дня делятся только дневная ставка и командировочные, почасовой труд — нет.
          const splitByDay = isDay || pay.perDiem + pay.food + pay.lodging > 0
          const fixedTitle = pay.fixedTrip ? tr('workDiariesAllowanceFixedHint') : undefined
          return (
            <div className="work-diaries-pay-row" key={worker.id}>
              <span className="work-diaries-pay-name">{worker.name}</span>
              <label className="work-diaries-pay-field">
                <span className="work-diaries-pay-label">{tr('workDiariesPayMode')}</span>
                <select
                  className="form-input"
                  value={state.pay_mode}
                  aria-label={`${tr('workDiariesPayMode')}: ${worker.name}`}
                  onChange={(event) =>
                    onChange(worker.id, {
                      pay_mode: event.target.value,
                      day_rate: '',
                      per_diem: '',
                      food: '',
                    })
                  }
                >
                  {PAY_MODES.map((mode) => (
                    <option key={mode} value={mode}>
                      {payModeLabel(mode)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="work-diaries-pay-field">
                <span className="work-diaries-pay-label">{tr('workDiariesDayRate')}</span>
                {isDay ? (
                  <>
                    <input
                      className="form-input"
                      type="number"
                      min="0"
                      step="0.01"
                      value={state.day_rate}
                      placeholder={String(Math.round(pay.dayRate * 100) / 100)}
                      aria-label={`${tr('workDiariesDayRate')}: ${worker.name}`}
                      onChange={(event) => onChange(worker.id, { day_rate: event.target.value })}
                    />
                    <small className="work-diaries-rate-hint">
                      {tr(DAY_RATE_SOURCE_KEYS[pay.dayRateSource] || 'workDiariesDayRateFromCard')}
                      {!readOnly && state.day_rate !== '' ? (
                        <button
                          type="button"
                          className="btn-link"
                          onClick={() => onChange(worker.id, { day_rate: '' })}
                        >
                          {tr('workDiariesApplyAutoRate')}
                        </button>
                      ) : null}
                    </small>
                    {pay.fixedTrip ? (
                      <small className="work-diaries-rate-hint" title={fixedTitle}>
                        {tr('workDiariesDayRateIncludesMeals')}
                      </small>
                    ) : null}
                    {pay.rateMissing ? (
                      <small className="work-diaries-rate-warning">{tr('workDiariesDayRateMissing')}</small>
                    ) : null}
                  </>
                ) : (
                  <span className="work-diaries-pay-muted">{tr('workDiariesPayHourlyRateHint')}</span>
                )}
              </label>
              {showMeals && pay.fixedTrip ? (
                <>
                  <IncludedInRate label={tr('workDiariesPerDiemDay')} title={fixedTitle} />
                  <IncludedInRate label={tr('workDiariesFoodDay')} title={fixedTitle} />
                </>
              ) : null}
              {showMeals && !pay.fixedTrip ? (
                <>
                  <AllowanceInput
                    label={tr('workDiariesPerDiemDay')}
                    value={state.per_diem}
                    placeholder={String(pay.perDiem)}
                    onChange={(value) => onChange(worker.id, { per_diem: value })}
                  />
                  <AllowanceInput
                    label={tr('workDiariesFoodDay')}
                    value={state.food}
                    placeholder={String(pay.food)}
                    onChange={(value) => onChange(worker.id, { food: value })}
                  />
                </>
              ) : null}
              {showAllowances ? (
                <AllowanceInput
                  label={tr('workDiariesLodgingNight')}
                  value={state.lodging}
                  placeholder={String(pay.lodging)}
                  onChange={(value) => onChange(worker.id, { lodging: value })}
                />
              ) : null}
              <div className="work-diaries-pay-accrued">
                <strong>{money((share?.labor || 0) + (share?.allowances || 0))}</strong>
                {others.length ? (
                  <>
                    {splitByDay ? (
                      <small>
                        {tr('workDiariesDayShare', { hours: hours(duration), total: hours(share?.dayHours) })}
                      </small>
                    ) : null}
                    <small>
                      {tr('workDiariesOtherEntries', {
                        list: others
                          .map((other) => `${other.project_name || '—'} (${hours(other.duration_hours)})`)
                          .join(', '),
                      })}
                    </small>
                  </>
                ) : null}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
