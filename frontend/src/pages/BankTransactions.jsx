import { useState, useEffect, useMemo } from 'react'
import { api } from '../api'
import { tr } from '../i18n'
import Modal from '../components/Modal'

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

export default function BankTransactions() {
    const [data, setData] = useState([])
    const [loading, setLoading] = useState(true)

    // Filters
    const [year, setYear] = useState(new Date().getFullYear())
    const [month, setMonth] = useState('')
    const [statusFilter, setStatusFilter] = useState('all')
    const [directionFilter, setDirectionFilter] = useState('all')
    const [search, setSearch] = useState('')

    // Sort
    const [sortCol, setSortCol] = useState('date')
    const [sortAsc, setSortAsc] = useState(false)

    // Matching Modal State
    const [matchTx, setMatchTx] = useState(null)
    const [suggestions, setSuggestions] = useState([])
    const [suggestLoading, setSuggestLoading] = useState(false)
    const [matchError, setMatchError] = useState('')

    // Projects State
    const [projects, setProjects] = useState([])
    const [selectedIds, setSelectedIds] = useState([])
    const [modalAssign, setModalAssign] = useState(false)
    const [assignProjectId, setAssignProjectId] = useState('')

    const loadData = async () => {
        setLoading(true)
        try {
            const params = { year }
            if (month) params.month = month
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
    }

    useEffect(() => { loadData() }, [statusFilter, directionFilter, year, month])

    // Filtered + sorted rows
    const displayed = useMemo(() => {
        const s = search.trim().toLowerCase()
        let rows = data
        if (s) {
            rows = data.filter(tx =>
                (tx.date || '').toLowerCase().includes(s) ||
                (tx.counterparty_name || '').toLowerCase().includes(s) ||
                (tx.purpose || '').toLowerCase().includes(s) ||
                String(tx.amount || '').includes(s) ||
                (tx.status || '').toLowerCase().includes(s) ||
                (projects.find(p => p.id === tx.project_id)?.name || '').toLowerCase().includes(s)
            )
        }
        rows = [...rows].sort((a, b) => {
            let valA = a[sortCol]
            let valB = b[sortCol]
            if (sortCol === 'project_id') {
                valA = projects.find(p => p.id === a.project_id)?.name || ''
                valB = projects.find(p => p.id === b.project_id)?.name || ''
            }
            if (valA == null) valA = ''
            if (valB == null) valB = ''
            if (valA < valB) return sortAsc ? -1 : 1
            if (valA > valB) return sortAsc ? 1 : -1
            return 0
        })
        return rows
    }, [data, search, sortCol, sortAsc, projects])

    const toggleSort = (col) => {
        if (sortCol === col) setSortAsc(!sortAsc)
        else { setSortCol(col); setSortAsc(true) }
    }

    const SortIcon = ({ col }) => {
        if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 4 }}>↕</span>
        return <span style={{ marginLeft: 4 }}>{sortAsc ? '↑' : '↓'}</span>
    }

    const handleUpdateStatus = async (id, newStatus) => {
        try {
            await api.bankTransactions.update(id, { status: newStatus })
            loadData()
        } catch (e) { console.error(e) }
    }

    const toggleSelect = (id) => {
        setSelectedIds(prev =>
            prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
        )
    }

    const toggleSelectAll = () => {
        if (selectedIds.length >= displayed.length) setSelectedIds([])
        else setSelectedIds(displayed.map(i => i.id))
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
        } catch (err) { console.error(err) }
    }

    const handleUnmatch = async (id) => {
        if (!confirm(tr('deleteIncome') + ' (Unmatch)')) return
        try {
            await api.bankTransactions.unmatch(id)
            loadData()
        } catch (e) { console.error(e) }
    }

    const openMatchModal = async (tx) => {
        setMatchTx(tx)
        setMatchError('')
        setSuggestions([])
        setSuggestLoading(true)
        try {
            const res = await api.bankTransactions.suggest(tx.id)
            setSuggestions(res)
        } catch (e) {
            setMatchError(e.message)
        } finally {
            setSuggestLoading(false)
        }
    }

    const performMatch = async (targetId, targetType) => {
        try {
            await api.bankTransactions.match(matchTx.id, { type: targetType, id: targetId })
            setMatchTx(null)
            loadData()
        } catch (e) { setMatchError(e.message) }
    }

    const currentYear = new Date().getFullYear()
    const years = Array.from({ length: 5 }, (_, i) => currentYear - i)

    return (
        <>
            <div className="page-header">
                <h1>{tr('bankTransactions')}</h1>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                    {/* Year selector */}
                    <select value={year} onChange={e => { setYear(Number(e.target.value)); setMonth('') }} className="input">
                        {years.map(y => <option key={y} value={y}>{y}</option>)}
                    </select>

                    {/* Month selector */}
                    <select value={month} onChange={e => setMonth(e.target.value)} className="input">
                        <option value="">{tr('allMonths') || 'Все месяцы'}</option>
                        {MONTHS.map(m => <option key={m} value={m}>{m.toString().padStart(2, '0')}</option>)}
                    </select>

                    {/* Status filter */}
                    <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="input">
                        <option value="all">{tr('bankTxAll')}</option>
                        <option value="unmatched">{tr('bankTxUnmatched')}</option>
                        <option value="matched">{tr('bankTxMatched')}</option>
                        <option value="ignored">{tr('bankTxIgnored')}</option>
                    </select>

                    {/* Direction filter */}
                    <select value={directionFilter} onChange={e => setDirectionFilter(e.target.value)} className="input">
                        <option value="all">{tr('bankTxAll')} ↕</option>
                        <option value="in">{tr('bankTxDirectionIn')} ↑</option>
                        <option value="out">{tr('bankTxDirectionOut')} ↓</option>
                    </select>

                    {/* Search */}
                    <input
                        className="input"
                        placeholder={tr('search') || 'Поиск...'}
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        style={{ minWidth: '160px' }}
                    />

                    {selectedIds.length > 0 && (
                        <button className="btn btn-primary btn-sm" onClick={() => setModalAssign(true)}>
                            {tr('assignProject')} ({selectedIds.length})
                        </button>
                    )}
                </div>
            </div>

            <div className="page-body">
                {loading ? <p>{tr('loading')}</p> : (
                    <div className="card" style={{ padding: 0, overflowX: 'auto', marginBottom: '1rem' }}>
                        <table className="table">
                            <thead>
                                <tr>
                                    <th style={{ width: '40px', textAlign: 'center' }}>
                                        <input
                                            type="checkbox"
                                            checked={displayed.length > 0 && selectedIds.length === displayed.length}
                                            onChange={toggleSelectAll}
                                        />
                                    </th>
                                    <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('date')}>{tr('date')} <SortIcon col="date" /></th>
                                    <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('counterparty_name')}>{tr('bankTxCounterparty')} <SortIcon col="counterparty_name" /></th>
                                    <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('purpose')}>{tr('bankTxPurpose')} / {tr('bankTxReference')} <SortIcon col="purpose" /></th>
                                    <th style={{ textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleSort('amount')}>{tr('amount')} <SortIcon col="amount" /></th>
                                    <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('project_id')}>{tr('project')} <SortIcon col="project_id" /></th>
                                    <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('status')}>{tr('filterStatus')} <SortIcon col="status" /></th>
                                    <th style={{ textAlign: 'right' }}>{tr('actions')}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {displayed.map(tx => (
                                    <tr key={tx.id}>
                                        <td style={{ textAlign: 'center' }}>
                                            <input
                                                type="checkbox"
                                                checked={selectedIds.includes(tx.id)}
                                                onChange={() => toggleSelect(tx.id)}
                                            />
                                        </td>
                                        <td style={{ whiteSpace: 'nowrap' }}>{tx.date}</td>
                                        <td>{tx.counterparty_name}</td>
                                        <td style={{ maxWidth: '300px' }}>
                                            {tx.project_id && (
                                                <span style={{ display: 'inline-block', fontSize: '0.75rem', padding: '0.1rem 0.4rem', background: 'var(--color-surface-hover)', borderRadius: '4px', marginBottom: '0.25rem', color: 'var(--color-text-muted)' }} title={projects.find(p => p.id === tx.project_id)?.code || ''}>
                                                    {projects.find(p => p.id === tx.project_id)?.name || '—'}
                                                </span>
                                            )}
                                            <div style={{ fontSize: '0.85em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={tx.purpose}>
                                                {tx.purpose}
                                            </div>
                                            {tx.bank_reference && (
                                                <div style={{ fontSize: '0.75em', color: 'gray' }}>Ref: {tx.bank_reference}</div>
                                            )}
                                        </td>
                                        <td style={{ textAlign: 'right', fontWeight: 'bold', color: tx.direction === 'in' ? 'green' : 'inherit' }}>
                                            {tx.direction === 'in' ? '+' : '-'}{tx.amount.toLocaleString('ru-RU', { style: 'currency', currency: tx.currency })}
                                        </td>
                                        <td style={{ fontSize: '0.85em', color: 'var(--color-text-muted)' }}>
                                            {tx.project_id ? (
                                                <span title={projects.find(p => p.id === tx.project_id)?.code || ''}>
                                                    {projects.find(p => p.id === tx.project_id)?.name || '—'}
                                                </span>
                                            ) : '—'}
                                        </td>
                                        <td>
                                            {tx.status === 'unmatched' && <span className="badge badge-warning">{tr('bankTxUnmatched')}</span>}
                                            {tx.status === 'matched' && <span className="badge badge-success">{tr('bankTxMatched')} ({tx.matched_type})</span>}
                                            {tx.status === 'ignored' && <span className="badge badge-secondary">{tr('bankTxIgnored')}</span>}
                                        </td>
                                        <td style={{ textAlign: 'right' }}>
                                            {tx.status === 'unmatched' && (
                                                <div style={{ display: 'flex', gap: '0.25rem', justifyContent: 'flex-end' }}>
                                                    <button className="btn btn-sm btn-primary" onClick={() => openMatchModal(tx)}>
                                                        {tr('bankTxMatchBtn')}
                                                    </button>
                                                    <button className="btn btn-sm btn-secondary" onClick={() => handleUpdateStatus(tx.id, 'ignored')}>
                                                        {tr('bankTxIgnore')}
                                                    </button>
                                                </div>
                                            )}
                                            {tx.status === 'ignored' && (
                                                <button className="btn btn-sm btn-secondary" onClick={() => handleUpdateStatus(tx.id, 'unmatched')}>
                                                    Восстановить
                                                </button>
                                            )}
                                            {tx.status === 'matched' && (
                                                <button className="btn btn-sm btn-danger" onClick={() => handleUnmatch(tx.id)}>
                                                    {tr('bankTxUnmatchBtn')}
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                                {displayed.length === 0 && (
                                    <tr>
                                        <td colSpan="8" style={{ textAlign: 'center', padding: '2rem' }}>{tr('noData')}</td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                )}

                <div style={{ padding: '0.5rem 0', color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
                    {!loading && `${tr('total') || 'Итого'}: ${displayed.length} ${tr('records') || 'записей'}`}
                </div>
            </div>

            {/* MATCH MODAL */}
            <Modal isOpen={!!matchTx} onClose={() => setMatchTx(null)} title={tr('bankTxMatchTitle')}>
                {matchTx && (
                    <div>
                        <div style={{ marginBottom: '1rem', padding: '1rem', background: 'var(--color-surface-hover)', borderRadius: '8px', border: '1px solid var(--color-border)' }}>
                            <strong>{matchTx.counterparty_name}</strong><br />
                            <span style={{ color: 'var(--color-text-muted)' }}>{matchTx.purpose}</span><br />
                            <span style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
                                {matchTx.direction === 'in' ? '+' : '-'}{matchTx.amount.toLocaleString()} {matchTx.currency}
                            </span>
                        </div>

                        {suggestLoading ? <p>{tr('loading')}</p> : (
                            <div>
                                <h5>{tr('bankTxScore')} (Top 5)</h5>
                                {suggestions.length === 0 ? <p>{tr('noData')}</p> : (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                        {suggestions.map((s, idx) => (
                                            <div key={idx} className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem' }}>
                                                <div style={{ paddingRight: '1rem' }}>
                                                    <strong>{s.type === 'income' ? tr('incomeLabel') : s.type === 'expense' ? tr('expenseLabel') : 'Obligation'} #{s.id}</strong>
                                                    <div style={{ fontSize: '0.9em', color: 'var(--color-text-muted)', margin: '0.25rem 0' }}>{s.description}</div>
                                                    <div style={{ fontSize: '0.85em', fontWeight: 'bold' }}>
                                                        {s.amount ? Number(s.amount).toLocaleString('ru-RU', { style: 'currency', currency: 'RSD' }) : ''} • {s.date}
                                                    </div>
                                                    {s.score !== undefined && (
                                                        <div style={{ fontSize: '0.8rem', color: s.score >= 80 ? 'var(--color-success)' : 'var(--color-warning)', marginTop: '0.25rem' }}>
                                                            {tr('bankTxScore')}: {s.score}%
                                                        </div>
                                                    )}
                                                </div>
                                                <button className="btn btn-sm btn-primary" onClick={() => performMatch(s.id, s.type)}>
                                                    {tr('bankTxMatchBtn')}
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                        {matchError && <div style={{ color: 'red', marginTop: '1rem' }}>{matchError}</div>}
                    </div>
                )}
            </Modal>

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
                            <option key={p.id} value={p.id}>{p.name}{p.code ? ` — ${p.code}` : ''}</option>
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
}
