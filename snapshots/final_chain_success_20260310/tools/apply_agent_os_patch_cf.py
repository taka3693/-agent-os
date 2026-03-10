#!/usr/bin/env python3
from pathlib import Path
import re
import shutil
from datetime import datetime

DIST = Path.home() / ".npm-global/lib/node_modules/openclaw/dist"
TARGET = DIST / "reply-CFQ8lILc.js"
BACKUP_DIR = Path.home() / "agent-os/backups"

HELPERS = r'''
        // AGENT_OS_PATCH_HELPERS_BEGIN
        const ROUTE_BRIDGE_PATH = "/home/milky/agent-os/bridge/route_to_task.py";
        const RESEARCH_RUNNER_PATH = "/home/milky/agent-os/runner/run_research_task.py";
        const RESEARCH_RUNNER_TIMEOUT_MS = 3e4;
        const ROUTE_ALLOWED_SKILLS = [
                "critique",
                "decision",
                "experiment",
                "execution",
                "research",
                "retrospective"
        ];
        const callRouteBridge = (text) => new Promise((resolve, reject) => {
                const child = spawn("/usr/bin/python3", [ROUTE_BRIDGE_PATH], {
                        stdio: ["pipe", "pipe", "pipe"]
                });
                let stdout = "";
                let stderr = "";
                child.stdout.on("data", (d) => {
                        stdout += String(d);
                });
                child.stderr.on("data", (d) => {
                        stderr += String(d);
                });
                child.on("error", (err) => {
                        reject(new Error(`bridge spawn error: ${String(err)}`));
                });
                child.on("close", (code) => {
                        if (code !== 0) {
                                reject(new Error(`bridge exit=${code} stderr=${stderr.trim()}`));
                                return;
                        }
                        try {
                                resolve(JSON.parse(stdout.trim()));
                        } catch (err) {
                                reject(new Error(`bridge json parse error: ${String(err)} raw=${stdout}`));
                        }
                });
                const payload = {
                        text,
                        allowed_skills: ROUTE_ALLOWED_SKILLS,
                        chain_count: 0,
                        source: "telegram"
                };
                child.stdin.write(JSON.stringify(payload));
                child.stdin.end();
        });
        const callResearchRunner = (taskPath) => new Promise((resolve, reject) => {
                const child = spawn("/usr/bin/python3", [RESEARCH_RUNNER_PATH, taskPath], {
                        stdio: ["ignore", "pipe", "pipe"]
                });
                let stdout = "";
                let stderr = "";
                let timedOut = false;
                const timer = setTimeout(() => {
                        timedOut = true;
                        try {
                                child.kill("SIGKILL");
                        } catch {}
                }, RESEARCH_RUNNER_TIMEOUT_MS);
                child.stdout.on("data", (d) => {
                        stdout += String(d);
                });
                child.stderr.on("data", (d) => {
                        stderr += String(d);
                });
                child.on("error", (err) => {
                        clearTimeout(timer);
                        reject(new Error(`runner spawn error: ${String(err)}`));
                });
                child.on("close", (code) => {
                        clearTimeout(timer);
                        if (timedOut) {
                                reject(new Error("runner timeout"));
                                return;
                        }
                        if (code !== 0) {
                                reject(new Error(`runner exit=${code} stderr=${stderr.trim()}`));
                                return;
                        }
                        try {
                                resolve(JSON.parse(stdout.trim()));
                        } catch (err) {
                                reject(new Error(`runner json parse error: ${String(err)} raw=${stdout}`));
                        }
                });
        });
        const readTaskJson = async (taskPath) => {
                const raw = await fs$1.readFile(taskPath, "utf-8");
                return JSON.parse(raw);
        };
        // AGENT_OS_PATCH_HELPERS_END
'''

EARLY_ROUTING = r'''
                // AGENT_OS_PATCH_ROUTE_BEGIN
                if (text && text.trim() && !isCommandLike) {
                        try {
                                const bridgeResult = await callRouteBridge(text);
                                console.error("[agent-os] bridge result:", JSON.stringify(bridgeResult));
                                if (bridgeResult?.ok && bridgeResult.selected_skill === "research") {
                                        const taskPath = bridgeResult.task_path;
                                        const taskId = bridgeResult.task_id ?? "unknown-task";
                                        console.error("[agent-os] calling research runner:", taskPath);
                                        await callResearchRunner(taskPath);
                                        const taskObj = await readTaskJson(taskPath);
                                        const summary = taskObj?.result?.summary;
                                        if (typeof summary === "string" && summary.trim()) {
                                                await bot.api.sendMessage(chatId, `research completed: ${summary} (task: ${taskId})`);
                                        } else {
                                                await bot.api.sendMessage(chatId, `research completed: (task: ${taskId})`);
                                        }
                                        return;
                                }
                                if (bridgeResult?.ok && bridgeResult.selected_skill !== "research") {
                                        if (typeof bridgeResult.reply === "string" && bridgeResult.reply.trim()) {
                                                await bot.api.sendMessage(chatId, bridgeResult.reply);
                                                return;
                                        }
                                        await bot.api.sendMessage(chatId, `routed task created: ${bridgeResult.task_id ?? "unknown"}`);
                                        return;
                                }
                                if (bridgeResult && !bridgeResult.ok) {
                                        await bot.api.sendMessage(chatId, "task creation failed");
                                        return;
                                }
                        } catch (err) {
                                console.error("[agent-os] processInboundMessage bridge/runner failed:", String(err));
                        }
                }
                // AGENT_OS_PATCH_ROUTE_END
'''

def backup_file(path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = BACKUP_DIR / f"{path.name}.{stamp}.cf_apply.bak"
    shutil.copy2(path, dst)
    return dst

def main():
    if not TARGET.exists():
        raise SystemExit(f"target missing: {TARGET}")

    text = TARGET.read_text()

    if "AGENT_OS_PATCH_HELPERS_BEGIN" in text or "AGENT_OS_PATCH_ROUTE_BEGIN" in text:
        print("already patched:", TARGET)
        return

    helper_anchor = '        const processInboundMessage = async (params) => {'
    if helper_anchor not in text:
        raise SystemExit("helper anchor not found")

    route_anchor = '''                const text = typeof msg.text === "string" ? msg.text : void 0;
                const isCommandLike = (text ?? "").trim().startsWith("/");
'''
    if route_anchor not in text:
        raise SystemExit("route anchor not found")

    bak = backup_file(TARGET)

    text = text.replace(helper_anchor, HELPERS + helper_anchor, 1)
    text = text.replace(route_anchor, route_anchor + EARLY_ROUTING, 1)

    TARGET.write_text(text)
    print("patched:", TARGET)
    print("backup:", bak)

if __name__ == "__main__":
    main()
