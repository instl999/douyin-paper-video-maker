"""Shared test fixtures: a throwaway PVM_HOME and a small, valid storyboard."""
from __future__ import annotations

import copy
import os
import shutil
import tempfile
import unittest

from pvm.schema import Paper

SCRIPT = (
    "你有没有发现，有些人明明不懂，却特别自信？\n"
    "两位心理学家在期刊上发表了一项研究。他们发现，测试得分最低的人高估了自己的表现。\n"
    "问题不在于不懂，而在于不知道自己不懂。\n"
    "所以下次特别确定的时候，先问问自己是怎么知道的。你身边有这样的人吗？"
)
# Sentences: 1 question · 2 attribution · 3 finding · 4 reading · 5 advice · 6 question

TITLE = "Calibration of Self-Assessment in Novices: A Fixture Study"
ABSTRACT = ("Across three studies, novice participants consistently overestimated their own performance on "
            "reasoning tasks. Feedback from peers reduced this overconfidence.")
FINDING = "novice participants consistently overestimated their own performance on reasoning tasks"


def fixture_paper(**overrides) -> Paper:
    data = {"title": TITLE, "authors": ["Ada Lovelace", "Alan Turing"], "year": 2020, "venue": "Journal of Fixtures",
            "doi": "10.1234/fixture.1", "abstract": ABSTRACT, "is_oa": False, "oa_status": "closed"}
    data.update(overrides)
    return Paper.model_validate(data)


BOARD = {
    "version": 2,
    "title": "测试视频",
    "hook": ["越不懂", "越高估自己"],
    "hook_until": 3,
    "hook_claim": {"type": "source_fact", "evidence": [{"source": "src1", "excerpt": FINDING}]},
    "claims": [
        {"sentences": [1, 1], "type": "interpretation"},
        {"sentences": [2, 2], "type": "source_fact", "evidence": [{"source": "src1", "excerpt": TITLE}]},
        {"sentences": [3, 3], "type": "source_fact", "evidence": [{"source": "src1", "excerpt": FINDING}]},
        {"sentences": [4, 4], "type": "interpretation"},
        {"sentences": [5, 5], "type": "advice"},
        {"sentences": [6, 6], "type": "interpretation"},
    ],
    "scenes": [
        {"id": "open", "type": "paper", "sentences": [1, 3], "highlights": [{"text": "overestimated", "at": 3}]},
        {"id": "p1", "type": "poster", "sentences": [4, 6], "title": "错而不自知", "sections": [
            {"heading": "不懂不自知", "visual": "mascot holds a wrong answer sheet", "labels": ["不会做"], "at": 4},
            {"heading": "先问自己", "visual": "mascot looks into a magnifying glass", "labels": ["怎么知道"], "at": 5},
            {"heading": "你呢", "visual": "mascot points at the viewer", "labels": [], "at": 6},
        ]},
    ],
}


def board(**changes) -> dict:
    data = copy.deepcopy(BOARD)
    data.update(changes)
    return data


class TempHome(unittest.TestCase):
    """Runs each test with PVM_HOME in a fresh temporary directory."""

    def setUp(self):
        self._old_home = os.environ.get("PVM_HOME")
        self.home = tempfile.mkdtemp(prefix="pvm-test-")
        os.environ["PVM_HOME"] = self.home

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("PVM_HOME", None)
        else:
            os.environ["PVM_HOME"] = self._old_home
        shutil.rmtree(self.home, ignore_errors=True)
