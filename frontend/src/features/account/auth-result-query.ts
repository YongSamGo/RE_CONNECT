// Callback values select a local screen only. They never establish a session.
export function parseAuthResultQuery(search: string) {
  const query = new URLSearchParams(search)
  const purpose = query.get('purpose')
  const status = query.get('status')
  if ([...query.keys()].length !== 2 || query.getAll('purpose').length !== 1
    || query.getAll('status').length !== 1
    || !['login', 'save', 'reauth'].includes(purpose ?? '')
    || !['success', 'cancelled', 'failed', 'expired'].includes(status ?? '')) return null
  return { purpose, status }
}
