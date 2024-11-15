from typing import Any, Callable, NamedTuple, Sequence, Type

from pydantic_core import to_json
from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text
from textual.containers import ScrollableContainer
from textual.widgets import Static

from inspect_ai._util.content import ContentText
from inspect_ai._util.format import format_function_call
from inspect_ai._util.transcript import (
    MARKDOWN_CODE_THEME,
    transcript_markdown,
    transcript_separator,
)
from inspect_ai.log._samples import ActiveSample
from inspect_ai.log._transcript import (
    ApprovalEvent,
    ErrorEvent,
    Event,
    InfoEvent,
    InputEvent,
    LoggerEvent,
    ModelEvent,
    SampleInitEvent,
    ScoreEvent,
    StepEvent,
    SubtaskEvent,
    ToolEvent,
)
from inspect_ai.model._chat_message import ChatMessage, ChatMessageUser
from inspect_ai.model._render import messages_preceding_assistant
from inspect_ai.tool._tool import ToolResult


class TranscriptView(ScrollableContainer):
    def __init__(self) -> None:
        super().__init__()
        self._sample: ActiveSample | None = None
        self._events: list[Event] = []

    async def sync_sample(self, sample: ActiveSample | None) -> None:
        # update existing
        if (
            sample is not None
            and self._sample is not None
            and (sample.id == self._sample.id)
        ):
            scrolled_to_bottom = abs(self.scroll_y - self.max_scroll_y) <= 3
            append_events = sample.transcript.events[len(self._events) :]
            self._events.extend(append_events)
            await self.mount_all(
                [Static(widget) for widget in self._widgets_for_events(append_events)]
            )
            if scrolled_to_bottom:
                self.scroll_end()
        # new sample
        else:
            self._sample = sample
            async with self.batch():
                await self.remove_children()
                if sample is not None:
                    self._events = list(sample.transcript.events)
                    await self.mount_all(
                        [
                            Static(widget)
                            for widget in self._widgets_for_events(self._events)
                        ]
                    )
                    self.scroll_end(animate=False)
                else:
                    self._events = []

    def _widgets_for_events(self, events: Sequence[Event]) -> list[RenderableType]:
        widgets: list[RenderableType] = []
        for event in events:
            display = render_event(event)
            if display and display.content:
                widgets.append(transcript_separator(display.title))
                if isinstance(display.content, Markdown):
                    display.content.code_theme = MARKDOWN_CODE_THEME
                widgets.append(display.content)
                widgets.append(Text(" "))
        return widgets


class EventDisplay(NamedTuple):
    """Display for an event group."""

    title: str
    """Text for title bar"""

    content: RenderableType | None = None
    """Optional custom content to display."""


def render_event(event: Event) -> EventDisplay | None:
    # see if we have a renderer
    for event_type, renderer in _renderers:
        if isinstance(event, event_type):
            display = renderer(event)
            if display:
                return display

    # no renderer
    return None


def render_sample_init_event(event: SampleInitEvent) -> EventDisplay:
    # alias sample
    sample = event.sample

    # input
    messages: list[ChatMessage] = (
        [ChatMessageUser(content=sample.input)]
        if isinstance(sample.input, str)
        else sample.input
    )
    content: list[RenderableType] = []
    for message in messages:
        content.extend(render_message(message))

    # target
    if sample.target:
        content.append(Text())
        content.append(Text("Target", style="bold"))
        content.append(Text())
        content.append(str(sample.target).strip())

    return EventDisplay("sample init", Group(*content))


def render_model_event(event: ModelEvent) -> EventDisplay:
    # content
    content: list[RenderableType] = []

    def append_message(message: ChatMessage) -> None:
        content.extend(render_message(message))

    # render preceding messages
    preceding = messages_preceding_assistant(event.input)
    for message in preceding:
        append_message(message)
        content.append(Text())

    # display assistant message (note that we don't render tool calls
    # because they will be handled as part of render_tool)
    if event.output.message.text:
        append_message(event.output.message)

    return EventDisplay(f"model: {event.model}", Group(*content))


def render_tool_event(event: ToolEvent) -> EventDisplay:
    # render the call
    content: list[RenderableType] = []
    if event.view:
        if event.view.format == "markdown":
            content.append(transcript_markdown(event.view.content))
        else:
            content.append(event.view.content)
    else:
        content.append(render_function_call(event.function, event.arguments))
    content.append(Text())

    # render the output
    if isinstance(event.result, list):
        result: ToolResult = "\n".join(
            [
                content.text
                for content in event.result
                if isinstance(content, ContentText)
            ]
        )
    else:
        result = event.result
    content.append(transcript_markdown(str(result)))

    return EventDisplay("tool call", Group(*content))


def render_step_event(event: StepEvent) -> EventDisplay:
    if event.type == "solver":
        return render_solver_event(event)
    if event.type == "scorer":
        return render_scorer_event(event)
    else:
        return EventDisplay(step_title(event))


def render_solver_event(event: StepEvent) -> EventDisplay:
    return EventDisplay(step_title(event))


def render_scorer_event(event: StepEvent) -> EventDisplay:
    return EventDisplay(step_title(event))


def render_score_event(event: ScoreEvent) -> EventDisplay:
    table = Table(box=None, show_header=False)
    table.add_column("", min_width=10, justify="left")
    table.add_column("", justify="left")
    table.add_row("Target", str(event.target).strip())
    if event.score.answer:
        table.add_row("Answer", transcript_markdown(event.score.answer))
    table.add_row("Score", str(event.score.value).strip())
    if event.score.explanation:
        table.add_row("Explanation", transcript_markdown(event.score.explanation))

    return EventDisplay("score", table)


def render_subtask_event(event: SubtaskEvent) -> EventDisplay:
    content: list[RenderableType] = [render_function_call(event.name, event.input)]
    content.append(Text())
    content.append(render_as_json(event.result))

    return EventDisplay(f"subtask: {event.name}", Group(*content))


def render_input_event(event: InputEvent) -> EventDisplay:
    return EventDisplay("input", Text.from_ansi(event.input_ansi.strip()))


def render_approval_event(event: ApprovalEvent) -> EventDisplay:
    content: list[RenderableType] = [
        f"[bold]{event.approver}[/bold]: {event.decision} ({event.explanation})"
    ]

    return EventDisplay("approval", Group(*content))


def render_info_event(event: InfoEvent) -> EventDisplay:
    if isinstance(event.data, str):
        content: RenderableType = transcript_markdown(event.data)
    else:
        content = render_as_json(event.data)
    return EventDisplay("info", content)


def render_logger_event(event: LoggerEvent) -> EventDisplay:
    content = event.message.level.upper()
    if event.message.name:
        content = f"{content} (${event.message.name})"
    content = f"{content}: {event.message.message}"
    return EventDisplay("logger", content)


def render_error_event(event: ErrorEvent) -> EventDisplay:
    return EventDisplay("error", event.error.traceback.strip())


def render_function_call(function: str, arguments: dict[str, Any]) -> RenderableType:
    call = format_function_call(function, arguments)
    return transcript_markdown("```python\n" + call + "\n```\n")


def render_as_json(json: Any) -> RenderableType:
    return transcript_markdown(
        "```json\n"
        + to_json(json, indent=2, fallback=lambda _: None).decode()
        + "\n```\n"
    )


def render_message(message: ChatMessage) -> list[RenderableType]:
    content: list[RenderableType] = [
        Text(message.role.capitalize(), style="bold"),
        Text(),
    ]
    if message.text:
        content.extend([transcript_markdown(message.text.strip())])
    return content


def step_title(event: StepEvent) -> str:
    return f"{event.type or 'step'}: {event.name}"


EventRenderer = Callable[[Any], EventDisplay | None]

_renderers: list[tuple[Type[Event], EventRenderer]] = [
    (SampleInitEvent, render_sample_init_event),
    (StepEvent, render_step_event),
    (ModelEvent, render_model_event),
    (ToolEvent, render_tool_event),
    (SubtaskEvent, render_subtask_event),
    (ScoreEvent, render_score_event),
    (InputEvent, render_input_event),
    (ApprovalEvent, render_approval_event),
    (InfoEvent, render_info_event),
    (LoggerEvent, render_logger_event),
    (ErrorEvent, render_error_event),
]
