"""고정 Qwen 12Hz 모델에 필요한 Transformers 5.19 호환 경계."""

import math

import torch
from transformers.masking_utils import create_causal_mask as _causal_mask
from transformers.masking_utils import create_sliding_window_causal_mask as _sliding_mask


def default_rope_parameters(config, device=None, seq_len=None):
    head_dim = getattr(config, 'head_dim', None) or config.hidden_size // config.num_attention_heads
    dim = int(head_dim * getattr(config, 'partial_rotary_factor', 1.0))
    if dim <= 0 or dim % 2 or not math.isfinite(config.rope_theta) or config.rope_theta <= 0:
        raise ValueError('고정 회전 임베딩 설정을 확인하지 못했습니다')
    frequencies = 1.0 / (config.rope_theta ** (torch.arange(0, dim, 2, dtype=torch.int64).float().to(device) / dim))
    return frequencies, 1.0


def create_causal_mask(*, input_embeds=None, cache_position=None, **kwargs):
    # 새 API는 현재 Cache와 position_ids로 위치를 계산한다.
    return _causal_mask(inputs_embeds=input_embeds, **kwargs)


def create_sliding_window_causal_mask(*, input_embeds=None, cache_position=None, **kwargs):
    return _sliding_mask(inputs_embeds=input_embeds, **kwargs)


def restore_rotary_buffers(model):
    restored = 0
    roots = [model]
    # Qwen의 speech_tokenizer는 nn.Module이 아닌 wrapper여서 model.modules()에 포함되지 않는다.
    tokenizer_model = getattr(getattr(model, 'speech_tokenizer', None), 'model', None)
    if isinstance(tokenizer_model, torch.nn.Module):
        roots.append(tokenizer_model)
    seen = set()
    for root in roots:
        parameter = next(root.parameters(), None)
        for module in root.modules():
            if id(module) in seen:
                continue
            seen.add(id(module))
            if hasattr(module, 'rope_init_fn') and hasattr(module, 'inv_freq'):
                device = module.inv_freq.device
                if device.type == 'meta':
                    if parameter is None or parameter.device.type == 'meta':
                        raise ValueError('회전 버퍼를 배치할 장치를 확인하지 못했습니다')
                    device = parameter.device
                frequencies, scaling = module.rope_init_fn(module.config, device=device)
                if not torch.isfinite(frequencies).all().item():
                    raise ValueError('회전 버퍼를 초기화하지 못했습니다')
                module.register_buffer('inv_freq', frequencies, persistent=False)
                module.original_inv_freq = frequencies
                module.attention_scaling = scaling
                restored += 1
    if restored == 0:
        raise ValueError('고정 모델의 회전 버퍼를 찾지 못했습니다')
    return restored


def require_complete_generation(sequences, eos_token_id):
    if (not isinstance(sequences, torch.Tensor) or sequences.ndim != 2
        or sequences.shape[0] < 1 or sequences.shape[1] < 1
        or not torch.all(sequences[:, -1] == eos_token_id).item()):
        raise RuntimeError('음성 생성이 종료 토큰에 도달하지 못했습니다')
