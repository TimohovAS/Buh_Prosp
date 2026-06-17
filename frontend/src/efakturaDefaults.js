export const DEFAULT_EFAKTURA_API_BASE_URL = 'https://efaktura.mfin.gov.rs'
export const DEFAULT_EFAKTURA_INCOMING_LIST_PATH = '/api/publicApi/purchase-invoice/ids?dateFrom={from}&dateTo={to}'
export const DEFAULT_EFAKTURA_INCOMING_DOCUMENT_PATH = '/api/publicApi/purchase-invoice/xml?invoiceId={id}'
export const DEFAULT_EFAKTURA_OUTGOING_LIST_PATH = '/api/publicApi/sales-invoice/ids?dateFrom={from}&dateTo={to}'
export const DEFAULT_EFAKTURA_OUTGOING_DOCUMENT_PATH = '/api/publicApi/sales-invoice/xml?invoiceId={id}'

export function isEfakturaApiConfigured(settings) {
  return Boolean(
    settings?.efaktura_enabled &&
    settings?.efaktura_api_key &&
    (settings?.efaktura_sync_incoming || settings?.efaktura_sync_outgoing)
  )
}

export function usesEfakturaDefaultRoutes(settings) {
  return Boolean(
    settings &&
    !settings.efaktura_api_base_url &&
    !settings.efaktura_incoming_list_path &&
    !settings.efaktura_incoming_document_path &&
    !settings.efaktura_outgoing_list_path &&
    !settings.efaktura_outgoing_document_path
  )
}
