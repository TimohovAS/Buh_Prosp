// Сколько отправить в cash_paid_amount. В поле — только то, что ввёл человек:
// пустое поле уходит как null, и сумму считает сервер (форма показывает его же
// расчёт для текущего черновика). Скрытых подставленных чисел нет, поэтому
// видимое и сохранённое не могут разойтись.
export const payoutCashForSubmit = (fieldValue) => {
  const value = String(fieldValue ?? '').trim()
  if (value === '') return null
  const amount = Number(value)
  return Number.isFinite(amount) ? amount : null
}

// Можно ли сохранять выплату: только когда есть серверный расчёт именно того
// черновика, что на экране. Ответ для прежнего черновика или ошибка расчёта —
// не повод сохранять по местным цифрам: они не знают, сколько уже закрыто
// покупками, и видимое разошлось бы с сохранённым.
export const payoutPreviewState = (serverPreview, draftKey) => {
  const forDraft = serverPreview && draftKey && serverPreview.key === draftKey ? serverPreview : null
  const failed = !!forDraft?.failed
  const ready = !!forDraft && !failed
  return { ready, failed, data: ready ? forDraft.data : null }
}
