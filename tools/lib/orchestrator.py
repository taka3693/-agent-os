from __future__ import annotations

from typing import Any, Callable

from tools.lib.command_parser import parse_command
from tools.lib.request_models import RequestContext, ResultEnvelope
from tools.lib.formatter_v2 import format_router_cli, format_router_telegram


def handle_request_v2(
    ctx: RequestContext,
    *,
    run_router: Callable[..., dict[str, Any]],
    run_legacy: Callable[[str], dict[str, Any]] | None = None,
    send_telegram: Callable[[str | int, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cmd = parse_command(ctx.raw_text)

    if cmd.kind == "router":
        result = run_router(cmd.raw_command, chat_id=ctx.chat_id)
        reply_text = format_router_cli(result)
        telegram_reply_text = format_router_telegram(result)
        telegram_send = result.get("telegram_send")

        if ctx.source == "telegram" and ctx.chat_id and send_telegram is not None:
            raw_send = send_telegram(ctx.chat_id, telegram_reply_text)
            telegram_send = {
                "ok": bool(raw_send.get("ok", True)) if isinstance(raw_send, dict) else True,
                "chat_id": str(ctx.chat_id),
                "text": telegram_reply_text,
                "raw": raw_send,
            }

        envelope = ResultEnvelope(
            ok=bool(result.get("ok")),
            mode=str(result.get("mode") or "router"),
            status=str(result.get("status") or "completed"),
            reply_text=reply_text,
            telegram_reply_text=telegram_reply_text,
            telegram_send=telegram_send,
            payload=result,
        )
        return envelope.to_dict()

    if run_legacy is not None:
        result = run_legacy(ctx.raw_text)
        reply_text = result.get("reply_text") or ""
        telegram_reply_text = result.get("telegram_reply_text") or reply_text
        envelope = ResultEnvelope(
            ok=bool(result.get("ok")),
            mode=str(result.get("mode") or "unknown"),
            status=str(result.get("status") or "completed"),
            reply_text=reply_text,
            telegram_reply_text=telegram_reply_text,
            telegram_send=result.get("telegram_send"),
            payload=result,
        )
        return envelope.to_dict()

    return ResultEnvelope(
        ok=False,
        mode="error",
        status="unsupported",
        reply_text="未対応コマンド",
        telegram_reply_text="未対応コマンド",
    ).to_dict()
