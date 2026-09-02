import { useState, useEffect, useMemo } from 'react'
import {
  Building2,
  ContactRound,
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
  bank_accounts: '',
  contact: '',
  phone: '',
  email: '',
  website: '',
  client_type: 'legal',
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
    <div className="client-profile-contact-row" title={label} aria-label={label} role="group">
      <Icon aria-hidden="true" size={16} />
      <div className="client-profile-contact-value">{children}</div>
    </div>
  )
}

function ClientContacts({ client }) {
  const phones = splitContactValues(client.phone)
  const emails = splitContactValues(client.email)
  const websites = splitContactValues(client.website)
  const person = String(client.contact || '').trim()

  if (!person && !phones.length && !emails.length && !websites.length) {
    return <div className="client-profile-empty">{UI_DASH}</div>
  }

  return (
    <div className="client-profile-contact-list">
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
    setModal('add')
  }

  const openEdit = (item) => {
    setForm({
      name: item.name,
      address: item.address || '',
      pib: item.pib || '',
      maticni_broj: item.maticni_broj || '',
      bank_accounts: (item.bank_accounts || []).join('\n'),
      contact: item.contact || '',
      phone: item.phone || '',
      email: item.email || '',
      website: item.website || '',
      client_type: item.client_type || 'legal',
    })
    setModal({ type: 'edit', id: item.id })
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
            <div className="client-profile">
              <div className="client-profile-hero">
                <div className="client-profile-identity">
                  <span className="client-profile-avatar">
                    <Building2 aria-hidden="true" size={24} />
                  </span>
                  <div>
                    <span className="client-profile-type">{getClientTypeLabel(detailModal)}</span>
                    <h4>{detailModal.name || `#${detailModal.id}`}</h4>
                    <div className="client-profile-address">
                      <MapPin aria-hidden="true" size={15} />
                      <span>{detailModal.address || tr('addressNotSpecified')}</span>
                    </div>
                  </div>
                </div>
                <div className="client-profile-actions">
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

              <div className="client-profile-content">
                <section className="client-profile-panel client-profile-requisites">
                  <div className="client-profile-panel-title">
                    <Building2 aria-hidden="true" size={17} />
                    <h4>{tr('clientRequisites')}</h4>
                  </div>
                  <div className="client-profile-facts">
                    <div className="client-profile-fact">
                      <span>{tr('pib')}</span>
                      <strong>{detailModal.pib || UI_DASH}</strong>
                    </div>
                    <div className="client-profile-fact">
                      <span>{tr('maticniBroj')}</span>
                      <strong>{detailModal.maticni_broj || UI_DASH}</strong>
                    </div>
                    <div className="client-profile-fact">
                      <span>{tr('type')}</span>
                      <strong>{getClientTypeLabel(detailModal)}</strong>
                    </div>
                  </div>
                </section>

                <section className="client-profile-panel">
                  <div className="client-profile-panel-title">
                    <ContactRound aria-hidden="true" size={17} />
                    <h4>{tr('clientContacts')}</h4>
                  </div>
                  <ClientContacts client={detailModal} />
                </section>

                <section className="client-profile-panel">
                  <div className="client-profile-panel-title">
                    <Landmark aria-hidden="true" size={17} />
                    <h4>{tr('bankAccounts')}</h4>
                  </div>
                  {detailModal.bank_accounts?.length ? (
                    <div className="client-profile-bank-list">
                      {detailModal.bank_accounts.map((account) => (
                        <code key={account}>{account}</code>
                      ))}
                    </div>
                  ) : (
                    <div className="client-profile-empty">{UI_DASH}</div>
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
                    onChange={(event) => setForm({ ...form, pib: event.target.value })}
                    inputMode="numeric"
                    maxLength={20}
                  />
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
                    onChange={(event) => setForm({ ...form, maticni_broj: event.target.value })}
                    inputMode="numeric"
                    maxLength={20}
                  />
                </div>
                <div className="form-group client-form-field--span-3">
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
                  <label className="form-label" htmlFor="client-form-type">
                    {tr('type')}
                  </label>
                  <select
                    id="client-form-type"
                    className="form-input"
                    value={form.client_type}
                    onChange={(event) => setForm({ ...form, client_type: event.target.value })}
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
