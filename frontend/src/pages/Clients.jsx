import { useState, useEffect, useMemo } from 'react'
import {
  AlertCircle,
  Building2,
  Check,
  ContactRound,
  Database,
  Globe2,
  Landmark,
  Mail,
  MapPin,
  Pencil,
  Phone,
  Trash2,
  UserRound,
} from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { tr } from '../i18n'
import EntityDetailModal from '../components/EntityDetailModal'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'
import SearchInput from '../components/SearchInput'
import SortIndicator from '../components/SortIndicator'
import useListPageState from '../hooks/useListPageState'
import { UI_DASH } from '../utils/formatters'

const EMPTY_CLIENT_FORM = {
  name: '',
  address: '',
  pib: '',
  maticni_broj: '',
  jbkjs: '',
  bank_accounts: '',
  contact: '',
  phone: '',
  email: '',
  website: '',
  client_type: 'legal',
}

const EMPTY_REGISTRY_LOOKUP = {
  status: 'idle',
  matches: [],
  data: null,
  error: '',
}

function registryDigits(value) {
  return String(value || '').replace(/\D/g, '')
}

function splitContactValues(value) {
  return String(value || '')
    .split(/[,;\n]+/)
    .map((part) => part.trim())
    .filter(Boolean)
}

function ClientContactRow({ icon: Icon, label, children }) {
  // Тип контакта показывает иконка, поэтому подпись живёт только в подсказке
  return (
    <div className="record-profile-contact-row" title={label} aria-label={label} role="group">
      <Icon aria-hidden="true" size={16} />
      <div className="record-profile-contact-value">{children}</div>
    </div>
  )
}

function ClientContacts({ client }) {
  const phones = splitContactValues(client.phone)
  const emails = splitContactValues(client.email)
  const websites = splitContactValues(client.website)
  const person = String(client.contact || '').trim()

  if (!person && !phones.length && !emails.length && !websites.length) {
    return <div className="record-profile-empty">{UI_DASH}</div>
  }

  return (
    <div className="record-profile-contact-list">
      {person ? (
        <ClientContactRow icon={UserRound} label={tr('contactPerson')}>
          <span>{person}</span>
        </ClientContactRow>
      ) : null}
      {phones.length ? (
        <ClientContactRow icon={Phone} label={tr('phone')}>
          {phones.map((phone) => (
            // tel: не принимает пробелы и слэши сербской записи номера
            <a key={phone} href={`tel:${phone.replace(/[^\d+]/g, '')}`}>
              {phone}
            </a>
          ))}
        </ClientContactRow>
      ) : null}
      {emails.length ? (
        <ClientContactRow icon={Mail} label={tr('email')}>
          {emails.map((email) => (
            <a key={email} href={`mailto:${email}`}>
              {email}
            </a>
          ))}
        </ClientContactRow>
      ) : null}
      {websites.length ? (
        <ClientContactRow icon={Globe2} label={tr('website')}>
          {websites.map((website) => (
            <a
              key={website}
              href={website.startsWith('http') ? website : `https://${website}`}
              target="_blank"
              rel="noreferrer"
            >
              {website}
            </a>
          ))}
        </ClientContactRow>
      ) : null}
    </div>
  )
}

export default function Clients() {
  const location = useLocation()
  const isActivePage = location.pathname === '/clients'
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [detailModal, setDetailModal] = useState(null)
  const [modal, setModal] = useState(null)
  const { search, setSearch, sortCol, sortAsc, toggleSort } = useListPageState({
    initialSortCol: 'name',
    initialSortAsc: true,
  })
  const [form, setForm] = useState(EMPTY_CLIENT_FORM)
  const [registryLookupField, setRegistryLookupField] = useState(null)
  const [registryLookup, setRegistryLookup] = useState(EMPTY_REGISTRY_LOOKUP)

  const load = () => {
    setLoading(true)
    api.clients
      .list({ search, archived: false })
      .then(setItems)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!isActivePage) return
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, isActivePage])

  const openAdd = () => {
    setForm(EMPTY_CLIENT_FORM)
    setRegistryLookupField(null)
    setRegistryLookup(EMPTY_REGISTRY_LOOKUP)
    setModal('add')
  }

  const openEdit = (item) => {
    setForm({
      name: item.name,
      address: item.address || '',
      pib: item.pib || '',
      maticni_broj: item.maticni_broj || '',
      jbkjs: item.jbkjs || '',
      bank_accounts: (item.bank_accounts || []).join('\n'),
      contact: item.contact || '',
      phone: item.phone || '',
      email: item.email || '',
      website: item.website || '',
      client_type: item.client_type || 'legal',
    })
    setRegistryLookupField(null)
    setRegistryLookup(EMPTY_REGISTRY_LOOKUP)
    setModal({ type: 'edit', id: item.id })
  }

  useEffect(() => {
    if (!modal || form.client_type !== 'legal' || !registryLookupField) return undefined

    const rawValue = registryLookupField === 'pib' ? form.pib : form.maticni_broj
    const value = registryDigits(rawValue)
    const requiredLength = registryLookupField === 'pib' ? 9 : 8
    if (value.length !== requiredLength) {
      setRegistryLookup(EMPTY_REGISTRY_LOOKUP)
      return undefined
    }

    let cancelled = false
    const timer = window.setTimeout(() => {
      setRegistryLookup({ status: 'loading', matches: [], data: null, error: '' })
      const excludeClientId = modal?.type === 'edit' ? modal.id : null
      api.clients
        .lookupCompanyRegistry(registryLookupField, value, excludeClientId)
        .then((data) => {
          if (cancelled) return
          if (!data.available) {
            setRegistryLookup({
              status: 'unavailable',
              matches: [],
              data,
              error: tr('companyRegistryUnavailable'),
            })
            return
          }
          setRegistryLookup({
            status: data.matches?.length ? 'found' : 'empty',
            matches: data.matches || [],
            data,
            error: '',
          })
        })
        .catch(() => {
          if (!cancelled) {
            setRegistryLookup({
              status: 'unavailable',
              matches: [],
              data: null,
              error: tr('companyRegistryUnavailable'),
            })
          }
        })
    }, 500)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [form.client_type, form.maticni_broj, form.pib, modal, registryLookupField])

  const applyRegistryMatch = (match) => {
    if (match.existing_client_id) return
    setForm((current) => ({
      ...current,
      name: String(match.name || current.name).slice(0, 200),
      pib: match.pib || current.pib,
      maticni_broj: match.maticni_broj || current.maticni_broj,
      jbkjs: match.jbkjs || current.jbkjs,
      client_type: 'legal',
    }))
    setRegistryLookupField(null)
    setRegistryLookup((current) => ({ ...current, status: 'applied' }))
  }

  const openExistingRegistryClient = async (match) => {
    try {
      const existing = items.find((item) => item.id === match.existing_client_id)
      const client = existing || (await api.clients.get(match.existing_client_id))
      setModal(null)
      setDetailModal(client)
    } catch (error) {
      console.error(error)
    }
  }

  const openDetail = (item) => {
    setDetailModal(item)
  }

  const openEditFromDetail = (item) => {
    setDetailModal(null)
    openEdit(item)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    try {
      const payload = {
        ...form,
        bank_accounts: form.bank_accounts
          .split(/[\n,;]+/)
          .map((value) => value.trim())
          .filter(Boolean),
      }
      if (modal === 'add') {
        await api.clients.create(payload)
      } else {
        await api.clients.update(modal.id, payload)
      }
      setModal(null)
      load()
    } catch (err) {
      console.error(err)
    }
  }

  const handleDeleteFromDetail = async (item) => {
    if (!confirm(tr('archiveClient'))) return
    try {
      await api.clients.delete(item.id)
      setDetailModal(null)
      load()
    } catch (err) {
      console.error(err)
    }
  }

  const sorted = useMemo(() => {
    return [...items].sort((left, right) => {
      const leftValue = left[sortCol] ?? ''
      const rightValue = right[sortCol] ?? ''
      if (leftValue < rightValue) return sortAsc ? -1 : 1
      if (leftValue > rightValue) return sortAsc ? 1 : -1
      return 0
    })
  }, [items, sortCol, sortAsc])

  const getClientTypeLabel = (client) =>
    client.client_type === 'legal' ? tr('legalEntity') : tr('individualEntity')

  return (
    <>
      <PageHeader
        title={tr('clients')}
        actions={
          <>
            <SearchInput
              placeholder={tr('search')}
              value={search}
              onChange={setSearch}
              style={{ width: 200 }}
            />
            <button className="btn btn-primary" onClick={openAdd}>
              {tr('add')}
            </button>
          </>
        }
      />

      <div className="page-body">
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('name')}>
                    {tr('name')} <SortIndicator active={sortCol === 'name'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('address')}>
                    {tr('address')} <SortIndicator active={sortCol === 'address'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('pib')}>
                    {tr('pib')} <SortIndicator active={sortCol === 'pib'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('maticni_broj')}>
                    {tr('maticniBroj')} <SortIndicator active={sortCol === 'maticni_broj'} asc={sortAsc} />
                  </th>
                  <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('client_type')}>
                    {tr('type')} <SortIndicator active={sortCol === 'client_type'} asc={sortAsc} />
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={5}>{tr('loading')}</td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ color: 'var(--color-text-muted)' }}>
                      {tr('noClients')}
                    </td>
                  </tr>
                ) : (
                  sorted.map((client) => (
                    <tr
                      key={client.id}
                      className="record-row"
                      onClick={() => openDetail(client)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          openDetail(client)
                        }
                      }}
                      tabIndex={0}
                    >
                      <td>{client.name}</td>
                      <td>
                        <span className="record-cell-ellipsis">{client.address || UI_DASH}</span>
                      </td>
                      <td>{client.pib || UI_DASH}</td>
                      <td>{client.maticni_broj || UI_DASH}</td>
                      <td>{getClientTypeLabel(client)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <EntityDetailModal
        isOpen={!!detailModal}
        onClose={() => setDetailModal(null)}
        title={tr('clientDetails')}
        maxWidth="920px"
        className="client-detail-modal"
        details={
          detailModal ? (
            <div className="record-profile">
              <div className="record-profile-hero">
                <div className="record-profile-identity">
                  <span className="record-profile-avatar">
                    <Building2 aria-hidden="true" size={24} />
                  </span>
                  <div>
                    <span className="record-profile-eyebrow">{getClientTypeLabel(detailModal)}</span>
                    <h4>{detailModal.name || `#${detailModal.id}`}</h4>
                    <div className="record-profile-subtitle">
                      <MapPin aria-hidden="true" size={15} />
                      <span>{detailModal.address || tr('addressNotSpecified')}</span>
                    </div>
                  </div>
                </div>
                <div className="record-profile-actions">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => openEditFromDetail(detailModal)}
                  >
                    <Pencil aria-hidden="true" size={16} /> {tr('edit')}
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={() => handleDeleteFromDetail(detailModal)}
                  >
                    <Trash2 aria-hidden="true" size={16} /> {tr('delete')}
                  </button>
                </div>
              </div>

              <div className="record-profile-content">
                <section className="record-profile-panel record-profile-panel--wide">
                  <div className="record-profile-panel-title">
                    <Building2 aria-hidden="true" size={17} />
                    <h4>{tr('clientRequisites')}</h4>
                  </div>
                  <div className="record-profile-facts">
                    <div className="record-profile-fact">
                      <span>{tr('pib')}</span>
                      <strong>{detailModal.pib || UI_DASH}</strong>
                    </div>
                    <div className="record-profile-fact">
                      <span>{tr('maticniBroj')}</span>
                      <strong>{detailModal.maticni_broj || UI_DASH}</strong>
                    </div>
                    <div className="record-profile-fact">
                      <span>{tr('jbkjs')}</span>
                      <strong>{detailModal.jbkjs || UI_DASH}</strong>
                    </div>
                    <div className="record-profile-fact">
                      <span>{tr('type')}</span>
                      <strong>{getClientTypeLabel(detailModal)}</strong>
                    </div>
                  </div>
                </section>

                <section className="record-profile-panel">
                  <div className="record-profile-panel-title">
                    <ContactRound aria-hidden="true" size={17} />
                    <h4>{tr('clientContacts')}</h4>
                  </div>
                  <ClientContacts client={detailModal} />
                </section>

                <section className="record-profile-panel">
                  <div className="record-profile-panel-title">
                    <Landmark aria-hidden="true" size={17} />
                    <h4>{tr('bankAccounts')}</h4>
                  </div>
                  {detailModal.bank_accounts?.length ? (
                    <div className="record-profile-code-list">
                      {detailModal.bank_accounts.map((account) => (
                        <code key={account}>{account}</code>
                      ))}
                    </div>
                  ) : (
                    <div className="record-profile-empty">{UI_DASH}</div>
                  )}
                </section>
              </div>
            </div>
          ) : null
        }
      />

      <Modal
        isOpen={!!modal}
        onClose={() => setModal(null)}
        title={`${modal === 'add' ? tr('add') : tr('edit')} ${tr('clientForm')}`}
        className="client-form-modal"
        bodyClassName="client-form-modal-body"
        maxWidth="860px"
        resizable={false}
      >
        {modal ? (
          <form className="client-form" onSubmit={handleSubmit}>
            <section className="client-form-section">
              <div className="client-form-section-title">
                <Building2 aria-hidden="true" size={17} />
                <h4>{tr('clientRequisites')}</h4>
              </div>
              <div className="client-form-fields">
                <div className="form-group client-form-field--span-2">
                  <label className="form-label" htmlFor="client-form-name">
                    {tr('name')}
                  </label>
                  <input
                    id="client-form-name"
                    type="text"
                    className="form-input"
                    value={form.name}
                    onChange={(event) => setForm({ ...form, name: event.target.value })}
                    maxLength={200}
                    autoFocus
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="client-form-pib">
                    {tr('pib')}
                  </label>
                  <input
                    id="client-form-pib"
                    type="text"
                    className="form-input"
                    value={form.pib}
                    onChange={(event) => {
                      setForm({ ...form, pib: event.target.value })
                      setRegistryLookupField('pib')
                    }}
                    inputMode="numeric"
                    maxLength={20}
                  />
                  <small className="client-form-hint">{tr('companyRegistryPibHint')}</small>
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="client-form-maticni">
                    {tr('maticniBroj')}
                  </label>
                  <input
                    id="client-form-maticni"
                    type="text"
                    className="form-input"
                    value={form.maticni_broj}
                    onChange={(event) => {
                      setForm({ ...form, maticni_broj: event.target.value })
                      setRegistryLookupField('maticni_broj')
                    }}
                    inputMode="numeric"
                    maxLength={20}
                  />
                  <small className="client-form-hint">{tr('companyRegistryMbHint')}</small>
                </div>
                {registryLookup.status !== 'idle' ? (
                  <div className="client-form-field--span-4 client-registry-lookup" aria-live="polite">
                    {registryLookup.status === 'loading' ? (
                      <div className="client-registry-state">
                        <Database aria-hidden="true" size={17} />
                        <span>{tr('companyRegistrySearching')}</span>
                      </div>
                    ) : null}

                    {registryLookup.status === 'empty' ? (
                      <div className="client-registry-state client-registry-state--muted">
                        <AlertCircle aria-hidden="true" size={17} />
                        <span>{tr('companyRegistryNotFound')}</span>
                      </div>
                    ) : null}

                    {registryLookup.status === 'empty' && registryLookup.data?.warning ? (
                      <div className="client-registry-state client-registry-state--warning">
                        <AlertCircle aria-hidden="true" size={17} />
                        <span>
                          {tr(
                            registryLookup.data.stale ? 'companyRegistryStale' : 'companyRegistryIncomplete'
                          )}
                        </span>
                      </div>
                    ) : null}

                    {registryLookup.status === 'unavailable' ? (
                      <div className="client-registry-state client-registry-state--warning">
                        <AlertCircle aria-hidden="true" size={17} />
                        <span>{registryLookup.error || tr('companyRegistryUnavailable')}</span>
                      </div>
                    ) : null}

                    {['found', 'applied'].includes(registryLookup.status) ? (
                      <div className="client-registry-results">
                        <div className="client-registry-heading">
                          <span>
                            <Database aria-hidden="true" size={17} />
                            {tr('companyRegistrySuggestion')}
                          </span>
                          {registryLookup.status === 'applied' ? (
                            <span className="client-registry-applied">
                              <Check aria-hidden="true" size={15} /> {tr('companyRegistryApplied')}
                            </span>
                          ) : null}
                        </div>
                        {registryLookup.matches.map((match, index) => (
                          <div
                            className={`client-registry-match${match.existing_client_id ? ' has-conflict' : ''}`}
                            key={`${match.pib || ''}-${match.maticni_broj || ''}-${match.jbkjs || ''}-${index}`}
                          >
                            <div className="client-registry-match-main">
                              <strong>{match.name}</strong>
                              <span>
                                {match.pib ? `PIB ${match.pib}` : null}
                                {match.pib && match.maticni_broj ? ' · ' : null}
                                {match.maticni_broj ? `${tr('maticniBroj')} ${match.maticni_broj}` : null}
                                {match.jbkjs ? ` · JBKJS ${match.jbkjs}` : null}
                              </span>
                              <div className="client-registry-meta">
                                {match.municipality ? (
                                  <span>{`${tr('companyRegistryMunicipality')}: ${match.municipality}`}</span>
                                ) : null}
                                {match.status ? (
                                  <span>{`${tr('companyRegistryStatus')}: ${match.status}`}</span>
                                ) : null}
                                {match.legal_form ? <span>{match.legal_form}</span> : null}
                                {match.founded_on ? (
                                  <span>{`${tr('companyRegistryFounded')}: ${match.founded_on}`}</span>
                                ) : null}
                                {match.activity_code ? (
                                  <span>{`${tr('companyRegistryActivity')}: ${match.activity_code}`}</span>
                                ) : null}
                              </div>
                              {match.existing_client_id ? (
                                <span className="client-registry-conflict">
                                  {tr('companyRegistryExistingClient', {
                                    name: match.existing_client_name,
                                  })}
                                </span>
                              ) : null}
                            </div>
                            {match.existing_client_id ? (
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => openExistingRegistryClient(match)}
                              >
                                {tr('companyRegistryOpenClient')}
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="btn btn-primary btn-sm"
                                onClick={() => applyRegistryMatch(match)}
                              >
                                {tr('companyRegistryApply')}
                              </button>
                            )}
                          </div>
                        ))}
                        <div className="client-registry-source">
                          <span>{tr('companyRegistryAddressNotice')}</span>
                          <span className="client-registry-attribution">
                            {tr('companyRegistryProcessed')}
                          </span>
                          <span>
                            {registryLookup.data?.matches?.[0]?.sources?.map((source, index) => {
                              const labelKey =
                                source.code === 'apr_open_data'
                                  ? 'companyRegistrySourceApr'
                                  : source.code === 'sef_company_list'
                                    ? 'companyRegistrySourceSef'
                                    : null
                              return (
                                <span key={source.code}>
                                  {index ? ' · ' : ''}
                                  <a href={source.url} target="_blank" rel="noreferrer">
                                    {labelKey ? tr(labelKey) : source.label}
                                  </a>
                                </span>
                              )
                            })}
                            {registryLookup.data?.matches?.[0]?.sources?.some(
                              (source) => source.code === 'apr_open_data'
                            ) && registryLookup.data?.apr_snapshot_date
                              ? ` · ${tr('companyRegistrySnapshot', {
                                  date: registryLookup.data.apr_snapshot_date,
                                })}`
                              : null}
                            {registryLookup.data?.refreshed_at
                              ? ` · ${tr('companyRegistryDownloaded', {
                                  date: registryLookup.data.refreshed_at.slice(0, 10),
                                })}`
                              : null}
                          </span>
                          {registryLookup.data?.warning ? (
                            <span>
                              {tr(
                                registryLookup.data.stale
                                  ? 'companyRegistryStale'
                                  : 'companyRegistryIncomplete'
                              )}
                            </span>
                          ) : null}
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <div className="form-group client-form-field--span-2">
                  <label className="form-label" htmlFor="client-form-address">
                    {tr('address')}
                  </label>
                  <input
                    id="client-form-address"
                    type="text"
                    className="form-input"
                    value={form.address}
                    onChange={(event) => setForm({ ...form, address: event.target.value })}
                    maxLength={500}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="client-form-jbkjs">
                    {tr('jbkjs')}
                  </label>
                  <input
                    id="client-form-jbkjs"
                    type="text"
                    className="form-input"
                    value={form.jbkjs}
                    onChange={(event) => setForm({ ...form, jbkjs: event.target.value })}
                    inputMode="numeric"
                    maxLength={20}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="client-form-type">
                    {tr('type')}
                  </label>
                  <select
                    id="client-form-type"
                    className="form-input"
                    value={form.client_type}
                    onChange={(event) => {
                      const clientType = event.target.value
                      setForm({ ...form, client_type: clientType })
                      if (clientType !== 'legal') {
                        setRegistryLookupField(null)
                        setRegistryLookup(EMPTY_REGISTRY_LOOKUP)
                      }
                    }}
                  >
                    <option value="legal">{tr('legalEntity')}</option>
                    <option value="individual">{tr('individualEntity')}</option>
                  </select>
                </div>
              </div>
            </section>

            <section className="client-form-section">
              <div className="client-form-section-title">
                <ContactRound aria-hidden="true" size={17} />
                <h4>{tr('clientContacts')}</h4>
              </div>
              <div className="client-form-fields client-form-fields--pairs">
                <div className="form-group client-form-field--span-2">
                  <label className="form-label" htmlFor="client-form-contact">
                    {tr('contactPerson')}
                  </label>
                  <input
                    id="client-form-contact"
                    type="text"
                    className="form-input"
                    value={form.contact}
                    onChange={(event) => setForm({ ...form, contact: event.target.value })}
                    maxLength={200}
                  />
                </div>
                <div className="form-group client-form-field--span-2">
                  <label className="form-label" htmlFor="client-form-phone">
                    {tr('phone')}
                  </label>
                  <input
                    id="client-form-phone"
                    type="tel"
                    className="form-input"
                    value={form.phone}
                    onChange={(event) => setForm({ ...form, phone: event.target.value })}
                    maxLength={100}
                  />
                  <small className="client-form-hint">{tr('clientPhoneHint')}</small>
                </div>
                <div className="form-group client-form-field--span-2">
                  <label className="form-label" htmlFor="client-form-email">
                    {tr('email')}
                  </label>
                  <input
                    id="client-form-email"
                    type="text"
                    className="form-input"
                    inputMode="email"
                    value={form.email}
                    onChange={(event) => setForm({ ...form, email: event.target.value })}
                    maxLength={120}
                  />
                </div>
                <div className="form-group client-form-field--span-2">
                  <label className="form-label" htmlFor="client-form-website">
                    {tr('website')}
                  </label>
                  <input
                    id="client-form-website"
                    type="text"
                    className="form-input"
                    inputMode="url"
                    value={form.website}
                    onChange={(event) => setForm({ ...form, website: event.target.value })}
                    maxLength={200}
                  />
                </div>
              </div>
            </section>

            <section className="client-form-section">
              <div className="client-form-section-title">
                <Landmark aria-hidden="true" size={17} />
                <h4>{tr('bankAccounts')}</h4>
              </div>
              <textarea
                className="form-input"
                aria-label={tr('bankAccounts')}
                value={form.bank_accounts}
                onChange={(event) => setForm({ ...form, bank_accounts: event.target.value })}
                rows={3}
              />
              <small className="client-form-hint">{tr('bankAccountsHint')}</small>
            </section>

            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>
                {tr('cancel')}
              </button>
              <button type="submit" className="btn btn-primary">
                {tr('save')}
              </button>
            </div>
          </form>
        ) : null}
      </Modal>
    </>
  )
}
