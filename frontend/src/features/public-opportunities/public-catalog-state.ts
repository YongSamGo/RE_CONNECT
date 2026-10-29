import { createContext, useContext } from 'react'
import type { useMemoryScope } from '../../state/useMemoryScope'
import type { ApiError } from '../../api/errors'
import type { OpportunityList, Search } from './catalog'

export type CatalogState = { status: 'idle' }
  | { status: 'loading'; query: Search; page: number }
  | { status: 'loaded'; query: Search; result: OpportunityList }
  | { status: 'error'; query: Search; page: number; error: ApiError }
export const emptySearch = (): Search => ({ q: '', regions: [], activity_type: '' })
type CatalogMemory = {
  draft: ReturnType<typeof useMemoryScope<Search>>
  result: ReturnType<typeof useMemoryScope<CatalogState>>
  resultsOnly: ReturnType<typeof useMemoryScope<boolean>>
}
export const PublicCatalogContext = createContext<CatalogMemory | null>(null)
export const usePublicCatalog = () => useContext(PublicCatalogContext)
