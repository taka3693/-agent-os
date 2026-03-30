"""
Agent-OS Router CLI - 契約完愖準拚版
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from executor import (
    _init_task_state,
    _execute_single_step,
    _now_iso,
    run_pipeline_executor,
)
from telegram_handler import telegram_send, extract_chat_id


class RouterCLI:
    def __init__(
        self,
        tasks_dir: str = "./tasks",
        skills_registry: Optional[Dict[str, Callable]] = None,
    ):
        self.tasks_dir = tasks_dir
        self.skills_registry = skills_registry or {}

    def register_skill(
        self,
        skill_name: str,
        skill_fn: Callable[[str], Dict[str, Any]],
    ) -> None:
        self.skills_registry[skill_name] = skill_fn

    def route(self, query: str) -> str:
        query_lower = query.lower()
        if "telegram" in query_lower or "送信" in query_lower:
            return "telegram"
        elif "search" in query_lower or "検索" in query_lower:
            return "search"
        elif "code" in query_lower or "コード" in query_lower:
            return "code"
        else:
            return "default"

    def execute(
        self,
        query: str,
        skill_override: Optional[str] = None,
        continue_on_error: bool = False,
        telegram_chat_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected_skill = skill_override or self.route(query)
        skill_chain = self._build_skill_chain(selected_skill)
        step_fns, step_names = self._build_step_fns(
            query=query,
            selected_skill=selected_skill,
            telegram_chat_id=telegram_chat_id,
        )

        task = run_pipeline_executor(
            query=query,
            selected_skill=selected_skill,
            step_fns=step_fns,
            step_names=step_names,
            skill_chain=skill_chain,
            tasks_dir=self.tasks_dir,
            continue_on_error=continue_on_error,
        )

        return task

    def _build_skill_chain(self, selected_skill: str) -> List[str]:
        chain = ["parse", selected_skill]
        if selected_skill == "telegram":
            chain.append("telegram_send")
        return chain

    def _build_step_fns(
        self,
        query: str,
        selected_skill: str,
        telegram_chat_id: Optional[str] = None,
    ) -> tuple:
        step_fns: List[Callable[[], Dict[str, Any]]] = []
        step_names: List[str] = []

        def parse_step() -> Dict[str, Any]:
            return {
                "parsed_query": query,
                "tokens": query.split(),
                "intent": selected_skill,
            }

        step_fns.append(parse_step)
        step_names.append("parse")

        if selected_skill in self.skills_registry:
            skill_fn = self.skills_registry[selected_skill]
            step_fns.append(lambda: skill_fn(query))
            step_names.append(selected_skill)
        else:
            def default_skill() -> Dict[str, Any]:
                return {"response": f"Processed: {query}"}
            step_fns.append(default_skill)
            step_names.append("default_skill")

        if selected_skill == "telegram" and telegram_chat_id:
            def telegram_step() -> Dict[str, Any]:
                return telegram_send(
                    chat_id=telegram_chat_id,
                    text=f"Response to: {query}",
                )
            step_fns.append(telegram_step)
            step_names.append("telegram_send")

        return step_fns, step_names

    def handle_telegram_update(
        self,
        update: Dict[str, Any],
    ) -> Dict[str, Any]:
        chat_id = extract_chat_id(update)

        text = ""
        if "message" in update:
            text = update["message"].get("text", "")
        elif "callback_query" in update:
            text = update["callback_query"].get("data", "")

        if not text:
            return {
                "telegram_send": telegram_send(
                    chat_id=chat_id,
                    text="Empty message received",
                )
            }

        task = self.execute(
            query=text,
            telegram_chat_id=chat_id,
        )

        reply_text = self._generate_reply(task)

        return {
            "telegram_send": telegram_send(
                chat_id=chat_id,
                text=reply_text,
            )
        }

    def _generate_reply(self, task: Dict[str, Any]) -> str:
        status = task.get("status", "unknown")
        if status == "completed":
            return f"✅ Task completed: {task.get('query', '')}"
        elif status == "failed":
            return f"❌ Task failed: {task.get('query', '')}"
        elif status == "partial":
            return f"⚠️ Task partially completed: {task.get('query', '')}"
        else:
            return f"📝 Task status: {status}"


def main():
    parser = argparse.ArgumentParser(description="Agent-OS Router CLI")
    parser.add_argument("query", nargs="?", help="Query to process")
    parser.add_argument("--skill", help="Override skill selection")
    parser.add_argument("--tasks-dir", default="./tasks", help="Tasks directory")
    parser.add_argument("--telegram-chat-id", help="Telegram chat ID")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        sys.exit(1)

    router = RouterCLI(tasks_dir=args.tasks_dir)

    task = router.execute(
        query=args.query,
        skill_override=args.skill,
        continue_on_error=args.continue_on_error,
        telegram_chat_id=args.telegram_chat_id,
    )

    if args.json:
        print(json.dumps(task, ensure_ascii=False, indent=2))
    else:
        print(f"Task ID: {task['task_id']}")
        print(f"Status: {task['status']}")
        print(f"Steps: {len(task['step_results'])}")


if __name__ == "__main__":
    main()
