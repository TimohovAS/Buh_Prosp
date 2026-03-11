import { useState, useEffect } from 'react'
import { api, getUser } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import { broadcastEnterpriseBrand } from '../hooks/useEnterpriseBrand'

const ROLES = [
  { value: 'admin', labelKey: 'roleAdmin' },
  { value: 'accountant', labelKey: 'roleAccountant' },
  { value: 'cashier', labelKey: 'roleCashier' },
  { value: 'observer', labelKey: 'roleObserver' },
]

const LANGS = [
  { value: 'sr', labelKey: 'langSr' },
  { value: 'ru', labelKey: 'langRu' },
]

const UI_DASH = '\u2014'
const UI_CLOSE = '\u00D7'
const MAX_EMBLEM_FILE_SIZE = 256 * 1024

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
    emblem_data_url: '',
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

  const [categories, setCategories] = useState([])
  const [catModal, setCatModal] = useState(null)
  const [catForm, setCatForm] = useState({
    name_ru: '',
    name_sr: '',
    category_type: 'expense',
    category_group: 'admin',
    is_active: true,
    sort_order: 0,
  })
  const [serviceData, setServiceData] = useState(null)
  const [serviceLoading, setServiceLoading] = useState(false)
  const [serviceBusy, setServiceBusy] = useState('')
  const [serviceMessage, setServiceMessage] = useState('')

  const loadUsers = () => {
    if (!isAdmin) return
    setUsersLoading(true)
    api.users.list(showInactive)
      .then(setUsers)
      .catch((err) => console.error(err))
      .finally(() => setUsersLoading(false))
  }

  const loadCategories = () => {
    api.categories.list({ include_inactive: true })
      .then(setCategories)
      .catch((err) => console.error(err))
  }

  const loadService = () => {
    if (!isAdmin) return
    setServiceLoading(true)
    api.service.backups()
      .then(setServiceData)
      .catch((err) => console.error(err))
      .finally(() => setServiceLoading(false))
  }

  useEffect(() => {
    loadUsers()
  }, [showInactive, isAdmin])
  useEffect(() => {
    loadCategories()
  }, [])
  useEffect(() => {
    loadService()
  }, [isAdmin])

  const formatBytes = (value) => {
    const size = Number(value) || 0
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
    if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`
    return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  const formatDateTime = (value) => {
    if (!value) return UI_DASH
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
  }

  const backupTypeLabel = (kind) => {
    if (kind === 'auto') return tr('serviceBackupsTypeAuto')
    if (kind === 'pre-restore') return tr('serviceBackupsTypePreRestore')
    return tr('serviceBackupsTypeManual')
  }

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

  const handleUserSubmit = async (event) => {
    event.preventDefault()
    try {
      if (userModal === 'add') {
        await api.users.create(userForm)
      } else {
        const payload = {
          full_name: userForm.full_name,
          role: userForm.role,
          default_language: userForm.default_language,
        }
        if (userForm.password) payload.password = userForm.password
        await api.users.update(userModal.id, payload)
      }
      setUserModal(null)
      loadUsers()
    } catch (err) {
      console.error(err)
    }
  }

  const handleDeactivate = async (id) => {
    if (id === currentUser?.id) {
      alert(tr('cannotDeactivateSelf'))
      return
    }
    if (!confirm(tr('confirmDeactivateUser'))) return
    try {
      await api.users.deactivate(id)
      loadUsers()
    } catch (err) {
      console.error(err)
    }
  }

  const handleActivate = async (id) => {
    try {
      await api.users.update(id, { is_active: true })
      loadUsers()
    } catch (err) {
      console.error(err)
    }
  }

  const roleLabel = (role) => {
    const option = ROLES.find((item) => item.value === role)
    return option ? tr(option.labelKey) : role
  }

  const handleEmblemSelected = (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!file.type.startsWith('image/')) {
      alert(tr('invalidImageFile'))
      return
    }
    if (file.size > MAX_EMBLEM_FILE_SIZE) {
      alert(tr('emblemTooLarge'))
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : ''
      setForm((current) => ({ ...current, emblem_data_url: result }))
    }
    reader.readAsDataURL(file)
  }

  const handleEmblemRemove = () => {
    setForm((current) => ({ ...current, emblem_data_url: '' }))
  }

  useEffect(() => {
    api.enterprise.get()
      .then((response) => {
        setData(response)
        if (response) {
          const defaultDate = `${new Date().getFullYear()}-01-01`
          setForm({
            name: response.name || '',
            address: response.address || '',
            pib: response.pib || '',
            maticni_broj: response.maticni_broj || '',
            emblem_data_url: response.emblem_data_url || '',
            bank_name: response.bank_name || '',
            bank_account: response.bank_account || '',
            bank_swift: response.bank_swift || '',
            main_activity_code: response.main_activity_code || '',
            opening_cash_balance: response.opening_cash_balance ?? 0,
            opening_cash_date: response.opening_cash_date || defaultDate,
          })
        }
      })
      .finally(() => setLoading(false))
  }, [])

  const handleSubmit = async (event) => {
    event.preventDefault()
    try {
      const updated = await api.enterprise.update(form)
      setData(updated)
      setForm((current) => ({ ...current, emblem_data_url: updated?.emblem_data_url || '' }))
      broadcastEnterpriseBrand(updated)
      setModal(false)
    } catch (err) {
      console.error(err)
    }
  }

  const handleCreateBackup = async () => {
    setServiceBusy('create')
    try {
      await api.service.createBackup()
      setServiceMessage(tr('serviceBackupsCreateSuccess'))
      loadService()
    } catch (err) {
      console.error(err)
    } finally {
      setServiceBusy('')
    }
  }

  const handleDownloadBackup = async (name) => {
    setServiceBusy(`download:${name}`)
    try {
      await api.service.downloadBackup(name)
    } catch (err) {
      console.error(err)
    } finally {
      setServiceBusy('')
    }
  }

  const handleRestoreBackup = async (name) => {
    if (!confirm(tr('serviceBackupsRestoreConfirm'))) return
    setServiceBusy(`restore:${name}`)
    try {
      await api.service.restoreBackup(name)
      setServiceMessage(tr('serviceBackupsRestoreSuccess'))
      loadService()
      setTimeout(() => window.location.reload(), 1200)
    } catch (err) {
      console.error(err)
    } finally {
      setServiceBusy('')
    }
  }

  if (loading) return <div>{tr('loading')}</div>

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
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
                <div className="brand-mark" style={{ width: '4rem', height: '4rem' }} aria-hidden="true">
                  {data.emblem_data_url ? <img src={data.emblem_data_url} alt="" /> : <span>P</span>}
                </div>
                <div>
                  <div style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem', marginBottom: '0.25rem' }}>{tr('emblemPreview')}</div>
                  <div style={{ fontWeight: 600 }}>{data.name}</div>
                </div>
              </div>
              <p><strong>{tr('name')}:</strong> {data.name}</p>
              <p><strong>{tr('address')}:</strong> {data.address || UI_DASH}</p>
              <p><strong>{tr('pib')}:</strong> {data.pib || UI_DASH}</p>
              <p><strong>{tr('maticniBroj')}:</strong> {data.maticni_broj || UI_DASH}</p>
              <p><strong>{tr('bankName')}:</strong> {data.bank_name || UI_DASH}</p>
              <p><strong>{tr('bankAccount')}:</strong> {data.bank_account || UI_DASH}</p>
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
                  <input type="checkbox" checked={showInactive} onChange={(event) => setShowInactive(event.target.checked)} />
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
                    users.map((user) => (
                      <tr key={user.id} style={!user.is_active ? { opacity: 0.6 } : {}}>
                        <td>{user.username}</td>
                        <td>{user.full_name || UI_DASH}</td>
                        <td>{roleLabel(user.role)}</td>
                        <td>{user.default_language === 'ru' ? 'RU' : 'SR'}</td>
                        <td>{user.is_active ? tr('active') : tr('inactive')}</td>
                        <td>
                          <button className="btn btn-sm btn-secondary" onClick={() => openEditUser(user)}>{tr('edit')}</button>
                          {user.is_active ? (
                            user.id !== currentUser?.id && (
                              <button className="btn btn-sm btn-danger" style={{ marginLeft: '0.5rem' }} onClick={() => handleDeactivate(user.id)}>
                                {tr('deactivate')}
                              </button>
                            )
                          ) : (
                            <button className="btn btn-sm btn-secondary" style={{ marginLeft: '0.5rem' }} onClick={() => handleActivate(user.id)}>
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

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2>{tr('categoriesTitle')}</h2>
            <button className="btn btn-primary" onClick={() => {
              setCatForm({ name_ru: '', name_sr: '', category_type: 'expense', category_group: 'admin', is_active: true, sort_order: 0 })
              setCatModal('add')
            }}>{tr('add')}</button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('categoryNameRu')}</th>
                  <th>{tr('categoryNameSr')}</th>
                  <th>{tr('categoryGroup')}</th>
                  <th>{tr('sortOrder')}</th>
                  <th>{tr('status')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {categories.length === 0 ? (
                  <tr><td colSpan={6} style={{ color: 'var(--color-text-muted)' }}>{tr('noCategories')}</td></tr>
                ) : categories.map((category) => (
                  <tr key={category.id} style={!category.is_active ? { opacity: 0.5 } : {}}>
                    <td>{category.name_ru}</td>
                    <td>{category.name_sr}</td>
                    <td>{tr(`categoryGroup${category.category_group.charAt(0).toUpperCase() + category.category_group.slice(1)}`)}</td>
                    <td>{category.sort_order}</td>
                    <td>
                      <span className="badge" style={{ backgroundColor: category.is_active ? 'var(--color-success)' : 'var(--color-text-muted)', color: '#fff', padding: '0.2rem 0.5rem', borderRadius: 4 }}>
                        {category.is_active ? tr('active') : tr('inactive')}
                      </span>
                    </td>
                    <td>
                      <button className="btn btn-sm btn-secondary" onClick={() => {
                        setCatForm({
                          name_ru: category.name_ru,
                          name_sr: category.name_sr,
                          category_type: category.category_type,
                          category_group: category.category_group,
                          is_active: category.is_active,
                          sort_order: category.sort_order,
                        })
                        setCatModal({ type: 'edit', id: category.id })
                      }}>{tr('edit')}</button>
                      <button
                        className={`btn btn-sm ${category.is_active ? 'btn-danger' : 'btn-secondary'}`}
                        style={{ marginLeft: '0.5rem' }}
                        onClick={async () => {
                          try {
                            await api.categories.update(category.id, { is_active: !category.is_active })
                            loadCategories()
                          } catch (err) {
                            console.error(err)
                          }
                        }}
                      >
                        {category.is_active ? tr('deactivate') : tr('activate')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {isAdmin && (
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
              <div>
                <div className="card-title">{tr('serviceBackupsTitle')}</div>
                <p style={{ margin: '0.5rem 0 0', color: 'var(--color-text-muted)' }}>{tr('serviceBackupsHint')}</p>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <button className="btn btn-secondary" onClick={loadService} disabled={serviceLoading || !!serviceBusy}>
                  {tr('serviceBackupsRefresh')}
                </button>
                <button className="btn btn-primary" onClick={handleCreateBackup} disabled={serviceLoading || !!serviceBusy || !serviceData?.settings?.supported}>
                  {tr('serviceBackupsCreate')}
                </button>
              </div>
            </div>

            {serviceMessage ? (
              <div style={{ marginBottom: '1rem', color: 'var(--color-success)' }}>{serviceMessage}</div>
            ) : null}

            {serviceLoading && !serviceData ? (
              <div>{tr('loading')}</div>
            ) : !serviceData?.settings?.supported ? (
              <div style={{ color: 'var(--color-text-muted)' }}>{tr('serviceBackupsUnsupported')}</div>
            ) : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
                  <div>
                    <strong>{tr('serviceBackupsLocation')}:</strong>
                    <div style={{ color: 'var(--color-text-muted)', wordBreak: 'break-word' }}>{serviceData?.settings?.backup_dir || UI_DASH}</div>
                  </div>
                  <div>
                    <strong>{tr('serviceBackupsDbPath')}:</strong>
                    <div style={{ color: 'var(--color-text-muted)', wordBreak: 'break-word' }}>{serviceData?.settings?.database_path || UI_DASH}</div>
                  </div>
                  <div>
                    <strong>{tr('serviceBackupsDbSize')}:</strong>
                    <div style={{ color: 'var(--color-text-muted)' }}>{formatBytes(serviceData?.settings?.current_db_size_bytes)}</div>
                  </div>
                  <div>
                    <strong>{tr('serviceBackupsInterval')}:</strong>
                    <div style={{ color: 'var(--color-text-muted)' }}>{serviceData?.settings?.auto_interval_hours} {tr('serviceBackupsHours')}</div>
                  </div>
                  <div>
                    <strong>{tr('serviceBackupsAutoRetention')}:</strong>
                    <div style={{ color: 'var(--color-text-muted)' }}>{serviceData?.settings?.auto_retention_count}</div>
                  </div>
                  <div>
                    <strong>{tr('serviceBackupsManualRetention')}:</strong>
                    <div style={{ color: 'var(--color-text-muted)' }}>{serviceData?.settings?.manual_retention_count}</div>
                  </div>
                  <div>
                    <strong>{tr('serviceBackupsPreRestoreRetention')}:</strong>
                    <div style={{ color: 'var(--color-text-muted)' }}>{serviceData?.settings?.pre_restore_retention_count}</div>
                  </div>
                </div>

                <div style={{ marginBottom: '0.75rem', color: 'var(--color-text-muted)' }}>{tr('serviceBackupsReloadHint')}</div>

                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>{tr('serviceBackupsName')}</th>
                        <th>{tr('serviceBackupsType')}</th>
                        <th>{tr('serviceBackupsCreatedAt')}</th>
                        <th>{tr('serviceBackupsSize')}</th>
                        <th>{tr('cashActions')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(serviceData?.backups || []).length === 0 ? (
                        <tr><td colSpan={5} style={{ color: 'var(--color-text-muted)' }}>{tr('serviceBackupsNoItems')}</td></tr>
                      ) : (
                        (serviceData?.backups || []).map((backup) => (
                          <tr key={backup.name}>
                            <td>{backup.name}</td>
                            <td>{backupTypeLabel(backup.kind)}</td>
                            <td>{formatDateTime(backup.created_at)}</td>
                            <td>{formatBytes(backup.archive_size_bytes)}</td>
                            <td>
                              <button
                                className="btn btn-sm btn-secondary"
                                onClick={() => handleDownloadBackup(backup.name)}
                                disabled={!!serviceBusy}
                              >
                                {tr('download')}
                              </button>
                              <button
                                className="btn btn-sm btn-danger"
                                style={{ marginLeft: '0.5rem' }}
                                onClick={() => handleRestoreBackup(backup.name)}
                                disabled={!!serviceBusy}
                              >
                                {tr('restore')}
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {modal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 500 }}>
            <div className="modal-header">
              <h2 className="modal-title">{tr('enterprise')}</h2>
              <button className="modal-close" onClick={() => setModal(false)}>{UI_CLOSE}</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('name')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('address')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.address}
                  onChange={(event) => setForm({ ...form, address: event.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('pib')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.pib}
                  onChange={(event) => setForm({ ...form, pib: event.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('maticniBroj')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.maticni_broj}
                  onChange={(event) => setForm({ ...form, maticni_broj: event.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('enterpriseEmblem')}</label>
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
                  <div className="brand-mark" style={{ width: '4rem', height: '4rem' }} aria-hidden="true">
                    {form.emblem_data_url ? <img src={form.emblem_data_url} alt="" /> : <span>P</span>}
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <label className="btn btn-secondary" style={{ position: 'relative', overflow: 'hidden' }}>
                      {tr('chooseImage')}
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/svg+xml"
                        onChange={handleEmblemSelected}
                        style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer' }}
                      />
                    </label>
                    {form.emblem_data_url ? (
                      <button type="button" className="btn btn-secondary" onClick={handleEmblemRemove}>
                        {tr('removeImage')}
                      </button>
                    ) : null}
                  </div>
                </div>
                <small style={{ color: 'var(--color-text-muted)' }}>{tr('enterpriseEmblemHint')}</small>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('bankName')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.bank_name}
                  onChange={(event) => setForm({ ...form, bank_name: event.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('bankAccount')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.bank_account}
                  onChange={(event) => setForm({ ...form, bank_account: event.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">SWIFT</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.bank_swift}
                  onChange={(event) => setForm({ ...form, bank_swift: event.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('mainActivityCode')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.main_activity_code}
                  onChange={(event) => setForm({ ...form, main_activity_code: event.target.value })}
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
                  onChange={(event) => setForm({ ...form, opening_cash_balance: parseFloat(event.target.value) || 0 })}
                  placeholder="0"
                />
                <small style={{ color: 'var(--color-text-muted)' }}>{tr('cashflowOpeningHint')}</small>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('cashflowOpeningDate')}</label>
                <DatePicker
                  value={form.opening_cash_date}
                  onChange={(value) => setForm({ ...form, opening_cash_date: value || `${new Date().getFullYear()}-01-01` })}
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
          <div className="modal" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 420 }}>
            <div className="modal-header">
              <h2 className="modal-title">{userModal === 'add' ? tr('add') : tr('edit')} {tr('user')}</h2>
              <button className="modal-close" onClick={() => setUserModal(null)}>{UI_CLOSE}</button>
            </div>
            <form onSubmit={handleUserSubmit}>
              <div className="form-group">
                <label className="form-label">{tr('username')}</label>
                <input
                  type="text"
                  className="form-input"
                  value={userForm.username}
                  onChange={(event) => setUserForm({ ...userForm, username: event.target.value })}
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
                  onChange={(event) => setUserForm({ ...userForm, password: event.target.value })}
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
                  onChange={(event) => setUserForm({ ...userForm, full_name: event.target.value })}
                  placeholder={tr('fullNamePlaceholder')}
                />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('role')}</label>
                <select
                  className="form-input"
                  value={userForm.role}
                  onChange={(event) => setUserForm({ ...userForm, role: event.target.value })}
                >
                  {ROLES.map((role) => (
                    <option key={role.value} value={role.value}>{roleLabel(role.value)}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('language')}</label>
                <select
                  className="form-input"
                  value={userForm.default_language}
                  onChange={(event) => setUserForm({ ...userForm, default_language: event.target.value })}
                >
                  {LANGS.map((lang) => (
                    <option key={lang.value} value={lang.value}>{tr(lang.labelKey)}</option>
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

      {catModal && (
        <div className="modal-overlay">
          <div className="modal" onClick={(event) => event.stopPropagation()} style={{ maxWidth: 480 }}>
            <div className="modal-header">
              <h2 className="modal-title">{catModal === 'add' ? tr('add') : tr('edit')} {UI_DASH} {tr('categoriesTitle')}</h2>
              <button className="modal-close" onClick={() => setCatModal(null)}>{UI_CLOSE}</button>
            </div>
            <form onSubmit={async (event) => {
              event.preventDefault()
              try {
                if (catModal === 'add') await api.categories.create(catForm)
                else await api.categories.update(catModal.id, catForm)
                setCatModal(null)
                loadCategories()
              } catch (err) {
                console.error(err)
              }
            }}>
              <div className="form-group">
                <label className="form-label">{tr('categoryNameRu')}</label>
                <input type="text" className="form-input" value={catForm.name_ru} onChange={(event) => setCatForm({ ...catForm, name_ru: event.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('categoryNameSr')}</label>
                <input type="text" className="form-input" value={catForm.name_sr} onChange={(event) => setCatForm({ ...catForm, name_sr: event.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">{tr('categoryGroup')}</label>
                <select className="form-input" value={catForm.category_group} onChange={(event) => setCatForm({ ...catForm, category_group: event.target.value })}>
                  <option value="commercial">{tr('categoryGroupCommercial')}</option>
                  <option value="admin">{tr('categoryGroupAdmin')}</option>
                  <option value="tax">{tr('categoryGroupTax')}</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr('sortOrder')}</label>
                <input type="number" className="form-input" value={catForm.sort_order} onChange={(event) => setCatForm({ ...catForm, sort_order: parseInt(event.target.value, 10) || 0 })} />
              </div>
              <div className="form-group">
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input type="checkbox" checked={catForm.is_active} onChange={(event) => setCatForm({ ...catForm, is_active: event.target.checked })} />
                  <span>{tr('active')}</span>
                </label>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setCatModal(null)}>{tr('cancel')}</button>
                <button type="submit" className="btn btn-primary">{tr('save')}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
