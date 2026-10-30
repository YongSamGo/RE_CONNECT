export function RuntimeFailure() {
  return <main className="error-page"><h1>화면을 표시하지 못했습니다</h1>
    <p role="alert">화면을 다시 열거나 새로 시작해 주세요. 저장하지 않은 입력은 사라집니다. 요청한 작업은 서버에서 처리되었을 수 있으니 다시 보내기 전에 결과를 확인해 주세요.</p>
    <div className="actions"><button type="button" className="button primary" onClick={() => window.location.reload()}>현재 화면 다시 열기</button><a className="button secondary" href="/">새로 시작하기</a></div>
  </main>
}
