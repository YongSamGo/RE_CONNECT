import { Link } from 'react-router-dom'

export function UnavailablePage({ title, children }: { title: string; children: string }) {
  return <div className="reading-width">
    <header className="page-heading"><p className="eyebrow">주소 확인</p><h1>{title}</h1><p>{children}</p></header>
    <div className="actions"><Link className="button primary" to="/">시작 화면으로</Link><Link className="text-link" to="/opportunities">공개 공고 살펴보기</Link></div>
  </div>
}
