"""Environment Monitor - システム環境の監視

CPU、メモリ、ディスク、プロセス等を監視する。
"""
from __future__ import annotations
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def get_system_resources() -> Dict[str, Any]:
    """システムリソースを取得"""
    resources = {}
    
    # CPU使用率
    try:
        result = subprocess.run(
            ["grep", "-c", "^processor", "/proc/cpuinfo"],
            capture_output=True, text=True, timeout=5
        )
        cpu_count = int(result.stdout.strip()) if result.returncode == 0 else 0
        
        # Load average
        load = os.getloadavg()
        resources["cpu"] = {
            "count": cpu_count,
            "load_1m": round(load[0], 2),
            "load_5m": round(load[1], 2),
            "load_15m": round(load[2], 2),
            "usage_percent": round((load[0] / cpu_count) * 100, 1) if cpu_count > 0 else 0,
        }
    except Exception as e:
        resources["cpu"] = {"error": str(e)}
    
    # メモリ
    try:
        result = subprocess.run(
            ["free", "-b"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            mem_line = lines[1].split()
            total = int(mem_line[1])
            used = int(mem_line[2])
            available = int(mem_line[6]) if len(mem_line) > 6 else total - used
            
            resources["memory"] = {
                "total_gb": round(total / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "available_gb": round(available / (1024**3), 2),
                "usage_percent": round((used / total) * 100, 1),
            }
    except Exception as e:
        resources["memory"] = {"error": str(e)}
    
    # ディスク
    try:
        result = subprocess.run(
            ["df", "-B1", str(PROJECT_ROOT)],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            disk_line = lines[1].split()
            total = int(disk_line[1])
            used = int(disk_line[2])
            available = int(disk_line[3])
            
            resources["disk"] = {
                "total_gb": round(total / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "available_gb": round(available / (1024**3), 2),
                "usage_percent": round((used / total) * 100, 1),
            }
    except Exception as e:
        resources["disk"] = {"error": str(e)}
    
    return resources


def get_process_info(process_name: str) -> Dict[str, Any]:
    """特定プロセスの情報を取得"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", process_name],
            capture_output=True, text=True, timeout=5
        )
        
        pids = result.stdout.strip().split("\n") if result.stdout.strip() else []
        pids = [p for p in pids if p]
        
        return {
            "ok": True,
            "process": process_name,
            "running": len(pids) > 0,
            "pid_count": len(pids),
            "pids": pids[:5],  # 最大5つ
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_service_status(service_name: str) -> Dict[str, Any]:
    """systemdサービスの状態を確認"""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", service_name],
            capture_output=True, text=True, timeout=5
        )
        
        status = result.stdout.strip()
        
        return {
            "ok": True,
            "service": service_name,
            "status": status,
            "is_active": status == "active",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_openclaw_status() -> Dict[str, Any]:
    """OpenClawの状態を取得"""
    gateway = check_service_status("openclaw-gateway")
    process = get_process_info("openclaw")
    
    return {
        "gateway_service": gateway,
        "process": process,
        "healthy": gateway.get("is_active", False) or process.get("running", False),
    }


def analyze_environment() -> Dict[str, Any]:
    """環境の総合分析"""
    resources = get_system_resources()
    openclaw = get_openclaw_status()
    
    # 警告とアクション提案
    warnings = []
    actions = []
    
    # リソース警告
    if resources.get("memory", {}).get("usage_percent", 0) > 80:
        warnings.append({
            "type": "high_memory",
            "usage": resources["memory"]["usage_percent"],
            "suggestion": "Consider freeing memory or adding resources",
        })
    
    if resources.get("disk", {}).get("usage_percent", 0) > 90:
        warnings.append({
            "type": "high_disk",
            "usage": resources["disk"]["usage_percent"],
            "suggestion": "Clean up disk space",
        })
        actions.append({
            "type": "cleanup",
            "target": "disk",
            "priority": "high",
        })
    
    if resources.get("cpu", {}).get("usage_percent", 0) > 90:
        warnings.append({
            "type": "high_cpu",
            "usage": resources["cpu"]["usage_percent"],
            "suggestion": "Check for runaway processes",
        })
    
    # OpenClaw警告
    if not openclaw.get("healthy"):
        warnings.append({
            "type": "openclaw_down",
            "suggestion": "Restart OpenClaw gateway",
        })
        actions.append({
            "type": "restart_service",
            "service": "openclaw-gateway",
            "priority": "high",
        })
    
    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "resources": resources,
        "openclaw": openclaw,
        "warnings": warnings,
        "suggested_actions": actions,
        "healthy": len(warnings) == 0,
    }


# === Phase 12: 外部環境適応拡張 ===

def detect_environment_changes() -> Dict[str, Any]:
    """リアルタイムで環境変化を検出"""
    import subprocess
    
    changes = []
    
    # ディスク使用量チェック
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
        for line in result.stdout.split("\n"):
            if "/" in line and "%" in line:
                usage = int(line.split()[-2].replace("%", ""))
                if usage > 90:
                    changes.append({
                        "type": "disk_critical",
                        "value": usage,
                        "action_required": True,
                    })
                elif usage > 80:
                    changes.append({
                        "type": "disk_warning",
                        "value": usage,
                        "action_required": False,
                    })
    except:
        pass
    
    # メモリチェック
    try:
        result = subprocess.run(["free", "-m"], capture_output=True, text=True)
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split()
            total = int(parts[1])
            used = int(parts[2])
            usage_pct = (used / total) * 100 if total > 0 else 0
            if usage_pct > 90:
                changes.append({
                    "type": "memory_critical",
                    "value": usage_pct,
                    "action_required": True,
                })
    except:
        pass
    
    # ネットワーク接続チェック
    try:
        result = subprocess.run(["ping", "-c", "1", "-W", "2", "8.8.8.8"], capture_output=True)
        if result.returncode != 0:
            changes.append({
                "type": "network_down",
                "value": None,
                "action_required": True,
            })
    except:
        pass
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "changes": changes,
        "critical_count": len([c for c in changes if c.get("action_required")]),
    }


def adapt_to_changes(changes: List[Dict]) -> Dict[str, Any]:
    """環境変化に適応"""
    adaptations = []
    
    for change in changes:
        change_type = change.get("type", "")
        
        if change_type == "disk_critical":
            adaptations.append({
                "action": "cleanup_temp_files",
                "command": "find /tmp -type f -mtime +7 -delete",
                "priority": "high",
            })
        
        elif change_type == "memory_critical":
            adaptations.append({
                "action": "reduce_parallelism",
                "setting": "max_parallel_tasks=1",
                "priority": "high",
            })
        
        elif change_type == "network_down":
            adaptations.append({
                "action": "switch_to_offline_mode",
                "setting": "offline_mode=true",
                "priority": "critical",
            })
        
        elif change_type == "disk_warning":
            adaptations.append({
                "action": "log_cleanup",
                "command": "find ~/agent-os/logs -name '*.log' -mtime +30 -delete",
                "priority": "low",
            })
    
    return {
        "adaptations": adaptations,
        "count": len(adaptations),
        "auto_applied": False,  # 手動確認を推奨
    }


def monitor_external_services() -> Dict[str, Any]:
    """外部サービスの状態を監視"""
    import subprocess
    
    services = {
        "github": {"url": "https://github.com", "status": "unknown"},
        "telegram": {"url": "https://api.telegram.org", "status": "unknown"},
        "openai": {"url": "https://api.openai.com", "status": "unknown"},
    }
    
    for name, info in services.items():
        try:
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5", info["url"]],
                capture_output=True,
                text=True,
            )
            code = result.stdout.strip()
            info["status"] = "up" if code in ["200", "301", "302", "403"] else "down"
            info["http_code"] = code
        except:
            info["status"] = "error"
    
    healthy = len([s for s in services.values() if s["status"] == "up"])
    
    return {
        "services": services,
        "healthy": healthy,
        "total": len(services),
        "all_healthy": healthy == len(services),
    }


def create_adaptation_plan(current_state: Dict, target_state: Dict) -> Dict[str, Any]:
    """現在の状態から目標状態への適応計画を作成"""
    plan = []
    
    # リソース差分を計算
    current_resources = current_state.get("resources", {})
    target_resources = target_state.get("resources", {})
    
    for resource, target_value in target_resources.items():
        current_value = current_resources.get(resource, 0)
        
        if current_value < target_value:
            plan.append({
                "action": "increase",
                "resource": resource,
                "from": current_value,
                "to": target_value,
                "priority": "medium",
            })
        elif current_value > target_value * 1.5:
            plan.append({
                "action": "decrease",
                "resource": resource,
                "from": current_value,
                "to": target_value,
                "priority": "low",
            })
    
    return {
        "plan": plan,
        "steps": len(plan),
        "estimated_time": len(plan) * 5,  # 5分/ステップ
    }
