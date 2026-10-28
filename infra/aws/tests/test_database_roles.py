"""전용 Unix socket PostgreSQL에서 초기 역할·DML/DDL·원자적 권한 적용을 확인한다."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

try:
    import psycopg
except ImportError:
    psycopg = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('DB_ROLE_TEST_SOCKET'), '별도 DB 역할 시험 클러스터 없음')
class DatabaseRoleTests(unittest.TestCase):
    @classmethod
    def connect(cls, *, user='postgres', database='reconnect'):
        return psycopg.connect(host=cls.socket, port=55491, user=user, dbname=database,
            connect_timeout=2, autocommit=True)

    @classmethod
    def script(cls, name, *, database='reconnect', user='postgres'):
        return subprocess.run([shutil.which('psql'), '-X', '-w', '--host', cls.socket, '--port', '55491',
            '--username', user, '--dbname', database, '--file', str(ROOT/name)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)

    @classmethod
    def setUpClass(cls):
        if psycopg is None or shutil.which('psql') is None:
            raise RuntimeError('명시한 DB 역할 시험에는 psycopg와 psql이 필요합니다')
        cls.socket = os.environ['DB_ROLE_TEST_SOCKET']
        if re.fullmatch(r'/tmp/reconnect-db-roles-[A-Za-z0-9]+/socket', cls.socket) is None:
            raise RuntimeError('전용 클러스터 경로만 허용합니다')
        with cls.connect(database='postgres') as admin:
            data, listen, version = admin.execute("SELECT current_setting('data_directory'), current_setting('listen_addresses'), current_setting('server_version_num')").fetchone()
            if data != str(Path(cls.socket).parent/'postgres') or listen != '' or not 160000 <= int(version) < 170000:
                raise RuntimeError('별도 PostgreSQL16 Unix socket 클러스터만 허용합니다')
            if admin.execute("SELECT count(*) FROM pg_roles WHERE rolname IN ('reconnect_migrator','reconnect_runtime')").fetchone()[0] != 0:
                raise RuntimeError('이전 역할이 없는 새 시험 클러스터만 허용합니다')
        if cls.script('bootstrap_database.sql', database='postgres').returncode == 0:
            raise AssertionError('다른 DB 초기화가 허용되었습니다')
        with cls.connect(database='postgres') as admin:
            assert admin.execute("SELECT count(*) FROM pg_roles WHERE rolname IN ('reconnect_migrator','reconnect_runtime')").fetchone()[0] == 0
        # Model PG16 RDS administration without granting superuser or SET/INHERIT.
        with cls.connect() as admin:
            admin.execute('CREATE ROLE rds_like_admin LOGIN CREATEROLE NOSUPERUSER NOINHERIT')
            admin.execute('ALTER DATABASE reconnect OWNER TO rds_like_admin')
        if cls.script('bootstrap_database.sql', user='rds_like_admin').returncode != 0:
            raise AssertionError('초기 역할 적용 실패')
        with cls.connect() as admin:
            cls.initial_flags = admin.execute("SELECT rolname,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolinherit FROM pg_roles WHERE rolname IN ('reconnect_migrator','reconnect_runtime') ORDER BY rolname").fetchall()
        for name in ('reconnect_migrator', 'reconnect_runtime'):
            try:
                with cls.connect(user=name): pass
            except psycopg.OperationalError:
                # libpq 연결 단계 오류에는 SQLSTATE가 없을 수 있다. 같은 서버의
                # 관리자 접속과 위에서 읽은 실제 rolcanlogin도 함께 확인한다.
                with cls.connect() as admin:
                    assert admin.execute('SELECT 1').fetchone()[0] == 1
            else:
                raise AssertionError('초기 NOLOGIN 역할에 접속했습니다')

    def setUp(self):
        # 운영 인증 설정을 흉내 내지 않는다. 새 로컬 trust 클러스터에서 실제 역할로 접속한다.
        with self.connect() as admin:
            admin.execute('ALTER ROLE reconnect_migrator LOGIN')
            admin.execute('ALTER ROLE reconnect_runtime LOGIN')
            admin.execute('DROP SCHEMA public CASCADE')
            admin.execute('CREATE SCHEMA public')
            admin.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
            admin.execute('GRANT USAGE, CREATE ON SCHEMA public TO reconnect_migrator')
            admin.execute('GRANT USAGE ON SCHEMA public TO reconnect_runtime')
        with self.connect(user='reconnect_migrator') as migrator:
            migrator.execute('CREATE TABLE public.app_rows(id bigserial PRIMARY KEY, value text NOT NULL)')
            migrator.execute('CREATE TABLE public.alembic_version(version_num text PRIMARY KEY)')
            migrator.execute("CREATE FUNCTION public.hidden_owner_function() RETURNS int LANGUAGE sql AS 'SELECT 1'")

    def tearDown(self):
        with self.connect() as admin:
            admin.execute('ALTER ROLE reconnect_migrator NOLOGIN')
            admin.execute('ALTER ROLE reconnect_runtime NOLOGIN')

    def grant(self):
        self.assertEqual(self.script('grant_runtime.sql', user='reconnect_migrator').returncode, 0)

    def denied(self, sql):
        with self.connect(user='reconnect_runtime') as runtime:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege): runtime.execute(sql)

    def test_initial_no_login_no_elevated_flags_and_no_owner_membership(self):
        self.assertEqual(len(self.initial_flags), 2)
        for row in self.initial_flags: self.assertEqual(row[1:], (False,)*7)
        with self.connect() as admin:
            self.assertFalse(admin.execute("SELECT pg_has_role('reconnect_runtime','reconnect_migrator','MEMBER')").fetchone()[0])
        self.denied('SET ROLE reconnect_migrator')
        self.denied('ALTER ROLE reconnect_runtime SUPERUSER')

    def test_normal_dml_and_sequence_use_but_no_ddl_truncate_schema_or_version_access(self):
        self.grant()
        with self.connect(user='reconnect_runtime') as runtime:
            identifier = runtime.execute("INSERT INTO public.app_rows(value) VALUES ('synthetic') RETURNING id").fetchone()[0]
            runtime.execute("UPDATE public.app_rows SET value='changed' WHERE id=%s", (identifier,))
            self.assertEqual(runtime.execute('SELECT value FROM public.app_rows').fetchall(), [('changed',)])
            runtime.execute('DELETE FROM public.app_rows WHERE id=%s', (identifier,))
            self.assertEqual(runtime.execute('SELECT count(*) FROM public.app_rows').fetchone()[0], 0)
            self.assertFalse(runtime.execute("SELECT has_table_privilege(current_user,'public.app_rows','SELECT WITH GRANT OPTION')").fetchone()[0])
        for sql in ('CREATE TABLE public.unapproved(id int)', 'CREATE SCHEMA unapproved',
            'CREATE TEMP TABLE unapproved(id int)', 'ALTER TABLE public.app_rows ADD COLUMN unapproved int',
            'DROP TABLE public.app_rows', 'TRUNCATE public.app_rows', 'SELECT * FROM public.alembic_version',
            "INSERT INTO public.alembic_version VALUES ('unapproved')", 'SELECT public.hidden_owner_function()',
            "SELECT setval('public.app_rows_id_seq',100)"):
            with self.subTest(sql=sql): self.denied(sql)

    def test_future_table_denied_until_explicit_regrant_and_regrant_is_idempotent(self):
        self.grant()
        with self.connect(user='reconnect_migrator') as migrator:
            migrator.execute('CREATE TABLE public.future_rows(id int)')
        self.denied('SELECT * FROM public.future_rows')
        self.grant(); self.grant()
        with self.connect(user='reconnect_runtime') as runtime:
            runtime.execute('INSERT INTO public.future_rows VALUES (1)')
            self.assertEqual(runtime.execute('SELECT * FROM public.future_rows').fetchall(), [(1,)])

    def test_existing_and_future_functions_are_not_executable_by_public(self):
        self.grant()
        with self.connect(user='reconnect_migrator') as migrator:
            migrator.execute("CREATE FUNCTION public.future_owner_function() RETURNS int LANGUAGE sql AS 'SELECT 1'")
        self.denied('SELECT public.hidden_owner_function()')
        self.denied('SELECT public.future_owner_function()')

    def test_foreign_function_owner_aborts_grants(self):
        with self.connect() as admin:
            admin.execute("CREATE FUNCTION public.foreign_owner_function() RETURNS int LANGUAGE sql AS 'SELECT 1'")
        self.assertNotEqual(self.script('grant_runtime.sql', user='reconnect_migrator').returncode, 0)
        self.denied('SELECT * FROM public.app_rows')

    def test_foreign_owner_aborts_all_grants_without_partial_authority(self):
        with self.connect() as admin: admin.execute('CREATE TABLE public.foreign_rows(id int)')
        self.assertNotEqual(self.script('grant_runtime.sql', user='reconnect_migrator').returncode, 0)
        self.denied('SELECT * FROM public.app_rows')
        self.denied('SELECT * FROM public.foreign_rows')
        self.denied("INSERT INTO public.app_rows(value) VALUES ('synthetic')")

    def test_repeat_bootstrap_does_not_reuse_or_modify_existing_roles(self):
        self.grant()
        self.assertNotEqual(self.script('bootstrap_database.sql').returncode, 0)
        with self.connect(user='reconnect_runtime') as runtime:
            runtime.execute("INSERT INTO public.app_rows(value) VALUES ('preserved')")
            self.assertEqual(runtime.execute('SELECT value FROM public.app_rows').fetchall(), [('preserved',)])


if __name__ == '__main__': unittest.main()
