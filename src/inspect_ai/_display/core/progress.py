from typing import Callable

import rich
from rich.progress import (
    BarColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.progress import Progress as RProgress
from typing_extensions import override

from .display import Progress
from .rich import is_vscode_notebook

# Note that use of rich progress seems to result in an extra
# empty cell after execution, see: https://github.com/Textualize/rich/issues/3274

PROGRESS_TOTAL = 102


class RichProgress(Progress):
    def __init__(
        self,
        total: int,
        progress: RProgress,
        description: str = "",
        model: str = "",
        status: Callable[[], str] | None = None,
        on_update: Callable[[], None] | None = None,
    ) -> None:
        self.total = total
        self.progress = progress
        self.status = status if status else lambda: ""
        self.on_update = on_update
        self.task_id = progress.add_task(
            description, total=PROGRESS_TOTAL, model=model, status=self.status()
        )

    @override
    def update(self, n: int = 1) -> None:
        advance = (float(n) / float(self.total)) * 100
        self.progress.update(
            task_id=self.task_id, advance=advance, refresh=True, status=self.status()
        )
        if self.on_update:
            self.on_update()

    @override
    def complete(self) -> None:
        self.progress.update(
            task_id=self.task_id, completed=PROGRESS_TOTAL, status=self.status()
        )


def rich_progress() -> RProgress:
    console = rich.get_console()
    return RProgress(
        TextColumn("{task.fields[status]}"),
        TextColumn("{task.description}"),
        TextColumn("{task.fields[model]}"),
        BarColumn(bar_width=40 if is_vscode_notebook(console) else None),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        transient=True,
        console=console,
        expand=not is_vscode_notebook(console),
    )