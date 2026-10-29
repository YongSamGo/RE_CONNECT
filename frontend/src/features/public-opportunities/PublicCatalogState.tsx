import type { ReactNode } from 'react'
import { useMemoryScope } from '../../state/useMemoryScope'
import { emptySearch, PublicCatalogContext } from './public-catalog-state'
import type { CatalogState } from './public-catalog-state'

/** Public search survives SPA detail navigation in RAM only, never history/storage. */
export function PublicCatalogProvider({ children }: { children: ReactNode }) {
  const draft = useMemoryScope(emptySearch)
  const result = useMemoryScope<CatalogState>(() => ({ status: 'idle' }))
  const resultsOnly = useMemoryScope(() => false)
  return <PublicCatalogContext.Provider value={{ draft, result, resultsOnly }}>{children}</PublicCatalogContext.Provider>
}
