import contextlib
from asyncio import CancelledError
from typing import Any, Coroutine, Generic, Iterator

import rich
from rich.console import Console
from textual.app import App, ComposeResult
from textual.events import Print
from textual.widgets import TabbedContent, TabPane
from textual.worker import Worker, WorkerState
from typing_extensions import override

from inspect_ai._util.terminal import detect_terminal_background

from ..core.display import (
    TR,
    Progress,
    TaskDisplay,
    TaskProfile,
    TaskResult,
    TaskScreen,
    TaskWithResult,
)
from ..core.rich import rich_initialise
from .widgets.footer import TaskScreenFooter
from .widgets.header import TaskScreenHeader
from .widgets.log import LogView
from .widgets.samples import SamplesView
from .widgets.tasks import TasksView


class TaskScreenResult(Generic[TR]):
    def __init__(
        self,
        value: TR | BaseException,
        tasks: list[TaskWithResult],
        output: list[str],
    ) -> None:
        self.value = value
        self.tasks = tasks
        self.output = output


class TaskScreenApp(App[TR]):
    CSS_PATH = "app.tcss"
    BINDINGS = [
        ("t", "show_tasks", "Task list"),
        ("s", "show_samples", "Running samples"),
        ("l", "show_log", "Log messages"),
    ]

    def __init__(self, title: str) -> None:
        # call super
        super().__init__()

        # initialise members
        self._title = title
        self._worker: Worker[TR] | None = None
        self._error: BaseException | None = None
        self._tasks: list[TaskWithResult] = []
        self._output: list[str] = []

        # dynamically enable dark mode or light mode
        self.dark = detect_terminal_background().dark

        # enable rich hooks
        rich_initialise(self.dark)

    def run_app(self, main: Coroutine[Any, Any, TR]) -> TaskScreenResult[TR]:
        # create the worker
        self._worker = self.run_worker(main, start=False, exit_on_error=False)

        # run the app
        self.run()

        # determine result value
        if self.return_value is not None:
            value: TR | BaseException = self.return_value
        elif self._error is not None:
            value = self._error
        else:
            value = RuntimeError("No application result available")

        # return result w/ output
        return TaskScreenResult(value=value, tasks=self._tasks, output=self._output)

    def task_screen(self, total_tasks: int, parallel: bool) -> TaskScreen:
        return TextualTaskScreen()

    def task_display(self, profile: TaskProfile) -> TaskDisplay:
        return TextualTaskDisplay(profile, self._tasks)

    def compose(self) -> ComposeResult:
        yield TaskScreenHeader()
        yield TaskScreenFooter()

        with TabbedContent(initial="log"):
            with TabPane("Tasks", id="tasks"):
                yield TasksView()
            with TabPane("Samples", id="samples"):
                yield SamplesView()
            with TabPane("Log", id="log"):
                yield LogView()

    def on_mount(self) -> None:
        self.workers.start_all()
        self.begin_capture_print(self)
        header = self.query_one(TaskScreenHeader)
        header.title = self._title

    def on_print(self, event: Print) -> None:
        # remove trailing newline
        text = event.text
        if text.endswith("\n"):
            text = text[:-1]

        # track output (for printing at the end)
        self._output.append(text)

        # write to log view
        self.query_one(LogView).write_ansi(text)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.state == WorkerState.ERROR:
            self._error = event.worker.error
            self.exit(None, 1)
        elif event.worker.state == WorkerState.CANCELLED:
            self._error = CancelledError()
            self.exit(None, 1)
        elif event.worker.state == WorkerState.SUCCESS:
            self.exit(event.worker.result)

    @override
    async def action_quit(self) -> None:
        if self._worker and self._worker.is_running:
            self._worker.cancel()

    def action_show_tasks(self) -> None:
        self.switch_tab("tasks")

    def action_show_samples(self) -> None:
        self.switch_tab("samples")

    def action_show_log(self) -> None:
        self.switch_tab("log")

    def switch_tab(self, id: str) -> None:
        self.query_one(TabbedContent).active = id


class TextualTaskScreen(TaskScreen):
    def __exit__(self, *excinfo: Any) -> None:
        pass

    @override
    @contextlib.contextmanager
    def input_screen(
        self,
        header: str | None = None,
        transient: bool | None = None,
        width: int | None = None,
    ) -> Iterator[Console]:
        yield rich.get_console()


class TextualTaskDisplay(TaskDisplay):
    def __init__(self, profile: TaskProfile, results: list[TaskWithResult]) -> None:
        self.profile = profile
        self.results = results

    @override
    @contextlib.contextmanager
    def progress(self) -> Iterator[Progress]:
        yield TextualProgress()

    @override
    def complete(self, result: TaskResult) -> None:
        self.results.append(TaskWithResult(self.profile, result))


class TextualProgress(Progress):
    @override
    def update(self, n: int = 1) -> None:
        pass

    @override
    def complete(self) -> None:
        pass