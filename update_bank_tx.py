import os
import re

path = r"d:\Work\Programming\Buh_Prosp\frontend\src\pages\BankTransactions.jsx"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# ADD IMPORTS & STATE
imports_old = """import { useState, useEffect } from 'react'
import { api } from '../api'
import { tr } from '../i18n'
import Modal from '../components/Modal'"""
imports_new = """import { useState, useEffect } from 'react'
import { api } from '../api'
import { tr } from '../i18n'
import Modal from '../components/Modal'
import { Check } from 'lucide-react'"""

text = text.replace(imports_old, imports_new)

state_old = """    const [matchError, setMatchError] = useState('')

    const LIMIT = 50"""

state_new = """    const [matchError, setMatchError] = useState('')

    // Projects State
    const [projects, setProjects] = useState([])
    const [selectedIds, setSelectedIds] = useState([])
    const [modalAssign, setModalAssign] = useState(false)
    const [assignProjectId, setAssignProjectId] = useState('')

    const LIMIT = 50"""
text = text.replace(state_old, state_new)


# ADD LOAD DATA EXTRAS
load_old = """    const loadData = async () => {
        setLoading(true)
        try {
            const params = { skip: page * LIMIT, limit: LIMIT }
            if (statusFilter !== 'all') params.status = statusFilter
            if (directionFilter !== 'all') params.direction = directionFilter
            const res = await api.bankTransactions.list(params)
            setData(res)
        } catch (err) {
            console.error(err)
        } finally {
            setLoading(false)
        }
    }"""
load_new = """    const loadData = async () => {
        setLoading(true)
        try {
            const params = { skip: page * LIMIT, limit: LIMIT }
            if (statusFilter !== 'all') params.status = statusFilter
            if (directionFilter !== 'all') params.direction = directionFilter
            const [res, proj] = await Promise.all([
                api.bankTransactions.list(params),
                api.projects.list()
            ])
            setData(res)
            setProjects(proj)
        } catch (err) {
            console.error(err)
        } finally {
            setLoading(false)
        }
    }"""
text = text.replace(load_old, load_new)

# ADD BULK HANDLERS
bulk_handlers_old = """    const handleUnmatch = async (id) => {"""
bulk_handlers_new = """    const toggleSelect = (id) => {
        setSelectedIds(prev =>
            prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
        )
    }

    const toggleSelectAll = () => {
        if (selectedIds.length >= data.length) setSelectedIds([])
        else setSelectedIds(data.map(i => i.id))
    }

    const handleBulkAssign = async () => {
        if (selectedIds.length === 0) return
        const pid = assignProjectId === '' || assignProjectId === '_none' ? null : parseInt(assignProjectId, 10)
        try {
            await api.bankTransactions.bulkAssignProject({ ids: selectedIds, project_id: pid })
            setModalAssign(false)
            setAssignProjectId('')
            setSelectedIds([])
            loadData()
        } catch (err) {
            console.error(err)
        }
    }

    const handleUnmatch = async (id) => {"""
text = text.replace(bulk_handlers_old, bulk_handlers_new)

# ADD CHECKBOXES TO TABLE HEAD
th_old = """                                    <th>{tr('date')}</th>"""
th_new = """                                    <th style={{ width: '40px', textAlign: 'center' }}>
                                        <input
                                            type="checkbox"
                                            checked={data.length > 0 && selectedIds.length === data.length}
                                            onChange={toggleSelectAll}
                                        />
                                    </th>
                                    <th>{tr('date')}</th>"""
text = text.replace(th_old, th_new)

# ADD CHECKBOXES TO TABLE BODY
td_old = """                                    <td style={{ whiteSpace: 'nowrap' }}>{tx.date}</td>"""
td_new = """                                    <td style={{ textAlign: 'center' }}>
                                        <input
                                            type="checkbox"
                                            checked={selectedIds.includes(tx.id)}
                                            onChange={() => toggleSelect(tx.id)}
                                        />
                                    </td>
                                    <td style={{ whiteSpace: 'nowrap' }}>{tx.date}</td>"""
text = text.replace(td_old, td_new)


# ADD PROJECT INFO TO TABLE BODY
cat_old = """                                        <div style={{ fontSize: '0.85em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={tx.purpose}>"""
cat_new = """                                        {tx.project_id && (
                                            <span style={{ display: 'inline-block', fontSize: '0.75rem', padding: '0.1rem 0.4rem', background: 'var(--color-surface-hover)', borderRadius: '4px', marginBottom: '0.25rem', color: 'var(--color-text-muted)' }} title={projects.find(p => p.id === tx.project_id)?.name || ''}>
                                                {projects.find(p => p.id === tx.project_id)?.code || '—'}
                                            </span>
                                        )}
                                        <div style={{ fontSize: '0.85em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={tx.purpose}>"""
text = text.replace(cat_old, cat_new)


# ADD ASSIGN BUTTON
btn_old = """                    <select
                        value={directionFilter}"""
btn_new = """                    {selectedIds.length > 0 && (
                        <button className="btn btn-primary btn-sm" onClick={() => setModalAssign(true)}>
                            {tr('assignProject')} ({selectedIds.length})
                        </button>
                    )}
                    <select
                        value={directionFilter}"""
text = text.replace(btn_old, btn_new)


# ADD MODAL BELOW MATCH MODAL
modal_old = """        </>
    )
}"""
modal_new = """
            <Modal isOpen={modalAssign} onClose={() => setModalAssign(false)} title={tr('assignProject')}>
                <div className="form-group">
                    <label className="form-label">{tr('projectLabel')}</label>
                    <select
                        className="form-input"
                        value={assignProjectId}
                        onChange={(e) => setAssignProjectId(e.target.value)}
                    >
                        <option value="">-- {tr('notSelected')} --</option>
                        <option value="_none">[{tr('removeProject')}]</option>
                        {projects.filter(p => p.is_active).map(p => (
                            <option key={p.id} value={p.id}>{p.code} - {p.name}</option>
                        ))}
                    </select>
                </div>
                <div className="modal-actions">
                    <button className="btn btn-secondary" onClick={() => setModalAssign(false)}>{tr('cancel')}</button>
                    <button className="btn btn-primary" onClick={handleBulkAssign}>{tr('save')}</button>
                </div>
            </Modal>
        </>
    )
}"""
text = text.replace(modal_old, modal_new)


with open(path, "w", encoding="utf-8") as f:
    f.write(text)
print("Updated BankTransactions.jsx")
