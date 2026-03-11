import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { getLang, tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import Modal from '../components/Modal'
import ProjectSelect from '../components/ProjectSelect'

const UI_DASH = '\u2014'

function fmtAmount(value) {
  return Number(value || 0).toLocaleString('sr-RS')
}

function buildContractLabel(contract) {
  if (!contract) return ''
  const parts = []
  if (contract.number) parts.push(contract.number)
  if (contract.subject) parts.push(contract.subject)
  return parts.join(` ${UI_DASH} `) || contract.number || contract.subject || ''
}

function buildBankLabel(item) {
  const parts = [item.counterparty_name, item.purpose, item.bank_reference].filter(Boolean)
  return parts.join(` ${UI_DASH} `) || UI_DASH
}

function isSalaryCategory(category) {
  const sr = String(category?.name_sr || '').trim().toLowerCase()
  const ru = String(category?.name_ru || '').trim().toLowerCase()
  return sr === 'zarade' || sr.includes('zarad') || ru.includes('зарп')
}

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

export default function CashRegister() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [pageError, setPageError] = useState('')
  const [summary, setSummary] = useState({ current_balance: 0, total_in: 0, total_out: 0, entries: [], available_withdrawals: [] })
  const [projects, setProjects] = useState([])
  const [contracts, setContracts] = useState([])
  const [categories, setCategories] = useState([])
  const [bankModalOpen, setBankModalOpen] = useState(false)
  const [expenseModal, setExpenseModal] = useState(null)
  const [adjustmentModal, setAdjustmentModal] = useState(null)
  const [withdrawalModal, setWithdrawalModal] = useState(null)
  const [expenseForm, setExpenseForm] = useState({
    date: todayIso(),
    description: '',
    amount: '',
    category_id: '',
    project_id: '',
    contract_id: '',
    note: '',
  })
  const [adjustmentForm, setAdjustmentForm] = useState({
    date: todayIso(),
    direction: 'out',
    amount: '',
    description: '',
    note: '',
  })
  const [withdrawalForm, setWithdrawalForm] = useState({
    description: '',
    project_id: '',
    contract_id: '',
    note: '',
  })

  const lang = getLang()
  const unassignedProject = projects.find((project) => project.code === 'INT-UNASSIGNED') || null
  const salaryProject = projects.find((project) => project.code === 'INT-SALARY') || null

  const loadData = () => {
    setLoading(true)
    setPageError('')
    return Promise.all([
      api.cash.summary(),
      api.projects.list({ show_archived: true }),
      api.categories.list({ category_type: 'expense' }),
      api.contracts.list({ limit: 500 }),
    ])
      .then(([cashSummary, projectList, categoryList, contractList]) => {
        setSummary(cashSummary)
        setProjects(projectList)
        setCategories(categoryList)
        setContracts(contractList)
      })
      .catch((error) => {
        setPageError(error.message || tr('loadError'))
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadData()
  }, [])

  const getCategoryLabel = (categoryId) => {
    const selectedCategory = categories.find((item) => item.id === categoryId)
    if (!selectedCategory) return UI_DASH
    return lang === 'ru' ? selectedCategory.name_ru : selectedCategory.name_sr
  }

  const getContractsForProject = (projectId) => contracts
    .filter((contract) => contract.project_id === projectId || contract.project_id == null)
    .sort((left, right) => {
      const leftRank = left.project_id === projectId ? 0 : 1
      const rightRank = right.project_id === projectId ? 0 : 1
      if (leftRank !== rightRank) return leftRank - rightRank
      return buildContractLabel(left).localeCompare(buildContractLabel(right), 'sr')
    })

  const expenseContracts = useMemo(() => {
    const selectedProjectId = expenseForm.project_id ? parseInt(expenseForm.project_id, 10) : null
    return selectedProjectId ? getContractsForProject(selectedProjectId) : []
  }, [contracts, expenseForm.project_id])

  const selectedExpenseCategory = useMemo(
    () => categories.find((item) => String(item.id) === String(expenseForm.category_id)) || null,
    [categories, expenseForm.category_id]
  )
  const expenseUsesSalaryProject = isSalaryCategory(selectedExpenseCategory) && !!salaryProject

  useEffect(() => {
    if (!expenseUsesSalaryProject) return
    const salaryProjectId = String(salaryProject.id)
    if (String(expenseForm.project_id || '') === salaryProjectId && !expenseForm.contract_id) return
    setExpenseForm((previous) => ({
      ...previous,
      project_id: salaryProjectId,
      contract_id: '',
    }))
  }, [expenseUsesSalaryProject, salaryProject, expenseForm.project_id, expenseForm.contract_id])

  const withdrawalContracts = useMemo(() => {
    const selectedProjectId = withdrawalForm.project_id ? parseInt(withdrawalForm.project_id, 10) : null
    return selectedProjectId ? getContractsForProject(selectedProjectId) : []
  }, [contracts, withdrawalForm.project_id])

  const openExpenseCreate = () => {
    setExpenseForm({
      date: todayIso(),
      description: '',
      amount: '',
      category_id: '',
      project_id: unassignedProject ? String(unassignedProject.id) : '',
      contract_id: '',
      note: '',
    })
    setExpenseModal({ entryId: null })
  }

  const openExpenseEdit = (entry) => {
    setExpenseForm({
      date: entry.date,
      description: entry.description || '',
      amount: entry.amount || '',
      category_id: entry.category_id ?? '',
      project_id: entry.project_id ?? (unassignedProject ? String(unassignedProject.id) : ''),
      contract_id: entry.contract_id ?? '',
      note: entry.note || '',
    })
    setExpenseModal({ entryId: entry.id })
  }

  const openAdjustmentCreate = () => {
    setAdjustmentForm({
      date: todayIso(),
      direction: summary.current_balance > 0 ? 'out' : 'in',
      amount: '',
      description: '',
      note: '',
    })
    setAdjustmentModal({ entryId: null })
  }

  const openAdjustmentEdit = (entry) => {
    setAdjustmentForm({
      date: entry.date,
      direction: entry.direction || 'out',
      amount: entry.amount || '',
      description: entry.description || '',
      note: entry.note || '',
    })
    setAdjustmentModal({ entryId: entry.id })
  }

  const openWithdrawalEdit = (entry) => {
    setWithdrawalForm({
      description: entry.description || '',
      project_id: entry.project_id ?? (unassignedProject ? String(unassignedProject.id) : ''),
      contract_id: entry.contract_id ?? '',
      note: entry.note || '',
    })
    setWithdrawalModal({ entryId: entry.id })
  }

  const updateExpenseProject = (projectId) => {
    setExpenseForm((previous) => {
      const selectedContract = previous.contract_id ? contracts.find((contract) => String(contract.id) === String(previous.contract_id)) : null
      const keepContract = selectedContract && String(selectedContract.project_id) === String(projectId)
      return {
        ...previous,
        project_id: projectId,
        contract_id: keepContract ? previous.contract_id : '',
      }
    })
  }

  const updateExpenseContract = (contractId) => {
    setExpenseForm((previous) => {
      if (!contractId) return { ...previous, contract_id: '' }
      const selectedContract = contracts.find((contract) => String(contract.id) === String(contractId))
      return {
        ...previous,
        contract_id: contractId,
        project_id: selectedContract?.project_id ? String(selectedContract.project_id) : previous.project_id,
      }
    })
  }

  const updateExpenseCategory = (categoryId) => {
    setExpenseForm((previous) => {
      const selectedCategory = categories.find((item) => String(item.id) === String(categoryId)) || null
      if (isSalaryCategory(selectedCategory) && salaryProject) {
        return {
          ...previous,
          category_id: categoryId,
          project_id: String(salaryProject.id),
          contract_id: '',
        }
      }
      return {
        ...previous,
        category_id: categoryId,
      }
    })
  }

  const updateWithdrawalProject = (projectId) => {
    setWithdrawalForm((previous) => {
      const selectedContract = previous.contract_id ? contracts.find((contract) => String(contract.id) === String(previous.contract_id)) : null
      const keepContract = selectedContract && String(selectedContract.project_id) === String(projectId)
      return {
        ...previous,
        project_id: projectId,
        contract_id: keepContract ? previous.contract_id : '',
      }
    })
  }

  const updateWithdrawalContract = (contractId) => {
    setWithdrawalForm((previous) => {
      if (!contractId) return { ...previous, contract_id: '' }
      const selectedContract = contracts.find((contract) => String(contract.id) === String(contractId))
      return {
        ...previous,
        contract_id: contractId,
        project_id: selectedContract?.project_id ? String(selectedContract.project_id) : previous.project_id,
      }
    })
  }

  const handleTransferToCash = async (transaction) => {
    setSaving(true)
    setPageError('')
    try {
      await api.cash.createWithdrawal({ bank_transaction_id: transaction.id })
      setBankModalOpen(false)
      await loadData()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveExpense = async (event) => {
    event.preventDefault()
    setSaving(true)
    setPageError('')
    try {
      const payload = {
        date: expenseForm.date,
        description: expenseForm.description.trim(),
        amount: parseFloat(expenseForm.amount) || 0,
        category_id: expenseForm.category_id ? parseInt(expenseForm.category_id, 10) : null,
        project_id: expenseForm.project_id ? parseInt(expenseForm.project_id, 10) : (unassignedProject ? unassignedProject.id : null),
        contract_id: expenseForm.contract_id ? parseInt(expenseForm.contract_id, 10) : null,
        note: expenseForm.note?.trim() || null,
      }
      if (expenseModal?.entryId) {
        await api.cash.updateEntry(expenseModal.entryId, payload)
      } else {
        await api.cash.createExpense(payload)
      }
      setExpenseModal(null)
      await loadData()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveAdjustment = async (event) => {
    event.preventDefault()
    setSaving(true)
    setPageError('')
    try {
      const payload = {
        date: adjustmentForm.date,
        direction: adjustmentForm.direction,
        amount: parseFloat(adjustmentForm.amount) || 0,
        description: adjustmentForm.description.trim(),
        note: adjustmentForm.note?.trim() || null,
      }
      if (adjustmentModal?.entryId) {
        await api.cash.updateEntry(adjustmentModal.entryId, payload)
      } else {
        await api.cash.createAdjustment(payload)
      }
      setAdjustmentModal(null)
      await loadData()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveWithdrawal = async (event) => {
    event.preventDefault()
    if (!withdrawalModal?.entryId) return
    setSaving(true)
    setPageError('')
    try {
      await api.cash.updateEntry(withdrawalModal.entryId, {
        description: withdrawalForm.description.trim(),
        project_id: withdrawalForm.project_id ? parseInt(withdrawalForm.project_id, 10) : (unassignedProject ? unassignedProject.id : null),
        contract_id: withdrawalForm.contract_id ? parseInt(withdrawalForm.contract_id, 10) : null,
        note: withdrawalForm.note?.trim() || null,
      })
      setWithdrawalModal(null)
      await loadData()
    } catch (error) {
      setPageError(error.message || tr('loadError'))
    } finally {
      setSaving(false)
    }
  }

  const openEditEntry = (entry) => {
    if (entry.entry_type === 'expense') {
      openExpenseEdit(entry)
      return
    }
    if (entry.entry_type === 'adjustment') {
      openAdjustmentEdit(entry)
      return
    }
    openWithdrawalEdit(entry)
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">{tr('cashRegisterTitle')}</h1>
          <div style={{ color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
            {tr('cashRegisterHint')}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button className="btn btn-secondary" onClick={() => setBankModalOpen(true)}>{tr('cashAddFromBank')}</button>
          <button className="btn btn-secondary" onClick={openAdjustmentCreate}>{tr('cashAddAdjustment')}</button>
          <button className="btn btn-primary" onClick={openExpenseCreate}>{tr('cashAddExpense')}</button>
        </div>
      </div>

      <div className="page-body">
        {pageError ? (
          <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
            {pageError}
          </div>
        ) : null}

        {loading ? (
          <div>{tr('loading')}</div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
              <div className="card">
                <div className="card-title">{tr('cashCurrentBalance')}</div>
                <div style={{ fontSize: '1.75rem', fontWeight: 700 }}>{fmtAmount(summary.current_balance)} RSD</div>
              </div>
              <div className="card">
                <div className="card-title">{tr('cashTotalIn')}</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-success)' }}>+{fmtAmount(summary.total_in)} RSD</div>
              </div>
              <div className="card">
                <div className="card-title">{tr('cashTotalOut')}</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-danger)' }}>-{fmtAmount(summary.total_out)} RSD</div>
              </div>
            </div>

            <div className="card">
              <div className="card-title">{tr('cashEntries')}</div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>{tr('date')}</th>
                      <th>{tr('cashEntryType')}</th>
                      <th>{tr('description')}</th>
                      <th>{tr('cashSource')}</th>
                      <th style={{ textAlign: 'right' }}>{tr('cashflowInflow')}</th>
                      <th style={{ textAlign: 'right' }}>{tr('cashflowOutflow')}</th>
                      <th style={{ textAlign: 'right' }}>{tr('cashBalanceAfter')}</th>
                      <th style={{ textAlign: 'right' }}>{tr('cashActions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.entries.length === 0 ? (
                      <tr>
                        <td colSpan={8} style={{ color: 'var(--color-text-muted)' }}>{tr('cashNoEntries')}</td>
                      </tr>
                    ) : summary.entries.map((entry) => {
                      const typeLabel = entry.entry_type === 'withdrawal'
                        ? tr('cashEntryTypeWithdrawal')
                        : entry.entry_type === 'expense'
                          ? tr('cashEntryTypeExpense')
                          : tr('cashEntryTypeAdjustment')
                      const sourceLabel = entry.bank_transaction_id
                        ? `${tr('cashSourceBank')}: ${entry.bank_reference || entry.counterparty_name || `#${entry.bank_transaction_id}`}`
                        : entry.expense_id
                          ? `${tr('cashSourceExpense')}: #${entry.expense_id}`
                          : UI_DASH
                      return (
                        <tr key={entry.id}>
                          <td>{entry.date}</td>
                          <td>{typeLabel}</td>
                          <td>
                            <div>{entry.description}</div>
                            {entry.note ? (
                              <div style={{ color: 'var(--color-text-muted)', fontSize: '0.8rem', marginTop: '0.2rem' }}>{entry.note}</div>
                            ) : null}
                          </td>
                          <td>{sourceLabel}</td>
                          <td style={{ textAlign: 'right', color: 'var(--color-success)' }}>
                            {entry.direction === 'in' ? `${fmtAmount(entry.amount)} ${entry.currency || 'RSD'}` : UI_DASH}
                          </td>
                          <td style={{ textAlign: 'right', color: 'var(--color-danger)' }}>
                            {entry.direction === 'out' ? `${fmtAmount(entry.amount)} ${entry.currency || 'RSD'}` : UI_DASH}
                          </td>
                          <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmtAmount(entry.balance_after)} RSD</td>
                          <td style={{ textAlign: 'right' }}>
                            <button className="btn btn-sm btn-secondary" disabled={saving} onClick={() => openEditEntry(entry)}>{tr('edit')}</button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>

      <Modal isOpen={bankModalOpen} onClose={() => setBankModalOpen(false)} title={tr('cashAddFromBank')}>
        <div className="card" style={{ padding: '1rem' }}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('date')}</th>
                  <th>{tr('description')}</th>
                  <th style={{ textAlign: 'right' }}>{tr('amount')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {summary.available_withdrawals.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ color: 'var(--color-text-muted)' }}>{tr('cashNoAvailableWithdrawals')}</td>
                  </tr>
                ) : summary.available_withdrawals.map((transaction) => (
                  <tr key={transaction.id}>
                    <td>{transaction.date}</td>
                    <td>
                      <div>{buildBankLabel(transaction)}</div>
                      {transaction.project_id ? (
                        <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                          {projects.find((project) => project.id === transaction.project_id)?.name || UI_DASH}
                        </div>
                      ) : null}
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmtAmount(transaction.amount)} {transaction.currency || 'RSD'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn btn-sm btn-primary" disabled={saving} onClick={() => handleTransferToCash(transaction)}>
                        {tr('cashTransferToCash')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Modal>

      <Modal isOpen={!!expenseModal} onClose={() => setExpenseModal(null)} title={expenseModal?.entryId ? tr('cashEditOperation') : tr('cashAddExpense')}>
        <form onSubmit={handleSaveExpense} className="card" style={{ padding: '1rem' }}>
          <div style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '0.75rem' }}>
            {tr('cashCreateExpenseHint')}
          </div>
          <div className="form-group">
            <label className="form-label">{tr('date')}</label>
            <DatePicker value={expenseForm.date} onChange={(value) => setExpenseForm((previous) => ({ ...previous, date: value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('description')}</label>
            <input className="form-input" value={expenseForm.description} onChange={(event) => setExpenseForm((previous) => ({ ...previous, description: event.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('amount')}</label>
            <input className="form-input" type="number" min="0" step="0.01" value={expenseForm.amount} onChange={(event) => setExpenseForm((previous) => ({ ...previous, amount: event.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('category')}</label>
            <select className="form-input" value={expenseForm.category_id} onChange={(event) => updateExpenseCategory(event.target.value)}>
              <option value="">{tr('allCategories')}</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>{getCategoryLabel(category.id)}</option>
              ))}
            </select>
          </div>
          {!expenseUsesSalaryProject ? (
            <>
              <div className="form-group">
                <label className="form-label">{tr('project')}</label>
                <ProjectSelect projects={projects} value={expenseForm.project_id} onChange={updateExpenseProject} allowEmpty emptyLabel={UI_DASH} />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('contracts')}</label>
                <select className="form-input" value={expenseForm.contract_id} onChange={(event) => updateExpenseContract(event.target.value)} disabled={!expenseForm.project_id}>
                  <option value="">{UI_DASH}</option>
                  {expenseContracts.map((contract) => (
                    <option key={contract.id} value={contract.id}>{buildContractLabel(contract)}</option>
                  ))}
                </select>
              </div>
            </>
          ) : null}
          <div className="form-group">
            <label className="form-label">{tr('note')}</label>
            <input className="form-input" value={expenseForm.note} onChange={(event) => setExpenseForm((previous) => ({ ...previous, note: event.target.value }))} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setExpenseModal(null)}>{tr('cancel')}</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? tr('loading') : tr('save')}</button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={!!adjustmentModal} onClose={() => setAdjustmentModal(null)} title={adjustmentModal?.entryId ? tr('cashEditOperation') : tr('cashAddAdjustment')}>
        <form onSubmit={handleSaveAdjustment} className="card" style={{ padding: '1rem' }}>
          <div className="form-group">
            <label className="form-label">{tr('date')}</label>
            <DatePicker value={adjustmentForm.date} onChange={(value) => setAdjustmentForm((previous) => ({ ...previous, date: value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('cashDirection')}</label>
            <select className="form-input" value={adjustmentForm.direction} onChange={(event) => setAdjustmentForm((previous) => ({ ...previous, direction: event.target.value }))}>
              <option value="in">{tr('cashDirectionIn')}</option>
              <option value="out">{tr('cashDirectionOut')}</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">{tr('amount')}</label>
            <input className="form-input" type="number" min="0" step="0.01" value={adjustmentForm.amount} onChange={(event) => setAdjustmentForm((previous) => ({ ...previous, amount: event.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('description')}</label>
            <input className="form-input" value={adjustmentForm.description} onChange={(event) => setAdjustmentForm((previous) => ({ ...previous, description: event.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('note')}</label>
            <input className="form-input" value={adjustmentForm.note} onChange={(event) => setAdjustmentForm((previous) => ({ ...previous, note: event.target.value }))} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setAdjustmentModal(null)}>{tr('cancel')}</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? tr('loading') : tr('save')}</button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={!!withdrawalModal} onClose={() => setWithdrawalModal(null)} title={tr('cashEditOperation')}>
        <form onSubmit={handleSaveWithdrawal} className="card" style={{ padding: '1rem' }}>
          <div style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '0.75rem' }}>
            {tr('cashEditWithdrawalHint')}
          </div>
          <div className="form-group">
            <label className="form-label">{tr('description')}</label>
            <input className="form-input" value={withdrawalForm.description} onChange={(event) => setWithdrawalForm((previous) => ({ ...previous, description: event.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('project')}</label>
            <ProjectSelect projects={projects} value={withdrawalForm.project_id} onChange={updateWithdrawalProject} allowEmpty emptyLabel={UI_DASH} />
          </div>
          <div className="form-group">
            <label className="form-label">{tr('contracts')}</label>
            <select className="form-input" value={withdrawalForm.contract_id} onChange={(event) => updateWithdrawalContract(event.target.value)} disabled={!withdrawalForm.project_id}>
              <option value="">{UI_DASH}</option>
              {withdrawalContracts.map((contract) => (
                <option key={contract.id} value={contract.id}>{buildContractLabel(contract)}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">{tr('note')}</label>
            <input className="form-input" value={withdrawalForm.note} onChange={(event) => setWithdrawalForm((previous) => ({ ...previous, note: event.target.value }))} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setWithdrawalModal(null)}>{tr('cancel')}</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? tr('loading') : tr('save')}</button>
          </div>
        </form>
      </Modal>
    </>
  )
}
