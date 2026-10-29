import { LoginEntry } from './notices'

export function LoginPage() {
  return <div className="account-stage login-stage">
    <div className="login-content">
      <h1>다시잇다에 로그인</h1>
      <p>카카오 계정으로 간편하게 시작해요.</p>
      <LoginEntry compact />
    </div>
  </div>
}
