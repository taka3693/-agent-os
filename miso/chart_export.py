"""MISO chart export — Export charts as PNG images for Obsidian"""

from __future__ import annotations
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib import font_manager
    import matplotlib
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Japanese font support
matplotlib.rcParams['font.sans-serif'] = ['Noto Sans JP', 'DejaVu Sans', 'sans-serif']
matplotlib.rcParams['axes.unicode_minus'] = False

# Chart output directory
CHART_DIR = Path("/mnt/c/Users/milky/Documents/OpenClaw-Obsidian/openclaw/20_MISO/charts")
CHART_DIR.mkdir(parents=True, exist_ok=True)

# Import analytics functions
from miso.analytics import analyze_by_hour, analyze_trends


def export_daily_trend_chart(days: int = 30) -> Dict[str, Any]:
    """Export daily trend chart (completed/error over time)"""
    if not MATPLOTLIB_AVAILABLE:
        return {"ok": False, "error": "matplotlib not installed"}

    # Get analytics data
    missions_analytics = analyze_trends([], days)
    trends = missions_analytics.get("trends", [])

    if not trends:
        return {"ok": False, "error": "No data available"}

    # Prepare data
    dates = [datetime.strptime(t["date"], "%Y-%m-%d") for t in trends]
    completed = [t["completed"] for t in trends]
    error = [t["error"] for t in trends]

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot lines
    ax.plot(dates, completed, marker='o', label='Complete ✅', color='#22c55e', linewidth=2, markersize=4)
    ax.plot(dates, error, marker='o', label='Error ❌', color='#ef4444', linewidth=2, markersize=4)

    # Fill area
    ax.fill_between(dates, completed, alpha=0.2, color='#22c55e')
    ax.fill_between(dates, error, alpha=0.2, color='#ef4444')

    # Formatting
    ax.set_xlabel('Date', fontsize=12)
    ax.set_ylabel('Count', fontsize=12)
    ax.set_title(f'Daily Mission Trends (Last {days} Days)', fontsize=14, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, days // 10)))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Tight layout
    plt.tight_layout()

    # Save
    output_path = CHART_DIR / "daily_trend.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='#1e293b', edgecolor='none')
    plt.close()

    return {"ok": True, "path": str(output_path)}


def export_hourly_dist_chart() -> Dict[str, Any]:
    """Export hourly distribution chart"""
    if not MATPLOTLIB_AVAILABLE:
        return {"ok": False, "error": "matplotlib not installed"}

    # Get analytics data
    hourly_analytics = analyze_by_hour([])
    by_hour = hourly_analytics.get("by_hour", [])

    if not by_hour:
        return {"ok": False, "error": "No data available"}

    # Prepare data
    hours = [h["hour"] for h in by_hour]
    total = [h["total"] for h in by_hour]
    time_ranges = [h["time_range"] for h in by_hour]

    # Create figure
    fig, ax = plt.subplots(figsize=(14, 6))

    # Plot bars
    bars = ax.bar(hours, total, color='#9333ea', alpha=0.7, edgecolor='#a855f7', linewidth=1)

    # Add value labels on top of bars
    for bar, value in zip(bars, total):
        if value > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                    str(value), ha='center', va='bottom', fontsize=9)

    # Formatting
    ax.set_xlabel('Hour of Day', fontsize=12)
    ax.set_ylabel('Mission Count', fontsize=12)
    ax.set_title('Hourly Mission Distribution', fontsize=14, fontweight='bold')
    ax.set_xticks(hours)
    ax.set_xticklabels(time_ranges, rotation=45, ha='right', fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')

    # Highlight peak hours (top 3)
    sorted_counts = sorted([(h, t) for h, t in zip(hours, total)], key=lambda x: x[1], reverse=True)[:3]
    for hour, _ in sorted_counts:
        ax.axvline(x=hour, color='yellow', alpha=0.3, linestyle='--')

    # Tight layout
    plt.tight_layout()

    # Save
    output_path = CHART_DIR / "hourly_dist.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='#1e293b', edgecolor='none')
    plt.close()

    return {"ok": True, "path": str(output_path)}


def export_success_rate_chart(days: int = 30) -> Dict[str, Any]:
    """Export success rate trend chart"""
    if not MATPLOTLIB_AVAILABLE:
        return {"ok": False, "error": "matplotlib not installed"}

    # Get analytics data
    missions_analytics = analyze_trends([], days)
    trends = missions_analytics.get("trends", [])

    if not trends:
        return {"ok": False, "error": "No data available"}

    # Prepare data
    dates = [datetime.strptime(t["date"], "%Y-%m-%d") for t in trends]
    success_rates = [t["success_rate"] for t in trends]

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot line
    ax.plot(dates, success_rates, marker='o', color='#f59e0b', linewidth=2, markersize=4)

    # Add reference line at 80%
    ax.axhline(y=80, color='red', linestyle='--', alpha=0.5, label='Target (80%)')

    # Fill area
    ax.fill_between(dates, success_rates, alpha=0.3, color='#f59e0b')

    # Formatting
    ax.set_xlabel('Date', fontsize=12)
    ax.set_ylabel('Success Rate (%)', fontsize=12)
    ax.set_title(f'Success Rate Trend (Last {days} Days)', fontsize=14, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 100)

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, days // 10)))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Tight layout
    plt.tight_layout()

    # Save
    output_path = CHART_DIR / "success_rate_trend.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='#1e293b', edgecolor='none')
    plt.close()

    return {"ok": True, "path": str(output_path)}


def main():
    if not MATPLOTLIB_AVAILABLE:
        print("❌ matplotlib is not installed. Install it with:")
        print("   pip install matplotlib")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="MISO Chart Export")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # all command
    all_parser = subparsers.add_parser("all", help="Export all charts")
    all_parser.add_argument(
        "--days", "-d",
        type=int,
        default=30,
        help="Number of days for trend charts (default: 30)",
    )

    # daily command
    daily_parser = subparsers.add_parser("daily", help="Export daily trend chart")
    daily_parser.add_argument(
        "--days", "-d",
        type=int,
        default=30,
        help="Number of days (default: 30)",
    )

    # hourly command
    hourly_parser = subparsers.add_parser("hourly", help="Export hourly distribution chart")

    # success-rate command
    success_parser = subparsers.add_parser("success-rate", help="Export success rate trend chart")
    success_parser.add_argument(
        "--days", "-d",
        type=int,
        default=30,
        help="Number of days (default: 30)",
    )

    args = parser.parse_args()

    results = []

    if args.command == "all":
        results.append(export_daily_trend_chart(args.days))
        results.append(export_hourly_dist_chart())
        results.append(export_success_rate_chart(args.days))
    elif args.command == "daily":
        results.append(export_daily_trend_chart(args.days))
    elif args.command == "hourly":
        results.append(export_hourly_dist_chart())
    elif args.command == "success-rate":
        results.append(export_success_rate_chart(args.days))

    # Print results
    for result in results:
        if result.get("ok"):
            print(f"✅ Exported: {result['path']}")
        else:
            print(f"❌ Error: {result.get('error')}")


if __name__ == "__main__":
    main()
