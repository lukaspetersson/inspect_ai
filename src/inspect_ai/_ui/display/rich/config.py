from inspect_ai._util.registry import is_registry_dict

from ..core.rich import rich_theme
from ..display import TaskProfile


def task_config(profile: TaskProfile, generate_config: bool = True) -> str:
    # merge config
    theme = rich_theme()
    # wind params back for display
    task_args = dict(profile.task_args)
    for key in task_args.keys():
        value = task_args[key]
        if is_registry_dict(value):
            task_args[key] = value["name"]
    config = task_args | dict(profile.eval_config.model_dump(exclude_none=True))
    if generate_config:
        config = config | dict(profile.generate_config.model_dump(exclude_none=True))
    if profile.tags:
        config["tags"] = ",".join(profile.tags)
    config_print: list[str] = []
    for name, value in config.items():
        if name == "approval":
            config_print.append(
                f"{name}: {','.join([approver['name'] for approver in value['approvers']])}"
            )
        elif name not in ["limit", "model", "log_images"]:
            config_print.append(f"{name}: {value}")
    values = ", ".join(config_print)
    if values:
        return f"[{theme.light}]{values}[/{theme.light}]"
    else:
        return ""
