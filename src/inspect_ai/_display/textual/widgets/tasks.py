import contextlib
from time import monotonic
from typing import Iterator, cast

from rich.console import RenderableType
from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer
from textual.reactive import reactive
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import ProgressBar, Static
from typing_extensions import override

from ...core.display import (
    Progress,
    TaskDisplay,
    TaskResult,
    TaskSpec,
    TaskWithResult,
)
from ...core.progress import (
    MAX_DESCRIPTION_WIDTH,
    MAX_MODEL_NAME_WIDTH,
    progress_description,
    progress_model_name,
    progress_status_icon,
    progress_time,
)


class TasksView(Container):
    DEFAULT_CSS = """
    TasksView {
        padding: 0 1;
        layout: grid;
        grid-size: 2 2;
        grid-columns: 1fr auto;
        grid-rows: auto 1fr;
    }
    #tasks-progress {
        column-span: 2;
        scrollbar-size-vertical: 1;
        margin-bottom: 1;
    }
    #tasks-targets {
        text-align: right;
    }
    """

    config: reactive[RenderableType] = reactive("")
    targets: reactive[RenderableType] = reactive("")

    def __init__(self) -> None:
        super().__init__()
        self.description_width = MAX_DESCRIPTION_WIDTH
        self.model_name_width = MAX_MODEL_NAME_WIDTH

    def init_tasks(self, tasks: list[TaskSpec]) -> None:
        # clear existing tasks
        self.tasks.remove_children()

        # compute the column widths by looking all of the tasks
        self.description_width = min(
            max([len(task.name) for task in tasks]), MAX_DESCRIPTION_WIDTH
        )
        self.model_name_width = min(
            max([len(str(task.model)) for task in tasks]), MAX_MODEL_NAME_WIDTH
        )

    def add_task(self, task: TaskWithResult) -> TaskDisplay:
        task_display = TaskProgressView(
            task, self.description_width, self.model_name_width
        )
        self.tasks.mount(task_display)
        self.tasks.scroll_to_widget(task_display)
        return task_display

    def compose(self) -> ComposeResult:
        yield Static(id="tasks-config")
        yield Static(id="tasks-targets")
        yield ScrollableContainer(id="tasks-progress")

    def watch_config(self, new_config: RenderableType) -> None:
        tasks_config = cast(Static, self.query_one("#tasks-config"))
        tasks_config.update(new_config)

    def watch_targets(self, new_targets: RenderableType) -> None:
        tasks_targets = cast(Static, self.query_one("#tasks-targets"))
        tasks_targets.update(new_targets)

    @property
    def tasks(self) -> ScrollableContainer:
        return cast(ScrollableContainer, self.query_one("#tasks-progress"))


class TaskProgressView(Widget):
    DEFAULT_CSS = """
    TaskProgressView {
        color: $text-muted;
        height: auto;
        width: 1fr;
        layout: grid;
        grid-size: 5 1;
        grid-columns: auto auto auto 1fr auto;
        grid-gutter: 1
    }
    TaskProgressView Bar {
        width: 1fr;
    }
    """

    def __init__(
        self, task: TaskWithResult, description_width: int, model_name_width: int
    ) -> None:
        super().__init__()
        self.t = task
        self.description_width = description_width
        self.model_name_width = model_name_width
        self.progress_bar = ProgressBar(total=task.profile.steps, show_eta=False)
        self.task_progress = TaskProgress(self.progress_bar)

    def compose(self) -> ComposeResult:
        yield TaskStatusIcon()
        yield Static(
            progress_description(self.t.profile, self.description_width, pad=True)
        )
        yield Static(
            progress_model_name(self.t.profile.model, self.model_name_width, pad=True)
        )
        yield self.progress_bar
        yield TaskTime()

    @contextlib.contextmanager
    def progress(self) -> Iterator[Progress]:
        yield self.task_progress

    def complete(self, result: TaskResult) -> None:
        self.t.result = result
        self.query_one(TaskStatusIcon).result = result
        self.query_one(TaskTime).complete()
        self.task_progress.complete()


class TaskStatusIcon(Static):
    result: reactive[TaskResult | None] = reactive(None)

    def __init__(self) -> None:
        super().__init__(progress_status_icon(None))

    def watch_result(self, new_result: TaskResult | None) -> None:
        self.update(progress_status_icon(new_result))


class TaskTime(Static):
    DEFAULT_CSS = """
    TaskTime {
        color: $accent-lighten-3;
    }
    """

    start_time: reactive[float] = reactive(monotonic)
    time = reactive(0.0)
    timer: Timer | None = None

    def complete(self) -> None:
        if self.timer:
            self.timer.stop()

    def on_mount(self) -> None:
        self.timer = self.set_interval(1, self.update_time)

    def update_time(self) -> None:
        self.time = monotonic() - self.start_time

    def watch_time(self, time: float) -> None:
        self.update(progress_time(time))


class TaskProgress(Progress):
    def __init__(self, progress_bar: ProgressBar) -> None:
        self.progress_bar = progress_bar

    @override
    def update(self, n: int = 1) -> None:
        self.progress_bar.update(advance=n)

    @override
    def complete(self) -> None:
        if self.progress_bar.total is not None:
            self.progress_bar.update(progress=self.progress_bar.total)
