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
