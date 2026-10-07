import copy
import json
import unittest

import httpx

from pvm import quota
from pvm.llm import LLM, LlmReply
from pvm.planner import PLAN_SYSTEM, plan, review, unsupported
from pvm.project import Project
from pvm.util import PvmError, read_json, write_json
from tests.helpers import SCRIPT, TempHome, board, fixture_paper


def completion(content: str) -> dict:
    return {"model": "deepseek-chat", "choices": [{"message": {"content": content}}], "usage": {"total_tokens": 10}}


class LlmClientTest(unittest.TestCase):
    def test_json_mode_request_and_retry_on_empty_content(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(json.loads(request.content))
            content = "" if len(calls) == 1 else json.dumps({"ok": True})
            return httpx.Response(200, json=completion(content))

        llm = LLM("https://api.example.com/", "k", "deepseek-chat", transport=httpx.MockTransport(handler))
        reply = llm.json("system says json", "user")
        self.assertEqual(reply.data, {"ok": True})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["response_format"], {"type": "json_object"})
        self.assertEqual([m["role"] for m in calls[0]["messages"]], ["system", "user"])

    def test_client_errors_are_not_retried(self):
        transport = httpx.MockTransport(lambda r: httpx.Response(401, text="bad key"))
        with self.assertRaises(PvmError) as ctx:
            LLM("https://api.example.com", "k", "m", transport=transport).json("s", "u")
        self.assertIn("401", str(ctx.exception))


class PlanTextSpendTest(TempHome):
    def test_plan_calls_are_billed_by_tokens_including_failed_attempts(self):
        replies = iter(["", json.dumps({"ok": True})])  # the first attempt comes back empty and is still billed

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": next(replies)}}],
                                             "usage": {"prompt_tokens": 12_000, "completion_tokens": 3_000}})

        llm = LLM("https://ark.cn-beijing.volces.com/api/plan/v3", "k", "deepseek-v4.1-flash",
                  transport=httpx.MockTransport(handler))
        llm.json("s", "u")
        # (12,000 + 3,000) tokens x 2.5 AFP per 10,000 = 3.75, rounded up per call
        self.assertEqual([(e["kind"], e["afp"]) for e in quota.entries()], [("text", 4), ("text", 4)])

    def test_other_endpoints_cost_no_afp(self):
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json=completion(json.dumps({"ok": True}))))
        LLM("https://api.deepseek.com", "k", "deepseek-chat", transport=transport).json("s", "u")
        self.assertEqual(quota.entries(), [])


class FakeLLM:
    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def json(self, system, user, **kw):
        self.prompts.append(user)
        return LlmReply(copy.deepcopy(self.replies.pop(0)), "fake-model", {})


class PlannerTest(TempHome):
    def project(self) -> Project:
        p, _ = Project.open_or_create("plan")
        p.set_script(SCRIPT)
        p.set_paper(fixture_paper())
        return p

    def test_prompt_requires_json_and_verbatim_excerpts(self):
        self.assertIn("JSON", PLAN_SYSTEM)
        self.assertIn("character for character", PLAN_SYSTEM)

    def test_invalid_draft_gets_one_repair_round_with_the_errors(self):
        p = self.project()
        bad = board(hook_claim=None)
        llm = FakeLLM(bad, board())
        meta = plan(p, llm)
        self.assertEqual((meta["rounds"], meta["errors"]), (2, []))
        self.assertIn("hook_claim missing", llm.prompts[1])
        self.assertIn("SOURCE TEXT", llm.prompts[0])
        self.assertEqual(read_json(p.storyboard_path)["hook"], board()["hook"])
        self.assertEqual(p.check().errors, [])

    def test_existing_storyboard_is_not_overwritten(self):
        p = self.project()
        write_json(p.storyboard_path, board(title="hand-written"))
        meta = plan(p, FakeLLM(board()))
        self.assertEqual(meta["file"], "storyboard.draft.json")
        self.assertEqual(read_json(p.storyboard_path)["title"], "hand-written")

    def test_review_flags_overreach(self):
        p = self.project()
        write_json(p.storyboard_path, board())
        verdicts = {"claims": [{"index": i, "supported": True, "issues": [], "fix": ""} for i in range(1, 7)],
                    "hook": {"supported": True, "issues": [], "fix": ""}}
        verdicts["claims"][2] = {"index": 3, "supported": False, "issues": ["causation"], "fix": "他们发现……相关"}
        llm = FakeLLM(verdicts)
        result = review(p, llm)
        self.assertIn("Journal of Fixtures", llm.prompts[0])  # the citation metadata reaches the reviewer
        self.assertFalse(result["passed"])
        problems = unsupported(result)
        self.assertEqual(len(problems), 1)
        self.assertIn("claim 3 (source_fact): causation", problems[0])
        self.assertTrue((p.dir / "review.json").exists())


if __name__ == "__main__":
    unittest.main()
