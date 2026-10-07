import os
import unittest
from unittest import mock

from pvm import config
from pvm.llm import make_llm
from pvm.render.video import default_jobs
from pvm.util import PvmError


class SettingsTest(unittest.TestCase):
    def settings(self, env: dict):
        config.get_settings.cache_clear()
        try:
            with mock.patch.object(config, "load_dotenv", return_value={}), mock.patch.dict(os.environ, env, clear=True):
                return config.get_settings()
        finally:
            config.get_settings.cache_clear()

    def test_agent_plan_key_never_covers_the_planner(self):
        # the plan's terms forbid API calls to its text models (risk of suspension or a ban)
        s = self.settings({"AGENT_PLAN_API_KEY": "plan-key"})
        self.assertEqual(s.api_key, "plan-key")
        self.assertIsNone(s.llm_api_key)
        with self.assertRaises(PvmError) as ctx:
            make_llm(s)
        self.assertIn("PVM_LLM_API_KEY", str(ctx.exception))

    def test_own_deepseek_key(self):
        s = self.settings({"AGENT_PLAN_API_KEY": "plan-key", "PVM_LLM_API_KEY": "ds-key"})
        self.assertEqual((s.llm_api_key, s.llm_base_url, s.llm_model), ("ds-key", "https://api.deepseek.com", "deepseek-chat"))
        self.assertEqual(make_llm(s).model, "deepseek-chat")

    def test_plan_endpoints_and_the_plan_key_are_refused(self):
        for env in ({"PVM_LLM_API_KEY": "k", "PVM_LLM_BASE_URL": config.AGENT_PLAN_BASE_URL},
                    {"PVM_LLM_API_KEY": "k", "PVM_LLM_BASE_URL": "https://ark.cn-beijing.volces.com/api/coding/v3"},
                    {"AGENT_PLAN_API_KEY": "plan-key", "PVM_LLM_API_KEY": "plan-key",
                     "PVM_LLM_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3"}):
            with self.assertRaises(PvmError, msg=env) as ctx:
                make_llm(self.settings(env))
            self.assertIn("terms", str(ctx.exception))
        pay_as_you_go = self.settings({"PVM_LLM_API_KEY": "ark-key", "PVM_LLM_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3"})
        self.assertEqual(make_llm(pay_as_you_go).base_url, "https://ark.cn-beijing.volces.com/api/v3")

    def test_image_model_default_and_price_override(self):
        s = self.settings({})
        self.assertEqual((s.image_model, s.afp_per_image), ("doubao-seedream-5-0-pro", None))
        self.assertEqual(self.settings({"PVM_AFP_PER_IMAGE": "120"}).afp_per_image, 120)


class RenderJobsTest(unittest.TestCase):
    def test_short_renders_stay_in_one_process(self):
        self.assertEqual(default_jobs(299), 1)
        self.assertGreaterEqual(default_jobs(3000), 1)


if __name__ == "__main__":
    unittest.main()
