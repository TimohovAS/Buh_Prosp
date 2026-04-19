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

export function contractMatchesProject(contract, projectId) {
  if (!contract) return false
  if (projectId == null || projectId === '') return true
  return contract.project_id == null || String(contract.project_id) === String(projectId)
}

export function filterContractsForProject(contracts, projectId) {
  const normalizedProjectId = projectId == null || projectId === '' ? '' : String(projectId)

  return [...contracts]
    .filter((contract) => contractMatchesProject(contract, normalizedProjectId))
    .sort((left, right) => {
      if (normalizedProjectId) {
        const leftRank = String(left.project_id) === normalizedProjectId ? 0 : 1
        const rightRank = String(right.project_id) === normalizedProjectId ? 0 : 1
        if (leftRank !== rightRank) return leftRank - rightRank
      }
      return buildContractLabel(left).localeCompare(buildContractLabel(right), 'sr')
    })
}
