"""운영자가 고정하는 장치 선택. CUDA 실패 시 CPU로 자동 전환하지 않는다."""
import os


def selected_device():
    device = os.environ.get('SPEECH_DEVICE', 'cpu')
    if device not in {'cpu', 'cuda'}:
        raise ValueError('unsupported speech device')
    return device


def stt_options(device):
    if device not in {'cpu', 'cuda'}:
        raise ValueError('unsupported speech device')
    return dict(device=device, compute_type='float16' if device == 'cuda' else 'int8',
                cpu_threads=2, num_workers=1, local_files_only=True)


def tts_options(device, torch):
    if device not in {'cpu', 'cuda'}:
        raise ValueError('unsupported speech device')
    if device == 'cuda' and not torch.cuda.is_available():
        raise ValueError('CUDA unavailable')
    # T4에서 float16 샘플링 NaN이 실측됐다. CPU/GPU 모두 float32를 사용한다.
    return dict(device_map=device, dtype=torch.float32, attn_implementation='eager')
