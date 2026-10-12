"""requirements*.txt / pyproject.toml의 패키지명이 유명 패키지와 1~2글자 차이이거나
접두·접미어만 다른지 찾는다(타이포스쿼팅 후보).
사용: python3 -I typo_check.py requirements.txt [pyproject.toml ...]"""
import difflib, re, sys

POPULAR = """requests urllib3 certifi idna charset-normalizer setuptools pip wheel six python-dateutil
numpy pandas scipy matplotlib pillow scikit-learn torch tensorflow keras opencv-python
flask django fastapi starlette uvicorn gunicorn werkzeug jinja2 click itsdangerous markupsafe
sqlalchemy psycopg2 psycopg2-binary pymysql redis celery boto3 botocore pydantic httpx aiohttp
pyyaml cryptography pycryptodome pyjwt bcrypt argon2-cffi paramiko lxml beautifulsoup4 selenium
python-dotenv colorama tqdm rich attrs packaging typing-extensions pytest coverage openai
python-utils utils dateutil discord.py web3 eth-account""".split()

# 다시잇다 스택에서 쓰는(쓸) 정상 패키지 — 오탐을 줄이고, 이 이름들의 오타도 함께 잡는다
PROJECT = """psycopg psycopg-binary psycopg-pool asyncpg pgvector alembic python-multipart
pydantic-settings email-validator passlib pytest-asyncio anthropic tiktoken
bandit pip-audit""".split()


def norm(n):  # PEP 503 정규화
    return re.sub(r"[-_.]+", "-", n).lower()


def names(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if path.endswith(".toml"):
        found = re.findall(r'^\s*["\']([A-Za-z0-9][A-Za-z0-9._-]*)', text, re.M)
        found += re.findall(r'^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*=\s*["{]', text, re.M)
    else:
        found = re.findall(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", text, re.M)
    return {norm(n) for n in found}


def main(paths):
    pop = {norm(p) for p in POPULAR + PROJECT}
    for path in paths:
        for n in sorted(names(path)):
            if n in pop:
                continue
            close = difflib.get_close_matches(n, pop, n=3, cutoff=0.8)
            affix = [p for p in pop if n != p and (n.endswith("-" + p) or n.startswith(p + "-")
                     or n.replace("python-", "").replace("-python", "") == p or n.replace("py", "", 1) == p)]
            if close or affix:
                print(f"의심: {path}: {n} ~ {sorted(set(close + affix))}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
