"""#91: 설정 삽입과 비인가 호스트 입력은 구성 생성 단계에서 거절한다."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'nginx_render', Path(__file__).resolve().parents[1] / 'render_config.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class RenderTests(unittest.TestCase):
    def test_domain_replaced_without_touching_nginx_variables(self):
        config = renderer.render('app.example.test')
        self.assertNotIn('@@DOMAIN@@', config)
        self.assertIn('server_name app.example.test;', config)
        self.assertIn('try_files $uri $uri/ /index.html;', config)
        self.assertIn('proxy_pass http://backend:8000;', config)

    def test_configuration_injection_and_non_dns_input_rejected(self):
        for domain in ('', 'localhost', 'APP.EXAMPLE.TEST', 'app.test;return 200;',
                       '*.example.test', '$host', 'app.test\ninclude /tmp/config;',
                       'app.test#', 'app.test.', 'a..test', '-app.test', 'app-.test',
                       '127.0.0.1', 'app.test:443', 'https://app.test', '가.test',
                       'a' * 64 + '.test', '.'.join(['a' * 63] * 5)):
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                renderer.render(domain)
