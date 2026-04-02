"""MISO Web Dashboard — Real-time browser dashboard"""

from __future__ import annotations
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from flask import Flask, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# Import analytics functions
from miso.analytics import (
    analyze_by_agents,
    analyze_by_hour,
    analyze_trends,
    generate_summary,
)
from miso.dashboard import load_all_missions
from miso.formatter import STATE_LABELS, STATUS_ICONS

# Flask app
app = Flask(__name__)

# Cache for analytics data
_cache: Dict[str, tuple[Any, float]] = {}
CACHE_TTL = 5  # seconds


def get_with_cache(key: str, func, *args, **kwargs):
    """Get data with cache"""
    now = datetime.now(timezone.utc).timestamp()
    if key in _cache:
        data, timestamp = _cache[key]
        if now - timestamp < CACHE_TTL:
            return data
    result = func(*args, **kwargs)
    _cache[key] = (result, now)
    return result


@app.route("/")
def index():
    """Render dashboard"""
    html_template = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MISO Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Noto Sans JP', sans-serif; }
        .card { backdrop-filter: blur(10px); }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .refreshing { animation: pulse 1s ease-in-out infinite; }
    </style>
</head>
<body class="bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 min-h-screen text-white">
    <div class="container mx-auto px-4 py-8">
        <!-- Header -->
        <div class="flex items-center justify-between mb-8">
            <div>
                <h1 class="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-pink-400 to-purple-400">
                    🤖 MISO Dashboard
                </h1>
                <p class="text-slate-400 mt-2" id="last-updated">Loading...</p>
            </div>
            <button onclick="location.reload()" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg flex items-center gap-2">
                <span id="refresh-icon">🔄</span> Refresh
            </button>
        </div>

        <!-- Summary Cards -->
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
            <div class="card bg-white/10 rounded-xl p-4 border border-white/20">
                <div class="text-slate-400 text-sm">Total</div>
                <div class="text-3xl font-bold" id="summary-total">-</div>
            </div>
            <div class="card bg-green-500/20 rounded-xl p-4 border border-green-500/30">
                <div class="text-green-400 text-sm">Complete</div>
                <div class="text-3xl font-bold text-green-400" id="summary-completed">-</div>
            </div>
            <div class="card bg-red-500/20 rounded-xl p-4 border border-red-500/30">
                <div class="text-red-400 text-sm">Error</div>
                <div class="text-3xl font-bold text-red-400" id="summary-error">-</div>
            </div>
            <div class="card bg-blue-500/20 rounded-xl p-4 border border-blue-500/30">
                <div class="text-blue-400 text-sm">Running</div>
                <div class="text-3xl font-bold text-blue-400" id="summary-running">-</div>
            </div>
            <div class="card bg-yellow-500/20 rounded-xl p-4 border border-yellow-500/30">
                <div class="text-yellow-400 text-sm">Success Rate</div>
                <div class="text-3xl font-bold text-yellow-400" id="summary-rate">-</div>
            </div>
        </div>

        <!-- Charts -->
        <div class="grid md:grid-cols-2 gap-6 mb-8">
            <div class="card bg-white/10 rounded-xl p-6 border border-white/20">
                <h2 class="text-xl font-semibold mb-4">📈 Daily Trends (30 Days)</h2>
                <canvas id="trendChart" height="200"></canvas>
            </div>
            <div class="card bg-white/10 rounded-xl p-6 border border-white/20">
                <h2 class="text-xl font-semibold mb-4">⏰ Hourly Distribution</h2>
                <canvas id="hourlyChart" height="200"></canvas>
            </div>
        </div>

        <!-- Running Missions -->
        <div class="card bg-white/10 rounded-xl p-6 border border-white/20 mb-8">
            <h2 class="text-xl font-semibold mb-4">🔥 Running Missions</h2>
            <div id="running-missions" class="space-y-3">
                <p class="text-slate-400">Loading...</p>
            </div>
        </div>

        <!-- Recent Missions -->
        <div class="card bg-white/10 rounded-xl p-6 border border-white/20">
            <h2 class="text-xl font-semibold mb-4">📜 Recent Missions</h2>
            <div id="recent-missions" class="space-y-3">
                <p class="text-slate-400">Loading...</p>
            </div>
        </div>

        <!-- Footer -->
        <div class="text-center text-slate-500 mt-8 text-sm">
            🌸 powered by miyabi | Auto-refresh every 10s
        </div>
    </div>

    <script>
        let trendChart = null;
        let hourlyChart = null;

        async function loadDashboard() {
            document.getElementById('refresh-icon').classList.add('refreshing');
            try {
                const response = await fetch('/api/dashboard');
                const data = await response.json();
                updateDashboard(data);
            } catch (error) {
                console.error('Failed to load dashboard:', error);
            } finally {
                document.getElementById('refresh-icon').classList.remove('refreshing');
            }
        }

        function updateDashboard(data) {
            // Update last updated time
            document.getElementById('last-updated').textContent =
                'Last updated: ' + new Date().toLocaleString('ja-JP');

            // Update summary cards
            document.getElementById('summary-total').textContent = data.summary.total_missions;
            document.getElementById('summary-completed').textContent = data.summary.completed;
            document.getElementById('summary-error').textContent = data.summary.error;
            document.getElementById('summary-running').textContent = data.summary.running;
            document.getElementById('summary-rate').textContent = data.summary.success_rate + '%';

            // Update trend chart
            updateTrendChart(data.trends);

            // Update hourly chart
            updateHourlyChart(data.hourly);

            // Update running missions
            updateRunningMissions(data.running_missions);

            // Update recent missions
            updateRecentMissions(data.recent_missions);
        }

        function updateTrendChart(trends) {
            const ctx = document.getElementById('trendChart').getContext('2d');
            const labels = trends.trends.map(t => t.date.slice(5)); // MM-DD
            const completedData = trends.trends.map(t => t.completed);
            const errorData = trends.trends.map(t => t.error);

            if (trendChart) {
                trendChart.destroy();
            }

            trendChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Complete',
                            data: completedData,
                            borderColor: 'rgb(34, 197, 94)',
                            backgroundColor: 'rgba(34, 197, 94, 0.1)',
                            fill: true,
                            tension: 0.4,
                        },
                        {
                            label: 'Error',
                            data: errorData,
                            borderColor: 'rgb(239, 68, 68)',
                            backgroundColor: 'rgba(239, 68, 68, 0.1)',
                            fill: true,
                            tension: 0.4,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            labels: { color: 'white' },
                        },
                    },
                    scales: {
                        x: {
                            ticks: { color: 'rgba(255,255,255,0.7)' },
                            grid: { color: 'rgba(255,255,255,0.1)' },
                        },
                        y: {
                            ticks: { color: 'rgba(255,255,255,0.7)' },
                            grid: { color: 'rgba(255,255,255,0.1)' },
                            beginAtZero: true,
                        },
                    },
                },
            });
        }

        function updateHourlyChart(hourly) {
            const ctx = document.getElementById('hourlyChart').getContext('2d');
            const labels = hourly.by_hour.map(h => h.time_range);
            const totalData = hourly.by_hour.map(h => h.total);

            if (hourlyChart) {
                hourlyChart.destroy();
            }

            hourlyChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Missions',
                        data: totalData,
                        backgroundColor: 'rgba(147, 51, 234, 0.6)',
                        borderColor: 'rgb(147, 51, 234)',
                        borderWidth: 1,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            labels: { color: 'white' },
                        },
                    },
                    scales: {
                        x: {
                            ticks: { color: 'rgba(255,255,255,0.7)', maxRotation: 45 },
                            grid: { color: 'rgba(255,255,255,0.1)' },
                        },
                        y: {
                            ticks: { color: 'rgba(255,255,255,0.7)' },
                            grid: { color: 'rgba(255,255,255,0.1)' },
                            beginAtZero: true,
                        },
                    },
                },
            });
        }

        function updateRunningMissions(missions) {
            const container = document.getElementById('running-missions');
            if (!missions || missions.length === 0) {
                container.innerHTML = '<p class="text-slate-400">No running missions</p>';
                return;
            }

            container.innerHTML = missions.map(m => `
                <div class="bg-white/5 rounded-lg p-4 border border-white/10">
                    <div class="flex justify-between items-start">
                        <div class="flex-1">
                            <div class="font-semibold text-lg">${m.mission_name}</div>
                            <div class="text-sm text-slate-400 mt-1">
                                ID: <code class="bg-white/10 px-2 py-0.5 rounded">${m.mission_id}</code>
                            </div>
                            <div class="text-sm text-slate-400 mt-1">
                                Elapsed: <span class="text-yellow-400">${m.elapsed}m</span>
                            </div>
                        </div>
                        <div class="text-2xl">🔥</div>
                    </div>
                    <div class="mt-2 text-sm">
                        ${m.goal}
                    </div>
                </div>
            `).join('');
        }

        function updateRecentMissions(missions) {
            const container = document.getElementById('recent-missions');
            if (!missions || missions.length === 0) {
                container.innerHTML = '<p class="text-slate-400">No recent missions</p>';
                return;
            }

            const stateIcons = {
                'COMPLETE': '✅',
                'ERROR': '❌',
                'RUNNING': '🔥',
                'AWAITING_APPROVAL': '👀',
                'INIT': '⏳',
            };

            container.innerHTML = missions.map(m => `
                <div class="bg-white/5 rounded-lg p-4 border border-white/10 hover:bg-white/10 transition">
                    <div class="flex justify-between items-start">
                        <div class="flex-1">
                            <div class="font-semibold">${stateIcons[m.state] || '⏳'} ${m.mission_name}</div>
                            <div class="text-xs text-slate-400 mt-1">
                                ${m.created_at} | ${m.elapsed}m
                            </div>
                        </div>
                        <div class="text-xs px-2 py-1 rounded ${
                            m.state === 'COMPLETE' ? 'bg-green-500/20 text-green-400' :
                            m.state === 'ERROR' ? 'bg-red-500/20 text-red-400' :
                            'bg-blue-500/20 text-blue-400'
                        }">
                            ${m.state}
                        </div>
                    </div>
                </div>
            `).join('');
        }

        // Auto-refresh every 10 seconds
        setInterval(loadDashboard, 10000);

        // Initial load
        loadDashboard();
    </script>
</body>
</html>
    """
    return html_template


@app.route("/api/dashboard")
def api_dashboard():
    """API endpoint for dashboard data"""
    missions = load_all_missions()

    # Get analytics data
    summary = get_with_cache("summary", generate_summary, missions)
    trends = get_with_cache("trends", analyze_trends, missions, 30)
    hourly = get_with_cache("hourly", analyze_by_hour, missions)

    # Running missions
    running_states = ("RUNNING", "PARTIAL", "RETRYING")
    running_missions = [
        {
            "mission_id": m.get("mission_id", "N/A")[:8],
            "mission_name": m.get("mission_name", "不明"),
            "goal": m.get("goal", ""),
            "elapsed": calculate_elapsed_minutes(m),
        }
        for m in missions
        if m.get("state") in running_states
    ]

    # Recent missions (last 10)
    recent_missions = []
    for m in missions[:10]:
        created_str = m.get("created_at", "")
        created_display = ""
        if created_str:
            try:
                dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                created_display = dt.strftime("%m/%d %H:%M")
            except Exception:
                pass

        recent_missions.append({
            "mission_id": m.get("mission_id", "N/A")[:8],
            "mission_name": m.get("mission_name", "不明"),
            "state": m.get("state", "INIT"),
            "created_at": created_display,
            "elapsed": calculate_elapsed_minutes(m),
        })

    return jsonify({
        "summary": summary,
        "trends": trends,
        "hourly": hourly,
        "running_missions": running_missions,
        "recent_missions": recent_missions,
    })


def calculate_elapsed_minutes(mission: Dict[str, Any]) -> int:
    """Calculate elapsed minutes for a mission"""
    created_str = mission.get("created_at")
    if not created_str:
        return 0

    updated_str = mission.get("updated_at", created_str)
    start_time = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
    end_time = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))

    delta = end_time - start_time
    return int(delta.total_seconds() / 60)


def main():
    if not FLASK_AVAILABLE:
        print("❌ Flask is not installed. Install it with:")
        print("   pip install flask")
        sys.exit(1)

    host = "127.0.0.1"
    port = 8765

    print(f"🌸 MISO Dashboard starting on http://{host}:{port}")
    print("   Press Ctrl+C to stop")

    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
