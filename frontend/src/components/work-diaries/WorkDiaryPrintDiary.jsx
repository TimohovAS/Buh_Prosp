import { tr } from '../../i18n'
import { dateLabel, dayName, hours, money, weatherPrintLabel } from './workDiaryUtils'

// Печатный «Грађевински дневник»: форма всегда на сербском (официальный документ)
export default function WorkDiaryPrintDiary({ entriesByDate, meta, objectName }) {
  return (
    <div className="work-diaries-print-surface">
      {Object.entries(entriesByDate).map(([date, dayEntries], index) => {
        const dayMaterials = dayEntries.flatMap((entry) => entry.materials || [])
        const descriptions = [...new Set(dayEntries.map((entry) => entry.description).filter(Boolean))]
        const notes = [...new Set(dayEntries.map((entry) => entry.note).filter(Boolean))]
        const dayWorkerNames = [...new Set(dayEntries.flatMap((entry) => entry.worker_names || []))]
        const workTimeRanges = [
          ...new Set(
            dayEntries.map((entry) =>
              entry.start_time && entry.end_time
                ? `${entry.start_time}–${entry.end_time}`
                : `${hours(entry.duration_hours)} h`
            )
          ),
        ]
        const weather = weatherPrintLabel(dayEntries.find((entry) => entry.weather)?.weather)
        const temperature = dayEntries.find((entry) => entry.temperature)?.temperature || ''
        return (
          <section className="work-diary-print-page" key={date}>
            <div className="work-diary-grid">
              <div>
                <strong>ИЗВОЂАЧ РАДОВА:</strong> {meta.contractor}
                <br />
                <strong>ОБЈЕКАТ:</strong> {objectName}
                <br />
                <strong>МЕСТО:</strong> {meta.place}
              </div>
              <div>
                <strong>ИНВЕСТИТОР:</strong>
                <br />
                {meta.investor}
                <br />
                <strong>Бр. грађ. дозволе:</strong> {meta.permit_number}
              </div>
              <div className="work-diary-title-cell">
                <h2>ГРАЂЕВИНСКИ ДНЕВНИК</h2>
                <span>
                  ДАН: <strong>{dayName(date)}</strong>
                </span>
                <span>
                  ДАТУМ: <strong>{dateLabel(date)}</strong>
                </span>
                <span>
                  Лист бр. <strong>{index + 1}</strong>
                </span>
              </div>
              <div>
                <strong>РАДНО ВРЕМЕ</strong>
                <br />
                {workTimeRanges.join(', ')}
              </div>
              <div>
                <strong>БРОЈ РАДНИКА</strong>
                <br />
                {dayWorkerNames.length}
              </div>
              <div>
                <strong>ВРЕМЕНСКИ УСЛОВИ</strong>
                <br />
                {weather} {temperature}
              </div>
            </div>
            <table className="work-diary-print-table">
              <tbody>
                <tr>
                  <th>ОПИС РАДОВА</th>
                  <td>
                    {descriptions.map((description) => (
                      <p key={description}>{description}</p>
                    ))}
                    {dayMaterials.length ? (
                      <>
                        <strong>Материјал:</strong>
                        {dayMaterials.map((material) => (
                          <p key={material.id}>
                            {material.description}
                            {material.quantity
                              ? ` - ${material.quantity}${material.unit ? ` ${material.unit}` : ''}`
                              : ''}
                            {material.amount ? ` - ${money(material.amount)}` : ''}
                          </p>
                        ))}
                      </>
                    ) : null}
                  </td>
                </tr>
                <tr>
                  <th>РАДНИЦИ</th>
                  <td>{dayWorkerNames.length ? dayWorkerNames.join(', ') : tr('workDiariesNoWorker')}</td>
                </tr>
                <tr>
                  <th>ПРИМЕДБЕ</th>
                  <td>{notes.join('; ')}</td>
                </tr>
              </tbody>
            </table>
            <div className="work-diary-signatures">
              <span>Одговорни извођач</span>
              <span>Надзорни орган</span>
            </div>
          </section>
        )
      })}
    </div>
  )
}
