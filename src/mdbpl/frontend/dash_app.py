"""Plotly Dash frontend for MongoDB Performance Lab.

This is a temporary UI for demo execution and visualization.
The REST API in api.py is designed to be consumed by any frontend,
making it easy to replace this Dash app with React/Next.js later.

Note: This Dash app imports and calls demo functions directly since it runs
in the same Python process. External frontends (React, etc.) should use the
REST API endpoints instead.
"""
import asyncio
import time
import threading
from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, html, dcc, callback, Input, Output, State, no_update, ALL

from ..demos import list_demos, get_demo
from ..dsl.loader import WorkloadLoader
from ..executor import WorkloadExecutor
from ..storage import BenchmarkStorage
import os

# Get MongoDB URI and initialize storage
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://mongodb:27017")
storage = BenchmarkStorage("/data/benchmarks.db")

# Global state for tracking demo execution progress
_demo_execution_state = {
    "running": False,
    "current_step": None,
    "completed_steps": [],
    "result": None,
    "error": None,
    "_last_hash": None  # Track state changes to prevent unnecessary updates
}


def run_demo_with_progress(demo_name: str):
    """Run a demo in a background thread and track progress in realtime."""
    global _demo_execution_state
    
    try:
        # Reset state
        _demo_execution_state["running"] = True
        _demo_execution_state["current_step"] = "Initializing demo..."
        _demo_execution_state["completed_steps"] = []
        _demo_execution_state["result"] = None
        _demo_execution_state["error"] = None
        _demo_execution_state["_last_hash"] = None  # Reset to force first update
        
        # Get demo instance
        demo = get_demo(demo_name)
        
        # Wrap the demo's run method to track steps in realtime
        original_run = demo.run
        
        def tracked_run():
            # Import here to avoid circular imports
            from ..demos.base import DemoResult, DemoStep
            
            # Patch DemoResult.steps list to track appends
            result = original_run()
            return result
        
        # Create a monitoring wrapper for DemoResult
        from ..demos.base import DemoResult
        original_init = DemoResult.__init__
        
        def tracked_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            # Wrap the steps list
            original_steps = self.steps
            
            class TrackedStepsList(list):
                def append(inner_self, step):
                    # Update global state when a step is added
                    _demo_execution_state["current_step"] = step.description
                    super().append(step)
                    if step.completed_at:
                        _demo_execution_state["completed_steps"].append({
                            "name": step.name,
                            "description": step.description,
                            "completed": True
                        })
            
            self.steps = TrackedStepsList(original_steps)
        
        # Temporarily patch DemoResult
        DemoResult.__init__ = tracked_init
        
        try:
            # Execute demo
            result = tracked_run()
            
            # Store result
            _demo_execution_state["running"] = False
            _demo_execution_state["current_step"] = None
            _demo_execution_state["result"] = result.to_dict()
        finally:
            # Restore original DemoResult
            DemoResult.__init__ = original_init
        
    except Exception as e:
        _demo_execution_state["running"] = False
        _demo_execution_state["current_step"] = None
        _demo_execution_state["error"] = str(e)
        _demo_execution_state["result"] = None


def create_dash_app(requests_pathname_prefix: str = "/") -> Dash:
    """Create and configure the Dash application.
    
    Args:
        requests_pathname_prefix: URL prefix for mounting within FastAPI
        
    Returns:
        Configured Dash app instance
    """
    app = Dash(
        __name__,
        requests_pathname_prefix=requests_pathname_prefix,
        suppress_callback_exceptions=True,
        title="MongoDB Performance Lab"
    )
    
    # Inject custom CSS into the app
    app.index_string = '''
    <!DOCTYPE html>
    <html>
        <head>
            {%metas%}
            <title>{%title%}</title>
            {%favicon%}
            {%css%}
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background: #f8fafc;
                    color: #1e293b;
                }
                
                #react-entry-point {
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                }
                
                .header {
                    background: white;
                    padding: 30px;
                    border-radius: 12px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                    margin-bottom: 30px;
                }
                
                .title {
                    font-size: 32px;
                    font-weight: 700;
                    margin-bottom: 8px;
                    color: #0f172a;
                }
                
                .subtitle {
                    font-size: 16px;
                    color: #64748b;
                }
                
                .main-content {
                    background: white;
                    padding: 30px;
                    border-radius: 12px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }
                
                .selector-container {
                    margin-bottom: 20px;
                }
                
                .label {
                    display: block;
                    font-weight: 600;
                    margin-bottom: 8px;
                    color: #334155;
                }
                
                .Select-control {
                    border-radius: 8px !important;
                    border: 1px solid #cbd5e1 !important;
                }
                
                .description {
                    margin: 20px 0;
                }
                
                .demo-desc {
                    padding: 16px;
                    background: #eff6ff;
                    border-radius: 8px;
                    border-left: 4px solid #3b82f6;
                    font-size: 15px;
                    line-height: 1.5;
                }
                
                button {
                    background: #3b82f6;
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: 600;
                    cursor: pointer;
                    margin-bottom: 20px;
                    transition: background 0.2s;
                }
                
                button:hover:not(:disabled) {
                    background: #2563eb;
                }
                
                button:disabled {
                    background: #cbd5e1;
                    cursor: not-allowed;
                }
                
                .status {
                    margin: 20px 0;
                    padding: 12px;
                    border-radius: 8px;
                    font-weight: 500;
                }
                
                .status-running {
                    color: #f59e0b;
                    font-size: 16px;
                    font-weight: 600;
                }
                
                .status-detail {
                    color: #64748b;
                    font-size: 14px;
                }
                
                .status-success {
                    color: #22c55e;
                    font-size: 16px;
                    font-weight: 600;
                }
                
                .status-error {
                    color: #ef4444;
                    font-size: 16px;
                    font-weight: 600;
                }
                
                .step-progress {
                    background: #f8fafc;
                    padding: 16px;
                    border-radius: 8px;
                    border: 1px solid #e2e8f0;
                    margin-top: 12px;
                }
                
                .step-item {
                    display: flex;
                    align-items: center;
                    margin-bottom: 8px;
                    padding: 8px;
                    border-radius: 6px;
                    transition: all 0.2s ease;
                }
                
                .step-item-running {
                    background: #fef3c7;
                    animation: pulse 1.5s ease-in-out infinite;
                }
                
                @keyframes pulse {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.7; }
                }
                
                .step-icon {
                    margin-right: 8px;
                    font-size: 16px;
                }
                
                .step-text {
                    font-size: 14px;
                }
                
                .step-text-completed {
                    color: #64748b;
                }
                
                .step-text-running {
                    color: #0f172a;
                    font-weight: 500;
                }
                
                .loading-container {
                    padding: 40px;
                    text-align: center;
                }
                
                .loading-text {
                    color: #64748b;
                    font-size: 14px;
                    margin-top: 12px;
                }
                
                .results {
                    margin-top: 30px;
                }
                
                .results-title {
                    font-size: 24px;
                    margin-bottom: 20px;
                    color: #0f172a;
                    font-weight: 700;
                }
                
                .section {
                    margin-bottom: 40px;
                }
                
                .section-title {
                    font-size: 18px;
                    margin-bottom: 16px;
                    color: #334155;
                    font-weight: 600;
                }
                
                .summary-box {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 24px;
                    border-radius: 12px;
                    margin-bottom: 24px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }
                
                .summary-title {
                    font-size: 20px;
                    font-weight: 700;
                    margin-bottom: 16px;
                }
                
                .summary-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 16px;
                }
                
                .summary-item {
                    background: rgba(255,255,255,0.1);
                    padding: 12px;
                    border-radius: 8px;
                }
                
                .summary-label {
                    font-size: 12px;
                    opacity: 0.9;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                }
                
                .summary-value {
                    font-size: 24px;
                    font-weight: 700;
                    margin-top: 4px;
                }
                
                .summary-change {
                    font-size: 14px;
                    margin-top: 4px;
                    font-weight: 600;
                }
                
                .changes-list {
                    background: #f8fafc;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 24px;
                    border: 1px solid #e2e8f0;
                }
                
                .change-item {
                    padding: 12px;
                    background: white;
                    border-radius: 6px;
                    margin-bottom: 8px;
                    border-left: 3px solid #3b82f6;
                }
                
                .change-item:last-child {
                    margin-bottom: 0;
                }
                
                .change-step {
                    font-weight: 600;
                    color: #334155;
                    margin-bottom: 4px;
                }
                
                .change-detail {
                    color: #64748b;
                    font-size: 14px;
                }
                
                .charts-container {
                    display: flex;
                    gap: 20px;
                    flex-wrap: wrap;
                }
                
                .chart {
                    flex: 1;
                    min-width: 400px;
                }
                
                .metrics-table {
                    width: 100%;
                    border-collapse: collapse;
                    background: white;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }
                
                .metrics-table th,
                .metrics-table td {
                    padding: 14px 16px;
                    text-align: left;
                    border-bottom: 1px solid #e2e8f0;
                }
                
                .table-header {
                    background: #f8fafc;
                    font-weight: 600;
                    color: #0f172a;
                }
                
                .improvement {
                    color: #22c55e;
                    font-weight: 600;
                }
                
                .degradation {
                    color: #ef4444;
                    font-weight: 600;
                }
                
                .timeline {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }
                
                .timeline-step {
                    padding: 16px;
                    background: #f8fafc;
                    border-radius: 8px;
                    border-left: 4px solid #94a3b8;
                }
                
                .step-success {
                    border-left-color: #22c55e;
                }
                
                .step-error {
                    border-left-color: #ef4444;
                }
                
                .step-header {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                }
                
                .step-number {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    width: 28px;
                    height: 28px;
                    background: #e2e8f0;
                    border-radius: 50%;
                    font-weight: 600;
                    font-size: 14px;
                    flex-shrink: 0;
                }
                
                .step-info {
                    flex: 1;
                }
                
                .duration {
                    color: #64748b;
                    font-size: 14px;
                    margin-left: 8px;
                }
                
                /* Tabs styling */
                .tabs-container {
                    margin-bottom: 24px;
                }
                
                .tabs-container .tab {
                    background: #f8fafc !important;
                    border: 1px solid #e2e8f0 !important;
                    border-bottom: none !important;
                    color: #64748b !important;
                    font-weight: 600 !important;
                    padding: 12px 24px !important;
                }
                
                .tabs-container .tab--selected {
                    background: white !important;
                    color: #3b82f6 !important;
                    border-bottom: 2px solid #3b82f6 !important;
                }
                
                .tab-content {
                    padding-top: 20px;
                }
                
                .input-group {
                    margin-bottom: 20px;
                }
                
                .input-group label {
                    display: block;
                    font-weight: 600;
                    margin-bottom: 8px;
                    color: #334155;
                }
                
                .input-group input {
                    width: 100%;
                    padding: 10px 12px;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    font-size: 14px;
                }
                
                .input-group input:focus {
                    outline: none;
                    border-color: #3b82f6;
                    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
                }
                
                .results-list {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }
                
                .result-card {
                    background: #f8fafc;
                    padding: 16px;
                    border-radius: 8px;
                    border: 1px solid #e2e8f0;
                    cursor: pointer;
                    transition: all 0.2s;
                }
                
                .result-card:hover {
                    border-color: #3b82f6;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                
                .result-card-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 8px;
                }
                
                .result-card-title {
                    font-weight: 600;
                    color: #0f172a;
                }
                
                .result-card-tag {
                    background: #3b82f6;
                    color: white;
                    padding: 4px 12px;
                    border-radius: 12px;
                    font-size: 12px;
                    font-weight: 600;
                }
                
                .result-card-meta {
                    color: #64748b;
                    font-size: 14px;
                }
                
                .empty-state {
                    text-align: center;
                    padding: 60px 20px;
                    color: #64748b;
                }
                
                .empty-state-icon {
                    font-size: 48px;
                    margin-bottom: 16px;
                }
                
                /* Checkbox styling */
                input[type="checkbox"] {
                    width: 18px;
                    height: 18px;
                    cursor: pointer;
                    accent-color: #3b82f6;
                }
                
                .result-card:has(input[type="checkbox"]:checked) {
                    border-color: #3b82f6;
                    background: #eff6ff;
                }
                
                /* Markdown content styling */
                .demo-markdown {
                    line-height: 1.7;
                    color: #334155;
                    max-width: 900px;
                }
                
                .demo-markdown h1 {
                    font-size: 28px;
                    font-weight: 700;
                    margin-top: 24px;
                    margin-bottom: 16px;
                    color: #0f172a;
                    border-bottom: 2px solid #e2e8f0;
                    padding-bottom: 8px;
                }
                
                .demo-markdown h2 {
                    font-size: 22px;
                    font-weight: 600;
                    margin-top: 20px;
                    margin-bottom: 12px;
                    color: #1e293b;
                }
                
                .demo-markdown h3 {
                    font-size: 18px;
                    font-weight: 600;
                    margin-top: 16px;
                    margin-bottom: 8px;
                    color: #334155;
                }
                
                .demo-markdown p {
                    margin-bottom: 12px;
                }
                
                .demo-markdown strong {
                    font-weight: 600;
                    color: #0f172a;
                }
                
                .demo-markdown code {
                    background: #f1f5f9;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                    font-size: 13px;
                    color: #e11d48;
                }
                
                .demo-markdown pre {
                    background: #1e293b;
                    padding: 16px;
                    border-radius: 8px;
                    overflow-x: auto;
                    margin: 16px 0;
                    border: 1px solid #334155;
                }
                
                .demo-markdown pre code {
                    background: none;
                    color: #94a3b8;
                    padding: 0;
                    font-size: 14px;
                }
                
                .demo-markdown ul, .demo-markdown ol {
                    margin-left: 24px;
                    margin-bottom: 16px;
                }
                
                .demo-markdown li {
                    margin-bottom: 8px;
                }
                
                .demo-markdown blockquote {
                    border-left: 4px solid #3b82f6;
                    padding-left: 16px;
                    margin: 16px 0;
                    color: #64748b;
                    font-style: italic;
                }
                
                .demo-markdown table {
                    border-collapse: collapse;
                    width: 100%;
                    margin: 16px 0;
                    font-size: 14px;
                }
                
                .demo-markdown th, .demo-markdown td {
                    border: 1px solid #e2e8f0;
                    padding: 10px 12px;
                    text-align: left;
                }
                
                .demo-markdown th {
                    background: #f8fafc;
                    font-weight: 600;
                    color: #0f172a;
                }
                
                .demo-markdown tr:nth-child(even) {
                    background: #f8fafc;
                }
                
                .demo-markdown hr {
                    border: none;
                    border-top: 2px solid #e2e8f0;
                    margin: 24px 0;
                }
                
                .demo-markdown a {
                    color: #3b82f6;
                    text-decoration: none;
                }
                
                .demo-markdown a:hover {
                    text-decoration: underline;
                }
                
                .footer {
                    margin-top: 40px;
                    padding: 24px 30px;
                    background: #f8fafc;
                    border-top: 1px solid #e2e8f0;
                    border-radius: 0 0 12px 12px;
                    text-align: center;
                }
                
                .footer-links {
                    display: flex;
                    justify-content: center;
                    gap: 32px;
                    flex-wrap: wrap;
                }
                
                .footer-link {
                    color: #64748b;
                    text-decoration: none;
                    font-size: 14px;
                    font-weight: 500;
                    transition: color 0.2s ease;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }
                
                .footer-link:hover {
                    color: #3b82f6;
                }
                
                .footer-icon {
                    font-size: 18px;
                }
            </style>
        </head>
        <body>
            {%app_entry%}
            <footer>
                {%config%}
                {%scripts%}
                {%renderer%}
            </footer>
        </body>
    </html>
    '''
    
    app.layout = html.Div([
        html.Div([
            html.H1("🚀 MongoDB Performance Lab", className="title"),
            html.P(
                "Interactive performance experimentation and benchmarking platform",
                className="subtitle"
            ),
        ], className="header"),
        
        html.Div([
            dcc.Tabs(id="tabs", value="demos", children=[
                dcc.Tab(label="📚 Demos", value="demos", className="custom-tab"),
                dcc.Tab(label="⚡ Run Benchmark", value="run-benchmark", className="custom-tab"),
                dcc.Tab(label="📊 View Results", value="view-results", className="custom-tab"),
            ], className="tabs-container"),
            
            html.Div(id="tab-content", className="tab-content"),
        ], className="main-content"),
        
        # Stores for tracking state
        dcc.Store(id="execution-state", data={"running": False, "result": None}),
        dcc.Store(id="benchmark-state", data={"running": False, "result": None}),
        
        # Footer
        html.Div([
            html.Div([
                html.A([
                    html.Span("📚", className="footer-icon"),
                    html.Span("MongoDB Documentation")
                ], href="https://www.mongodb.com/docs/", target="_blank", className="footer-link"),
                html.A([
                    html.Span("💻", className="footer-icon"),
                    html.Span("GitHub: @spencershepard")
                ], href="https://github.com/spencershepard/MongoDB-Performance-Lab", target="_blank", className="footer-link"),
            ], className="footer-links")
        ], className="footer"),
        
    ], className="app-container")
    
    # Define callbacks
    setup_callbacks(app)
    
    return app


def render_demos_tab():
    """Render the demos tab content."""
    return html.Div([
        html.Div([
            html.Label("Select Demo:", className="label"),
            dcc.Dropdown(
                id="demo-selector",
                options=[],
                placeholder="Choose a demo to run...",
                className="dropdown"
            ),
        ], className="selector-container"),
        
        html.Div(id="demo-description", className="description"),
        
        html.Button(
            "Run Demo",
            id="run-button",
            n_clicks=0,
            disabled=True,
            className="run-button"
        ),
        
        dcc.Loading(
            id="loading",
            type="default",
            children=[
                html.Div(id="status-message", className="status"),
                html.Div(id="results-container", children=[]),
            ],
            className="loading-container"
        ),
        
        dcc.Interval(
            id="interval-component",
            interval=500,  # Poll every 500ms for progress updates
            n_intervals=0,
            disabled=True
        ),
    ])


def render_run_benchmark_tab():
    """Render the run benchmark tab content."""
    return html.Div([
        html.Div([
            html.Label("Select Workload:", className="label"),
            dcc.Dropdown(
                id="workload-selector",
                options=[],
                placeholder="Choose a workload...",
                className="dropdown"
            ),
        ], className="selector-container"),
        
        html.Div(id="workload-description", className="description"),
        
        html.Div([
            html.Div([
                html.Label("Duration (seconds):", className="label"),
                dcc.Input(
                    id="duration-input",
                    type="number",
                    value=30,
                    min=5,
                    max=300,
                    className="input"
                ),
            ], className="input-group", style={"width": "48%", "display": "inline-block"}),
            
            html.Div([
                html.Label("Tag (optional):", className="label"),
                dcc.Input(
                    id="tag-input",
                    type="text",
                    placeholder="e.g., baseline, optimized",
                    className="input"
                ),
            ], className="input-group", style={"width": "48%", "display": "inline-block", "marginLeft": "4%"}),
        ]),
        
        html.Button(
            "Run Benchmark",
            id="run-benchmark-button",
            n_clicks=0,
            disabled=True,
            className="run-button"
        ),
        
        dcc.Loading(
            id="benchmark-loading",
            type="default",
            children=[
                html.Div(id="benchmark-status", className="status"),
                html.Div(id="benchmark-results", children=[]),
            ],
            className="loading-container"
        ),
    ])


def render_view_results_tab():
    """Render the view results tab content."""
    return html.Div([
        # Comparison results shown at top
        html.Div(id="comparison-from-results", children=[]),
        
        # Action buttons below comparison
        html.Div([
            html.Button(
                "Refresh",
                id="refresh-results-button",
                n_clicks=0,
                className="run-button",
                style={"marginRight": "12px"}
            ),
            html.Button(
                "Compare Selected (0)",
                id="compare-selected-button",
                n_clicks=0,
                disabled=True,
                className="run-button"
            ),
        ], style={"marginBottom": "20px", "marginTop": "20px", "display": "flex", "alignItems": "center"}),
        
        # List of benchmark results with checkboxes
        html.Div(id="results-list", children=[]),
        
        # Store for tracking selected runs
        dcc.Store(id="selected-runs", data=[])
    ])





def setup_callbacks(app: Dash):
    """Setup all Dash callbacks."""
    
    # Tab content rendering
    @app.callback(
        Output("tab-content", "children"),
        Input("tabs", "value")
    )
    def render_tab_content(tab):
        """Render content based on selected tab."""
        if tab == "demos":
            return render_demos_tab()
        elif tab == "run-benchmark":
            return render_run_benchmark_tab()
        elif tab == "view-results":
            return render_view_results_tab()
        return html.Div("Select a tab")
    
    # Demo tab callbacks
    @app.callback(
        Output("demo-selector", "options"),
        Input("demo-selector", "id")
    )
    def load_demos(_):
        """Load available demos from demo registry."""
        try:
            demos = list_demos()
            return [
                {"label": f"{d['title']}", "value": d["name"]}
                for d in demos
            ]
        except Exception as e:
            return [{"label": f"Error loading demos: {e}", "value": "error"}]
    
    @app.callback(
        [Output("demo-description", "children"),
         Output("run-button", "disabled")],
        Input("demo-selector", "value")
    )
    def update_demo_info(demo_name):
        """Display demo description when selected."""
        if not demo_name or demo_name == "error":
            return "", True
        
        try:
            demo = get_demo(demo_name)
            markdown_content = demo.get_markdown_content()
            
            # Use dcc.Markdown to render the content with syntax highlighting
            return html.Div([
                dcc.Markdown(
                    markdown_content,
                    className="demo-markdown",
                    highlight_config={
                        "theme": "dark"
                    }
                )
            ], style={"marginTop": "20px"}), False
        except Exception as e:
            return html.P(f"Error: {e}", className="error"), True
    
    @app.callback(
        [Output("execution-state", "data"),
         Output("run-button", "disabled", allow_duplicate=True),
         Output("interval-component", "disabled", allow_duplicate=True)],
        Input("run-button", "n_clicks"),
        [State("demo-selector", "value"),
         State("execution-state", "data")],
        prevent_initial_call=True
    )
    def start_demo(n_clicks, demo_name, state):
        """Start the demo execution in a background thread."""
        if n_clicks == 0 or not demo_name:
            return no_update, no_update, no_update
        
        # If already running, ignore
        if _demo_execution_state["running"]:
            return no_update, no_update, no_update
        
        # Start demo in background thread
        thread = threading.Thread(target=run_demo_with_progress, args=(demo_name,), daemon=True)
        thread.start()
        
        # Enable interval polling and disable button
        return {"running": True}, True, False
    
    @app.callback(
        [Output("status-message", "children"),
         Output("execution-state", "data", allow_duplicate=True),
         Output("run-button", "disabled", allow_duplicate=True),
         Output("interval-component", "disabled", allow_duplicate=True)],
        Input("interval-component", "n_intervals"),
        State("execution-state", "data"),
        prevent_initial_call=True
    )
    def update_progress(n_intervals, state):
        """Poll for demo progress and update UI."""
        global _demo_execution_state
        
        # Create hash of current state to detect changes
        import hashlib
        import json
        
        state_data = {
            "running": _demo_execution_state["running"],
            "current_step": _demo_execution_state["current_step"],
            "completed_steps": len(_demo_execution_state["completed_steps"]),
            "has_result": _demo_execution_state["result"] is not None,
            "has_error": _demo_execution_state["error"] is not None
        }
        current_hash = hashlib.md5(json.dumps(state_data, sort_keys=True).encode()).hexdigest()
        
        # If state hasn't changed, don't update anything
        if current_hash == _demo_execution_state["_last_hash"]:
            return no_update, no_update, no_update, no_update
        
        # Update the hash
        _demo_execution_state["_last_hash"] = current_hash
        
        # Check if demo is still running
        if not _demo_execution_state["running"]:
            # Demo completed - check for result or error
            if _demo_execution_state["error"]:
                status = html.Span(
                    f"❌ Demo failed: {_demo_execution_state['error']}",
                    className="status-error"
                )
                return status, {"running": False, "result": None}, False, True
            
            elif _demo_execution_state["result"]:
                result = _demo_execution_state["result"]
                if result.get("success"):
                    status = html.Span("✅ Demo completed successfully!", className="status-success")
                else:
                    status = html.Span(
                        f"❌ Demo failed: {result.get('error', 'Unknown error')}",
                        className="status-error"
                    )
                return status, {"running": False, "result": result}, False, True
            
            # Demo finished but no result yet (shouldn't happen)
            return no_update, no_update, no_update, no_update
        
        # Demo is running - show progress
        current_step = _demo_execution_state["current_step"]
        completed_steps = _demo_execution_state["completed_steps"]
        
        # Build progress display with nice styling
        if completed_steps or current_step:
            step_list = []
            
            # Show completed steps
            for step in completed_steps:
                step_list.append(
                    html.Div([
                        html.Span("✅", className="step-icon"),
                        html.Span(step["description"], className="step-text step-text-completed")
                    ], className="step-item")
                )
            
            # Show current step with animation
            if current_step:
                step_list.append(
                    html.Div([
                        html.Span("⏳", className="step-icon"),
                        html.Span(current_step, className="step-text step-text-running")
                    ], className="step-item step-item-running")
                )
            
            status = html.Div([
                html.Div("Demo in progress", className="status-running", style={"marginBottom": "12px"}),
                html.Div(step_list, className="step-progress")
            ])
        else:
            status = html.Div([
                html.Span("⏳ Starting demo... ", className="status-running"),
                html.Span("This may take 1-2 minutes.", className="status-detail")
            ])
        
        # Only update button and interval states when transitioning
        return status, no_update, no_update, no_update
    
    @app.callback(
        Output("results-container", "children"),
        Input("execution-state", "data")
    )
    def display_results(state):
        """Render results visualization when demo completes."""
        result = state.get("result")
        if not result or not result.get("success"):
            return html.Div()
        
        steps = result.get("steps", [])
        
        # Find baseline and optimized benchmarks
        baseline = None
        optimized = None
        
        for step in steps:
            if "baseline" in step["name"].lower() and step.get("result"):
                baseline = step["result"]
            elif ("indexed" in step["name"].lower() or 
                  "index" in step["name"].lower() and 
                  "benchmark" in step["name"].lower()) and step.get("result"):
                optimized = step["result"]
        
        # Find comparison results
        comparison = None
        for step in steps:
            if step["name"] == "compare" and step.get("result"):
                comparison = step["result"]
        
        if not baseline or not optimized:
            return html.Div("No benchmark data found in results")
        
        # Extract what changed from steps
        changes = extract_changes(steps)
        
        # Create visualizations
        summary = create_summary_box(baseline, optimized, comparison, changes)
        changes_display = create_changes_display(changes)
        charts = create_comparison_charts(baseline, optimized, comparison)
        table = create_metrics_table(baseline, optimized, comparison)
        timeline = create_timeline(steps)
        
        return html.Div([
            html.H2("📊 Results", className="results-title"),
            
            # Summary box at top
            summary,
            
            # What changed section
            html.Div([
                html.H3("🔧 What Changed", className="section-title"),
                changes_display,
            ], className="section"),
            
            html.Div([
                html.H3("Performance Comparison", className="section-title"),
                html.Div(charts, className="charts-container"),
            ], className="section"),
            
            html.Div([
                html.H3("Detailed Metrics", className="section-title"),
                table,
            ], className="section"),
            
            html.Div([
                html.H3("Execution Timeline", className="section-title"),
                timeline,
            ], className="section"),
        ], className="results")
    
    # Benchmark tab callbacks
    @app.callback(
        Output("workload-selector", "options"),
        Input("workload-selector", "id")
    )
    def load_workloads(_):
        """Load available workloads."""
        try:
            workloads = WorkloadLoader.list_builtin_workloads()
            return [{"label": w, "value": w} for w in workloads]
        except Exception as e:
            return [{"label": f"Error: {e}", "value": "error"}]
    
    @app.callback(
        [Output("workload-description", "children"),
         Output("run-benchmark-button", "disabled")],
        Input("workload-selector", "value")
    )
    def update_workload_info(workload_name):
        """Update workload description when selection changes."""
        if not workload_name or workload_name == "error":
            return "", True
        
        try:
            workload = WorkloadLoader.load_builtin(workload_name)
            description = html.Div([
                html.P(workload.description or "No description available"),
                html.P(f"Distribution: {workload.distribution.type if workload.distribution else 'uniform'}", 
                       style={"fontSize": "14px", "color": "#64748b"})
            ], className="demo-description")
            return description, False
        except Exception as e:
            return html.Div(f"Error loading workload: {e}", className="error"), True
    
    @app.callback(
        [Output("benchmark-state", "data"),
         Output("benchmark-status", "children"),
         Output("benchmark-results", "children")],
        Input("run-benchmark-button", "n_clicks"),
        [State("workload-selector", "value"),
         State("duration-input", "value"),
         State("tag-input", "value"),
         State("benchmark-state", "data")]
    )
    def run_benchmark_workload(n_clicks, workload_name, duration, tag, state):
        """Execute a benchmark workload."""
        if n_clicks == 0 or not workload_name:
            return no_update, no_update, no_update
        
        if state.get("running"):
            return no_update, no_update, no_update
        
        try:
            # Load workload
            workload = WorkloadLoader.load_builtin(workload_name)
            
            # Create executor
            executor_instance = WorkloadExecutor(
                workload=workload,
                mongodb_uri=MONGODB_URI,
                record_count=10000  # Default record count
            )
            
            # Update status
            status = html.Span("⏳ Running benchmark... This may take a minute.", className="status-running")
            
            # Run benchmark
            result = executor_instance.run(duration or 30, tag or "")
            
            # Save to storage
            run_id = storage.save_result(
                result=result,
                tag=tag or ""
            )
            
            # Update state
            new_state = {"running": False, "result": result}
            success_status = html.Span(f"✅ Benchmark completed! Run ID: {run_id}", className="status-success")
            
            # Create results display
            results_display = html.Div([
                html.H3("📊 Results", className="results-title"),
                html.Div([
                    html.Div([
                        html.Label("Throughput:"),
                        html.Span(f"{result.operations_per_second:.2f} ops/sec", className="metric-value")
                    ], className="metric-item"),
                    html.Div([
                        html.Label("Latency P50:"),
                        html.Span(f"{result.latency_p50:.3f} ms", className="metric-value")
                    ], className="metric-item"),
                    html.Div([
                        html.Label("Latency P95:"),
                        html.Span(f"{result.latency_p95:.3f} ms", className="metric-value")
                    ], className="metric-item"),
                    html.Div([
                        html.Label("Latency P99:"),
                        html.Span(f"{result.latency_p99:.3f} ms", className="metric-value")
                    ], className="metric-item"),
                ], style={"display": "grid", "gridTemplateColumns": "repeat(2, 1fr)", "gap": "16px", "marginTop": "20px"})
            ])
            
            return new_state, success_status, results_display
            
        except Exception as e:
            new_state = {"running": False, "result": None}
            error_status = html.Span(f"❌ Error: {str(e)}", className="status-error")
            return new_state, error_status, html.Div()
    
    # View results tab callbacks
    @app.callback(
        Output("results-list", "children"),
        [Input("refresh-results-button", "n_clicks"),
         Input("tabs", "value")]
    )
    def load_results(n_clicks, tab):
        """Load and display recent benchmark results."""
        if tab != "view-results":
            return no_update
        
        try:
            runs = storage.list_runs(limit=20)
            
            if not runs:
                return html.Div([
                    html.Div("📭", className="empty-state-icon"),
                    html.P("No benchmark results yet. Run a benchmark to see results here!"),
                ], className="empty-state")
            
            result_cards = []
            for run in runs:
                # Create a unique ID for this checkbox
                checkbox_id = f"checkbox-run-{run['id']}"
                
                card = html.Div([
                    html.Div([
                        dcc.Checklist(
                            id={"type": "result-checkbox", "index": run['id']},
                            options=[{"label": "", "value": run['id']}],
                            value=[],
                            style={"marginRight": "12px"}
                        ),
                        html.Div([
                            html.Div([
                                html.Div(run["workload_name"], className="result-card-title"),
                                html.Div(run["tag"] if run.get("tag") else "untagged", className="result-card-tag") if run.get("tag") else html.Div(),
                            ], className="result-card-header"),
                            html.Div([
                                html.Span(f"Throughput: {run['operations_per_second']:.2f} ops/sec | "),
                                html.Span(f"P95: {run['latency_p95']:.2f}ms | "),
                                html.Span(f"Duration: {run['duration_seconds']:.0f}s"),
                            ], className="result-card-meta"),
                            html.Div(f"Run ID: {run['id']} | {run['timestamp']}", 
                                    style={"fontSize": "12px", "color": "#94a3b8", "marginTop": "8px"}),
                        ], style={"flex": "1"})
                    ], style={"display": "flex", "alignItems": "flex-start"}),
                ], className="result-card")
                result_cards.append(card)
            
            return html.Div(result_cards, className="results-list")
            
        except Exception as e:
            return html.Div(f"Error loading results: {e}", className="error")
    
    # Track checkbox selections
    @app.callback(
        Output("selected-runs", "data"),
        Input({"type": "result-checkbox", "index": ALL}, "value"),
        State({"type": "result-checkbox", "index": ALL}, "id")
    )
    def update_selected_runs(checkbox_values, checkbox_ids):
        """Track which runs are selected via checkboxes."""
        selected = []
        for values, checkbox_id in zip(checkbox_values, checkbox_ids):
            if values:  # If checkbox is checked
                selected.append(checkbox_id["index"])
        return selected
    
    # Update compare button based on selections
    @app.callback(
        [Output("compare-selected-button", "children"),
         Output("compare-selected-button", "disabled")],
        Input("selected-runs", "data")
    )
    def update_compare_button(selected_runs):
        """Update compare button text and state based on selections."""
        count = len(selected_runs) if selected_runs else 0
        button_text = f"Compare Selected ({count})"
        disabled = count != 2
        return button_text, disabled
    
    # Handle compare button click
    @app.callback(
        Output("comparison-from-results", "children"),
        Input("compare-selected-button", "n_clicks"),
        State("selected-runs", "data")
    )
    def compare_selected_runs(n_clicks, selected_runs):
        """Compare two selected runs."""
        if n_clicks == 0 or not selected_runs or len(selected_runs) != 2:
            return html.Div()
        
        try:
            # Get the two runs
            run1 = storage.get_run_by_id(selected_runs[0])
            run2 = storage.get_run_by_id(selected_runs[1])
            
            if not run1 or not run2:
                return html.Div("❌ Could not find selected runs.", className="error")
            
            # Normalize data structure
            baseline = run1
            optimized = run2
            
            baseline['throughput'] = baseline.get('operations_per_second', 0)
            optimized['throughput'] = optimized.get('operations_per_second', 0)
            
            # Calculate deltas
            def calculate_delta(val1, val2):
                if val1 == 0:
                    return 0.0
                return ((val2 - val1) / val1) * 100
            
            improvements = {
                'throughput_percent': calculate_delta(baseline['operations_per_second'], optimized['operations_per_second']),
                'latency_p50_percent': calculate_delta(baseline['latency_p50'], optimized['latency_p50']),
                'latency_p95_percent': calculate_delta(baseline['latency_p95'], optimized['latency_p95']),
                'latency_p99_percent': calculate_delta(baseline['latency_p99'], optimized['latency_p99']),
            }
            
            comparison_normalized = {'improvements': improvements}
            
            throughput_change = improvements['throughput_percent']
            latency_change = improvements['latency_p95_percent']
            
            # Calculate query efficiency metrics
            def calc_efficiency(examined, returned):
                if examined == 0 or returned == 0:
                    return None
                return (returned / examined) * 100
            
            baseline_efficiency = calc_efficiency(
                baseline.get('total_docs_examined', 0),
                baseline.get('total_docs_returned', 0)
            )
            optimized_efficiency = calc_efficiency(
                optimized.get('total_docs_examined', 0),
                optimized.get('total_docs_returned', 0)
            )
            
            # Create comparison display
            return html.Div([
                html.H3("📊 Comparison Results", className="results-title", style={"marginTop": "0px", "marginBottom": "20px"}),
                
                # Run details
                html.Div([
                    html.Div("Comparing Runs", className="summary-title"),
                    html.Div([
                        html.Div([
                            html.Div("Run 1", style={"fontSize": "12px", "color": "#64748b", "marginBottom": "4px", "textTransform": "uppercase", "fontWeight": "600"}),
                            html.Div(f"{baseline['workload_name']}", style={"fontSize": "16px", "fontWeight": "600", "marginBottom": "4px"}),
                            html.Div(f"Tag: {baseline.get('tag', 'untagged')}", style={"fontSize": "14px", "color": "#64748b"}),
                            html.Div(f"Run ID: {baseline['id']}", style={"fontSize": "12px", "color": "#94a3b8"}),
                        ], style={"padding": "12px", "backgroundColor": "#f8fafc", "borderRadius": "6px", "border": "1px solid #e2e8f0"}),
                        html.Div([
                            html.Div("Run 2", style={"fontSize": "12px", "color": "#64748b", "marginBottom": "4px", "textTransform": "uppercase", "fontWeight": "600"}),
                            html.Div(f"{optimized['workload_name']}", style={"fontSize": "16px", "fontWeight": "600", "marginBottom": "4px"}),
                            html.Div(f"Tag: {optimized.get('tag', 'untagged')}", style={"fontSize": "14px", "color": "#64748b"}),
                            html.Div(f"Run ID: {optimized['id']}", style={"fontSize": "12px", "color": "#94a3b8"}),
                        ], style={"padding": "12px", "backgroundColor": "#f8fafc", "borderRadius": "6px", "border": "1px solid #e2e8f0"}),
                    ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginTop": "12px"}),
                ], style={"marginBottom": "20px", "padding": "16px", "backgroundColor": "white", "borderRadius": "8px", "border": "1px solid #e2e8f0"}),
                
                # Summary
                html.Div([
                    html.Div("Comparison Summary", className="summary-title"),
                    html.Div([
                        html.Div([
                            html.Div("Throughput Change", className="summary-label"),
                            html.Div(f"{baseline['operations_per_second']:.1f} → {optimized['operations_per_second']:.1f} ops/sec", className="summary-value"),
                            html.Div(f"{'+' if throughput_change > 0 else ''}{throughput_change:.1f}%", className="summary-change"),
                        ], className="summary-item"),
                        html.Div([
                            html.Div("Latency P95 Change", className="summary-label"),
                            html.Div(f"{baseline['latency_p95']:.2f} → {optimized['latency_p95']:.2f} ms", className="summary-value"),
                            html.Div(f"{'-' if latency_change < 0 else '+'}{abs(latency_change):.1f}%", className="summary-change"),
                        ], className="summary-item"),
                    ], className="summary-grid"),
                ], className="summary-box"),
                
                # Query Efficiency Metrics
                html.Div([
                    html.Div("Query Efficiency", className="summary-title"),
                    html.Div([
                        html.Div([
                            html.Div("Run 1", style={"fontSize": "12px", "color": "#64748b", "marginBottom": "8px", "fontWeight": "600"}),
                            html.Div(f"Docs Examined: {baseline.get('total_docs_examined', 0):,}", style={"fontSize": "14px", "marginBottom": "4px", "color": "#64748b"}),
                            html.Div(f"Docs Returned: {baseline.get('total_docs_returned', 0):,}", style={"fontSize": "14px", "marginBottom": "4px", "color": "#64748b"}),
                            html.Div([
                                html.Span("Efficiency: ", style={"fontSize": "14px", "color": "#64748b"}),
                                html.Span(
                                    f"{baseline_efficiency:.1f}%" if baseline_efficiency else "N/A",
                                    style={
                                        "fontSize": "16px",
                                        "fontWeight": "600",
                                        "color": "#22c55e" if baseline_efficiency and baseline_efficiency > 80 else "#f59e0b" if baseline_efficiency and baseline_efficiency > 50 else "#ef4444"
                                    }
                                )
                            ]),
                            html.Div(f"Index Scans: {baseline.get('index_scans', 0)} | Collection Scans: {baseline.get('collection_scans', 0)}",
                                    style={"fontSize": "12px", "color": "#64748b", "marginTop": "8px"}),
                        ], style={"padding": "12px", "backgroundColor": "#f8fafc", "borderRadius": "6px", "border": "1px solid #e2e8f0"}),
                        html.Div([
                            html.Div("Run 2", style={"fontSize": "12px", "color": "#64748b", "marginBottom": "8px", "fontWeight": "600"}),
                            html.Div(f"Docs Examined: {optimized.get('total_docs_examined', 0):,}", style={"fontSize": "14px", "marginBottom": "4px", "color": "#64748b"}),
                            html.Div(f"Docs Returned: {optimized.get('total_docs_returned', 0):,}", style={"fontSize": "14px", "marginBottom": "4px", "color": "#64748b"}),
                            html.Div([
                                html.Span("Efficiency: ", style={"fontSize": "14px", "color": "#64748b"}),
                                html.Span(
                                    f"{optimized_efficiency:.1f}%" if optimized_efficiency else "N/A",
                                    style={
                                        "fontSize": "16px",
                                        "fontWeight": "600",
                                        "color": "#22c55e" if optimized_efficiency and optimized_efficiency > 80 else "#f59e0b" if optimized_efficiency and optimized_efficiency > 50 else "#ef4444"
                                    }
                                )
                            ]),
                            html.Div(f"Index Scans: {optimized.get('index_scans', 0)} | Collection Scans: {optimized.get('collection_scans', 0)}",
                                    style={"fontSize": "12px", "color": "#64748b", "marginTop": "8px"}),
                        ], style={"padding": "12px", "backgroundColor": "#f8fafc", "borderRadius": "6px", "border": "1px solid #e2e8f0"}),
                    ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginTop": "12px"}),
                    html.Div([
                        html.Div("💡 Efficiency Score = (Docs Returned / Docs Examined) × 100", 
                                style={"fontSize": "12px", "color": "#ffffff", "marginTop": "12px", "fontStyle": "italic"}),
                        html.Div("🟢 >80% = Excellent | 🟡 50-80% = Good | 🔴 <50% = Needs Index", 
                                style={"fontSize": "12px", "color": "#ffffff", "marginTop": "4px"}),
                    ]),
                ], className="summary-box", style={"marginTop": "20px"}),
                
                # Detailed metrics
                html.Div([
                    html.H4("Detailed Metrics", style={"marginTop": "30px", "marginBottom": "16px"}),
                    create_metrics_table(baseline, optimized, comparison_normalized),
                ]),
            ], style={"marginBottom": "30px"})
            
        except Exception as e:
            return html.Div(f"❌ Error comparing runs: {e}", className="error")


def extract_changes(steps: list) -> list:
    """Extract what changed during the demo from the steps."""
    changes = []
    
    for step in steps:
        if "load" in step["name"].lower():
            if step.get("result") and "records" in step["result"]:
                changes.append({
                    "step": "Data Preparation",
                    "detail": f"Loaded {step['result']['records']:,} test records into MongoDB"
                })
        elif "create" in step["name"].lower() and "index" in step["name"].lower():
            if step.get("result") and "index" in step["result"]:
                changes.append({
                    "step": "Index Creation",
                    "detail": f"Created index: {step['result']['index']}"
                })
        elif "drop" in step["name"].lower() and "index" in step["name"].lower():
            changes.append({
                "step": "Index Removal",
                "detail": step.get("description", "Dropped indexes")
            })
    
    return changes


def create_summary_box(baseline: dict, optimized: dict, comparison: dict, changes: list) -> html.Div:
    """Create a summary box showing key improvements."""
    improvements = comparison.get("improvements", {}) if comparison else {}
    
    throughput_change = improvements.get("throughput_percent", 0)
    latency_change = improvements.get("latency_p95_percent", 0)
    
    # Determine if improvement or degradation
    throughput_sign = "+" if throughput_change > 0 else ""
    latency_sign = "-" if latency_change > 0 else "+"
    
    return html.Div([
        html.Div("Performance Impact Summary", className="summary-title"),
        html.Div([
            html.Div([
                html.Div("Throughput Change", className="summary-label"),
                html.Div(f"{baseline.get('throughput', 0):.1f} → {optimized.get('throughput', 0):.1f} ops/sec", className="summary-value"),
                html.Div(f"{throughput_sign}{throughput_change:.1f}%", className="summary-change"),
            ], className="summary-item"),
            html.Div([
                html.Div("Latency p95 Change", className="summary-label"),
                html.Div(f"{baseline.get('latency_p95', 0):.2f} → {optimized.get('latency_p95', 0):.2f} ms", className="summary-value"),
                html.Div(f"{latency_sign}{abs(latency_change):.1f}%", className="summary-change"),
            ], className="summary-item"),
            html.Div([
                html.Div("Total Operations", className="summary-label"),
                html.Div(f"{optimized.get('total_operations', 0):,}", className="summary-value"),
                html.Div("in 30 seconds", className="summary-change"),
            ], className="summary-item"),
        ], className="summary-grid"),
    ], className="summary-box")


def create_changes_display(changes: list) -> html.Div:
    """Create a display of what changed during the demo."""
    if not changes:
        return html.Div("No configuration changes recorded")
    
    items = []
    for change in changes:
        items.append(html.Div([
            html.Div(change["step"], className="change-step"),
            html.Div(change["detail"], className="change-detail"),
        ], className="change-item"))
    
    return html.Div(items, className="changes-list")


def create_comparison_charts(baseline: dict, optimized: dict, comparison: dict) -> html.Div:
    """Create side-by-side comparison charts."""
    
    # Throughput comparison
    throughput_fig = go.Figure()
    throughput_fig.add_trace(go.Bar(
        x=["Run 1", "Run 2"],
        y=[baseline.get("throughput", 0), optimized.get("throughput", 0)],
        marker_color=["#ef4444", "#22c55e"],
        text=[f"{baseline.get('throughput', 0):.1f}", f"{optimized.get('throughput', 0):.1f}"],
        textposition="auto",
    ))
    throughput_fig.update_layout(
        title="Throughput (ops/sec)",
        yaxis_title="Operations per Second",
        height=300,
        showlegend=False,
    )
    
    # Latency comparison
    latency_fig = go.Figure()
    latency_fig.add_trace(go.Bar(
        x=["p50", "p95", "p99"],
        y=[
            baseline.get("latency_p50", 0),
            baseline.get("latency_p95", 0),
            baseline.get("latency_p99", 0) if "latency_p99" in baseline else baseline.get("latency_p95", 0)
        ],
        name="Run 1",
        marker_color="#ef4444",
    ))
    latency_fig.add_trace(go.Bar(
        x=["p50", "p95", "p99"],
        y=[
            optimized.get("latency_p50", 0),
            optimized.get("latency_p95", 0),
            optimized.get("latency_p99", 0) if "latency_p99" in optimized else optimized.get("latency_p95", 0)
        ],
        name="Run 2",
        marker_color="#22c55e",
    ))
    latency_fig.update_layout(
        title="Latency Percentiles (ms)",
        yaxis_title="Latency (milliseconds)",
        barmode="group",
        height=300,
    )
    
    return html.Div([
        dcc.Graph(figure=throughput_fig, className="chart"),
        dcc.Graph(figure=latency_fig, className="chart"),
    ], style={"display": "flex", "gap": "20px", "flexWrap": "wrap"})


def create_metrics_table(baseline: dict, optimized: dict, comparison: dict) -> html.Div:
    """Create detailed metrics comparison table."""
    
    improvements = comparison.get("improvements", {}) if comparison else {}
    
    rows = [
        html.Tr([
            html.Th("Metric"),
            html.Th("Run 1"),
            html.Th("Run 2"),
            html.Th("Change"),
        ], className="table-header")
    ]
    
    # Throughput row
    throughput_change = improvements.get("throughput_percent", 0)
    rows.append(html.Tr([
        html.Td("Throughput (ops/sec)"),
        html.Td(f"{baseline.get('throughput', 0):.2f}"),
        html.Td(f"{optimized.get('throughput', 0):.2f}"),
        html.Td(
            f"+{throughput_change:.1f}%" if throughput_change > 0 else f"{throughput_change:.1f}%",
            className="improvement" if throughput_change > 0 else "degradation"
        ),
    ]))
    
    # Latency rows
    for percentile in ["p50", "p95", "p99"]:
        key = f"latency_{percentile}"
        if key in baseline and key in optimized:
            change_key = f"latency_{percentile}_percent"
            change = improvements.get(change_key, 0)
            
            rows.append(html.Tr([
                html.Td(f"Latency {percentile.upper()} (ms)"),
                html.Td(f"{baseline[key]:.3f}"),
                html.Td(f"{optimized[key]:.3f}"),
                html.Td(
                    f"-{change:.1f}%" if change > 0 else f"+{abs(change):.1f}%",
                    className="improvement" if change > 0 else "degradation"
                ),
            ]))
    
    # Total operations
    rows.append(html.Tr([
        html.Td("Total Operations"),
        html.Td(f"{baseline.get('total_operations', 0):,}"),
        html.Td(f"{optimized.get('total_operations', 0):,}"),
        html.Td("-"),
    ]))
    
    return html.Table(rows, className="metrics-table")


def create_timeline(steps: list) -> html.Div:
    """Create execution timeline showing all steps."""
    
    timeline_items = []
    for i, step in enumerate(steps):
        duration = 0
        if step.get("started_at") and step.get("completed_at"):
            start = datetime.fromisoformat(step["started_at"])
            end = datetime.fromisoformat(step["completed_at"])
            duration = (end - start).total_seconds()
        
        status_class = "step-success" if not step.get("error") else "step-error"
        
        timeline_items.append(html.Div([
            html.Div([
                html.Span(f"{i+1}", className="step-number"),
                html.Div([
                    html.Strong(step["description"]),
                    html.Span(f" ({duration:.2f}s)", className="duration"),
                ], className="step-info"),
            ], className="step-header"),
        ], className=f"timeline-step {status_class}"))
    
    return html.Div(timeline_items, className="timeline")

