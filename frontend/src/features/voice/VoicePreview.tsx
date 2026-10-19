import { Link } from 'react-router-dom'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { TextAreaField } from '../../ui/Fields'
import { StatusNotice } from '../../ui/StatusNotice'
import { useAudioRecorder } from './useAudioRecorder'
import { AudioRecorderControls } from './AudioRecorderControls'

export function VoicePreview({ onUseText }: { onUseText: (text: string) => void }) {
  const text = useMemoryScope(() => '')
  const recorder = useAudioRecorder()
  const reset = () => { recorder.reset(); text.clear() }
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">음성 입력 미리보기</p><h1>말로 경험을 연습해 봐요</h1><p>녹음 시작을 누르면 브라우저에 마이크 권한을 요청합니다.</p></header>
    <StatusNotice label="기기 내 녹음 연습" title="음성 인식은 아직 연결되지 않았어요">녹음은 현재 화면에서만 재생하며 서버에 보내지 않습니다. 자동 전사 결과는 제공하지 않습니다. 가상의 경험만 녹음해 주세요. 최대 90초·6MiB이며 화면을 떠나면 녹음이 삭제됩니다.</StatusNotice>
    <AudioRecorderControls recorder={recorder} onReset={reset} />
    <section className="panel"><h2>직접 글로 확인하기</h2><TextAreaField label="확인한 경험 문장" value={text.value} onChange={event => text.setValue(event.target.value)} maxLength={2000} hint="자동 전사가 아닙니다. 녹음한 내용을 직접 적거나 글로 입력해 주세요. 기존 경험 입력을 이 문장으로 바꿉니다." /><Button disabled={!text.value.trim()} onClick={() => { const confirmed = text.value; reset(); onUseText(confirmed) }}>이 문장을 경험 입력에 사용하기</Button></section>
    <Link className="text-link" to="/conversation">글로 작성하는 화면으로 →</Link>
  </div>
}
