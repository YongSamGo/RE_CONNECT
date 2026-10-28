from types import SimpleNamespace
from pathlib import Path
import subprocess
import sys

import pytest
import torch
from transformers import Qwen3Config
from transformers.cache_utils import DynamicCache

from tts_compat.compat import create_causal_mask, create_sliding_window_causal_mask, default_rope_parameters
from tts_compat.compat import require_complete_generation, restore_rotary_buffers


@pytest.mark.parametrize('head_dim,partial,expected', [
    (8, 1.0, [1, 0.1, 0.01, 0.001]), (8, 0.5, [1, 0.01]), (None, 1.0, [1, 0.01]),
])
def test_default_rotary_frequencies_preserve_known_model_geometry(head_dim, partial, expected):
    config = SimpleNamespace(head_dim=head_dim, hidden_size=8, num_attention_heads=2,
        partial_rotary_factor=partial, rope_theta=10000)
    actual, scaling = default_rope_parameters(config, device='cpu')
    assert torch.allclose(actual, torch.tensor(expected, dtype=torch.float32), atol=1e-7)
    assert scaling == 1


@pytest.mark.parametrize('dimension,theta', [(3, 10000), (0, 10000), (8, 0), (8, float('nan'))])
def test_invalid_rotary_geometry_cannot_create_silent_nonfinite_outputs(dimension, theta):
    with pytest.raises(ValueError):
        default_rope_parameters(SimpleNamespace(head_dim=dimension, hidden_size=0,
            num_attention_heads=1, rope_theta=theta))


def test_postload_restores_nan_and_meta_nonpersistent_buffers_without_changing_parameters():
    class Rotary(torch.nn.Module):
        def __init__(self, device):
            super().__init__()
            self.config = SimpleNamespace(head_dim=8, rope_theta=10000)
            self.rope_init_fn = default_rope_parameters
            self.register_buffer('inv_freq', torch.full((4,), float('nan'), device=device), persistent=False)
            self.original_inv_freq = self.inv_freq
    model = torch.nn.Module()
    model.anchor = torch.nn.Parameter(torch.tensor([7.0]))
    model.first, model.second = Rotary('cpu'), Rotary('meta')
    tokenizer = torch.nn.Module()
    tokenizer.rotary = Rotary('cpu')
    model.speech_tokenizer = SimpleNamespace(model=tokenizer)
    assert torch.isfinite(model.anchor).all()  # 파라미터만 검사해서는 이 결함을 찾지 못한다.
    assert restore_rotary_buffers(model) == 3
    for module in (model.first, model.second, tokenizer.rotary):
        assert module.inv_freq.device.type == 'cpu'
        assert torch.allclose(module.inv_freq, torch.tensor([1, 0.1, 0.01, 0.001]))
        assert torch.equal(module.original_inv_freq, module.inv_freq)
    assert list(model.state_dict()) == ['anchor'] and model.anchor.item() == 7


def config(*, sliding=False):
    result = Qwen3Config(hidden_size=8, intermediate_size=16, num_attention_heads=2,
        num_key_value_heads=2, num_hidden_layers=1, head_dim=4, sliding_window=2 if sliding else None,
        layer_types=['sliding_attention' if sliding else 'full_attention'], use_sliding_window=sliding)
    result._attn_implementation = 'eager'
    return result


def test_legacy_mask_bridge_keeps_future_tokens_hidden_and_self_tokens_visible():
    mask = create_causal_mask(config=config(), input_embeds=torch.ones(1, 3, 8),
        attention_mask=torch.ones(1, 3), cache_position=torch.arange(3), past_key_values=None,
        position_ids=torch.arange(3).unsqueeze(0))
    assert mask.shape == (1, 1, 3, 3)
    assert mask[0, 0, 0, 0] == 0 and (mask[0, 0, 0, 1:] < -1000).all()
    assert (mask[0, 0, 2] == 0).all()


def test_cached_decoding_preserves_past_and_current_positions():
    settings = config()
    cache = DynamicCache(config=settings)
    cache.update(torch.zeros(1, 2, 2, 4), torch.zeros(1, 2, 2, 4), layer_idx=0)
    mask = create_causal_mask(config=settings, input_embeds=torch.ones(1, 1, 8),
        attention_mask=torch.ones(1, 3), cache_position=torch.tensor([2]), past_key_values=cache,
        position_ids=torch.tensor([[2]]))
    assert mask.shape == (1, 1, 1, 3) and (mask == 0).all()


def test_sliding_mask_keeps_only_local_history():
    mask = create_sliding_window_causal_mask(config=config(sliding=True), input_embeds=torch.ones(1, 3, 8),
        attention_mask=torch.ones(1, 3), cache_position=torch.arange(3), past_key_values=None,
        position_ids=torch.arange(3).unsqueeze(0))
    assert mask[0, 0, 2, 0] < -1000 and (mask[0, 0, 2, 1:] == 0).all()


def test_end_token_is_required_even_when_waveform_could_be_constructed_from_a_length_cap():
    require_complete_generation(torch.tensor([[1, 2, 99]]), 99)
    for sequences in (torch.tensor([[1, 2, 3]]), torch.tensor([[1, 99], [1, 2]]),
        torch.empty(1, 0, dtype=torch.long), torch.tensor([1, 99]), []):
        with pytest.raises(RuntimeError, match='종료 토큰'):
            require_complete_generation(sequences, 99)


def test_verified_upstream_sources_import_with_pinned_runtime_without_loading_weights():
    speech = Path(__file__).resolve().parents[2]
    code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import prepare_tts_code
prepare_tts_code.verify()
sys.path.insert(0, str(prepare_tts_code.OUTPUT))
import qwen_tts
assert Path(qwen_tts.__file__).resolve().is_relative_to(prepare_tts_code.OUTPUT.resolve())
assert callable(qwen_tts.Qwen3TTSModel.from_pretrained)
prepare_tts_code.verify()
print('verified-source-import-ok')
"""
    result = subprocess.run([sys.executable, '-B', '-c', code, str(speech)],
        capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr[-2000:]
    # Upstream의 비치명적 docstring 진단이 stdout에 함께 출력될 수 있다.
    assert result.stdout.strip().splitlines()[-1] == 'verified-source-import-ok'
