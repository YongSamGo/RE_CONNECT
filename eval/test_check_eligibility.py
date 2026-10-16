"""기대값 검사기의 미확인 정보·기준일·연산 경계 회귀 시험.

실행: python -m unittest discover -s eval -p test_*.py
"""

import unittest

from check_eligibility import judge, judge_posting


def condition(**changes):
    return {"id": "r1", "field": "age", "operator": "gte", "value": 60,
            "clarity": "clear", "reference_date": "2026-10-14",
            "group_id": None, "group_operator": None, **changes}


class EligibilityBoundaries(unittest.TestCase):
    def test_age_requires_its_own_reference_date(self):
        self.assertEqual(judge(condition(reference_date=None), {"birth_year": 1960}, 2026), "unknown")
        self.assertEqual(judge(condition(reference_date="2020-01-01"), {"birth_year": 1965}, 2026), "not_satisfied")
        self.assertEqual(judge(condition(), {"birth_year": 1965}, 2020), "satisfied")

    def test_unknown_district_is_not_a_mismatch(self):
        profile = {"residence_region": {"province": "seoul", "district": None}}
        rule = condition(field="residence_region", operator="in", value=[{"province": "seoul", "district": "seongdong"}])
        self.assertEqual(judge(rule, profile, 2026), "unknown")
        rule["value"].append({"province": "seoul", "district": None})
        self.assertEqual(judge(rule, profile, 2026), "satisfied")
        rule["value"] = [{"province": "incheon", "district": None}]
        self.assertEqual(judge(rule, profile, 2026), "not_satisfied")

    def test_invalid_operator_is_rejected_even_when_input_is_unknown(self):
        for field, operator in [("age", "in"), ("weekday", "gte"), ("certification", "has"), ("residence_region", "includes")]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                judge(condition(field=field, operator=operator), {}, 2026)

    def test_invalid_group_cannot_default_to_and(self):
        for rules in [
            [condition(group_id="g")],
            [condition(group_operator="and")],
            [condition(group_id="g", group_operator="and"), condition(id="r2", group_id="g", group_operator="or")],
        ]:
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                judge_posting({"labels": {}, "requirements": rules}, {"birth_year": 1960}, 2026)


if __name__ == "__main__":
    unittest.main()
