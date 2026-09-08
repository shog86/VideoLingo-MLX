# -*- coding: utf-8 -*-
"""
在翻译前独立生成源语言字幕 src.srt。

背景：
  原流程把 src.srt 与 trans.srt 一并放在 _6_gen_sub 生成，导致 src.srt 被
  绑定到翻译之后。但 src.srt 只依赖"源文本 + 时间戳"，与翻译无关。

本模块数据流（放在 _3_2 之后、_4 之前运行）：
  本地词级转录(_2_CLEANED_CHUNKS)  +  在线 LLM 语义切分后的源句(_3_2_SPLIT_BY_MEANING)
    -> 按字幕长度标准做"源侧"粒度切分(复用 _5 的 split_sentence 与长度基准)
    -> align_timestamp 只输出 src.srt

收益：
  - src.srt 在翻译前一次性定稿，翻译链路任何改动都不影响它；
  - 后续 _6_gen_sub 不再生成/覆盖它，避免覆盖初始版本。
"""
import os
import pandas as pd
from rich import print as rprint
from rich.panel import Panel
from core.utils import *
from core.utils.models import *

# NOTE: 跨步骤依赖延迟导入，避免与 core/__init__.py 的加载顺序耦合
#   - split_sentence:         在线 LLM 语义切分（来自 _3_2）
#   - get_effective_max_length: 字幕最大行长的权威基准（来自 _5）
#   - align_timestamp:        词级到句级时间戳对齐 + SRT 写盘（来自 _6）


def _split_source_lines_to_subtitle(lines, max_sub_length):
    """把仍超长的源句切到字幕长度标准（复用在线 LLM 的 split_sentence）。

    因为源句可能很长，单次 num_parts=2 不一定够，这里最多做 3 轮递归切分；
    若某轮 LLM 未按 [br] 返回切分，则保留原句以规避死循环。

    参数:
        lines: 源句列表
        max_sub_length: 单条字幕允许的最大长度

    返回:
        切分后的源字幕行列表
    """
    from core._3_2_split_meaning import split_sentence

    result = []
    for line in lines:
        current = [line]
        for _round in range(3):
            # 全部满足长度则提前结束这一行
            if all(len(l) <= max_sub_length for l in current):
                break
            nxt = []
            for l in current:
                if len(l) <= max_sub_length:
                    nxt.append(l)
                    continue
                parts = split_sentence(l, num_parts=2).strip().split('\n')
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) <= 1:
                    # LLM 未按 [br] 切出多段，退化为原句，避免无端死循环
                    nxt.append(l)
                    rprint(f"[yellow][src_srt] 第 {_round + 1} 轮未获得可切分结果，保留原句: {l[:30]}...[/yellow]")
                else:
                    nxt.extend(parts)
            current = nxt
        result.extend(current)
    return result


def gen_source_srt(progress_callback=None):
    """前置生成源语言字幕 src.srt（在翻译前调用，依赖在线 LLM 做源句语义切分）。"""
    from translations.translations import translate as t
    def _report(pct, key):
        if progress_callback:
            try:
                progress_callback(step="src_srt", detail=t(key), percent=pct)
            except Exception:
                pass
    _report(5, "src_srt_start")
    rprint("[cyan][src_srt] 🎬 开始前置生成源语言字幕 src.srt...[/cyan]")

    # 1. 校验前置中间文件必须已存在
    if not os.path.exists(_2_CLEANED_CHUNKS):
        rprint("[red][src_srt] ❌ 未找到词级转录文件，请先运行 ASR(_2_asr)。[/red]")
        return
    if not os.path.exists(_3_2_SPLIT_BY_MEANING):
        rprint("[red][src_srt] ❌ 未找到语义切分文件，请先运行 _3_2_split_meaning。[/red]")
        return

    # 2. 读取本地 MLX 词级转录（提供时间戳）
    df_text = pd.read_excel(_2_CLEANED_CHUNKS)
    df_text['text'] = df_text['text'].str.strip('"').str.strip()

    # 3. 读取 _3_2 的源句（已用在线 LLM 按语义切好）
    with open(_3_2_SPLIT_BY_MEANING, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f if l.strip()]

    # 4. 源侧字幕粒度切分（复用 _5 的长度标准）
    from core._5_split_sub import get_effective_max_length
    max_sub_length = get_effective_max_length()
    rprint(f"[cyan][src_srt] 源句数={len(lines)}，字幕最大长度={max_sub_length}[/cyan]")
    _report(40, "src_srt_split")
    src_lines = _split_source_lines_to_subtitle(lines, max_sub_length)
    rprint(f"[cyan][src_srt] 字幕行数={len(src_lines)}（切分后）[/cyan]")

    # 5. 时间戳对齐并只输出 src.srt（Translation 留空不影响 Source 对齐）
    _report(70, "src_srt_align")
    from core._6_gen_sub import align_timestamp
    df_src = pd.DataFrame({'Source': src_lines, 'Translation': [''] * len(src_lines)})
    align_timestamp(df_text, df_src, [('src.srt', ['Source'])], _OUTPUT_DIR, for_display=False)

    _report(100, "src_srt_done")
    rprint(Panel("[bold green][src_srt] 🎉📝 源语言字幕 src.srt 已前置生成，翻译流程不再覆盖它。[/bold green]"))


if __name__ == "__main__":
    gen_source_srt()