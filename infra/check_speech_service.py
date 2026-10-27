"""실제 실행 중인 CPU 음성 컨테이너의 격리/자원 제한을 확인한다."""

import argparse
import json
from pathlib import Path
import re
import subprocess  # nosec B404 - 운영자용 Docker 상태 검사에만 사용하며 shell은 실행하지 않는다.

ROOT = Path(__file__).resolve().parents[1]
KERNEL_PROBE = '''
import errno,json,os,socket
from pathlib import Path
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
limits={name:Path('/sys/fs/cgroup',name).read_text().strip() for name in ('cpu.max','memory.max','memory.swap.max','pids.max')}
tmp=os.statvfs('/tmp');flags=tmp.f_flag
root_ro=bool(os.statvfs('/app').f_flag & os.ST_RDONLY)
models_ro=bool(os.statvfs('/app/models').f_flag & os.ST_RDONLY)
tmp_flags=all(flags & value for value in (os.ST_NOEXEC,os.ST_NOSUID,os.ST_NODEV))
default_route=any(line.split()[1]=='00000000' for line in Path('/proc/net/route').read_text().splitlines()[1:])
blocked=False
try:
    with socket.create_connection(('1.1.1.1',443),timeout=1):pass
except OSError as error:
    blocked=error.errno in (errno.ENETUNREACH,errno.EHOSTUNREACH)
print(json.dumps(dict(uid=os.getuid(),cap_eff=status['CapEff'].strip(),no_new_privs=status['NoNewPrivs'].strip(),
    seccomp=status['Seccomp'].strip(),limits=limits,root_read_only=root_ro,models_read_only=models_ro,
    tmp_noexec_nosuid_nodev=tmp_flags,tmp_bytes=tmp.f_blocks*tmp.f_frsize,no_default_route=not default_route,egress_no_route=blocked)))
'''


def validate(metadata, network, kernel):
    config, host = metadata['Config'], metadata['HostConfig']
    checks = {
        'healthy': metadata['State']['Health']['Status'] == 'healthy',
        'unprivileged_user': config['User'] == '10001:10001' and kernel['uid'] == 10001,
        'read_only': host['ReadonlyRootfs'] is True and kernel['root_read_only'] and kernel['models_read_only'],
        'capabilities_dropped': set(host['CapDrop']) == {'ALL'} and not host.get('CapAdd') and not host['Privileged'] and int(kernel['cap_eff'], 16) == 0,
        'no_new_privileges': 'no-new-privileges:true' in host['SecurityOpt'] and kernel['no_new_privs'] == '1',
        'seccomp': kernel['seccomp'] == '2',
        'init': host['Init'] is True,
        'cpu': host['NanoCpus'] == 2_000_000_000 and kernel['limits']['cpu.max'] == '200000 100000',
        'memory': host['Memory'] == 8 * 1024**3 and kernel['limits']['memory.max'] == str(8 * 1024**3),
        'no_swap': host['MemorySwap'] == host['Memory'] and kernel['limits']['memory.swap.max'] == '0',
        'pids': host['PidsLimit'] == 128 and kernel['limits']['pids.max'] == '128',
        'no_host_ports': not host.get('PortBindings'),
        'internal_network_only': network['Internal'] is True and len(metadata['NetworkSettings']['Networks']) == 1,
        'no_egress_route': kernel['no_default_route'] and kernel['egress_no_route'],
        'tmpfs_flags': kernel['tmp_noexec_nosuid_nodev'] and kernel['tmp_bytes'] == 64 * 1024**2,
        'shared_memory_limit': host['ShmSize'] == 64 * 1024**2,
        'no_file_logs': host['LogConfig']['Type'] == 'none',
        'no_auto_restart': host['RestartPolicy']['Name'] == 'no',
    }
    if not all(checks.values()):
        raise ValueError('실제 음성 컨테이너 제한 확인 실패: ' + ', '.join(key for key, value in checks.items() if not value))
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker-host', help='시험용 Docker 엔진을 명시할 때만 사용')
    args = parser.parse_args()
    docker = ['docker'] + (['--host', args.docker_host] if args.docker_host else [])
    def command(arguments):
        # host는 운영자 CLI 옵션이고 arguments는 아래 고정된 상태 조회/검사 명령뿐이다.
        result = subprocess.run(docker + arguments, capture_output=True, timeout=15, check=True, shell=False)  # nosec B603 - Docker argv를 shell 없이 전달하고 실행 대상 ID를 검증한다.
        return result.stdout.decode('utf-8')
    try:
        container = command(['compose', '-f', str(ROOT / 'infra/compose.speech-cpu.yaml'), 'ps', '-q', 'speech']).strip()
        if not re.fullmatch('[0-9a-f]{64}', container):
            raise ValueError('검증할 음성 컨테이너가 없습니다')
        metadata = json.loads(command(['inspect', container]))[0]
        names = list(metadata['NetworkSettings']['Networks'])
        if len(names) != 1:
            raise ValueError('음성 컨테이너의 네트워크 수가 다릅니다')
        network = json.loads(command(['network', 'inspect', names[0]]))[0]
        kernel = json.loads(command(['exec', container, '/opt/venv/bin/python', '-I', '-c', KERNEL_PROBE]))
        print(json.dumps({'checks': validate(metadata, network, kernel), 'kernel': kernel}, ensure_ascii=False))
        return 0
    except ValueError as error:
        print(str(error))
    except (OSError, KeyError, TypeError, subprocess.SubprocessError):
        print('음성 컨테이너의 실제 상태를 확인하지 못했습니다')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
