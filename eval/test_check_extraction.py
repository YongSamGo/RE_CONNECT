"""경험 추출 채점기 회귀 시험. 2026-10-28 EC2 측정의 실제 출력 형태를 재현한다.

실행: python -m unittest discover -s eval -p test_*.py
"""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace as N

from check_extraction import CASES, korean_number, score, summary

PERSONAS = Path(__file__).resolve().parent / "personas"


def persona(persona_id):
    return json.loads((PERSONAS / f"{persona_id}.json").read_text(encoding="utf-8"))


def quote(text, turn):
    return N(text=text, turn_index=turn)


def selected(description, turn, duration=None, skills=()):
    return N(description=quote(description, turn), duration=quote(duration, turn) if duration else None,
             skills=[quote(skill, turn) for skill in skills])


def accepted(description, duration=None, skills=()):
    return N(description=description, duration_note=duration, skill_tags=list(skills))


class KoreanNumber(unittest.TestCase):
    def test_sino_korean_years(self):
        cases = {"삼십오 년": 35, "이십 년": 20, "십오 년": 15, "칠 년 정도": 7, "한 삼십 년.": 30, "25년": 25, "이십이 년": 22}
        self.assertEqual({text: korean_number(text) for text in cases}, cases)
        self.assertIsNone(korean_number("오래"))
        self.assertIsNone(korean_number("일했어요"))


class Scoring(unittest.TestCase):
    def test_v2_p04_drops_next_turn_skills(self):
        # 모델은 다음 턴(1번)의 업무 구절을 기술로 붙였고 서버가 버렸다.
        plan = N(experiences=[selected("중소기업 경리, 회계 업무", 0, "이십오 년", ["세금계산서 발행"])])
        plan.experiences[0].skills[0].turn_index = 1
        preview = N(experiences=[accepted("중소기업 경리, 회계 업무", "이십오 년")])
        result = score(persona("P04"), CASES["P04"], plan, preview)
        self.assertEqual((result["accepted"], result["turn_recall"], result["non_experience"]), (True, 0.5, 0))
        self.assertEqual((result["duration_recall"], result["dropped"], result["leaks"]), (1.0, 1, 0))
        self.assertEqual(result["skill_recall"], 0.25)  # "회계"만 설명과 겹친다

    def test_v2_p07_certification_as_skill_and_whole_turn(self):
        plan = N(experiences=[selected("병원에서 간호조무사", 0, "이십이 년", ["요양보호사 자격증"])])
        preview = N(experiences=[accepted("병원에서 간호조무사", "이십이 년", ["요양보호사 자격증"])])
        result = score(persona("P07"), CASES["P07"], plan, preview)
        self.assertEqual((result["cert_as_skill"], result["whole_turn"], result["leaks"]), (1, 0, 0))

    def test_non_experience_turn_whole_sentence_and_leak_are_counted(self):
        turns = persona("P08")["interview"]
        plan = N(experiences=[selected(turns[0], 0), selected("620315-2123456", 1)])
        preview = N(experiences=[accepted(turns[0]), accepted("620315-2123456")])
        result = score(persona("P08"), CASES["P08"], plan, preview)
        self.assertEqual((result["whole_turn"], result["non_experience"], result["leaks"]), (1, 1, 1))

    def test_rejected_result_scores_zero(self):
        result = score(persona("P01"), CASES["P01"], None, None)
        self.assertEqual((result["accepted"], result["experiences"], result["turn_recall"]), (False, 0, 0.0))

    def test_summary_totals(self):
        rows = [dict(accepted=True, over_limit=False, latency_s=20.0, turn_recall=1.0, skill_recall=0.5, duration_recall=1.0,
                     non_experience=0, whole_turn=1, cert_as_skill=0, dropped=2, leaks=0),
                dict(accepted=False, over_limit=True, latency_s=70.0, turn_recall=0.0, skill_recall=0.0, duration_recall=0.0,
                     non_experience=0, whole_turn=0, cert_as_skill=0, dropped=0, leaks=0)]
        self.assertEqual(summary(rows), {"runs": 2, "accepted": 1, "over_limit": 1, "latency_max_s": 70.0, "turn_recall": 0.5,
                                         "skill_recall": 0.25, "duration_recall": 0.5, "non_experience": 0, "whole_turn": 1,
                                         "cert_as_skill": 0, "dropped": 2, "leaks": 0})


class Cases(unittest.TestCase):
    def test_cases_cover_personas_and_valid_turns(self):
        self.assertEqual(set(CASES), {path.stem for path in PERSONAS.glob("P0*.json")})
        for persona_id, case in CASES.items():
            turns = persona(persona_id)["interview"]
            self.assertTrue(case["experience_turns"])
            self.assertTrue(all(0 <= turn < len(turns) for turn in case["experience_turns"]), persona_id)
            # 자격증 구절은 실제 대화에 나온 표현이어야 한다(P07의 주입 문장 포함).
            self.assertTrue(all(any(cert in turn for turn in turns) for cert in case["certifications"]), persona_id)


if __name__ == "__main__":
    unittest.main()
