import unittest

import numpy as np

from pvm.schema import parse_storyboard
from pvm.timeline import build_cues, build_timeline, char_time, srt
from pvm.tts import Word, _ark_words, ark_resource_id
from pvm.voice import SentenceAudio, VoiceTrack, align_words, trim_silence
from tests.helpers import board

TEXTS = ["你有没有发现，有些人明明不懂，却特别自信？", "两位心理学家在期刊上发表了一项研究。",
         "他们发现，测试得分最低的人高估了自己的表现。", "问题不在于不懂，而在于不知道自己不懂。",
         "所以下次特别确定的时候，先问问自己是怎么知道的。", "你身边有这样的人吗？"]


def sa(n, text, start, end, words=(), para_end=False):
    return SentenceAudio(n, text, start, end, para_end, [list(w) for w in words])


def fake_track() -> VoiceTrack:
    t, sentences = 0.3, []
    for i, text in enumerate(TEXTS, 1):
        dur = len(text) * 0.2
        sentences.append(sa(i, text, round(t, 3), round(t + dur, 3)))
        t += dur + 0.25
    return VoiceTrack("audio/voice.wav", round(t + 1.0, 3), {"engine": "test"}, sentences)


class CharTimeTest(unittest.TestCase):
    def test_interpolates_between_word_timings(self):
        s = sa(1, "哈佛大学经济学家", 1.0, 3.0, [(1.0, 1.5, 0, 2), (1.5, 2.0, 2, 4), (2.0, 3.0, 4, 8)])
        self.assertAlmostEqual(char_time(s, 2), 1.5)
        self.assertAlmostEqual(char_time(s, 6), 2.5)

    def test_proportional_without_word_timings(self):
        self.assertAlmostEqual(char_time(sa(1, "一二三四", 0.0, 4.0), 2), 2.0)


class VoiceTest(unittest.TestCase):
    def test_tokens_map_to_characters_in_order(self):
        words = [Word(0.1, 0.5, "2022"), Word(0.5, 0.8, "年"), Word(1.2, 1.5, "哈佛")]
        out = align_words("2022年，哈佛大学", words, offset=0.1, duration=5.0)
        self.assertEqual([w[2:] for w in out], [[0, 4], [4, 5], [6, 8]])
        self.assertAlmostEqual(out[0][0], 0.0)

    def test_trim_silence_keeps_a_little_padding(self):
        x = np.concatenate([np.zeros(500), np.full(1000, 0.5), np.zeros(700)]).astype(np.float32)
        y, cut = trim_silence(x, 1000)
        self.assertAlmostEqual(cut, 0.46, places=3)
        self.assertEqual(len(y), 1099)

    def test_ark_helpers(self):
        self.assertEqual(ark_resource_id("zh_male_jieshuoxiaoming_uranus_bigtts"), "seed-tts-2.0")
        self.assertEqual(ark_resource_id("S_abc123"), "seed-icl-2.0")
        self.assertEqual(ark_resource_id("zh_female_shuangkuaisisi_moon_bigtts"), "seed-tts-1.0")
        msg = {"sentence": {"text": "你好", "words": [{"word": "你", "startTime": 50, "endTime": 180},
                                                      {"word": "好", "startTime": 180, "endTime": 400}]}}
        self.assertEqual([(w.text, w.start) for w in _ark_words(msg)], [("你", 0.05), ("好", 0.18)])  # ms -> s
        long = {"sentence": {"words": [{"word": "长", "startTime": 1000, "endTime": 125000}]}}
        self.assertAlmostEqual(_ark_words(long)[0].end, 125.0)  # milliseconds are detected


class TimelineTest(unittest.TestCase):
    def test_scenes_cut_in_pauses_and_focus_follows_the_narration(self):
        track = fake_track()
        tl = build_timeline(parse_storyboard(board()), track)
        s = track.sentences
        self.assertEqual(tl.scenes[0].start, 0.0)
        self.assertAlmostEqual(tl.scenes[1].start, (s[2].end + s[3].start) / 2, places=3)
        self.assertEqual(tl.scenes[-1].end, track.duration)
        self.assertEqual([f[0] for f in tl.scenes[1].focus], [0, 1, 2])
        self.assertAlmostEqual(tl.scenes[1].focus[0][1], tl.scenes[1].start, places=3)
        self.assertAlmostEqual(tl.scenes[1].focus[1][1], s[4].start - 0.15, places=3)
        self.assertEqual(tl.scenes[0].highlights[0][0], "overestimated")
        self.assertAlmostEqual(tl.hook[1], tl.scenes[0].end, places=3)
        self.assertEqual(len(tl.facts), 2)

    def test_cues_run_in_order_without_overlap(self):
        cues = build_cues(fake_track().sentences)
        self.assertTrue(all(c.end > c.start for c in cues))
        self.assertTrue(all(a.end <= b.start + 1e-6 for a, b in zip(cues, cues[1:])))
        self.assertTrue(all(len(c.text) <= 16 for c in cues))

    def test_srt_timestamps(self):
        text = srt(build_cues(fake_track().sentences)[:1])
        self.assertTrue(text.startswith("1\n00:00:00,300 --> 00:00:0"), text)


if __name__ == "__main__":
    unittest.main()
