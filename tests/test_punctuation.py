# -*- coding: utf-8 -*-
"""Offline unit tests for punctuation restoration and subtitle-timestamp fuzzy alignment.

这些测试**不触发 LLM/网络**，只验证纯函数/确定性逻辑：
  - ensure_sentence_case:      句首大写 + 句末标点（用户回归项：输出必须句首大写、句末有标点）
  - restore_punctuation_and_case: 非英文/空输入原样返回
  - get_sentence_timestamps:   精确匹配失败时用模糊匹配兜底（容忍 ASR 清填充词等微差）
"""
import pandas as pd

from core.asr_backend.punctuation import ensure_sentence_case, restore_punctuation_and_case
from core._6_gen_sub import get_sentence_timestamps


# ----------------------------
# ensure_sentence_case（确定性）
# ----------------------------
def test_sentence_case_capitalizes_first_letter():
    """输入小写句子，应当句首字母大写、句末补句号。"""
    assert ensure_sentence_case("it was covered in white paint") == "It was covered in white paint."


def test_sentence_case_preserves_question_mark():
    """句末问号应保留，且不以句点替代。"""
    out = ensure_sentence_case("you know what?")
    assert out.startswith("You")
    assert out.endswith("?")
    assert "know what?" in out


def test_sentence_case_multi_sentence():
    """多句文本应逐句大写并以句点/叹号分隔。"""
    out = ensure_sentence_case("hello world. goodbye now")
    assert out.startswith("Hello world.")
    assert out.lower().endswith("goodbye now.")
    assert out.count(".") == 2


def test_sentence_case_empty_or_nonnone():
    """空/空白输入应原样返回，不崩溃。"""
    assert ensure_sentence_case("") == ""
    assert ensure_sentence_case(None) is None


# ------------------------------------
# restore_punctuation_and_case（主入口）
# ------------------------------------
def test_restore_passthrough_non_english():
    """非英文输入不应被处理（原样返回），避免改动 CJK。"""
    src = "これはテストです"
    assert restore_punctuation_and_case(src, "ja") == src


def test_restore_passthrough_empty():
    """空输入应原样返回。"""
    assert restore_punctuation_and_case("", "en") == ""
    assert restore_punctuation_and_case(None, "en") is None


def test_is_english_variants():
    """逗号分隔的英文语言码应被识别为英文。"""
    from core.asr_backend.punctuation import is_english
    assert is_english("en")
    assert is_english("en-US")
    assert is_english("English")
    assert not is_english("zh")


# ------------------------------------
# get_sentence_timestamps（模糊对齐兜底）
# ------------------------------------
def test_alignment_fuzzy_fallback():
    """源句与 ASR 词串含微差（如填充词 'you know' 被清洗）时，应走模糊匹配而非抛错。

    ASR 词串:  "so it was always you know covered in white paint"
    源句:      "it was always covered in white paint"（'you know' 已被清）
    """
    words = ["so", "it", "was", "always", "you", "know", "covered", "in", "white", "paint"]
    df_words = pd.DataFrame({
        "text": [w for w in words],
        "start": [i * 1.0 for i in range(len(words))],
        "end": [(i + 1) * 1.0 for i in range(len(words))],
    })
    df_sentences = pd.DataFrame({
        "Source": ["it was always covered in white paint"]
    })

    stamps = get_sentence_timestamps(df_words, df_sentences)
    assert len(stamps) == 1
    start, end = stamps[0]
    # 模糊兜底按字符窗口匹配，因 ASR 中插入了 'you know'，窗口无法全覆盖完整句尾。
    # 预期：起点应对应 "it"（索引 1），终点落在句子真实区间附近（"white"/"paint"）。
    assert start == 1.0
    assert 8.0 <= end <= 10.0


def test_alignment_exact_match_unchanged():
    """全文完全一致时，精确匹配路径仍应正常工作。"""
    words = ["hello", "world"]
    df_words = pd.DataFrame({
        "text": ["hello", "world"],
        "start": [0.0, 1.0],
        "end": [1.0, 2.0],
    })
    df_sentences = pd.DataFrame({"Source": ["hello world"]})
    stamps = get_sentence_timestamps(df_words, df_sentences)
    assert stamps == [(0.0, 2.0)]


if __name__ == "__main__":
    import sys
    # 简单手跑：python tests/test_punctuation.py
    cases = [
        test_sentence_case_capitalizes_first_letter,
        test_sentence_case_preserves_question_mark,
        test_sentence_case_multi_sentence,
        test_sentence_case_empty_or_nonnone,
        test_restore_passthrough_non_english,
        test_restore_passthrough_empty,
        test_is_english_variants,
        test_alignment_fuzzy_fallback,
        test_alignment_exact_match_unchanged,
    ]
    failures = 0
    for fn in cases:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {fn.__name__}: {e}")
    sys.exit(1 if failures else 0)