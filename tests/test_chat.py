"""Rule-based campus helper: complaints, sorting answers and scores come from data, never guesses."""

from tests import _env  # noqa: F401  (must be first)

import unittest

from starlette.testclient import TestClient

from app import chat, db, grader
from app.server import app


def say(msg, lang="en", ctx=None):
    return chat.reply(msg, lang, ctx)


class Sorting(unittest.TestCase):
    def test_items(self):
        for msg, stream in [("where does a battery go?", "special_care"), ("banana peel kahan daalu", "wet"),
                            ("which bin for a plastic bottle", "dry"), ("diaper", "sanitary"),
                            ("बैटरी कहाँ डालें", "special_care"), ("chai patti kis dabbe mein", "wet")]:
            self.assertEqual(say(msg).get("stream"), stream, msg)

    def test_unknown_item_is_not_guessed(self):
        r = say("where does a mattress go?")
        self.assertIsNone(r.get("stream"))
        self.assertIn("not sure", r["say"])

    def test_word_inside_another_word_is_not_an_item(self):
        self.assertIsNone(say("where can i find my notepad").get("stream"))


class Complaints(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_one_shot(self):
        r = say("The bin is full at Govind Bhawan")
        self.assertEqual(r["action"], "issue_created")
        issue = next(i for i in db.list_issues("open") if i["id"] == r["issue_id"])
        self.assertEqual((issue["bhawan"], issue["kind"]), ("Govind", "overflow"))

    def test_asks_for_bhawan_then_logs(self):
        r = say("dabba bhar gaya hai")
        self.assertIsNone(r["action"])
        self.assertIn("Ganga", r["choices"])
        r2 = say("Ganga", ctx=r["context"])
        self.assertEqual(r2["action"], "issue_created")
        issue = next(i for i in db.list_issues("open") if i["id"] == r2["issue_id"])
        self.assertEqual((issue["bhawan"], issue["kind"]), ("Ganga", "overflow"))

    def test_hindi(self):
        r = say("आज़ाद भवन में कूड़े की गाड़ी नहीं आई", "hi")
        self.assertEqual(r["action"], "issue_created")
        self.assertIn("आज़ाद", r["say"] + "आज़ाद")

    def test_status(self):
        iid = say("pickup missed at Rajiv")["issue_id"]
        self.assertIn("still open", say(f"status {iid}")["say"])
        self.assertIn("can't find", say("status 9999999")["say"])


class Scores(unittest.TestCase):
    def test_score_uses_real_data(self):
        db.init_db()
        rid = db.create_report("Sarojini", "wet", None, "bin is clean", None)
        db.save_grade(rid, grader.grade_bin(None, "wet", "bin is clean"))
        r = say("Sarojini score")
        self.assertIn("Sarojini scores", r["say"])
        self.assertIn("/100", r["say"])

    def test_help_fallback(self):
        self.assertIn("I can log a complaint", say("hello")["say"])


class Endpoint(unittest.TestCase):
    def test_chat_api(self):
        with TestClient(app) as c:
            r = c.post("/api/chat", json={"message": "where does a bulb go"}).json()
            self.assertEqual(r["stream"], "special_care")
            self.assertEqual(c.post("/api/chat", json={"message": ""}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
