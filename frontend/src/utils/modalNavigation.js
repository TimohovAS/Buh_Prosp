export const MODAL_CHAIN_CLOSE_EVENT = 'prospel:modal-chain-close'

export function closeParentModalChain(returnPath) {
  if (!returnPath) return
  window.dispatchEvent(
    new CustomEvent(MODAL_CHAIN_CLOSE_EVENT, {
      detail: { returnPath },
    })
  )
}
