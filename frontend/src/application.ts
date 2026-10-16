export const applicationTextLimit = 2000
export type ApplicationDraft = {
  introduction: string
  motivation: string
  profileVersion: number
  approved: boolean
}
export const emptyApplication = (profileVersion: number): ApplicationDraft => ({
  introduction: '', motivation: '', profileVersion, approved: false,
})
export function canApproveApplication(draft: ApplicationDraft): boolean {
  return [draft.introduction, draft.motivation].every(text => text.trim().length > 0 && text.length <= applicationTextLimit)
}
export function applicationText(draft: ApplicationDraft): string {
  return `자기소개\n${draft.introduction}\n\n지원동기\n${draft.motivation}`
}
