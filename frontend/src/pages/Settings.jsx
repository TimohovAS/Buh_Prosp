import { useState, useEffect } from 'react'
import { api, getUser } from '../api'
import { tr, getLang } from '../i18n'
import DatePicker from '../components/DatePicker'

const ROLES = [
  { value: 'admin', label: { sr: 'Администратор', ru: 'Администратор' } },
  { value: 'accountant', label: { sr: 'Бухгалтер', ru: 'Бухгалтер' } },
  { value: 'cashier', label: { sr: 'Благајник', ru: 'Кассир' } },
  { value: 'observer', label: { sr: 'Посматрач', ru: 'Наблюдатель' } },
]

const LANGS = [
  { value: 'sr', label: 'Српски' },
  { value: 'ru', label: 'Русский' },
]

export default function Settings() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(false)
  const currentYear = new Date().getFullYear()
  const [form, setForm] = useState({
    name: '',
    address: '',
    pib: '',
    maticni_broj: '',
    bank_name: '',
    bank_account: '',
    bank_swift: '',
    main_activity_code: '',
    opening_cash_balance: 0,
    opening_cash_date: `${currentYear}-01-01`,
  })

  const currentUser = getUser()
  const isAdmin = currentUser?.role === 'admin'

  const [users, setUsers] = useState([])
  const [showInactive, setShowInactive] = useState(false)
  const [usersLoading, setUsersLoading] = useState(false)
  const [userModal, setUserModal] = useState(null)
  const [userForm, setUserForm] = useState({
    username: '',
    password: '',
    full_name: '',
    role: 'accountant',
    default_language: 'sr',
  })

  const loadUsers = () => {
    if (!isAdmin) return
    setUsersLoading(true)
    api.users.list(showInactive)
      .then(setUsers)
      .catch((err) => alert(err.message))
      .finally(() => setUsersLoading(false))
  }

  useEffect(loadUsers, [showInactive, isAdmin])

  const openAddUser = () => {
    setUserForm({ username: '', password: '', full_name: '', role: 'accountant', default_language: 'sr' })
    setUserModal('add')
  }

  const openEditUser = (item) => {
    setUserForm({
      username: item.username,
      password: '',
      full_name: item.full_name || '',
      role: item.role || 'accountant',
      default_language: item.default_language || 'sr',
    })
    setUserModal({ type: 'edit', id: item.id })
  }

  const handleUserSubmit = async (e) => {
    e.preventDefault()
    try {
      if (userModal === 'add') {
        await api.users.create(userForm)
      } else {
        const payload = { full_name: userForm.full_name, role: userForm.role, default_language: userForm.default_language }
        if (userForm.password) payload.password = userForm.password
        await api.users.update(userModal.id, payload)
      }
      setUserModal(null)
      loadUsers()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDeactivate = async (id) => {
    if (id === currentUser?.id) { alert(tr('cannotDeactivateSelf')); return }
    if (!confirm(tr('confirmDeactivateUser'))) return
    try {
      await api.users.deactivate(id)
      loadUsers()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleActivate = async (id) => {
    try {
      await api.users.update(id, { is_active: true })
      loadUsers()
    } catch (err) {
      alert(err.message)
    }
  }

  const roleLabel = (r) => ROLES.find((x) => x.value === r)?.label?.[getLang()] || r

  useEffect(() => {
    api.enterprise.get().then((r) => {
      setData(r)
      if (r) {
        const defaultDate = `${new Date().getFullYear()}-01-01`
        setForm({
          name: r.name || '',
          address: r.address || '',
          pib: r.pib || '',
          maticni_broj: r.maticni_broj || '',
          bank_name: r.bank_name || '',
          bank_account: r.bank_account || '',
          bank_swift: r.bank_swift || '',
          main_activity_code: r.main_activity_code || '',
          opening_cash_balance: r.opening_cash_balance ?? 0,
          opening_cash_date: r.opening_cash_date || defaultDate,
        })
      }
    }).finally(() => setLoading(false))
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      await api.enterprise.update(form)
      setData({ ...data, ...form })
      setModal(false)
    } catch (err) {
      alert(err.message)
    }
  }

  if (loading) return <div>Загрузка...</div>

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{tr('settings')}</h1>
        <button className="btn btn-primary" onClick={() => setModal(true)}>
          {tr('enterprise')}
        </button>
      </div>

      <div className="page-body">
      <div className="card">
        <div className="card-title">{tr('enterpriseData')}</div>
        {data ? (
          <div>
            <p><strong>{tr('name')}:</strong> {data.name}</p>
            <p><strong>{tr('address')}:</strong> {data.address || '-'}</p>
            <p><strong>{tr('pib')}:</strong> {data.pib || '-'}</p>
            <p><strong>{tr('maticniBroj')}:</strong> {data.maticni_broj || '-'}</p>
            <p><strong>{tr('bankName')}:</strong> {data.bank_name || '-'}</p>
            <p><strong>{tr('bankAccount')}:</strong> {data.bank_account || '-'}</p>
          </div>
        ) : (
          <p style={{ color: 'var(--color-text-muted)' }}>{tr('fillEnterpriseData')}</p>
        )}
      </div>

      {isAdmin && (
        <div className="card">
          <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
            <span>{tr('users')}</span>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
                <span>{tr('showInactive')}</span>
              </label>
              <button className="btn btn-primary btn-sm" onClick={openAddUser}>{tr('add')}</button>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('username')}</th>
                  <th>{tr('fullName')}</th>
                  <th>{tr('role')}</th>
                  <th>{tr('language')}</th>
                  <th>{tr('status')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {usersLoading ? (
                  <tr><td colSpan={6}>{tr('loading')}</td></tr>
                ) : users.length === 0 ? (
                  <tr><td colSpan={6} style={{ color: 'var(--color-text-muted)' }}>{tr('noUsers')}</td></tr>
                ) : (
                  users.map((u) => (
                    <tr key={u.id} style={!u.is_active ? { opacity: 0.6 } : {}}>
                      <td>{u.username}</td>
                      <td>{u.full_name || '-'}</td>
                      <td>{roleLabel(u.role)}</td>
                      <td>{u.default_language === 'ru' ? 'RU' : 'SR'}</td>
                      <td>{u.is_active ? tr('active') : tr('inactive')}</td>
                      <td>
                        <button className="btn btn-sm btn-secondary" onClick={() => openEditUser(u)}>{tr('edit')}</button>
                        {u.is_active ? (
                          u.id !== currentUser?.id && (
                            <button className="btn btn-sm btn-danger" style={{ marginLeft: '0.5rem' }} onClick={() => handleDeactivate(u.id)}>
                              {tr('deactivate')}
                            </button>
                          )
                        ) : (
                          <button className="btn btn-sm btn-secondary" style={{ marginLeft: '0.5rem' }} onClick={() => handleActivate(u.id)}>
                            {tr('activate')}
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
      )}

      <div className="card">
        <div className="card-title">{tr('limits')}</div>
        <p>{tr('limitsDescription')}</p>
      </div>
      </div>

      {modal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 500 }}>
            <div className="modal-header">
              <h2 className="modal-title">{tr('enterprise')}</h2>
              <button className="modal-close" onClick={() => setModal(false)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('name')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('address')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.address}
                  onChange={(e) => setForm({ ...form, address: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('pib')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.pib}
                  onChange={(e) => setForm({ ...form, pib: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('maticniBroj')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.maticni_broj}
                  onChange={(e) => setForm({ ...form, maticni_broj: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('bankName')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.bank_name}
                  onChange={(e) => setForm({ ...form, bank_name: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('bankAccount')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.bank_account}
                  onChange={(e) => setForm({ ...form, bank_account: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">SWIFT</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.bank_swift}
                  onChange={(e) => setForm({ ...form, bank_swift: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('mainActivityCode')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.main_activity_code}
                  onChange={(e) => setForm({ ...form, main_activity_code: e.target.value })}
                  placeholder={tr('bankCodePlaceholder')}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('cashflowOpening')}</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  value={form.opening_cash_balance}
                  onChange={(e) => setForm({ ...form, opening_cash_balance: parseFloat(e.target.value) || 0 })}
                  placeholder="0"
                />
                <small style={{ color: 'var(--color-text-muted)' }}>{tr('cashflowOpeningHint')}</small>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('cashflowOpeningDate')}</label>
                <DatePicker
                  value={form.opening_cash_date}
                  onChange={(v) => setForm({ ...form, opening_cash_date: v || `${new Date().getFullYear()}-01-01` })}
                  className="form-input"
                  style={{ width: '100%' }}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setModal(false)}>
                  {tr('cancel')}
                </button>
                <button type="submit" className="btn btn-primary">{tr('save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {userModal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 420 }}>
            <div className="modal-header">
              <h2 className="modal-title">{userModal === 'add' ? tr('add') : tr('edit')} {tr('user')}</h2>
              <button className="modal-close" onClick={() => setUserModal(null)}>×</button>
            </div>
            <form onSubmit={handleUserSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('username')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={userForm.username}
                  onChange={(e) => setUserForm({ ...userForm, username: e.target.value })}
                  required
                  disabled={userModal !== 'add'}
                  autoComplete="username"
                />
                {userModal !== 'add' && <small style={{ color: 'var(--color-text-muted)' }}>{tr('loginCannotChange')}</small>}
              </div>
              <div className="form-group">
                <label className="form-label">{tr('password')}</label>
                <input
                  type="password"
                  className="form-input"
                  value={userForm.password}
                  onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
                  placeholder={userModal === 'add' ? '' : tr('leaveEmptyHint')}
                  required={userModal === 'add'}
                  autoComplete={userModal === 'add' ? 'new-password' : 'current-password'}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('fullName')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={userForm.full_name}
                  onChange={(e) => setUserForm({ ...userForm, full_name: e.target.value })}
                  placeholder={tr('fullNamePlaceholder')}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('role')}</label>
                <select
                  className="form-input"
                  value={userForm.role}
                  onChange={(e) => setUserForm({ ...userForm, role: e.target.value })}
                >
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>{roleLabel(r.value)}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('language')}</label>
                <select
                  className="form-input"
                  value={userForm.default_language}
                  onChange={(e) => setUserForm({ ...userForm, default_language: e.target.value })}
                >
                  {LANGS.map((l) => (
                    <option key={l.value} value={l.value}>{l.label}</option>
                  ))}
                </select>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setUserModal(null)}>
                  {tr('cancel')}
                </button>
                <button type="submit" className="btn btn-primary">{tr('save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
