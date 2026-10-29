import { Link } from 'react-router-dom'
import './opportunity-list.css'

export function OpportunityListCard({ title, organization, tags, to, targetBlank = false, state, onDetail }: {
  title: string
  organization: string
  tags: readonly string[]
  to?: string
  targetBlank?: boolean
  state?: unknown
  onDetail?: () => void
}) {
  return <li className="shared-opportunity-item"><article className="shared-opportunity-card">
    <h2>{title}</h2>
    <p className="shared-opportunity-organization">{organization}</p>
    <ul className="shared-opportunity-tags" aria-label="공고 정보">{tags.map((tag, index) => <li key={`${tag}:${index}`}>{tag}</li>)}</ul>
    {onDetail ? <button className="button primary" type="button" onClick={onDetail} aria-label={`${title} 자세히 보기`}>자세히 보기</button>
      : <Link className="button primary" to={to ?? '/opportunities'} target={targetBlank ? '_blank' : undefined} rel={targetBlank ? 'noopener noreferrer' : undefined} state={state} aria-label={`${title} 자세히 보기`}>자세히 보기</Link>}
  </article></li>
}
