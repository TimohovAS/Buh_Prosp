export function downloadBlobFile(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function downloadTextFile(content, filename, mimeType = 'text/plain;charset=utf-8;') {
  const blob = new Blob([content], { type: mimeType })
  downloadBlobFile(blob, filename)
}
