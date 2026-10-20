import type { components } from '../../api/schema'
import { invalid, isOpportunityId, record, timestamp } from '../public-opportunities/catalog'
import { parseProfileView } from '../profile/server-model'

export type MessageResult = components['schemas']['MessageResult']
export type MessageInput = components['schemas']['MessageCreate']
export type ProfileView = components['schemas']['ProfileDraftView']
export const firstQuestion = '지금까지 해 오신 일 가운데 기억에 남는 일을 한 가지 들려주세요.'

export function profileQuestion(view: ProfileView): string | null {
  const missing = view.missing_for_recommendation
  return missing.includes('experiences') ? firstQuestion : missing.includes('preferred_regions') ? '어느 지역에서 활동하고 싶으세요?'
    : missing.includes('activity_types') ? '취업과 봉사 중 어떤 활동을 원하세요?' : null
}

function text(value: unknown, max: number): string {
  return typeof value === 'string' && !!value.trim() && [...value].length <= max ? value : invalid()
}
export function parseMessageResult(value: unknown, baseRevision: number): MessageResult {
  const item = record(value), profile = parseProfileView(item.profile)
  if (item.revision !== baseRevision + 1 || profile.revision !== item.revision
    || typeof item.user_message_id !== 'string' || !isOpportunityId(item.user_message_id)
    || !Array.isArray(item.notices) || item.notices.length > 10
    || !['continue', 'review_profile'].includes(item.next_step as string)
    || (item.assistant_message === null) !== (item.next_step === 'review_profile')
    || (profile.missing_for_recommendation.length === 0) !== (item.next_step === 'review_profile')) return invalid()
  let assistant: MessageResult['assistant_message'] = null
  if (item.assistant_message !== null) {
    const message = record(item.assistant_message)
    if (typeof message.message_id !== 'string' || !isOpportunityId(message.message_id)
      || message.message_id === item.user_message_id || !timestamp(message.created_at)) return invalid()
    assistant = { message_id: message.message_id, text: text(message.text, 2000), created_at: message.created_at as string }
  }
  return { revision: profile.revision, profile, user_message_id: item.user_message_id,
    assistant_message: assistant, notices: item.notices.map(value => text(value, 300)), next_step: item.next_step as MessageResult['next_step'] }
}
