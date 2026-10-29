from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('speech_isolation', Path(__file__).resolve().parents[2] / 'infra/check_speech_service.py')
isolation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isolation)


def baseline():
    metadata = dict(State={'Health': {'Status': 'healthy'}}, Config={'User': '10001:10001'},
        HostConfig=dict(ReadonlyRootfs=True, CapDrop=['ALL'], CapAdd=None, Privileged=False,
            SecurityOpt=['no-new-privileges:true'], Init=True, NanoCpus=2_000_000_000,
            Memory=8*1024**3, MemorySwap=8*1024**3, PidsLimit=128, ShmSize=64*1024**2,
            PortBindings={}, LogConfig={'Type': 'none'}, RestartPolicy={'Name': 'no'}),
        NetworkSettings={'Networks': {'speech': {}}})
    kernel = dict(uid=10001, cap_eff='0000000000000000', no_new_privs='1', seccomp='2',
        limits={'cpu.max': '200000 100000', 'memory.max': str(8*1024**3), 'memory.swap.max': '0', 'pids.max': '128'},
        root_read_only=True, models_read_only=True, tmp_noexec_nosuid_nodev=True, tmp_bytes=64*1024**2,
        no_default_route=True, egress_no_route=True)
    return metadata, {'Internal': True}, kernel


def test_isolation_uses_inspect_and_actual_kernel_values_together():
    assert all(isolation.validate(*baseline()).values())


@pytest.mark.parametrize('mode', ['published-port', 'writable-model', 'unlimited-memory', 'unlimited-cpu',
    'egress', 'public-network', 'new-privileges', 'privileged', 'tmpfs-size'])
def test_apparently_healthy_container_with_weakened_isolation_is_rejected(mode):
    metadata, network, kernel = deepcopy(baseline())
    if mode == 'published-port':
        metadata['HostConfig']['PortBindings'] = {'8001/tcp': [{'HostPort': '8001'}]}
    elif mode == 'writable-model':
        kernel['models_read_only'] = False
    elif mode == 'unlimited-memory':
        kernel['limits']['memory.max'] = 'max'
    elif mode == 'unlimited-cpu':
        kernel['limits']['cpu.max'] = 'max 100000'
    elif mode == 'egress':
        kernel['egress_no_route'] = False
    elif mode == 'public-network':
        network['Internal'] = False
    elif mode == 'new-privileges':
        kernel['no_new_privs'] = '0'
    elif mode == 'privileged':
        metadata['HostConfig']['Privileged'] = True
    elif mode == 'tmpfs-size':
        kernel['tmp_bytes'] = 128*1024**2
    with pytest.raises(ValueError, match='제한 확인 실패'):
        isolation.validate(metadata, network, kernel)
