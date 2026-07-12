import { tr } from '../../i18n'
import { dateLabel, hours, money } from './workDiaryUtils'

function entryWorkerName(entry) {
  return entry.worker_names?.length ? entry.worker_names.join(', ') : tr('workDiariesNoWorker')
}

// Печатный отчет «Евиденција радних сати и утрошеног материјала» (всегда на сербском)
export default function WorkDiaryPrintReport({
  entries,
  summary,
  meta,
  projectName,
  objectName,
  dateFrom,
  dateTo,
}) {
  return (
    <div className="work-diaries-print-surface">
      <section className="work-diary-report-page">
        <div className="work-diary-report-header">
          <div>
            <span>Градилиште</span>
            <strong>{projectName}</strong>
          </div>
          <div>
            <span>Сектор</span>
            <strong>{meta.sector}</strong>
          </div>
          <div>
            <span>Објекат</span>
            <strong>{objectName}</strong>
          </div>
          <div>
            <span>Период</span>
            <strong>
              {dateLabel(dateFrom) || '...'} - {dateLabel(dateTo) || '...'}
            </strong>
          </div>
        </div>
        <h2>Евиденција радних сати и утрошеног материјала</h2>
        <table className="work-diary-report-table">
          <thead>
            <tr>
              <th>Датум</th>
              <th>Радник</th>
              <th>Опис радова</th>
              <th>Поч.</th>
              <th>Крај</th>
              <th>Човек-сати</th>
              <th>Ред. ч-с</th>
              <th>Прек. ч-с</th>
              <th>Материјал</th>
              <th>За фактурисање</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td>{dateLabel(entry.date)}</td>
                <td>{entryWorkerName(entry)}</td>
                <td>{entry.description}</td>
                <td>{entry.start_time}</td>
                <td>{entry.end_time}</td>
                <td>{hours(entry.person_hours)}</td>
                <td>{hours(entry.regular_person_hours)}</td>
                <td>{entry.overtime_person_hours > 0 ? hours(entry.overtime_person_hours) : ''}</td>
                <td>{money(entry.material_amount)}</td>
                <td>{money(entry.billable_amount)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={5}>УКУПНО</td>
              <td>{hours(summary?.person_hours)}</td>
              <td>{hours(summary?.regular_person_hours)}</td>
              <td>{hours(summary?.overtime_person_hours)}</td>
              <td>{money(summary?.material_amount)}</td>
              <td>{money(summary?.billable_amount)}</td>
            </tr>
          </tfoot>
        </table>
      </section>
    </div>
  )
}
