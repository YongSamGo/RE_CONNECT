"""#90: 부적절한 인가·중요정보 평문 전송을 막는 배포 경계 회귀."""
import copy
from pathlib import Path
import unittest

import yaml


def assert_isolated(test, resources):
    db = resources['Database']['Properties']
    test.assertIs(db['PubliclyAccessible'], False)
    test.assertIs(db['StorageEncrypted'], True)
    test.assertIs(db['ManageMasterUserPassword'], True)
    test.assertNotIn('MasterUserPassword', db)
    test.assertEqual(resources['DatabaseParameters']['Properties']['Parameters']['rds.force_ssl'], '1')
    test.assertEqual(db['DBSubnetGroupName'], {'Ref': 'DatabaseSubnets'})
    test.assertEqual(db['VPCSecurityGroups'], [{'Ref': 'DatabaseSecurityGroup'}])
    rules = resources['DatabaseSecurityGroup']['Properties']['SecurityGroupIngress']
    test.assertEqual(rules, [dict(IpProtocol='tcp', FromPort=5432, ToPort=5432,
                                 SourceSecurityGroupId={'Ref': 'AppSecurityGroup'})])
    for name in ('DatabaseSubnetA', 'DatabaseSubnetB'):
        test.assertIs(resources[name]['Properties']['MapPublicIpOnLaunch'], False)
    for resource in resources.values():
        if resource['Type'] == 'AWS::EC2::Route':
            test.assertNotEqual(resource['Properties']['RouteTableId'], {'Ref': 'DatabaseRoutes'})
    ingress = resources['AppSecurityGroup']['Properties']['SecurityGroupIngress']
    test.assertEqual(ingress, [dict(IpProtocol='tcp', FromPort=443, ToPort=443, CidrIp='0.0.0.0/0')])
    test.assertEqual(resources['Application']['Properties']['MetadataOptions']['HttpTokens'], 'required')


class NetworkTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'network.yaml'
        self.resources = yaml.safe_load(path.read_text(encoding='utf-8'))['Resources']

    def test_network_is_isolated(self):
        assert_isolated(self, self.resources)

    def test_reject_public_database_and_plaintext(self):
        for field in ('PubliclyAccessible', 'StorageEncrypted', 'ManageMasterUserPassword'):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.resources)
                changed['Database']['Properties'][field] = field == 'PubliclyAccessible'
                with self.assertRaises(AssertionError):
                    assert_isolated(self, changed)

    def test_reject_world_database_ingress(self):
        changed = copy.deepcopy(self.resources)
        rule = changed['DatabaseSecurityGroup']['Properties']['SecurityGroupIngress'][0]
        rule.pop('SourceSecurityGroupId')
        rule['CidrIp'] = '0.0.0.0/0'
        with self.assertRaises(AssertionError):
            assert_isolated(self, changed)

    def test_reject_database_internet_route(self):
        changed = copy.deepcopy(self.resources)
        changed['LeakedRoute'] = copy.deepcopy(changed['AppInternetRoute'])
        changed['LeakedRoute']['Properties']['RouteTableId'] = {'Ref': 'DatabaseRoutes'}
        with self.assertRaises(AssertionError):
            assert_isolated(self, changed)
