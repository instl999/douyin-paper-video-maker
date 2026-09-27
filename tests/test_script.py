import unittest

from pvm.script import display_text, sentences_hash, split_sentences, subtitle_chunks, word_starts


class SentenceSplitTest(unittest.TestCase):
    def test_splits_and_keeps_closing_quotes(self):
        s = split_sentences("研究发现，人会高估自己……真的吗？“我不信。”\n第二段")
        self.assertEqual([x.text for x in s], ["研究发现，人会高估自己……", "真的吗？", "“我不信。”", "第二段"])
        self.assertEqual([x.para_end for x in s], [False, False, True, True])

    def test_hash_tracks_the_text(self):
        a = sentences_hash(["一。", "二。"])
        self.assertEqual(a, sentences_hash(["一。", "二。"]))
        self.assertNotEqual(a, sentences_hash(["一。", "二！"]))


class DisplayTextTest(unittest.TestCase):
    def test_strips_punctuation_but_keeps_marks_inside_tokens(self):
        self.assertEqual(display_text("丹尼尔·卡尼曼的研究"), "丹尼尔·卡尼曼的研究")
        self.assertEqual(display_text("Kahneman's book, e.g. Thinking"), "Kahneman's book eg Thinking")
        self.assertEqual(display_text("增长了3.5倍，共1,200人。"), "增长了3.5倍共1,200人")
        self.assertEqual(display_text("“好吗？”他说。"), "好吗他说")


class SubtitleChunkTest(unittest.TestCase):
    LONG = "当你身边全是处境相近的同龄人时，你会不自觉地和所有人做出一样的选择"

    def test_words_stay_intact(self):
        if word_starts("测试") is None:
            self.skipTest("jieba not installed")
        chunks = [c[2] for c in subtitle_chunks(self.LONG)]
        self.assertEqual("".join(chunks), display_text(self.LONG))
        for word in ("处境", "所有"):
            self.assertTrue(any(word in c for c in chunks), (word, chunks))

    def test_chunks_stay_near_the_width_limit(self):
        for _, _, text in subtitle_chunks(self.LONG, max_chars=14):
            self.assertLessEqual(len(text), 16)

    def test_explicit_boundaries_win_near_the_target(self):
        s = "一二三四五六七八九十一二三四五六七八"
        chunks = subtitle_chunks(s, max_chars=10, boundaries={0, 8, 12})
        self.assertEqual(chunks[0][1], 8)


if __name__ == "__main__":
    unittest.main()
