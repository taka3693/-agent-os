"""Action Policy Store - 学習から導出された行動ポリシー

パターンから生成されたポリシーを保存・適用する。
ポリシーは次の行動時に参照される。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE_DIR = Path(__file__).resolve().parents[1] / "state"
POLICY_FILE = STATE_DIR / "learned_policies.jsonl"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_policies() -> List[Dict[str, Any]]:
    """保存されたポリシーを読み込む"""
    if not POLICY_FILE.exists():
        return []
    
    policies = []
    for line in POLICY_FILE.read_text().strip().split("\n"):
        if line.strip():
            try:
                policies.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return policies


def save_policy(policy: Dict[str, Any]) -> bool:
    """新しいポリシーを保存"""
    policy["created_at"] = utc_now_iso()
    policy["active"] = True
    
    with open(POLICY_FILE, "a") as f:
        f.write(json.dumps(policy, ensure_ascii=False) + "\n")
    return True


def get_active_policies() -> List[Dict[str, Any]]:
    """アクティブなポリシーのみ取得"""
    return [p for p in load_policies() if p.get("active", True)]


def get_policies_for_target(target: str) -> List[Dict[str, Any]]:
    """特定のターゲットに適用されるポリシーを取得"""
    return [
        p for p in get_active_policies()
        if p.get("target") == target or p.get("target") == "*"
    ]


def apply_policies_to_action(
    action_type: str,
    target: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """アクションに対してポリシーを適用
    
    Returns:
        {
            "allowed": bool,
            "modifications": [...],  # 適用された修正
            "warnings": [...],       # 警告
            "applied_policies": [...] # 適用されたポリシー
        }
    """
    policies = get_active_policies()
    
    modifications = []
    warnings = []
    applied = []
    
    for policy in policies:
        policy_target = policy.get("target", "*")
        policy_action = policy.get("action")
        
        # ターゲットマッチング
        if policy_target != "*" and policy_target != target:
            continue
        
        # ポリシー適用
        if policy_action == "add_review_step":
            warnings.append({
                "type": "require_review",
                "message": f"High-risk area: {policy.get('reason')}",
                "policy_id": policy.get("id"),
            })
            applied.append(policy)
        
        elif policy_action == "automate_approval":
            modifications.append({
                "type": "skip_approval",
                "reason": policy.get("reason"),
                "policy_id": policy.get("id"),
            })
            applied.append(policy)
        
        elif policy_action == "add_validation":
            modifications.append({
                "type": "extra_validation",
                "validation_type": policy.get("target"),
                "policy_id": policy.get("id"),
            })
            applied.append(policy)
    
    return {
        "allowed": True,  # デフォルトは許可
        "modifications": modifications,
        "warnings": warnings,
        "applied_policies": [p.get("id") for p in applied],
    }


def generate_policies_from_recommendations(
    recommendations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """推奨から新しいポリシーを生成"""
    import uuid
    
    new_policies = []
    for rec in recommendations:
        policy = {
            "id": f"policy-{uuid.uuid4().hex[:8]}",
            "action": rec["action"],
            "target": rec["target"],
            "reason": rec["reason"],
            "priority": rec.get("priority", "medium"),
            "source": "learning_pattern",
        }
        new_policies.append(policy)
    
    return new_policies
