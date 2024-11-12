import contextlib
from typing import Any, Coroutine, Iterator

import rich
from typing_extensions import override

from ..core.display import (
    TR,
    Display,
    Progress,
    TaskDisplay,
    TaskProfile,
    TaskScreen,
)
from ..core.progress import RichProgress, rich_progress
from ..core.results import tasks_results
from .app import TaskScreenApp


class TextualDisplay(Display):
    @override
    def print(self, message: str) -> None:
        rich.get_console().print(message, markup=False, highlight=False)

    @override
    @contextlib.contextmanager
    def progress(self, total: int) -> Iterator[Progress]:
        with rich_progress() as progress:
            yield RichProgress(total, progress)

    @override
    def run_task_app(self, title: str, main: Coroutine[Any, Any, TR]) -> TR:
        # create and run the app
        self.app = TaskScreenApp[TR](title)
        result = self.app.run_app(main)

        # print output
        print("\n".join(result.output))

        # print tasks
        rich.print(tasks_results(result.tasks))

        # raise error as required
        if isinstance(result.value, BaseException):
            raise result.value

        # success! return value
        else:
            return result.value

    @override
    @contextlib.contextmanager
    def task_screen(self, total_tasks: int, parallel: bool) -> Iterator[TaskScreen]:
        yield self.app.task_screen(total_tasks, parallel)

    @override
    @contextlib.contextmanager
    def task(self, profile: TaskProfile) -> Iterator[TaskDisplay]:
        yield self.app.task_display(profile)