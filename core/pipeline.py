"""统一的处理流程定义，供 Streamlit UI、批处理与本地 API 共用。

历史上 st.py 与 batch/utils/video_processor.py 各自维护了一份步骤清单，
改动容易漏改（例如 ``_gen_source_srt`` 之前只存在于 UI 侧）。这里把流程
收敛成唯一的一份定义，三个入口都从这里取步骤，避免继续分叉。

步骤定义形如 ``(标签, 调用列表, 进度权重)``：
  * 标签保持为翻译 key，只有 UI 负责翻译展示；
  * 调用列表里是 ``"模块.函数"`` 字符串，延迟导入，避免在导入期拉起重依赖；
  * 进度权重用来把该步骤内部 0-100 的进度映射到整条流水线的对应区间。
"""

from __future__ import annotations

import inspect
import json
from functools import partial
from importlib import import_module
from pathlib import Path
from typing import Callable, Optional

from core.task_runner import TaskRunner
from core.utils.config_utils import load_key, load_key_or
from core.utils.models import _4_1_TERMINOLOGY, _4_2_TRANSLATION, _5_SPLIT_SUB


# ── 字幕（转写 + 翻译）流水线 ──────────────────────────────────────────────
# 权重取自 st.py 原先的分步区间：ASR 55 / NLP 5 / 语义切分 10 / 源字幕 3 /
# 摘要 5 / 翻译 12 / 长句切分 6 / 时间轴对齐 4。
_TRANSCRIBE_CORE = [
    ("section_transcribe", ("_2_asr.transcribe",), 55),
    ("ph_nlp", ("_3_1_split_nlp.split_by_spacy",), 5),
    ("ph_meaning", ("_3_2_split_meaning.split_sentences_by_meaning",), 10),
    ("ph_src_srt", ("_gen_source_srt.gen_source_srt",), 3),
]

# 只生成源字幕，不做翻译、不合成视频
TRANSCRIBE_STEPS = _TRANSCRIBE_CORE

# 完整字幕流程（不含烧录；烧录由 UI 选择轨道或 API 单独触发）
SUBTITLE_STEPS = _TRANSCRIBE_CORE + [
    ("ph_sum", ("_4_1_summarize.get_summary",), 5),
    # 术语表检查点在翻译前后各插一次，直接复用 TaskRunner 的暂停能力
    ("ph_trans", ("pipeline.review_terminology", "_4_2_translate.translate_all",
                  "pipeline.review_translation"), 12),
    ("ph_split", ("_5_split_sub.split_for_sub_main",), 6),
    ("ph_gen", ("_6_gen_sub.align_timestamp_main",), 4),
]

# ── 配音流水线 ──────────────────────────────────────────────────────────────
DUBBING_STEPS = [
    ("Generate audio tasks", ("_8_1_audio_task.gen_audio_task_main", "_8_2_dub_chunks.gen_dub_chunks"), 10),
    ("Extract refer audio", ("_9_refer_audio.extract_refer_audio_main",), 20),
    ("Generate all audio", ("_10_gen_audio.gen_audio",), 50),
    ("Merge full audio", ("_11_merge_audio.merge_full_audio",), 10),
    ("Merge dubbing to the video", ("_12_dub_to_vid.merge_video_audio",), 10),
]

# 烧录步骤：默认烧 [src.srt, trans.srt]；UI 会自行指定用户选择的轨道
BURN_STEP = ("section_burn", ("_7_sub_into_vid.merge_subtitles_to_video",), 1)


# ── 检查点提示文案（同样作为翻译 key） ────────────────────────────────────
REVIEW_TERMINOLOGY = "Terminology is ready for review. Edit `output/log/terminology.json` if needed, then press Resume to start translating."
INVALID_TERMINOLOGY = "`output/log/terminology.json` can not be read after your edit. Fix it, then press Resume."
REVIEW_TRANSLATION = "Translation is ready for review. Edit the `Translation` column of `output/log/translation_results.xlsx` if needed, without changing the `Source` column or the number of rows. Save and close the file, then press Resume."
INVALID_TRANSLATION = "`output/log/translation_results.xlsx` can not be used after your edit. Keep the rows and the `Source` column as they were, leave no translation empty, and close the file. Then press Resume."


# ── 检查点校验 ──────────────────────────────────────────────────────────────

def terminology_error():
    """返回术语表文件的问题说明；可用时返回 None。"""
    try:
        terminology = json.loads(Path(_4_1_TERMINOLOGY).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return str(e)
    terms = terminology.get("terms") if isinstance(terminology, dict) else None
    if not isinstance(terms, list):
        return "`terms` must be a list"
    for term in terms:
        if not isinstance(term, dict) or not all(isinstance(term.get(key), str) for key in ("src", "tgt", "note")):
            return f"Each term needs the texts `src`, `tgt` and `note`: {term}"
    return None


def review_terminology():
    """可选检查点 ``pause_before_translate``：暂停等待用户确认术语表后再翻译。"""
    runner = TaskRunner._current
    if runner is None or not load_key("pause_before_translate") or Path(_4_2_TRANSLATION).exists():
        return
    message = REVIEW_TERMINOLOGY
    while True:
        runner.pause(message)
        TaskRunner.check_cancel()
        error = terminology_error()
        if error is None:
            return
        print(f"⚠️ {_4_1_TERMINOLOGY}: {error}")
        message = INVALID_TERMINOLOGY


def read_translation():
    """读取翻译结果表，返回 ``[源文列表, 译文列表]``，空单元格记为 ''。"""
    import pandas as pd
    df = pd.read_excel(_4_2_TRANSLATION)
    return [["" if pd.isna(value) else str(value).strip() for value in df[column]] for column in ("Source", "Translation")]


def translation_error(source, translation):
    """返回用户修改后翻译结果表的问题；可用时返回 None。"""
    try:
        edited_source, edited_translation = read_translation()
    except Exception as e:  # 被表格软件占用 / 已不是表格 / 缺列
        return f"{type(e).__name__}: {e}"
    if edited_source != source:
        return "the rows or the `Source` column have changed"
    for row, (before, after) in enumerate(zip(translation, edited_translation), 2):
        if before and not after:
            return f"the translation in row {row} is empty"
    return None


def review_translation():
    """可选检查点 ``pause_after_translate``：暂停等待用户确认译文后再切分字幕。"""
    runner = TaskRunner._current
    if runner is None or not load_key_or("pause_after_translate", False) or Path(_5_SPLIT_SUB).exists():
        return
    source, translation = read_translation()
    message = REVIEW_TRANSLATION
    while True:
        runner.pause(message)
        TaskRunner.check_cancel()
        error = translation_error(source, translation)
        if error is None:
            return
        print(f"⚠️ {_4_2_TRANSLATION}: {error}")
        message = INVALID_TRANSLATION


# ── 执行引擎 ────────────────────────────────────────────────────────────────

def _load_callable(dotted: str) -> Callable:
    """把 ``"模块.函数"`` 解析为可调用对象；``pipeline.*`` 指向本模块。"""
    module, function = dotted.split(".")
    if module == "pipeline":
        return globals()[function]
    return getattr(import_module(f"core.{module}"), function)


def _accepts_progress(func: Callable) -> bool:
    """判断目标函数是否接受 progress_callback 关键字参数。"""
    try:
        return "progress_callback" in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def _scaled(progress_callback, lo: float, hi: float):
    """把子步骤 0-100 的进度映射到整体 [lo, hi] 区间。"""
    if progress_callback is None:
        return None

    def _cb(step=None, detail=None, percent=None):
        if percent is None:
            progress_callback(step=step, detail=detail, percent=None)
            return
        try:
            p = max(0.0, min(100.0, float(percent)))
        except (TypeError, ValueError):
            progress_callback(step=step, detail=detail, percent=None)
            return
        progress_callback(step=step, detail=detail, percent=lo + (hi - lo) * p / 100.0)

    return _cb


def _run_calls(calls, lo: float, hi: float, progress_callback=None):
    """执行一个步骤内的若干函数，并把该步骤的进度窗口分配给它。

    同一窗口内若有多个函数支持进度回调，则平均分配；不支持回调的函数
    （例如检查点）视为瞬时完成，不占用窗口。
    """
    funcs = [_load_callable(call) for call in calls]
    progress_funcs = [f for f in funcs if _accepts_progress(f)]
    span = (hi - lo) / len(progress_funcs) if progress_funcs else 0.0
    slot = 0
    for func in funcs:
        # 每个函数前都检查一次，保证取消 / 暂停能及时生效
        TaskRunner.check_cancel()
        if _accepts_progress(func):
            func(progress_callback=_scaled(progress_callback, lo + slot * span, lo + (slot + 1) * span))
            slot += 1
        else:
            func()
    TaskRunner.check_cancel()


def _select_plans(stage: str, dubbing: bool, burn: bool):
    """根据阶段参数挑选步骤清单。"""
    if stage not in {"transcribe", "subtitles", "dubbing", "all"}:
        raise ValueError(f"Unknown stage: {stage}")
    plans = []
    if stage == "transcribe":
        plans.append(TRANSCRIBE_STEPS)
    elif stage == "subtitles":
        plans.append(SUBTITLE_STEPS)
    elif stage == "all":
        plans.append(SUBTITLE_STEPS)
        # 仅当显式要求配音时才追加，保持与 UI“字幕先于配音”一致
        if dubbing:
            plans.append(DUBBING_STEPS)
    elif stage == "dubbing":
        plans.append(DUBBING_STEPS)
    if burn:
        plans.append([BURN_STEP])
    return plans


def get_steps(stage: str = "subtitles", progress_callback=None, dubbing: bool = False,
              burn: bool = False) -> list[tuple[str, Callable]]:
    """构建一次完整的顺序执行计划，返回 ``(标签, 无参可调用)`` 列表给 TaskRunner。

    ``stage="all"`` 时仅当 ``dubbing=True`` 才追加配音步骤（与 UI 的“字幕先于
    配音”一致）。所有步骤的进度权重会统一归一化到 0-100。
    """
    plans = _select_plans(stage, dubbing, burn)
    definitions = [step for plan in plans for step in plan]
    total = sum(weight for _, _, weight in definitions) or 1.0
    steps = []
    consumed = 0.0
    for label, calls, weight in definitions:
        lo = consumed / total * 100.0
        consumed += weight
        hi = consumed / total * 100.0
        steps.append((label, partial(_run_calls, calls, lo, hi, progress_callback)))
    return steps


def run_stage(stage: str, dubbing: bool = False, burn: bool = False, progress_callback=None):
    """同步执行某个阶段，供批处理等没有 TaskRunner 的调用方使用。"""
    for _, step in get_steps(stage, progress_callback=progress_callback, dubbing=dubbing, burn=burn):
        step()


def burn_subtitles(tracks=None, log_callback=None):
    """把指定轨道烧录进视频；``tracks`` 为空时由底层默认取 src.srt + trans.srt。"""
    _load_callable("_7_sub_into_vid.merge_subtitles_to_video")(tracks=tracks, log_callback=log_callback)
