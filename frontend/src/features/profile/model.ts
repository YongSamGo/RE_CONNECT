import type { components } from '../../api/schema'
export type ProfilePreferences = { regions: components['schemas']['Province'][]; activities: ('employment' | 'volunteering')[]; reviewed: boolean }
export const emptyPreferences = (): ProfilePreferences => ({ regions: [], activities: [], reviewed: false })
