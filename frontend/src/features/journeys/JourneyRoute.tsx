import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { StatusNotice } from '../../ui/StatusNotice'
import { isOpportunityId } from '../public-opportunities/catalog'

/** Reentry UX applies to both journey pages; ownership always stays on the server. */
export function JourneyRoute({ page, children }: { page: 'profile' | 'conversation'; children: (id: string) => ReactNode }) {
  const { journeyId } = useParams()
  const navigate = useNavigate()
  const [reentry] = useState(() => {
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
    return !!navigation && (navigation.type === 'reload' || navigation.type === 'back_forward')
      && new URL(navigation.name).pathname === `/journeys/${journeyId}/${page}`
  })
  useEffect(() => {
    const restore = (event: PageTransitionEvent) => { if (event.persisted) navigate('/', { replace: true }) }
    window.addEventListener('pageshow', restore)
    return () => window.removeEventListener('pageshow', restore)
  }, [navigate])
  if (reentry) return <Navigate to="/" replace />
  return journeyId && isOpportunityId(journeyId) ? children(journeyId)
    : <StatusNotice title="체험 주소를 확인해 주세요">올바른 체험 화면에서 다시 이동해 주세요.</StatusNotice>
}
