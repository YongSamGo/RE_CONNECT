export type Activity = 'employment' | 'volunteering'
export type Profile = { experience: string; region: string; activities: Activity[] }
export const emptyProfile = (): Profile => ({ experience: '', region: '', activities: [] })
export function canConfirm(profile: Profile): boolean {
  return profile.experience.trim().length > 0 && profile.experience.length <= 2000
    && profile.region.trim().length > 0 && profile.region.length <= 100
    && profile.activities.length > 0
}
