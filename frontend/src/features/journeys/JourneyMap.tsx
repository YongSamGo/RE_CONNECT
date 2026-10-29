import { Link } from 'react-router-dom'
import './journey-map.css'

const nodeWidth = 184
const nodeHeight = 82
const nodes = [
  { id: 'home', x: 34, y: 90, title: '시작 화면', detail: '이야기 시작과 공고 탐색', path: '/', lane: 'start' },
  { id: 'start', x: 270, y: 90, title: '시작 전 안내', detail: 'AI 처리 안내 확인', path: '/start', lane: 'start' },
  { id: 'conversation', x: 506, y: 90, title: '경험 이야기', detail: '대화로 경험 정리', path: '/conversation', lane: 'story' },
  { id: 'recommendations', x: 742, y: 90, title: '추천 공고', detail: '경험과 연결된 기회', path: '/recommendations', lane: 'opportunity' },
  { id: 'opportunities', x: 270, y: 334, title: '전체 공고 탐색', detail: '지역과 활동 유형으로 찾기', path: '/opportunities', lane: 'opportunity' },
  { id: 'detail', x: 506, y: 334, title: '공고 상세 보기', detail: '목록에서 공고 선택', path: '/opportunities', lane: 'opportunity' },
  { id: 'application', x: 742, y: 334, title: '지원서 작성', detail: '상세 화면에서 이어서 작성', path: '/opportunities', lane: 'application' },
  { id: 'me', x: 978, y: 604, title: '나의 정보', detail: '이름, 연락처와 거주 정보', path: '/me', lane: 'member' },
  { id: 'myprofile', x: 1214, y: 604, title: '나의 이야기', detail: '정리한 경험과 희망 활동', path: '/me/story', lane: 'member' },
  { id: 'saved', x: 1450, y: 604, title: '저장한 공고', detail: '관심 공고 다시 확인', path: '/me/saved', lane: 'member' },
] as const

const byId = Object.fromEntries(nodes.map(node => [node.id, node]))
const edges = [
  { from: 'home', to: 'start', label: '시작하기' },
  { from: 'home', to: 'opportunities', label: '공고 먼저 보기' },
  { from: 'start', to: 'conversation', label: '안내 게시와 동의, 체험 생성' },
  { from: 'start', to: 'opportunities', label: '동의 없이 둘러보기' },
  { from: 'conversation', to: 'recommendations', label: '경험 답변 확인 완료' },
  { from: 'recommendations', to: 'detail', label: '추천 공고 선택' },
  { from: 'opportunities', to: 'detail', label: '공고 선택' },
  { from: 'detail', to: 'application', label: '지원서 작성하기' },
  { from: 'me', to: 'myprofile', label: '이야기 확인' },
  { from: 'myprofile', to: 'saved', label: '공고 확인' },
] as const

function edgePath(from: string, to: string) {
  const source = byId[from as keyof typeof byId]
  const target = byId[to as keyof typeof byId]
  const scx = source.x + nodeWidth / 2
  const scy = source.y + nodeHeight / 2
  const tcx = target.x + nodeWidth / 2
  const tcy = target.y + nodeHeight / 2
  const dx = tcx - scx
  const dy = tcy - scy
  const sourceScale = 1 / Math.max(Math.abs(dx) / (nodeWidth / 2), Math.abs(dy) / (nodeHeight / 2))
  const targetScale = sourceScale
  const sx = scx + dx * sourceScale
  const sy = scy + dy * sourceScale
  const tx = tcx - dx * targetScale
  const ty = tcy - dy * targetScale
  const bend = Math.max(38, Math.abs(tx - sx) * 0.42)
  const direction = tx >= sx ? 1 : -1
  return `M ${sx} ${sy} C ${sx + bend * direction} ${sy}, ${tx - bend * direction} ${ty}, ${tx} ${ty}`
}

export function JourneyMap() {
  return <div className="journey-map-page">
    <header className="journey-map-heading">
      <div><p className="journey-map-kicker">서비스 화면 지도</p><h1>이용 흐름 한눈에 보기</h1>
        <p>상자를 누르면 해당 화면을 열어요. 선 위에는 다음 화면으로 이어지는 조건을 적었습니다.</p></div>
      <Link className="journey-map-back" to="/guide">목록으로</Link>
    </header>
    <div className="journey-map-legend" aria-label="흐름 구간">
      <span><i className="legend-story" /> 경험 정리</span><span><i className="legend-opportunity" /> 기회 탐색</span>
      <span><i className="legend-application" /> 지원서 작성</span><span><i className="legend-member" /> 계정 관리</span>
    </div>
    <div className="journey-map-scroll" tabIndex={0} aria-label="좌우로 이동할 수 있는 사용자 흐름 지도">
      <svg className="journey-map-canvas" viewBox="0 0 1920 970" role="group" aria-labelledby="map-title map-description">
        <title id="map-title">다시잇다 사용자 흐름</title>
        <desc id="map-description">경험 이야기, 추천 공고, 공고 상세와 지원서 작성, 계정 관리 화면의 이동 조건을 연결한 지도입니다.</desc>
        <defs><marker id="journey-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#728b97" /></marker></defs>
        <g className="journey-map-lanes" aria-hidden="true">
          <rect x="18" y="52" width="1460" height="172" rx="18" />
          <rect x="248" y="286" width="1190" height="178" rx="18" />
          <rect x="952" y="562" width="700" height="170" rx="18" />
          <text x="34" y="75">이야기에서 기회로</text><text x="264" y="309">공고 상세에서 지원서 작성</text><text x="968" y="585">계정 관리</text>
        </g>
        <g className="journey-map-edges" aria-hidden="true">
          {edges.map((edge, index) => <g key={`${edge.from}-${edge.to}`}>
            <path d={edgePath(edge.from, edge.to)} markerEnd="url(#journey-arrow)" />
            <text className="journey-map-edge-label" x={(() => { const a = byId[edge.from as keyof typeof byId]; const b = byId[edge.to as keyof typeof byId]; return (a.x + b.x + nodeWidth) / 2 })()} y={(() => { const a = byId[edge.from as keyof typeof byId]; const b = byId[edge.to as keyof typeof byId]; return (a.y + b.y + nodeHeight) / 2 + (index % 2 ? 21 : -13) })()}>{edge.label}</text>
          </g>)}
        </g>
        {nodes.map(node => <foreignObject key={node.id} x={node.x} y={node.y} width={nodeWidth} height={nodeHeight}>
          <Link className={`journey-map-node lane-${node.lane}`} to={node.path}>
            <strong>{node.title}</strong><span>{node.detail}</span>
          </Link>
        </foreignObject>)}
      </svg>
    </div>
    <p className="journey-map-note">추천 공고에서 상세를 확인한 뒤, 같은 공고 흐름에서 지원서를 작성하고 공식 신청처로 이동합니다.</p>
  </div>
}
