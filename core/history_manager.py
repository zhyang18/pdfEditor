"""
历史操作与撤销/重做管理模块。
基于命令模式（Command Pattern）实现用户操作的追溯、撤销与重做。
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Callable


class Command(ABC):
    """
    可撤销操作命令抽象基类。
    所有支持撤销重做的具体页面或文档操作均需继承并实现该接口。
    """

    def __init__(self, description: str) -> None:
        """
        初始化命令对象。

        @param description 当前命令的人类可读中文描述信息，例如 '移动第 3 页到第 1 页'
        """
        self._description = description

    @property
    def description(self) -> str:
        """
        获取命令描述。

        @return 命令的中文描述文本
        """
        return self._description

    @abstractmethod
    def execute(self) -> bool:
        """
        执行命令逻辑。

        @return 执行是否成功完成
        """
        pass

    @abstractmethod
    def undo(self) -> bool:
        """
        撤销命令逻辑，将状态还原至执行前。

        @return 撤销是否成功完成
        """
        pass


class HistoryManager:
    """
    撤销与重做历史记录管理器。
    维护撤销栈与重做栈，并提供状态变更回调机制。
    """

    def __init__(self, max_history_size: int = 50) -> None:
        """
        初始化历史记录管理器。

        @param max_history_size 撤销栈的最大容量，默认为 50
        """
        self._max_history_size: int = max_history_size
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        self._on_change_callbacks: List[Callable[[], None]] = []

    def add_on_change_listener(self, callback: Callable[[], None]) -> None:
        """
        注册撤销/重做栈状态改变监听回调。

        @param callback 状态改变时触发的无参回调函数
        """
        self._on_change_callbacks.append(callback)

    def _notify_change(self) -> None:
        """
        通知所有已注册的回调函数，状态发生改变。
        """
        for callback in self._on_change_callbacks:
            try:
                callback()
            except Exception:
                pass

    def push(self, command: Command) -> bool:
        """
        执行新命令并压入撤销栈，同时清空重做栈。

        @param command 待执行的具体命令对象
        @return 命令执行是否成功
        """
        success = command.execute()
        if success:
            self._undo_stack.append(command)
            if len(self._undo_stack) > self._max_history_size:
                self._undo_stack.pop(0)
            self._redo_stack.clear()
            self._notify_change()
        return success

    def execute_command(self, command: Command) -> bool:
        """
        执行新命令并压入撤销栈（push 方法的语义别名）。

        @param command 待执行的具体命令对象
        @return 命令执行是否成功
        """
        return self.push(command)

    def push_already_executed(self, command: Command) -> None:
        """
        将已经在外部执行完毕的命令记录直接压入撤销栈，清空重做栈。

        @param command 已经执行完毕的命令对象
        """
        self._undo_stack.append(command)
        if len(self._undo_stack) > self._max_history_size:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._notify_change()

    def undo(self) -> bool:
        """
        撤销最近一次执行的命令，并将其转移至重做栈。

        @return 撤销是否成功
        """
        if not self.can_undo():
            return False
        cmd = self._undo_stack.pop()
        success = cmd.undo()
        if success:
            self._redo_stack.append(cmd)
            self._notify_change()
            return True
        else:
            # 撤销失败，回退状态
            self._undo_stack.append(cmd)
            self._notify_change()
            return False

    def redo(self) -> bool:
        """
        重做最近一次被撤销的命令，并将其重新压入撤销栈。

        @return 重做是否成功
        """
        if not self.can_redo():
            return False
        cmd = self._redo_stack.pop()
        success = cmd.execute()
        if success:
            self._undo_stack.append(cmd)
            self._notify_change()
            return True
        else:
            # 重做失败，回退状态
            self._redo_stack.append(cmd)
            self._notify_change()
            return False

    def can_undo(self) -> bool:
        """
        判断当前是否可以执行撤销。

        @return 若撤销栈不为空返回 True，否则返回 False
        """
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        """
        判断当前是否可以执行重做。

        @return 若重做栈不为空返回 True，否则返回 False
        """
        return len(self._redo_stack) > 0

    def get_undo_description(self) -> Optional[str]:
        """
        获取当前待撤销命令的描述文本。

        @return 待撤销命令的中文描述；若无可撤销项则返回 None
        """
        if self.can_undo():
            return self._undo_stack[-1].description
        return None

    def get_redo_description(self) -> Optional[str]:
        """
        获取当前待重做命令的描述文本。

        @return 待重做命令的中文描述；若无可重做项则返回 None
        """
        if self.can_redo():
            return self._redo_stack[-1].description
        return None

    def clear(self) -> None:
        """
        清空全部撤销与重做历史记录。
        """
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._notify_change()
