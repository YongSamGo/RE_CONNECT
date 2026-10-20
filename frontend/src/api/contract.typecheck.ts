import { createApiClient } from './client'
import type { components } from './schema'

// Compiled by tsc, never run or imported by the app. @ts-expect-error also fails
// if a future contract unexpectedly starts allowing these invalid requests.
async function contractChecks() {
  const api = createApiClient()
  const me = await api.GET('/me')
  const authenticated: boolean | undefined = me.data?.authenticated
  void authenticated
  await api.GET('/opportunities', { params: { query: { page: 1, activity_type: 'employment' } } })
  await api.POST('/journeys', {
    params: { header: { 'Idempotency-Key': crypto.randomUUID() } },
    body: { ai_notice_version: 'test-notice', saved_profile: null },
  })
  await api.POST('/journeys/{journey_id}/transcriptions', {
    params: { path: { journey_id: crypto.randomUUID() }, header: { 'Idempotency-Key': crypto.randomUUID() } },
    body: { audio: new Blob(['test'], { type: 'audio/webm' }) },
    bodySerializer(body) {
      const form = new FormData()
      form.set('audio', body.audio, 'recording.webm')
      return form
    },
  })
  // @ts-expect-error A route absent from the contract cannot be called.
  await api.GET('/invented-endpoint')
  // @ts-expect-error Internal health must not be exposed by the browser client.
  await api.GET('/health/ready')
  // @ts-expect-error OAuth requires navigation with server state, not API fetch.
  await api.GET('/auth/kakao/start')
  // @ts-expect-error Wrong HTTP method for /me.
  await api.POST('/me')
  // @ts-expect-error activity_type has a closed enum.
  await api.GET('/opportunities', { params: { query: { activity_type: 'mentoring' } } })
  // @ts-expect-error Required request body and idempotency header are missing.
  await api.POST('/journeys')
  // @ts-expect-error A valid body still requires an explicit idempotency key.
  await api.POST('/journeys', { body: { ai_notice_version: 'test-notice', saved_profile: null } })
  // @ts-expect-error Explicit null is required for the optional saved profile.
  const missingNull: components['schemas']['JourneyCreate'] = { ai_notice_version: 'test-notice' }
  void missingNull
}
void contractChecks
