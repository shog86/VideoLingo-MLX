"""单进程顺序任务执行器，供 Streamlit UI 与本地 API 共用。

背景：core 里的长循环（ASR、翻译、配音等）会调用
``core.utils.check_cancel()``。在引入本模块之前那只是一个空实现，取消和
暂停都无法真正生效。这里提供后台线程 + 协作式取消的机制，让那些调用点
立刻变为可用：暂停时线程阻塞在 ``check_cancel()``，停止时抛出 ``StopTask``。
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from typing import Callable, ClassVar


class StopTask(Exception):
    """用户请求停止任务时抛出，用于打断 core 内部的长循环。"""

    pass


@dataclass
class TaskRunner:
    """在后台线程里顺序执行一组步骤，并提供暂停 / 继续 / 停止能力。"""

    # 对外只读状态
    state: str = "idle"  # idle | running | paused | stopping | stopped | completed | error
    current_step: int = -1  # 0 起算，-1 表示尚未开始
    total_steps: int = 0
    current_label: str = ""
    error_msg: str = ""
    pause_message: str = ""  # 任务自身暂停的原因；用户手动暂停时为空

    # 内部状态
    _pause_event: threading.Event = field(default_factory=threading.Event)
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _steps: list = field(default_factory=list)
    # 步骤回调上报的整体进度（0.0~1.0）；为 None 时退化为按步骤数估算。
    _progress_pct: float | None = field(default=None, repr=False)

    # 类级别的“当前执行器”指针，使 core 内部函数无需持有引用即可调用
    # TaskRunner.check_cancel()。该指针只在 start() 启动的后台线程里有意义。
    _current: ClassVar["TaskRunner | None"] = None

    def __post_init__(self):
        self._pause_event.set()  # 初始为“未暂停”

    # ------ 取消相关（由 core 代码调用） ------

    @classmethod
    def check_cancel(cls) -> None:
        """暂停时阻塞等待，收到停止请求时抛出 :class:`StopTask`。

        可从任意线程调用；没有活动执行器时（例如命令行直接调用 core 脚本）
        是空操作。
        """
        runner = cls._current
        if runner is None:
            return
        # 暂停时阻塞，让长循环也能冻结在暂停点。
        runner._pause_event.wait()
        if runner._stop_event.is_set():
            raise StopTask()

    # ------ 控制接口 ------

    def start(self, steps: list[tuple[str, Callable]]):
        """在后台线程启动执行。

        参数:
            steps: ``(标签, 无参可调用)`` 列表，按顺序执行。
        """
        if self.is_active:
            raise RuntimeError("A task is already active")

        self._steps = steps
        self.total_steps = len(steps)
        self.current_step = -1
        self.current_label = ""
        self.error_msg = ""
        self.pause_message = ""
        self._progress_pct = None
        self.state = "running"

        self._pause_event.set()
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self, message: str = ""):
        """请求暂停；任务会停在下一个 check_cancel() 处。"""
        if self.state == "running":
            self._pause_event.clear()
            self.pause_message = message
            self.state = "paused"

    def resume(self):
        """继续被暂停的任务。"""
        if self.state == "paused":
            self.pause_message = ""
            self._pause_event.set()
            self.state = "running"

    def stop(self):
        """请求停止；任务会在下一个检查点停止。"""
        if self.state in ("running", "paused"):
            self.state = "stopping"
            self.pause_message = ""
            self._stop_event.set()
            self._pause_event.set()  # 若处于暂停则解除阻塞，让线程能退出

    def reset(self):
        """重置为 idle（仅在任务不活动时允许）。"""
        if not self.is_active:
            self.state = "idle"
            self.current_step = -1
            self.total_steps = 0
            self.current_label = ""
            self.error_msg = ""
            self.pause_message = ""
            self._progress_pct = None
            self._steps = []

    def set_progress(self, value: float) -> None:
        """记录 pipeline 步骤回调上报的整体进度（0.0~1.0），供 /status 等读取。

        由步骤内部的 progress_callback 调用（工作线程），把流水线归一的整体
        进度写进执行器，避免进度只按步骤数粗糙估算。
        """
        self._progress_pct = max(0.0, min(1.0, value))

    @property
    def is_active(self) -> bool:
        return self.state in ("running", "paused", "stopping") or bool(self._thread and self._thread.is_alive())

    @property
    def is_done(self) -> bool:
        return self.state in ("completed", "stopped", "error")

    @property
    def progress(self) -> float:
        """整体进度，取值 0.0 ~ 1.0。

        优先返回流水线按权重归一的回调进度；若步骤没有回报（例如检查点或
        纯命令步骤），退化为按步骤数估算。任务完成后一律为 1.0。
        """
        if self.state == "completed":
            return 1.0
        if self._progress_pct is not None:
            return self._progress_pct
        if self.total_steps == 0:
            return 0.0
        return max(self.current_step, 0) / self.total_steps

    # ------ 内部实现 ------

    def _run(self):
        """后台线程主体：按顺序执行各步骤，并响应暂停 / 停止。"""
        type(self)._current = self
        try:
            for i, (label, func) in enumerate(self._steps):
                # 每步开始前检查是否已请求停止
                if self._stop_event.is_set():
                    self.state = "stopped"
                    return

                # 暂停时在此阻塞
                self._pause_event.wait()

                # 恢复后再次检查停止
                if self._stop_event.is_set():
                    self.state = "stopped"
                    return

                self.current_step = i
                self.current_label = label
                func()
                self.check_cancel()

            self.state = "completed"
        except StopTask:
            self.state = "stopped"
        except Exception as e:
            self.error_msg = str(e)
            self.state = "error"
            traceback.print_exc()
        finally:
            if type(self)._current is self:
                type(self)._current = None
