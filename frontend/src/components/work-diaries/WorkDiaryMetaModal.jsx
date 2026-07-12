import { useEffect, useState } from 'react'
import { Save } from 'lucide-react'
import { api } from '../../api'
import { tr } from '../../i18n'
import Modal from '../Modal'
import { num } from './workDiaryUtils'

const emptyMeta = {
  investor: '',
  permit_number: '',
  contractor: '',
  place: '',
  supervision: '',
  object_name: '',
  sector: '',
  responsible_person: '',
  billing_hourly_rate: '',
}

function metaFromResponse(data) {
  return {
    investor: data.investor || '',
    permit_number: data.permit_number || '',
    contractor: data.contractor || '',
    place: data.place || '',
    supervision: data.supervision || '',
    object_name: data.object_name || '',
    sector: data.sector || '',
    responsible_person: data.responsible_person || '',
    billing_hourly_rate: data.billing_hourly_rate || '',
  }
}

export default function WorkDiaryMetaModal({ isOpen, onClose, projectId, projectName, onSaved }) {
  const [meta, setMeta] = useState(emptyMeta)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!isOpen || !projectId) return
    api.workDiaries.projectMeta(projectId).then((data) => setMeta(metaFromResponse(data)))
  }, [isOpen, projectId])

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    try {
      const saved = await api.workDiaries.updateProjectMeta(projectId, {
        ...meta,
        billing_hourly_rate: num(meta.billing_hourly_rate),
      })
      setMeta(metaFromResponse(saved))
      await onSaved()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={saving ? () => {} : onClose}
      title={`${tr('workDiariesMetaTitle')}${projectName ? ` — ${projectName}` : ''}`}
      maxWidth="720px"
      resizable={false}
    >
      <form onSubmit={submit}>
        <div className="work-diaries-meta-grid">
          {[
            ['investor', tr('workDiariesInvestor')],
            ['permit_number', tr('workDiariesPermit')],
            ['contractor', tr('workDiariesContractor')],
            ['place', tr('workDiariesPlace')],
            ['supervision', tr('workDiariesSupervision')],
            ['object_name', tr('workDiariesObject')],
            ['sector', tr('workDiariesSector')],
            ['responsible_person', tr('workDiariesResponsible')],
            ['billing_hourly_rate', tr('workDiariesBillingRate')],
          ].map(([key, label]) => (
            <label className="form-group" key={key}>
              <span className="form-label">{label}</span>
              <input
                className="form-input"
                type={key === 'billing_hourly_rate' ? 'number' : 'text'}
                min="0"
                step="0.01"
                value={meta[key]}
                onChange={(event) => setMeta((prev) => ({ ...prev, [key]: event.target.value }))}
              />
            </label>
          ))}
        </div>
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>
            {tr('cancel')}
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            <Save size={16} /> {saving ? tr('saving') : tr('save')}
          </button>
        </div>
      </form>
    </Modal>
  )
}
