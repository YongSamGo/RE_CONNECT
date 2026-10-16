import type { components } from '../../api/schema'
export type ProfilePreferences = { regions: components['schemas']['Region'][]; activities: ('employment' | 'volunteering')[]; reviewed: boolean }
export const emptyPreferences = (): ProfilePreferences => ({ regions: [], activities: [], reviewed: false })
