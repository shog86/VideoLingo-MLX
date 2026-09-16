# -*- coding: utf-8 -*-
"""
标点恢复 + 句首大写（punctuation restoration + sentence case）。

背景：
  Whisper 英文转录常不带标点，导致下游 spaCy 断句依赖缺失、字幕句子首字母
  大小写不统一、句末无标点。本模块为英文转录补充标点与整句大写，且**严格不改
  动任何实词、拼写、专有名词、数字**（只增标点、只加大写，不增减词），保证
  clean/生产级字幕的忠实度。

数据流：
  _3_1 split_by_mark 在句级拼接后、spaCy 断句前调用本模块
  restore_punctuation_and_case(input_text, language)
    -> 分块 -> 每块走 LLM 恢复 -> 确定性 ensure_sentence_case 兜底保证。

注意：
  - 仅对英文启用（CJK 空格分隔语义不同，不做处理）。
  - 失败时回退到确定性句首大写 + 句末标点，绝不中断流程。
"""
import re
from rich import print as rprint
from core.prompts import get_punctuation_restore_prompt

# 单个 LLM 分块的最大字符数（受上下文窗口与成本限制）
_PUNCT_CHUNK_SIZE = 9000

# 按句子边界切分并保留分隔符（用于确定性句首大写/句末标点）
_SENT_SPLIT_RE = re.compile(r'[^.!?]*[.!?]+|[^.!?]+$')


def is_english(language: str) -> bool:
    """判断检测语言是否为英文（含 en/en-US 等）。"""
    return (language or '').lower().lstrip().startswith('en')


def ensure_sentence_case(text: str) -> str:
    """确定性兜底：保证每个已知句子句首首字母大写、句末有 . ? !。

    以现有 . ! ? 为句子边界；对已正确的内容保持不变（仅整句首字母、句末标点）。
    不新增/删除任何词，只调整大小写与补齐句末标点。
    """
    if not isinstance(text, str) or not text.strip():
        return text

    parts = _SENT_SPLIT_RE.findall(text)
    rebuilt = []
    for part in parts:
        s = part.strip()
        if not s:
            continue
        # 句首首字母大写
        m = re.search(r'[A-Za-z]', s)
        if m:
            s = s[:m.start()] + s[m.start()].upper() + s[m.start() + 1:]
        # 句末标点补齐（允许结尾引号）
        s = s.rstrip()
        if not re.search(r'[.!?](?:[\'\"”’»]*)\Z', s):
            s += '.'
        rebuilt.append(s)
    return ' '.join(rebuilt)


def _chunk_text(text: str, size: int = _PUNCT_CHUNK_SIZE) -> list:
    """把长文本切分为不超过 size 的块（优先在空格处断开，避免切断单词）。"""
    text = text.strip()
    chunks = []
    while len(text) > size:
        cut = text.rfind(' ', 0, size)
        if cut < size * 0.5:  # 找不到合适空格时硬切
            cut = size
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


def _restore_chunk(chunk: str, language: str):
    """对单个文本块做 LLM 标点恢复；失败返回 None 让调用方回退确定性处理。"""
    from core.utils.ask_gpt import ask_gpt  # lazy import: keeps module offline-testable

    prompt = get_punctuation_restore_prompt(chunk, language)
    try:
        resp = ask_gpt(prompt, resp_type='json', log_title='restore_punctuation')
        restored = resp.get('text') if isinstance(resp, dict) else None
        if isinstance(restored, str) and restored.strip():
            return restored.strip()
        rprint("[yellow]⚠️ Punctuation restoration returned empty, using deterministic fallback.[/yellow]")
    except Exception as e:  # noqa: BLE001 - 任何异常都回退，不中断主流程
        rprint(f"[yellow]⚠️ Punctuation restoration failed, using deterministic fallback: {e}[/yellow]")
    return None


def restore_punctuation_and_case(text: str, language: str) -> str:
    """对英文转录补标点 + 整句大写（主入口）。

    处理顺序：分块 -> LLM 恢复 -> 确定性 ensure_sentence_case 兜底保证。
    非英文或空输入原样返回。
    """
    if not isinstance(text, str) or not text.strip() or not is_english(language or ''):
        return text

    out = []
    for chunk in _chunk_text(text):
        restored = _restore_chunk(chunk, language) or chunk
        restored = ensure_sentence_case(restored)
        if restored.strip():
            out.append(restored)

    joined = ' '.join(p for p in out if p)
    return re.sub(r'\s+', ' ', joined).strip()


if __name__ == '__main__':
    # 纯本地确定性校验（不触发 LLM）
    for case in ["hello world", "it was covered in white paint",
                 "you know what", "so it was always covered in white paint"]:
        print(f"{case!r} -> {ensure_sentence_case(case)!r}")