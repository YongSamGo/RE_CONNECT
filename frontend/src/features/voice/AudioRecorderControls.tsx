import { Button } from '../../ui/Button'
import { StatusNotice } from '../../ui/StatusNotice'
import type { useAudioRecorder } from './useAudioRecorder'

export function AudioRecorderControls({ recorder, onReset, disabled = false }: { recorder: ReturnType<typeof useAudioRecorder>; onReset: () => void; disabled?: boolean }) {
  return <section className="panel"><h2>녹음하고 들어보기</h2><p role="status">{recorder.status === 'permission' ? '마이크 권한을 확인하고 있어요.' : recorder.status === 'recording' ? `녹음 중 · ${recorder.seconds} / 90초` : recorder.status === 'ready' ? '녹음이 끝났어요. 아래에서 들어볼 수 있습니다.' : '녹음은 시작 버튼을 누른 뒤에만 진행합니다.'}</p>
    <div className="actions"><Button disabled={disabled || recorder.status === 'permission' || recorder.status === 'recording'} onClick={() => void recorder.start()}>{recorder.audioUrl ? '다시 녹음하기' : '녹음 시작하기'}</Button>
      {recorder.status === 'recording' && <Button variant="secondary" onClick={recorder.stop}>녹음 마치기</Button>}<Button variant="secondary" onClick={onReset}>녹음·입력 취소하고 삭제</Button></div>
    {recorder.audioUrl && <audio ref={element => { recorder.setPlayer(element) }} className="voice-player" src={recorder.audioUrl} controls aria-label="내 녹음 들어보기" />}
    {recorder.status === 'error' && <StatusNotice kind="error" title="녹음을 사용할 수 없어요">{recorder.error}</StatusNotice>}
  </section>
}
