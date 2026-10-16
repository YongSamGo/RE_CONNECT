export type ManualDraft = { introduction: string; motivation: string; reviewed: boolean }
export const emptyManualDraft = (): ManualDraft => ({ introduction: '', motivation: '', reviewed: false })
