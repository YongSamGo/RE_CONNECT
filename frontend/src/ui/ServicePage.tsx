import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import './service.css'

export function MemberNavigation() {
  return <nav className="member-navigation" aria-label="내 정보 메뉴">
    <NavLink to="/me" end>내 정보</NavLink>
    <NavLink to="/me/profile">내 프로필</NavLink>
    <NavLink to="/me/saved">저장한 자료</NavLink>
  </nav>
}

export function ServicePage({ title, description, children, member = false, className = '' }: {
  title: string; description?: string; children: ReactNode; member?: boolean; className?: string
}) {
  return <div className={`service-stage ${className}`}>
    {member && <MemberNavigation />}
    <header className="service-heading"><h1>{title}</h1>{description && <p>{description}</p>}</header>
    {children}
  </div>
}

export function JourneyNavigation({ current, journeyId }: { current: 'conversation' | 'results' | 'recommendations'; journeyId?: string }) {
  const steps = [
    { id: 'conversation', label: '경험 이야기', to: journeyId ? `/journeys/${journeyId}/conversation` : '/conversation' },
    { id: 'recommendations', label: '추천 공고', to: journeyId ? `/journeys/${journeyId}/recommendations` : '/recommendations' },
  ]
  return <nav className="journey-navigation" aria-label="서비스 이용 단계"><ol>{steps.map((step, i) => <li key={step.id}>
    <Link to={step.to} aria-current={step.id === current ? 'step' : undefined}><span aria-hidden="true">{i + 1}</span>{step.label}</Link>
  </li>)}</ol></nav>
}

export function EmptySection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="service-blank"><h2>{title}</h2><div className="service-blank-body">{children}</div></section>
}

export function ConversationSurface({ children }: { children: ReactNode }) {
  return <div className="conversation-surface">{children}</div>
}
