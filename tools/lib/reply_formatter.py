def build_step_sections(results):
    if not results:
        return ""

    out = ""

    for i, r in enumerate(results, start=1):
        step_id = r.get("step_id") or r.get("step_label") or str(i)
        command = r.get("command", "")
        mode = r.get("mode", "")
        ok = r.get("ok", False)
        cont = r.get("continue_on_error", False)

        out += (
            "\n---\n"
            f"step: {i}\n"
            f"id: {step_id}\n"
            f"command: {command}\n"
            f"mode: {mode}\n"
            f"ok: {ok}\n"
            f"continue_on_error: {cont}\n"
        )

    return out


def build_cli_reply(header, results):
    reply = header

    sections = build_step_sections(results)

    if sections:
        reply += sections

    return reply


def build_telegram_reply(text):
    return text
