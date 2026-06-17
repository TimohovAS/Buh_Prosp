import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { api, getUser } from '../api'
import { tr } from '../i18n'
import DatePicker from '../components/DatePicker'
import Modal from '../components/Modal'
import ProjectSelect from '../components/ProjectSelect'
import { broadcastEnterpriseBrand } from '../hooks/useEnterpriseBrand'
import {
  DEFAULT_EFAKTURA_API_BASE_URL,
  DEFAULT_EFAKTURA_INCOMING_DOCUMENT_PATH,
  DEFAULT_EFAKTURA_INCOMING_LIST_PATH,
  DEFAULT_EFAKTURA_OUTGOING_DOCUMENT_PATH,
  DEFAULT_EFAKTURA_OUTGOING_LIST_PATH,
} from '../efakturaDefaults'

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
const DEFAULT_SERVICE_FORM = {
  backup_dir: '',
  auto_enabled: true,
  auto_interval_hours: 6,
  auto_retention_count: 60,
  manual_retention_count: 30,
  pre_restore_retention_count: 20,
  scheduler_check_minutes: 5,
}

function SettingsTooltip({ text }) {
  if (!text) return null
  return (
    <span className="settings-tooltip" tabIndex={0} aria-label={text}>
      <span className="settings-tooltip-trigger" aria-hidden="true">i</span>
      <span className="settings-tooltip-bubble" role="tooltip">{text}</span>
    </span>
  )
}

function SettingsFieldHead({ label, hint }) {
  return (
    <div className="settings-field-head">
      <div className="settings-field-label">{label}</div>
      <SettingsTooltip text={hint} />
    </div>
  )
}

function SettingsSection({ title, summary, actions, open, onToggle, children }) {
  if (!open) return null
  return (
    <section className={`settings-section ${open ? 'open' : ''}`}>
      <div className="settings-section-header">
        <button type="button" className="settings-section-toggle" onClick={onToggle}>
          <div className="settings-section-copy">
            <div className="settings-section-title">{title}</div>
            {summary ? <div className="settings-section-summary">{summary}</div> : null}
          </div>
          <span className={`settings-section-arrow ${open ? 'open' : ''}`}>▾</span>
        </button>
        {actions ? <div className="settings-section-actions">{actions}</div> : null}
      </div>
      {open ? <div className="settings-section-body">{children}</div> : null}
    </section>
  )
}

export default function Settings() {
  const location = useLocation()
  const isActivePage = location.pathname === '/settings'
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
  const [projects, setProjects] = useState([])
  const [catModal, setCatModal] = useState(null)
  const [catForm, setCatForm] = useState({
    name_ru: '',
    name_sr: '',
    category_type: 'expense',
    category_group: 'admin',
    default_project_id: '',
    is_active: true,
    sort_order: 0,
  })
  const [serviceData, setServiceData] = useState(null)
  const [serviceForm, setServiceForm] = useState(DEFAULT_SERVICE_FORM)
  const [serviceLoading, setServiceLoading] = useState(false)
  const [serviceBusy, setServiceBusy] = useState('')
  const [serviceMessage, setServiceMessage] = useState('')
  const [serviceMessageTone, setServiceMessageTone] = useState('success')
  const [efakturaForm, setEfakturaForm] = useState({
    efaktura_enabled: false,
    efaktura_api_base_url: '',
    efaktura_api_key: '',
    efaktura_api_key_header: 'ApiKey',
    efaktura_api_key_prefix: '',
    efaktura_sync_incoming: true,
    efaktura_sync_outgoing: true,
    efaktura_sync_lookback_days: 30,
    efaktura_incoming_list_path: '',
    efaktura_incoming_document_path: '',
    efaktura_outgoing_list_path: '',
    efaktura_outgoing_document_path: '',
    efaktura_save_pdf: false,
    efaktura_incoming_pdf_path: '',
    efaktura_outgoing_pdf_path: '',
  })
  const [efakturaLoading, setEfakturaLoading] = useState(false)
  const [efakturaSaving, setEfakturaSaving] = useState(false)
  const [efakturaMessage, setEfakturaMessage] = useState('')
  const [activeSection, setActiveSection] = useState('enterprise')
  const [backupView, setBackupView] = useState('settings')

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

  const loadProjects = () => {
    api.projects.list({ show_archived: true })
      .then(setProjects)
      .catch((err) => console.error(err))
  }

  const loadService = () => {
    if (!isAdmin) return
    setServiceLoading(true)
    api.service.backups()
      .then((response) => {
        setServiceData(response)
        setServiceForm(mapServiceSettingsToForm(response?.settings))
        return response
      })
      .catch((err) => console.error(err))
      .finally(() => setServiceLoading(false))
  }

  const loadEfakturaSettings = () => {
    if (!isAdmin) return
    setEfakturaLoading(true)
    api.efaktura.settings()
      .then((response) => {
        setEfakturaForm({
          efaktura_enabled: !!response?.efaktura_enabled,
          efaktura_api_base_url: response?.efaktura_api_base_url || '',
          efaktura_api_key: response?.efaktura_api_key || '',
          efaktura_api_key_header: response?.efaktura_api_key_header || 'ApiKey',
          efaktura_api_key_prefix: response?.efaktura_api_key_prefix || '',
          efaktura_sync_incoming: response?.efaktura_sync_incoming ?? true,
          efaktura_sync_outgoing: response?.efaktura_sync_outgoing ?? true,
          efaktura_sync_lookback_days: response?.efaktura_sync_lookback_days ?? 30,
          efaktura_incoming_list_path: response?.efaktura_incoming_list_path || '',
          efaktura_incoming_document_path: response?.efaktura_incoming_document_path || '',
          efaktura_outgoing_list_path: response?.efaktura_outgoing_list_path || '',
          efaktura_outgoing_document_path: response?.efaktura_outgoing_document_path || '',
          efaktura_save_pdf: response?.efaktura_save_pdf ?? false,
          efaktura_incoming_pdf_path: response?.efaktura_incoming_pdf_path || '',
          efaktura_outgoing_pdf_path: response?.efaktura_outgoing_pdf_path || '',
        })
      })
      .catch((err) => console.error(err))
      .finally(() => setEfakturaLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return
    loadUsers()
  }, [showInactive, isAdmin, isActivePage])
  useEffect(() => {
    if (!isActivePage) return
    loadCategories()
  }, [isActivePage])
  useEffect(() => {
    if (!isActivePage) return
    loadProjects()
  }, [isActivePage])
  useEffect(() => {
    if (!isActivePage) return
    loadService()
  }, [isAdmin, isActivePage])
  useEffect(() => {
    if (!isActivePage) return
    loadEfakturaSettings()
  }, [isAdmin, isActivePage])

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

  const mapServiceSettingsToForm = (settings) => ({
    backup_dir: settings?.backup_dir || '',
    auto_enabled: settings?.auto_enabled ?? true,
    auto_interval_hours: settings?.auto_interval_hours ?? DEFAULT_SERVICE_FORM.auto_interval_hours,
    auto_retention_count: settings?.auto_retention_count ?? DEFAULT_SERVICE_FORM.auto_retention_count,
    manual_retention_count: settings?.manual_retention_count ?? DEFAULT_SERVICE_FORM.manual_retention_count,
    pre_restore_retention_count: settings?.pre_restore_retention_count ?? DEFAULT_SERVICE_FORM.pre_restore_retention_count,
    scheduler_check_minutes: settings?.scheduler_check_minutes ?? DEFAULT_SERVICE_FORM.scheduler_check_minutes,
  })

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

  const getProjectName = (projectId) => projects.find((project) => project.id === projectId)?.name || UI_DASH

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
    if (!isActivePage) return
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
  }, [isActivePage])

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
    setServiceMessage('')
    try {
      await api.service.createBackup()
      setServiceMessageTone('success')
      setServiceMessage(tr('serviceBackupsCreateSuccess'))
      loadService()
    } catch (err) {
      console.error(err)
      setServiceMessageTone('error')
      setServiceMessage(err.message || tr('loadError'))
    } finally {
      setServiceBusy('')
    }
  }

  const handleCreateAndDownloadBackup = async () => {
    setServiceBusy('create-download')
    setServiceMessage('')
    try {
      const response = await api.service.createBackup()
      const backupName = response?.backup?.name
      if (!backupName) throw new Error(tr('serviceBackupsCreateDownloadError'))
      await api.service.downloadBackup(backupName)
      setServiceMessageTone('success')
      setServiceMessage(tr('serviceBackupsCreateDownloadSuccess'))
      loadService()
    } catch (err) {
      console.error(err)
      setServiceMessageTone('error')
      setServiceMessage(err.message || tr('loadError'))
    } finally {
      setServiceBusy('')
    }
  }

  const handleServiceSave = async () => {
    setServiceBusy('save')
    setServiceMessage('')
    try {
      await api.service.updateSettings({
        backup_dir: serviceForm.backup_dir || null,
        auto_enabled: !!serviceForm.auto_enabled,
        auto_interval_hours: Math.max(1, Number(serviceForm.auto_interval_hours) || DEFAULT_SERVICE_FORM.auto_interval_hours),
        auto_retention_count: Math.max(1, Number(serviceForm.auto_retention_count) || DEFAULT_SERVICE_FORM.auto_retention_count),
        manual_retention_count: Math.max(1, Number(serviceForm.manual_retention_count) || DEFAULT_SERVICE_FORM.manual_retention_count),
        pre_restore_retention_count: Math.max(
          1,
          Number(serviceForm.pre_restore_retention_count) || DEFAULT_SERVICE_FORM.pre_restore_retention_count,
        ),
        scheduler_check_minutes: Math.max(
          1,
          Number(serviceForm.scheduler_check_minutes) || DEFAULT_SERVICE_FORM.scheduler_check_minutes,
        ),
      })
      setServiceMessageTone('success')
      setServiceMessage(tr('serviceBackupsSettingsSaved'))
      loadService()
    } catch (err) {
      console.error(err)
      setServiceMessageTone('error')
      setServiceMessage(err.message || tr('serviceBackupsSettingsSaveError'))
    } finally {
      setServiceBusy('')
    }
  }

  const handleEfakturaSave = async () => {
    setEfakturaSaving(true)
    setEfakturaMessage('')
    try {
      await api.efaktura.updateSettings({
        ...efakturaForm,
        efaktura_api_base_url: efakturaForm.efaktura_api_base_url || null,
        efaktura_api_key: efakturaForm.efaktura_api_key || null,
        efaktura_api_key_header: efakturaForm.efaktura_api_key_header || 'ApiKey',
        efaktura_api_key_prefix: efakturaForm.efaktura_api_key_prefix || '',
        efaktura_sync_lookback_days: Number(efakturaForm.efaktura_sync_lookback_days) || 30,
        efaktura_incoming_list_path: efakturaForm.efaktura_incoming_list_path || null,
        efaktura_incoming_document_path: efakturaForm.efaktura_incoming_document_path || null,
        efaktura_outgoing_list_path: efakturaForm.efaktura_outgoing_list_path || null,
        efaktura_outgoing_document_path: efakturaForm.efaktura_outgoing_document_path || null,
        efaktura_save_pdf: !!efakturaForm.efaktura_save_pdf,
        efaktura_incoming_pdf_path: efakturaForm.efaktura_incoming_pdf_path || null,
        efaktura_outgoing_pdf_path: efakturaForm.efaktura_outgoing_pdf_path || null,
      })
      setEfakturaMessage(tr('efakturaSettingsSaved'))
      loadEfakturaSettings()
    } catch (err) {
      console.error(err)
      setEfakturaMessage(err.message || tr('efakturaSettingsSaveError'))
    } finally {
      setEfakturaSaving(false)
    }
  }

  const handleDownloadBackup = async (name) => {
    setServiceBusy(`download:${name}`)
    setServiceMessage('')
    try {
      await api.service.downloadBackup(name)
    } catch (err) {
      console.error(err)
      setServiceMessageTone('error')
      setServiceMessage(err.message || tr('loadError'))
    } finally {
      setServiceBusy('')
    }
  }

  const handleRestoreBackup = async (name) => {
    if (!confirm(tr('serviceBackupsRestoreConfirm'))) return
    setServiceBusy(`restore:${name}`)
    setServiceMessage('')
    try {
      await api.service.restoreBackup(name)
      setServiceMessageTone('success')
      setServiceMessage(tr('serviceBackupsRestoreSuccess'))
      loadService()
      setTimeout(() => window.location.reload(), 1200)
    } catch (err) {
      console.error(err)
      setServiceMessageTone('error')
      setServiceMessage(err.message || tr('loadError'))
    } finally {
      setServiceBusy('')
    }
  }

  if (loading) return <div>{tr('loading')}</div>

  const activeUsers = users.filter((user) => user.is_active).length
  const activeCategories = categories.filter((category) => category.is_active).length
  const latestBackup = serviceData?.backups?.[0]?.created_at
  const enterpriseSummary = data
    ? [data.name, data.pib ? `PIB ${data.pib}` : null].filter(Boolean).join(' · ')
    : tr('fillEnterpriseData')
  const usersSummary = users.length > 0 ? `${activeUsers}/${users.length} ${tr('active').toLowerCase()}` : tr('noUsers')
  const categoriesSummary = categories.length > 0 ? `${activeCategories}/${categories.length} ${tr('active').toLowerCase()}` : tr('noCategories')
  const backupsSummary = !serviceData?.settings?.supported
    ? tr('serviceBackupsUnsupported')
    : (latestBackup ? `${tr('serviceBackupsCreatedAt')}: ${formatDateTime(latestBackup)}` : tr('serviceBackupsNoItems'))
  const backupActions = backupView === 'archives'
    ? (
      <>
        <button className="btn btn-secondary" onClick={loadService} disabled={serviceLoading || !!serviceBusy}>
          {tr('serviceBackupsRefresh')}
        </button>
        <button className="btn btn-primary" onClick={handleCreateAndDownloadBackup} disabled={serviceLoading || !!serviceBusy || !serviceData?.settings?.supported}>
          {tr('serviceBackupsCreateAndDownload')}
        </button>
        <button className="btn btn-primary" onClick={handleCreateBackup} disabled={serviceLoading || !!serviceBusy || !serviceData?.settings?.supported}>
          {tr('serviceBackupsCreate')}
        </button>
      </>
    )
    : (
      <>
        <button className="btn btn-secondary" onClick={loadService} disabled={serviceLoading || !!serviceBusy}>
          {tr('serviceBackupsRefresh')}
        </button>
        <button className="btn btn-primary" onClick={handleCreateAndDownloadBackup} disabled={serviceLoading || !!serviceBusy || !serviceData?.settings?.supported}>
          {tr('serviceBackupsCreateAndDownload')}
        </button>
        <button className="btn btn-primary" onClick={handleServiceSave} disabled={serviceLoading || !!serviceBusy || !serviceData?.settings?.supported}>
          {tr('save')}
        </button>
      </>
    )
  const sections = [
    { key: 'enterprise', title: tr('enterpriseData'), summary: [tr('name'), tr('address'), tr('bankName'), tr('cashflowOpening')].join(' • ') },
    ...(isAdmin ? [{ key: 'users', title: tr('users'), summary: [tr('role'), tr('language'), tr('status')].join(' • ') }] : []),
    ...(isAdmin ? [{ key: 'efaktura', title: tr('efakturaSettingsTitle'), summary: tr('efakturaSettingsSummary') }] : []),
    { key: 'categories', title: tr('categoriesTitle'), summary: [tr('categoryNameRu'), tr('categoryGroup'), tr('sortOrder')].join(' • ') },
    ...(isAdmin ? [{ key: 'backups', title: tr('serviceBackupsTitle'), summary: serviceData?.settings?.supported ? [tr('serviceBackupsCreate'), tr('download'), tr('restore')].join(' • ') : tr('serviceBackupsUnsupported') }] : []),
  ]

  return (
    <>
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">{tr('settings')}</h1>
        </div>
      </div>

      <div className="page-body settings-page">
        <div className="settings-shell">
          <aside className="settings-sidebar">
            <div className="settings-nav">
              {sections.map((section) => (
                <button
                  key={section.key}
                  type="button"
                  className={`settings-nav-button ${activeSection === section.key ? 'active' : ''}`}
                  onClick={() => setActiveSection(section.key)}
                >
                  <span className="settings-nav-title">{section.title}</span>
                  <span className="settings-nav-meta">{section.summary}</span>
                </button>
              ))}
            </div>
          </aside>

          <div className="settings-content">

        <SettingsSection
          title={tr('enterpriseData')}
          summary={[tr('name'), tr('address'), tr('bankName'), tr('cashflowOpening')].join(' • ')}
          open={activeSection === 'enterprise'}
          onToggle={() => setActiveSection('enterprise')}
          actions={(
            <button className="btn btn-primary btn-sm" onClick={() => setModal(true)}>
              {tr('edit')}
            </button>
          )}
        >
          {data ? (
            <div className="settings-enterprise-grid">
              <div className="settings-emblem-card">
                <div className="brand-mark" style={{ width: '4rem', height: '4rem' }} aria-hidden="true">
                  {data.emblem_data_url ? <img src={data.emblem_data_url} alt="" /> : <span>P</span>}
                </div>
                <div className="settings-emblem-copy">
                  <div className="settings-field-label">{tr('emblemPreview')}</div>
                  <div className="settings-emblem-name">{data.name}</div>
                </div>
              </div>

              <div className="settings-info-grid">
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('name')}</div>
                  <div className="settings-field-value">{data.name || UI_DASH}</div>
                </div>
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('address')}</div>
                  <div className="settings-field-value">{data.address || UI_DASH}</div>
                </div>
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('pib')}</div>
                  <div className="settings-field-value">{data.pib || UI_DASH}</div>
                </div>
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('maticniBroj')}</div>
                  <div className="settings-field-value">{data.maticni_broj || UI_DASH}</div>
                </div>
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('bankName')}</div>
                  <div className="settings-field-value">{data.bank_name || UI_DASH}</div>
                </div>
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('bankAccount')}</div>
                  <div className="settings-field-value">{data.bank_account || UI_DASH}</div>
                </div>
              </div>
            </div>
          ) : (
            <p className="settings-empty-text">{tr('fillEnterpriseData')}</p>
          )}
        </SettingsSection>

        {isAdmin && (
          <SettingsSection
            title={tr('users')}
            summary={[tr('role'), tr('language'), tr('status')].join(' • ')}
            open={activeSection === 'users'}
            onToggle={() => setActiveSection('users')}
            actions={(
              <>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input type="checkbox" checked={showInactive} onChange={(event) => setShowInactive(event.target.checked)} />
                  <span>{tr('showInactive')}</span>
                </label>
                <button className="btn btn-primary btn-sm" onClick={openAddUser}>{tr('add')}</button>
              </>
            )}
          >
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
          </SettingsSection>
        )}

        {isAdmin && (
          <SettingsSection
            title={tr('efakturaSettingsTitle')}
            summary={tr('efakturaSettingsSummary')}
            open={activeSection === 'efaktura'}
            onToggle={() => setActiveSection('efaktura')}
              actions={(
                <button className="btn btn-primary btn-sm" onClick={handleEfakturaSave} disabled={efakturaLoading || efakturaSaving}>
                  {efakturaSaving ? tr('efakturaSaving') : tr('save')}
                </button>
              )}
            >
              <div className="settings-callout" style={{ marginBottom: '1rem' }}>
                <div>{tr('efakturaSettingsHint')}</div>
              </div>

            {efakturaMessage ? (
              <div style={{ marginBottom: '1rem', color: efakturaMessage === tr('efakturaSettingsSaved') ? 'var(--color-success)' : 'var(--color-danger)' }}>
                {efakturaMessage}
              </div>
            ) : null}

            <div className="settings-info-grid" style={{ marginBottom: '1rem' }}>
              <label className="settings-info-item" style={{ cursor: 'pointer' }}>
                <div className="settings-field-label">{tr('efakturaEnabled')}</div>
                <div className="settings-field-value">
                  <input
                    type="checkbox"
                    checked={efakturaForm.efaktura_enabled}
                    onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_enabled: event.target.checked }))}
                  />
                </div>
              </label>
              <label className="settings-info-item" style={{ cursor: 'pointer' }}>
                <div className="settings-field-label">{tr('efakturaSyncIncomingToggle')}</div>
                <div className="settings-field-value">
                  <input
                    type="checkbox"
                    checked={efakturaForm.efaktura_sync_incoming}
                    onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_sync_incoming: event.target.checked }))}
                  />
                </div>
              </label>
              <label className="settings-info-item" style={{ cursor: 'pointer' }}>
                <div className="settings-field-label">{tr('efakturaSyncOutgoingToggle')}</div>
                <div className="settings-field-value">
                  <input
                    type="checkbox"
                    checked={efakturaForm.efaktura_sync_outgoing}
                    onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_sync_outgoing: event.target.checked }))}
                  />
                </div>
              </label>
              <div className="settings-info-item">
                <div className="settings-field-label">{tr('efakturaLookbackDays')}</div>
                <input
                  className="form-input"
                  type="number"
                  min="1"
                  max="365"
                  value={efakturaForm.efaktura_sync_lookback_days}
                  onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_sync_lookback_days: event.target.value }))}
                />
              </div>
            </div>

            <div className="settings-info-grid">
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('efakturaBaseUrl')}</div>
                  <input
                    className="form-input"
                    value={efakturaForm.efaktura_api_base_url}
                    onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_api_base_url: event.target.value }))}
                    placeholder={DEFAULT_EFAKTURA_API_BASE_URL}
                  />
                </div>
              <div className="settings-info-item">
                <div className="settings-field-label">{tr('efakturaApiKeyHeader')}</div>
                <input
                  className="form-input"
                  value={efakturaForm.efaktura_api_key_header}
                  onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_api_key_header: event.target.value }))}
                  placeholder="ApiKey"
                />
              </div>
              <div className="settings-info-item">
                <div className="settings-field-label">{tr('efakturaApiKeyPrefix')}</div>
                <input
                  className="form-input"
                  value={efakturaForm.efaktura_api_key_prefix}
                  onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_api_key_prefix: event.target.value }))}
                  placeholder="Bearer "
                />
              </div>
              <div className="settings-info-item" style={{ gridColumn: '1 / -1' }}>
                <div className="settings-field-label">{tr('efakturaApiKey')}</div>
                <input
                  className="form-input"
                  value={efakturaForm.efaktura_api_key}
                  onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_api_key: event.target.value }))}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                />
              </div>
              <div className="settings-callout" style={{ gridColumn: '1 / -1', margin: '0.25rem 0' }}>
                <strong>{tr('efakturaFileDownloadSettings')}</strong>
                <div style={{ marginTop: '0.35rem' }}>{tr('efakturaFileDownloadHint')}</div>
              </div>
              <label className="settings-info-item" style={{ cursor: 'pointer' }}>
                <div className="settings-field-label">{tr('efakturaSavePdf')}</div>
                <div className="settings-field-value">
                  <input
                    type="checkbox"
                    checked={efakturaForm.efaktura_save_pdf}
                    onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_save_pdf: event.target.checked }))}
                  />
                </div>
              </label>
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('efakturaIncomingListPath')}</div>
                  <input
                    className="form-input"
                    value={efakturaForm.efaktura_incoming_list_path}
                    onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_incoming_list_path: event.target.value }))}
                    placeholder={DEFAULT_EFAKTURA_INCOMING_LIST_PATH}
                  />
                </div>
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('efakturaIncomingDocumentPath')}</div>
                  <input
                    className="form-input"
                    value={efakturaForm.efaktura_incoming_document_path}
                    onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_incoming_document_path: event.target.value }))}
                    placeholder={DEFAULT_EFAKTURA_INCOMING_DOCUMENT_PATH}
                  />
                </div>
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('efakturaOutgoingListPath')}</div>
                  <input
                    className="form-input"
                    value={efakturaForm.efaktura_outgoing_list_path}
                    onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_outgoing_list_path: event.target.value }))}
                    placeholder={DEFAULT_EFAKTURA_OUTGOING_LIST_PATH}
                  />
                </div>
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('efakturaOutgoingDocumentPath')}</div>
                  <input
                    className="form-input"
                    value={efakturaForm.efaktura_outgoing_document_path}
                    onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_outgoing_document_path: event.target.value }))}
                    placeholder={DEFAULT_EFAKTURA_OUTGOING_DOCUMENT_PATH}
                  />
                </div>
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('efakturaIncomingPdfPath')}</div>
                  <input
                    className="form-input"
                    value={efakturaForm.efaktura_incoming_pdf_path}
                    onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_incoming_pdf_path: event.target.value }))}
                    placeholder={tr('efakturaPdfPathPlaceholder')}
                  />
                </div>
                <div className="settings-info-item">
                  <div className="settings-field-label">{tr('efakturaOutgoingPdfPath')}</div>
                  <input
                    className="form-input"
                    value={efakturaForm.efaktura_outgoing_pdf_path}
                    onChange={(event) => setEfakturaForm((current) => ({ ...current, efaktura_outgoing_pdf_path: event.target.value }))}
                    placeholder={tr('efakturaPdfPathPlaceholder')}
                  />
                </div>
              </div>
          </SettingsSection>
        )}

        <SettingsSection
          title={tr('categoriesTitle')}
          summary={[tr('categoryNameRu'), tr('categoryGroup'), tr('sortOrder')].join(' • ')}
          open={activeSection === 'categories'}
          onToggle={() => setActiveSection('categories')}
            actions={(
              <button className="btn btn-primary" onClick={() => {
              setCatForm({ name_ru: '', name_sr: '', category_type: 'expense', category_group: 'admin', default_project_id: '', is_active: true, sort_order: 0 })
                setCatModal('add')
              }}>{tr('add')}</button>
            )}
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{tr('categoryNameRu')}</th>
                  <th>{tr('categoryNameSr')}</th>
                  <th>{tr('categoryGroup')}</th>
                  <th>{tr('project')}</th>
                  <th>{tr('sortOrder')}</th>
                  <th>{tr('status')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {categories.length === 0 ? (
                  <tr><td colSpan={7} style={{ color: 'var(--color-text-muted)' }}>{tr('noCategories')}</td></tr>
                ) : categories.map((category) => (
                  <tr key={category.id} style={!category.is_active ? { opacity: 0.5 } : {}}>
                    <td>{category.name_ru}</td>
                    <td>{category.name_sr}</td>
                    <td>{tr(`categoryGroup${category.category_group.charAt(0).toUpperCase() + category.category_group.slice(1)}`)}</td>
                    <td>{getProjectName(category.default_project_id)}</td>
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
                          default_project_id: category.default_project_id ? String(category.default_project_id) : '',
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
        </SettingsSection>

        {isAdmin && (
          <SettingsSection
            title={tr('serviceBackupsTitle')}
            summary={serviceData?.settings?.supported ? [tr('serviceBackupsCreate'), tr('download'), tr('restore')].join(' • ') : tr('serviceBackupsUnsupported')}
            open={activeSection === 'backups'}
            onToggle={() => setActiveSection('backups')}
            actions={backupActions}
          >
            {serviceMessage ? (
              <div style={{ marginBottom: '1rem', color: serviceMessageTone === 'error' ? 'var(--color-danger)' : 'var(--color-success)' }}>{serviceMessage}</div>
            ) : null}

            {serviceLoading && !serviceData ? (
              <div>{tr('loading')}</div>
            ) : !serviceData?.settings?.supported ? (
              <div style={{ color: 'var(--color-text-muted)' }}>{tr('serviceBackupsUnsupported')}</div>
            ) : (
              <>
                <div className="settings-subtabs">
                  <button
                    type="button"
                    className={`settings-subtab ${backupView === 'settings' ? 'active' : ''}`}
                    onClick={() => setBackupView('settings')}
                  >
                    {tr('serviceBackupsTabSettings')}
                  </button>
                  <button
                    type="button"
                    className={`settings-subtab ${backupView === 'archives' ? 'active' : ''}`}
                    onClick={() => setBackupView('archives')}
                  >
                    {tr('serviceBackupsTabArchives')}
                  </button>
                </div>

                {backupView === 'settings' ? (
                  <div className="settings-service-layout">
                    <div className="settings-callout">
                      <p>{tr('serviceBackupsHint')}</p>
                    </div>

                    <div className="settings-status-grid">
                      <div className="settings-status-card">
                        <div className="settings-field-label">{tr('serviceBackupsDbPath')}</div>
                        <div className="settings-field-value">{serviceData?.settings?.database_path || UI_DASH}</div>
                      </div>
                      <div className="settings-status-card">
                        <div className="settings-field-label">{tr('serviceBackupsDbSize')}</div>
                        <div className="settings-field-value">{formatBytes(serviceData?.settings?.current_db_size_bytes)}</div>
                      </div>
                    </div>

                    <div className="settings-form-grid">
                      <div className="settings-info-item settings-info-item--wide">
                        <SettingsFieldHead label={tr('serviceBackupsLocation')} hint={tr('serviceBackupsLocationHint')} />
                        <input
                          className="form-input"
                          value={serviceForm.backup_dir}
                          onChange={(event) => setServiceForm((current) => ({ ...current, backup_dir: event.target.value }))}
                          disabled={!!serviceBusy}
                        />
                      </div>
                      <div className="settings-info-item">
                        <SettingsFieldHead label={tr('serviceBackupsAutoEnabled')} hint={tr('serviceBackupsAutoEnabledHint')} />
                        <label className="settings-toggle-control">
                          <input
                            type="checkbox"
                            checked={!!serviceForm.auto_enabled}
                            onChange={(event) => setServiceForm((current) => ({ ...current, auto_enabled: event.target.checked }))}
                            disabled={!!serviceBusy}
                          />
                          <span>{serviceForm.auto_enabled ? tr('yes') : tr('no')}</span>
                        </label>
                      </div>
                      <div className="settings-info-item">
                        <SettingsFieldHead label={`${tr('serviceBackupsInterval')} (${tr('serviceBackupsHours')})`} hint={tr('serviceBackupsIntervalHint')} />
                        <input
                          type="number"
                          min="1"
                          className="form-input"
                          value={serviceForm.auto_interval_hours}
                          onChange={(event) => setServiceForm((current) => ({ ...current, auto_interval_hours: event.target.value }))}
                          disabled={!!serviceBusy}
                        />
                      </div>
                      <div className="settings-info-item">
                        <SettingsFieldHead label={tr('serviceBackupsAutoRetention')} hint={tr('serviceBackupsAutoRetentionHint')} />
                        <input
                          type="number"
                          min="1"
                          className="form-input"
                          value={serviceForm.auto_retention_count}
                          onChange={(event) => setServiceForm((current) => ({ ...current, auto_retention_count: event.target.value }))}
                          disabled={!!serviceBusy}
                        />
                      </div>
                      <div className="settings-info-item">
                        <SettingsFieldHead label={tr('serviceBackupsManualRetention')} hint={tr('serviceBackupsManualRetentionHint')} />
                        <input
                          type="number"
                          min="1"
                          className="form-input"
                          value={serviceForm.manual_retention_count}
                          onChange={(event) => setServiceForm((current) => ({ ...current, manual_retention_count: event.target.value }))}
                          disabled={!!serviceBusy}
                        />
                      </div>
                      <div className="settings-info-item">
                        <SettingsFieldHead label={tr('serviceBackupsPreRestoreRetention')} hint={tr('serviceBackupsPreRestoreRetentionHint')} />
                        <input
                          type="number"
                          min="1"
                          className="form-input"
                          value={serviceForm.pre_restore_retention_count}
                          onChange={(event) => setServiceForm((current) => ({ ...current, pre_restore_retention_count: event.target.value }))}
                          disabled={!!serviceBusy}
                        />
                      </div>
                      <div className="settings-info-item">
                        <SettingsFieldHead label={`${tr('serviceBackupsSchedulerCheck')} (${tr('serviceBackupsMinutes')})`} hint={tr('serviceBackupsSchedulerCheckHint')} />
                        <input
                          type="number"
                          min="1"
                          className="form-input"
                          value={serviceForm.scheduler_check_minutes}
                          onChange={(event) => setServiceForm((current) => ({ ...current, scheduler_check_minutes: event.target.value }))}
                          disabled={!!serviceBusy}
                        />
                      </div>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="settings-callout" style={{ marginBottom: '1rem' }}>
                      <p>{tr('serviceBackupsReloadHint')}</p>
                    </div>

                    <div className="settings-archives-list table-wrap-scroll">
                      {(serviceData?.backups || []).length === 0 ? (
                        <div className="settings-empty-text">{tr('serviceBackupsNoItems')}</div>
                      ) : (
                        (serviceData?.backups || []).map((backup) => (
                          <div key={backup.name} className="settings-archive-card">
                            <div className="settings-archive-main">
                              <div className="settings-archive-name">{backup.name}</div>
                              <div className="settings-archive-meta">
                                <span>{backupTypeLabel(backup.kind)}</span>
                                <span>{formatDateTime(backup.created_at)}</span>
                                <span>{formatBytes(backup.archive_size_bytes)}</span>
                              </div>
                            </div>
                            <div className="settings-archive-actions">
                              <button
                                className="btn btn-sm btn-secondary"
                                onClick={() => handleDownloadBackup(backup.name)}
                                disabled={!!serviceBusy}
                              >
                                {tr('download')}
                              </button>
                              <button
                                className="btn btn-sm btn-danger"
                                onClick={() => handleRestoreBackup(backup.name)}
                                disabled={!!serviceBusy}
                              >
                                {tr('restore')}
                              </button>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </>
                )}
              </>
            )}
          </SettingsSection>
        )}
          </div>
        </div>
      </div>

      <Modal
        isOpen={!!modal}
        onClose={() => setModal(false)}
        title={tr('enterprise')}
        maxWidth="500px"
      >
        {modal ? (
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
        ) : null}
      </Modal>

      <Modal
        isOpen={!!userModal}
        onClose={() => setUserModal(null)}
        title={userModal ? `${userModal === 'add' ? tr('add') : tr('edit')} ${tr('user')}` : ''}
        maxWidth="420px"
      >
        {userModal ? (
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
        ) : null}
      </Modal>

      <Modal
        isOpen={!!catModal}
        onClose={() => setCatModal(null)}
        title={catModal ? `${catModal === 'add' ? tr('add') : tr('edit')} ${UI_DASH} ${tr('categoriesTitle')}` : ''}
        maxWidth="480px"
      >
        {catModal ? (
              <form onSubmit={async (event) => {
                event.preventDefault()
                try {
                  const payload = {
                    ...catForm,
                    default_project_id: catForm.default_project_id ? parseInt(catForm.default_project_id, 10) : null,
                  }
                  if (catModal === 'add') await api.categories.create(payload)
                  else await api.categories.update(catModal.id, payload)
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
                <label className="form-label">{tr('project')}</label>
                <ProjectSelect
                  projects={projects}
                  value={catForm.default_project_id}
                  onChange={(nextValue) => setCatForm({ ...catForm, default_project_id: nextValue })}
                  allowEmpty
                  emptyLabel={UI_DASH}
                />
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
        ) : null}
      </Modal>
    </>
  )
}
