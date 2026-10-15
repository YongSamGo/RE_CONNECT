"""로컬 추론·외부 연동 Adapter 인터페이스.

여기에는 서비스가 의존하는 Protocol만 둔다. 실제 구현(Ollama·음성 서비스·공고 API 등)은
각 작업에서 이 Protocol을 따르는 클래스로 만들고, `app/main.py`에서 끼워 넣는다.
"""
