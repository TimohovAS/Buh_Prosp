import { useEffect, useState } from 'react'
import { api } from '../api'

const STORAGE_KEY = 'prospel_enterprise_brand'
const UPDATE_EVENT = 'enterprise-brand-updated'
const DEFAULT_BRAND = {
  name: 'ProspEl',
  emblem_data_url: '',
}

function normalizeBrand(value) {
  return {
    name: value?.name || DEFAULT_BRAND.name,
    emblem_data_url: value?.emblem_data_url || '',
  }
}

function readStoredBrand() {
  if (typeof window === 'undefined') return DEFAULT_BRAND
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? normalizeBrand(JSON.parse(raw)) : DEFAULT_BRAND
  } catch {
    return DEFAULT_BRAND
  }
}

function writeStoredBrand(value) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalizeBrand(value)))
  } catch {
  }
}

function ensureFaviconLink() {
  let link = document.querySelector('link[rel="icon"]')
  if (!link) {
    link = document.createElement('link')
    link.setAttribute('rel', 'icon')
    document.head.appendChild(link)
  }
  return link
}

function applyFavicon(value) {
  if (typeof document === 'undefined') return
  const brand = normalizeBrand(value)
  const link = ensureFaviconLink()
  if (brand.emblem_data_url) {
    const mime = brand.emblem_data_url.startsWith('data:')
      ? brand.emblem_data_url.slice(5, brand.emblem_data_url.indexOf(';'))
      : ''
    link.setAttribute('href', brand.emblem_data_url)
    if (mime) link.setAttribute('type', mime)
    else link.removeAttribute('type')
  } else {
    link.setAttribute('href', '/favicon.ico')
    link.removeAttribute('type')
  }
}

export function broadcastEnterpriseBrand(value) {
  if (typeof window === 'undefined') return normalizeBrand(value)
  const brand = normalizeBrand(value)
  writeStoredBrand(brand)
  applyFavicon(brand)
  window.dispatchEvent(new CustomEvent(UPDATE_EVENT, { detail: brand }))
  return brand
}

export function useEnterpriseBrand() {
  const [brand, setBrand] = useState(() => readStoredBrand())

  useEffect(() => {
    let active = true

    const handleBrandUpdate = (event) => {
      const next = normalizeBrand(event.detail)
      writeStoredBrand(next)
      applyFavicon(next)
      if (active) setBrand(next)
    }

    window.addEventListener(UPDATE_EVENT, handleBrandUpdate)

    api.enterprise.branding()
      .then((response) => {
        const next = normalizeBrand(response)
        writeStoredBrand(next)
        applyFavicon(next)
        if (active) setBrand(next)
      })
      .catch(() => {
        applyFavicon(readStoredBrand())
      })

    return () => {
      active = false
      window.removeEventListener(UPDATE_EVENT, handleBrandUpdate)
    }
  }, [])

  return brand
}