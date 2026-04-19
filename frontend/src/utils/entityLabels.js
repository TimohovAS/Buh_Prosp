import { UI_DASH } from './formatters'

export function buildContractLabel(contract, emptyLabel = UI_DASH) {
  if (!contract) return emptyLabel
  const parts = [contract.number, contract.subject].filter(Boolean)
  return parts.join(` ${UI_DASH} `) || contract.number || contract.subject || emptyLabel
}

export function getProjectName(projects, projectId, emptyLabel = UI_DASH) {
  if (projectId == null || projectId === '') return emptyLabel
  return projects.find((project) => project.id === projectId)?.name || emptyLabel
}
