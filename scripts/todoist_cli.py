#!/usr/bin/env python3
"""Todoist CLI — JSON bridge for Claude Code skill."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from functools import wraps


def get_api():
    from todoist_api_python.api import TodoistAPI

    token = os.environ["TODOIST_API_TOKEN"]
    return TodoistAPI(token)


def collect_all(iterator):
    """Drain a cursor-based paginator into a flat list of dicts."""
    results = []
    for batch in iterator:
        for item in batch:
            results.append(
                item.__dict__ if hasattr(item, "__dict__") else item
            )
    return results


def output(data):
    print(json.dumps(data, indent=2, default=str))


def handle_errors(fn):
    @wraps(fn)
    def wrapper(args):
        try:
            return fn(args)
        except Exception as e:
            error = {"error": str(e), "type": type(e).__name__}
            print(json.dumps(error, indent=2), file=sys.stderr)
            sys.exit(1)

    return wrapper


# ── Tasks ────────────────────────────────────────────────────────────────────


@handle_errors
def tasks_list(args):
    api = get_api()
    if args.filter:
        iterator = api.filter_tasks(query=args.filter)
    else:
        kwargs = {}
        if args.project_id:
            kwargs["project_id"] = args.project_id
        if args.label:
            kwargs["label"] = args.label
        iterator = api.get_tasks(**kwargs)
    output(collect_all(iterator))


@handle_errors
def tasks_get(args):
    api = get_api()
    task = api.get_task(args.task_id)
    output(task.__dict__ if hasattr(task, "__dict__") else task)


@handle_errors
def tasks_create(args):
    api = get_api()
    kwargs = {"content": args.content}
    if args.description:
        kwargs["description"] = args.description
    if args.due_string:
        kwargs["due_string"] = args.due_string
    if args.priority:
        kwargs["priority"] = args.priority
    if args.project_id:
        kwargs["project_id"] = args.project_id
    if args.labels:
        kwargs["labels"] = [l.strip() for l in args.labels.split(",")]
    task = api.add_task(**kwargs)
    output(task.__dict__ if hasattr(task, "__dict__") else task)


@handle_errors
def tasks_quick_add(args):
    api = get_api()
    task = api.add_task_quick(text=args.text)
    output(task.__dict__ if hasattr(task, "__dict__") else task)


@handle_errors
def tasks_complete(args):
    api = get_api()
    results = []
    for task_id in args.task_ids:
        success = api.complete_task(task_id)
        results.append({"id": task_id, "completed": success})
    output(results)


@handle_errors
def tasks_update(args):
    api = get_api()
    kwargs = {}
    if args.content is not None:
        kwargs["content"] = args.content
    if args.due_string is not None:
        kwargs["due_string"] = args.due_string
    if args.priority is not None:
        kwargs["priority"] = args.priority
    if args.labels is not None:
        kwargs["labels"] = [l.strip() for l in args.labels.split(",")]
    if args.description is not None:
        kwargs["description"] = args.description
    task = api.update_task(args.task_id, **kwargs)
    output(task.__dict__ if hasattr(task, "__dict__") else task)


@handle_errors
def tasks_batch_update(args):
    api = get_api()
    changes = json.loads(args.changes_json)
    updated = []
    failed = []
    for entry in changes:
        task_id = entry.pop("id")
        # Normalize labels from comma string if provided as string
        if "labels" in entry and isinstance(entry["labels"], str):
            entry["labels"] = [l.strip() for l in entry["labels"].split(",")]
        try:
            task = api.update_task(task_id, **entry)
            updated.append(task.__dict__ if hasattr(task, "__dict__") else task)
        except Exception as e:
            failed.append({"id": task_id, "error": str(e)})
    output({"updated": updated, "failed": failed})


# ── Projects ─────────────────────────────────────────────────────────────────


@handle_errors
def projects_list(args):
    api = get_api()
    output(collect_all(api.get_projects()))


@handle_errors
def projects_get(args):
    api = get_api()
    project = api.get_project(args.project_id)
    output(project.__dict__ if hasattr(project, "__dict__") else project)


# ── Labels ───────────────────────────────────────────────────────────────────


@handle_errors
def labels_list(args):
    api = get_api()
    output(collect_all(api.get_labels()))


@handle_errors
def labels_create(args):
    api = get_api()
    kwargs = {"name": args.name}
    if args.color:
        kwargs["color"] = args.color
    label = api.add_label(**kwargs)
    output(label.__dict__ if hasattr(label, "__dict__") else label)


@handle_errors
def labels_ensure(args):
    api = get_api()
    desired = [n.strip() for n in args.names.split(",")]
    existing = {l.name for l in _collect_all_raw(api.get_labels())}
    created = []
    skipped = []
    for name in desired:
        if name in existing:
            skipped.append(name)
        else:
            label = api.add_label(name=name)
            created.append(label.__dict__ if hasattr(label, "__dict__") else label)
            existing.add(name)
    output({"created": created, "skipped": skipped})


def _collect_all_raw(iterator):
    """Drain paginator into flat list of raw objects (not dicts)."""
    results = []
    for batch in iterator:
        results.extend(batch)
    return results


# ── History ──────────────────────────────────────────────────────────────────


@handle_errors
def history(args):
    api = get_api()
    since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    until_str = args.until or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    until = datetime.strptime(until_str, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )
    iterator = api.get_completed_tasks_by_completion_date(since=since, until=until)
    output(collect_all(iterator))


# ── CLI Setup ────────────────────────────────────────────────────────────────


def build_parser():
    parser = argparse.ArgumentParser(description="Todoist CLI")
    subparsers = parser.add_subparsers(dest="resource", required=True)

    # ── tasks ──
    tasks_parser = subparsers.add_parser("tasks")
    tasks_sub = tasks_parser.add_subparsers(dest="action", required=True)

    # tasks list
    p = tasks_sub.add_parser("list")
    p.add_argument("--filter", default=None)
    p.add_argument("--project-id", default=None)
    p.add_argument("--label", default=None)
    p.set_defaults(func=tasks_list)

    # tasks get
    p = tasks_sub.add_parser("get")
    p.add_argument("task_id")
    p.set_defaults(func=tasks_get)

    # tasks create
    p = tasks_sub.add_parser("create")
    p.add_argument("--content", required=True)
    p.add_argument("--description", default=None)
    p.add_argument("--due-string", default=None)
    p.add_argument("--priority", type=int, default=None)
    p.add_argument("--project-id", default=None)
    p.add_argument("--labels", default=None)
    p.set_defaults(func=tasks_create)

    # tasks quick-add
    p = tasks_sub.add_parser("quick-add")
    p.add_argument("text")
    p.set_defaults(func=tasks_quick_add)

    # tasks complete
    p = tasks_sub.add_parser("complete")
    p.add_argument("task_ids", nargs="+")
    p.set_defaults(func=tasks_complete)

    # tasks update
    p = tasks_sub.add_parser("update")
    p.add_argument("task_id")
    p.add_argument("--content", default=None)
    p.add_argument("--description", default=None)
    p.add_argument("--due-string", default=None)
    p.add_argument("--priority", type=int, default=None)
    p.add_argument("--labels", default=None)
    p.set_defaults(func=tasks_update)

    # tasks batch-update
    p = tasks_sub.add_parser("batch-update")
    p.add_argument("changes_json")
    p.set_defaults(func=tasks_batch_update)

    # ── projects ──
    projects_parser = subparsers.add_parser("projects")
    projects_sub = projects_parser.add_subparsers(dest="action", required=True)

    p = projects_sub.add_parser("list")
    p.set_defaults(func=projects_list)

    p = projects_sub.add_parser("get")
    p.add_argument("project_id")
    p.set_defaults(func=projects_get)

    # ── labels ──
    labels_parser = subparsers.add_parser("labels")
    labels_sub = labels_parser.add_subparsers(dest="action", required=True)

    p = labels_sub.add_parser("list")
    p.set_defaults(func=labels_list)

    p = labels_sub.add_parser("create")
    p.add_argument("--name", required=True)
    p.add_argument("--color", default=None)
    p.set_defaults(func=labels_create)

    p = labels_sub.add_parser("ensure")
    p.add_argument("names")
    p.set_defaults(func=labels_ensure)

    # ── history ──
    p = subparsers.add_parser("history")
    p.add_argument("--since", required=True)
    p.add_argument("--until", default=None)
    p.set_defaults(func=history)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
