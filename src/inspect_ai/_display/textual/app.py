from asyncio import CancelledError
from typing import Any, Coroutine

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header
from textual.worker import Worker, WorkerState
from typing_extensions import override

from inspect_ai._display.core.display import TR
from inspect_ai._util.terminal import detect_terminal_background

from ..core.rich import rich_initialise


class TaskScreenApp(App[TR]):
    TITLE = "Inspect Eval"
    CSS_PATH = "app.tcss"
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]

    def __init__(self, main: Coroutine[Any, Any, TR]) -> None:
        # call super
        super().__init__()

        # worker
        self.worker: Worker[TR] = self.run_worker(
            main, start=False, exit_on_error=False
        )

        # error
        self.error: BaseException | None = None

        # dynamically enable dark mode or light mode
        self.dark = detect_terminal_background().dark

        # enable rich hooks
        rich_initialise(self.dark)

    def result(self) -> TR | BaseException:
        if self.return_value is not None:
            return self.return_value
        elif self.error is not None:
            return self.error
        else:
            return RuntimeError("No application result available")

    def compose(self) -> ComposeResult:
        yield Header(classes="header")
        yield Footer()

    def on_mount(self) -> None:
        self.workers.start_all()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.state == WorkerState.ERROR:
            self.error = self.worker.error
            self.exit(None, 1)
        elif event.worker.state == WorkerState.CANCELLED:
            self.error = CancelledError()
            self.exit(None, 1)
        elif event.worker.state == WorkerState.SUCCESS:
            self.exit(self.worker.result)

    @override
    async def action_quit(self) -> None:
        if self.worker.is_running:
            self.worker.cancel()

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark
