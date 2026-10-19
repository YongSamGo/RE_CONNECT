# 고정 Qwen 12Hz 코드의 호환 준비

이 폴더는 공식 qwen-tts0.1.1의 선택한12Hz 코드와 Transformers5.19를 연결하기 위한 로컬 호환 빌드다. 원본 패키지의 배포판이나 새 버전을 가장하지 않는다. 실제 서비스의 TTS HTTP 연결은 아직 별도 작업이며 speech readiness도 계속 실패 상태다.

## 준비와 검증

Python3.12의 새 격리 환경에서 저장소 루트 기준으로 실행한다.

```sh
python -m pip install --require-hashes -r speech/requirements.txt -r speech/tts_compat/requirements.txt -r speech/tts_compat/requirements-dev.txt
python -I speech/prepare_tts_code.py
python -I speech/prepare_tts_code.py --verify-only
cd speech/tts_compat
python -B -m pytest -q
```

원본 wheel을 이미 받았다면 준비 명령에 `--wheel <경로>`를 준다. 그 경우도 고정 크기·SHA-256을 검사한다. 준비는 source를 실행하거나 모델을 받지 않는다. 결과는 Git 제외 경로 `speech/runtime_vendor/qwen12-tf519-r1/`에 저장한다.

- 원본 wheel113,529바이트의 URL·SHA-256과 선택한10개 source의 원본/수정 후 해시는 [recipe.json](recipe.json)에 있다. 줄 단위 수정 범위/원문/결과를 모두 대조한다. [upstream.patch](upstream.patch)는 같은 변경의 검토용 diff다.
- 선택하지 않은25Hz·웹 데모·배포 메타데이터를 설치하지 않는다. 원본의 오래된 Transformers4.57.3/accelerate1.12 pins도 설치하지 않는다.
- Apache2 라이선스·원래 저작권과 수정 고지를 보존한다([UPSTREAM_LICENSE](UPSTREAM_LICENSE), [NOTICE](NOTICE)). 변경한 source에도 수정 표시를 넣는다.
- 이미 준비된 파일은 전체 hash를 검사해 재사용한다. 손상·미완료·추가 파일을 자동 덮어쓰기/삭제하지 않는다. 쓰기 중 중단된 폴더도 확인 후 별도로 복구해야 한다.
- 링크·경로 탈출·ZIP 중복/팽창·원문과 다른 패치를 거절한다. 알려지지 않은 `__pycache__/*.pyc`도 거절한다. 실제 importer는 먼저 검증하고 `-B` 또는 같은 bytecode 미생성 설정과 읽기 전용 source를 사용해야 한다.

## 바꾼 동작

25Hz 등록과 voice clone/design·외부 오디오 입력 helper를 비활성화했다. 선택한 모델은12Hz CustomVoice이며, 사용자용 loader/API는 한국어·Sohee를 고정해야 한다. 준비 코드의 일반 CustomVoice 메서드를 사용자 입력 선택기로 공개하지 않는다.

[compat.py](compat.py)는 기본 RoPE 주파수, 마스크 인자 변경, pad 기본값 등 새 API에 필요한 경계를 제공한다. 특히 새 적재 방식의 비영속 RoPE 버퍼는 체크포인트 파라미터가 정상이어도 미초기화될 수 있다. 주 모델과 nn.Module 트리에 들어 있지 않은 speech tokenizer wrapper의 내부 모델을 모두 복구한다. 최대 생성 길이에 닿은 것을 정상 음성으로 처리하지 않도록 마지막 codec 종료 토큰도 요구한다.

이 수정은 “버전만 바꾸면 호환된다”는 가정으로 만들지 않았다. 최초 실제 시험에서 pad 속성·decorator·마스크 인자·RoPE API 차이를 확인했고, 무한 반복에 가까운 길이 한도 출력과 NaN 확률을 추적해 비영속 버퍼 초기화 문제를 찾았다. 실패 출력을 정상 음성으로 계산하지 않는다.

## 의존성·검증 범위

CPU PyTorch는 공식 [CPU wheel 인덱스](https://download.pytorch.org/whl/cpu/torch/)와 hash로 고정한다. 런타임 잠금은 기본 speech 잠금을 제약으로 사용해 공통 패키지 버전이 어긋나지 않게 한다. Linux/Python3.12에서2026-10-11을 기준으로 출시 제한을 적용했고 실제 배포 메타데이터도 대조했다.

모든 전이 의존성이 나열된 해시 잠금 전체를 OSV로 감사한다. `--no-deps --disable-pip`는 +cpu 패키지를 PyPI 기본 배포판으로 다시 해석하지 않기 위한 것으로, 잠금에 나열된 전이 패키지도 모두 조회한다. 원본 qwen source의 알려진 취약점은 설치용이 아닌 [upstream-advisory.in](upstream-advisory.in)으로 별도 확인한다. 생성된 외부 source의 원본/수정 hash를 검사하고, 자체 app·준비 도구·compat helper는 각각 정적 검사한다.

준비 도구 보안 시험26개와 실제 Torch/Transformers에서의 호환 회귀 시험13개를 검증한다. 회귀 시험은 알려진 회전 주파수·NaN/meta 버퍼·별도 tokenizer 복구·과거/현재/미래 마스크·종료 토큰 미도달과 가중치 없는 실제 원본 코드 import를 확인한다. CI는 준비 단계를 거친 뒤 검사하며 원본 코드의 새 라이브러리 import 실패도 잡는다.

실제 고정 가중치로 오프라인 CPU 합성을 별도 수행했다. 후속 [TTS 로더](../TTS_RUNTIME.md)에서 고정 화자·WAV 검증·로컬 파형 정리와 Whisper의 같은 프로세스 공존도 확인했다. 로더 시험22개가 추가되어 이 폴더의 시험은35개다. 실제3개 문장 교차 확인에서 숫자 문장은 불일치했다. 사람의 청취 평가·긴 문장·대상 기기·EC2/GPU·동시성·서비스 전체 준비를 검증한 결과가 아니다. 실제 HTTP 연결과 반환 응답의 수명 정리는 다음 단계다.
