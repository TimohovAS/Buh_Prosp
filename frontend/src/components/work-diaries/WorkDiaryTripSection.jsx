import { Plus } from 'lucide-react'
import { tr } from '../../i18n'
import { money, num } from './workDiaryUtils'

const round2 = (value) => String(Math.round((num(value) + Number.EPSILON) * 100) / 100)

// Выезд: время в пути и расстояние — справочно, для услуг заказчику. Оплату работников
// отметка не меняет, а транспорт (топливо, путарина, парковка) приходит из расходов проекта.
export default function WorkDiaryTripSection({
  form,
  totals,
  teamBillingRate,
  readOnly,
  setFormField,
  onAddService,
}) {
  const exitSuggestion = totals.dayTopUp + totals.tripAllowances
  // Из чего складывается подсказка: доплату до полного дня не путаем с надбавкой дня
  // командировки, а фиксированная ставка командировки уже включает дневницу и питание.
  const costParts = [
    totals.fullDayTopUp > 0 ? tr('workDiariesTripCostFullDay', { amount: money(totals.fullDayTopUp) }) : '',
    totals.tripDayExtra > 0
      ? tr(
          totals.tripDayIncludesMeals ? 'workDiariesTripCostTripDayIncluded' : 'workDiariesTripCostTripDay',
          {
            amount: money(totals.tripDayExtra),
          }
        )
      : '',
    totals.tripAllowances > 0
      ? tr('workDiariesTripCostAllowances', { amount: money(totals.tripAllowances) })
      : '',
  ].filter(Boolean)
  const presets = [
    {
      key: 'exit',
      description: 'Troškovi izlaska',
      quantity: '1',
      unit: 'usl',
      unit_price: exitSuggestion > 0 ? round2(exitSuggestion) : '',
    },
    {
      key: 'travel-time',
      description: 'Vreme putovanja',
      quantity: num(form.travel_hours) > 0 ? String(form.travel_hours) : '1',
      unit: 'h',
      unit_price: teamBillingRate > 0 ? round2(teamBillingRate) : '',
    },
    {
      key: 'travel-cost',
      description: 'Putni troškovi',
      quantity: num(form.travel_km) > 0 ? String(form.travel_km) : '1',
      unit: num(form.travel_km) > 0 ? 'km' : 'usl',
      unit_price: '',
    },
  ]
  return (
    <div className="work-diaries-trip">
      <div className="work-diaries-trip-fields">
        <label className="form-group">
          <span className="form-label">{tr('workDiariesTravelHours')}</span>
          <input
            className="form-input"
            type="number"
            min="0"
            step="0.25"
            value={form.travel_hours}
            onChange={(event) => setFormField('travel_hours', event.target.value)}
          />
        </label>
        <label className="form-group">
          <span className="form-label">{tr('workDiariesTravelKm')}</span>
          <input
            className="form-input"
            type="number"
            min="0"
            step="1"
            value={form.travel_km}
            onChange={(event) => setFormField('travel_km', event.target.value)}
          />
        </label>
      </div>
      <p className="work-diaries-trip-hint">{tr('workDiariesTripHint')}</p>
      {!readOnly ? (
        <div className="work-diaries-trip-actions">
          <span>{tr('workDiariesAddForCustomer')}</span>
          {presets.map(({ key, ...service }) => (
            <button
              key={key}
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => onAddService(service)}
            >
              <Plus size={14} /> {service.description}
            </button>
          ))}
        </div>
      ) : null}
      {costParts.length ? (
        <small className="work-diaries-trip-suggestion">
          {tr('workDiariesTripCostSuggestion', { parts: costParts.join('; ') })}
        </small>
      ) : null}
    </div>
  )
}
