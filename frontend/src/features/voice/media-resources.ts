const recordingTypes = ['audio/webm;codecs=opus', 'audio/mp4;codecs=mp4a.40.2', 'audio/mp4']

export function recordingType(): string | undefined {
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') return undefined
  try { return recordingTypes.find(type => MediaRecorder.isTypeSupported(type)) } catch { return undefined }
}

// Cleanup must continue to the microphone even if a browser media operation
// throws. No device details are logged or shown to the user.
export function releasePlayer(player: HTMLAudioElement | null) {
  if (!player) return
  player.onended = null
  player.onerror = null
  try { player.pause() } catch { /* Continue releasing the source. */ }
  try { player.removeAttribute('src') } catch { /* Continue releasing the source. */ }
  try { player.load() } catch { /* Continue releasing other resources. */ }
}

export function stopTracks(stream: MediaStream | null) {
  if (!stream) return
  for (const track of stream.getTracks()) {
    track.onended = null
    try { track.stop() } catch { /* Still stop the remaining tracks. */ }
  }
}

export function releaseRecorder(recorder: MediaRecorder | null) {
  if (!recorder) return
  recorder.ondataavailable = null
  recorder.onstop = null
  recorder.onerror = null
  try { if (recorder.state !== 'inactive') recorder.stop() } catch { /* Tracks are stopped separately. */ }
}

export function closeAudioContext(context: AudioContext | null) {
  try { void context?.close().catch(() => undefined) } catch { /* Context may already be unavailable. */ }
}

export function revokeAudioUrl(url: string | null) {
  if (url) { try { URL.revokeObjectURL(url) } catch { /* Do not block microphone cleanup. */ } }
}
