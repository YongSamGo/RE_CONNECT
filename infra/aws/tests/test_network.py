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
    for name in ('DatabaseRouteAssociationA', 'DatabaseRouteAssociationB'):
        test.assertEqual(resources[name]['Properties']['RouteTableId'], {'Ref': 'DatabaseRoutes'})
    test.assertEqual(resources['DatabaseSecurityGroup']['Properties'].get('SecurityGroupEgress'),
                     [dict(IpProtocol='tcp', FromPort=9, ToPort=9, CidrIp='127.0.0.1/32')])
    test.assertEqual(resources['AppSecurityGroup']['Properties'].get('SecurityGroupEgress'),
                     [dict(IpProtocol='tcp', FromPort=443, ToPort=443, CidrIp='0.0.0.0/0')])
    test.assertEqual(resources['AppDatabaseEgress']['Properties'], dict(
        GroupId={'Ref': 'AppSecurityGroup'}, IpProtocol='tcp', FromPort=5432, ToPort=5432,
        DestinationSecurityGroupId={'Ref': 'DatabaseSecurityGroup'}))
    for resource in resources.values():
        if resource['Type'] == 'AWS::EC2::Route':
            test.assertNotEqual(resource['Properties']['RouteTableId'], {'Ref': 'DatabaseRoutes'})
    ingress = resources['AppSecurityGroup']['Properties']['SecurityGroupIngress']
    test.assertEqual(ingress, [dict(IpProtocol='tcp', FromPort=443, ToPort=443, CidrIp='0.0.0.0/0')])
    test.assertEqual(resources['Application']['Properties']['MetadataOptions']['HttpTokens'], 'required')
    test.assertEqual(resources['Application']['Properties']['MetadataOptions']['HttpPutResponseHopLimit'], 2)
    test.assertEqual(resources['Application']['Properties']['IamInstanceProfile'], {'Ref': 'InstanceProfileName'})
    test.assertEqual(resources['ApplicationAddress']['Properties'],
                     dict(Domain='vpc', InstanceId={'Ref': 'Application'}))
    test.assertEqual(resources['ApplicationAddress']['DependsOn'], 'GatewayAttachment')


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

    def test_reject_database_subnet_on_application_routes(self):
        for name in ('DatabaseRouteAssociationA', 'DatabaseRouteAssociationB'):
            with self.subTest(name=name):
                changed = copy.deepcopy(self.resources)
                changed[name]['Properties']['RouteTableId'] = {'Ref': 'AppRoutes'}
                with self.assertRaises(AssertionError):
                    assert_isolated(self, changed)

    def test_reject_implicit_or_unrestricted_egress(self):
        for name in ('DatabaseSecurityGroup', 'AppSecurityGroup'):
            for replacement in (None, [dict(IpProtocol='-1', CidrIp='0.0.0.0/0')]):
                with self.subTest(name=name, replacement=replacement):
                    changed = copy.deepcopy(self.resources)
                    if replacement is None:
                        del changed[name]['Properties']['SecurityGroupEgress']
                    else:
                        changed[name]['Properties']['SecurityGroupEgress'] = replacement
                    with self.assertRaises(AssertionError):
                        assert_isolated(self, changed)

    def test_reject_missing_management_profile_static_address_or_container_imds(self):
        for field in ('IamInstanceProfile', 'MetadataOptions'):
            changed = copy.deepcopy(self.resources)
            del changed['Application']['Properties'][field]
            with self.assertRaises((AssertionError, KeyError)):
                assert_isolated(self, changed)
        changed = copy.deepcopy(self.resources)
        changed['Application']['Properties']['MetadataOptions']['HttpPutResponseHopLimit'] = 1
        with self.assertRaises(AssertionError):
            assert_isolated(self, changed)
        changed = copy.deepcopy(self.resources)
        del changed['ApplicationAddress']
        with self.assertRaises(KeyError):
            assert_isolated(self, changed)
