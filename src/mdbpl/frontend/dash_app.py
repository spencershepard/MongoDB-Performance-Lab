"""Plotly Dash frontend for MongoDB Performance Lab.

This is a temporary UI for demo execution and visualization.
The REST API in api.py is designed to be consumed by any frontend,
making it easy to replace this Dash app with React/Next.js later.

Note: This Dash app imports and calls demo functions directly since it runs
in the same Python process. External frontends (React, etc.) should use the
REST API endpoints instead.
"""
import asyncio
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, html, dcc, callback, Input, Output, State, no_update, ALL, MATCH, callback_context

from ..demos import list_demos, get_demo
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
    # Get the directory where this file is located
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    assets_folder = os.path.join(current_dir, "assets")
    
    app = Dash(
        __name__,
        requests_pathname_prefix=requests_pathname_prefix,
        suppress_callback_exceptions=True,
        title="MongoDB Performance Lab",
        assets_folder=assets_folder
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
                    background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
                    padding: 20px 30px;
                    border-radius: 12px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.08);
                    margin-bottom: 30px;
                    display: flex;
                    justify-content: flex-start;
                    align-items: center;
                    border: 1px solid #e2e8f0;
                }
                
                .header-logo {
                    height: 80px;
                    width: auto;
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
                
                .demo-list {
                    margin-bottom: 30px;
                }
                
                .demo-card {
                    display: flex;
                    align-items: center;
                    gap: 20px;
                    padding: 20px;
                    background: #f8fafc;
                    border-radius: 8px;
                    border: 1px solid #e2e8f0;
                    margin-bottom: 12px;
                    transition: all 0.2s;
                }
                
                .demo-card:hover {
                    border-color: #3b82f6;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    transform: translateY(-2px);
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
                
                /* Collapsible code snippet sections */
                .demo-markdown details {
                    margin: 20px 0;
                    padding: 0;
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                    background: #ffffff;
                    overflow: hidden;
                    transition: all 0.2s ease;
                }
                
                .demo-markdown details:hover {
                    border-color: #cbd5e1;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
                }
                
                .demo-markdown details[open] {
                    border-color: #3b82f6;
                }
                
                .demo-markdown summary {
                    padding: 16px 20px;
                    cursor: pointer;
                    user-select: none;
                    background: #f8fafc;
                    border-bottom: 1px solid #e2e8f0;
                    font-size: 16px;
                    display: flex;
                    align-items: center;
                    transition: background 0.2s ease;
                    list-style: none;
                }
                
                .demo-markdown summary::-webkit-details-marker {
                    display: none;
                }
                
                .demo-markdown summary::before {
                    content: '▶';
                    margin-right: 10px;
                    color: #64748b;
                    font-size: 12px;
                    transition: transform 0.2s ease;
                    display: inline-block;
                }
                
                .demo-markdown details[open] summary::before {
                    transform: rotate(90deg);
                }
                
                .demo-markdown summary:hover {
                    background: #f1f5f9;
                }
                
                .demo-markdown details[open] summary {
                    background: #eff6ff;
                    border-bottom-color: #3b82f6;
                }
                
                .demo-markdown details > *:not(summary) {
                    padding: 0 20px 20px 20px;
                }
                
                .demo-markdown details pre {
                    margin-top: 16px;
                }
                
                .demo-markdown details > :first-child:not(summary) {
                    padding-top: 20px;
                }
                
                /* Step-by-step execution styles */
                .step-card {
                    margin-bottom: 20px;
                    padding: 24px;
                    border-radius: 12px;
                    border: 2px solid #e2e8f0;
                    transition: all 0.3s ease;
                    background: white;
                }
                
                .step-current {
                    border-color: #3b82f6;
                    background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%);
                    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
                }
                
                .step-completed {
                    border-color: #22c55e;
                    background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%);
                }
                
                .step-locked {
                    border-color: #cbd5e1;
                    background: #f8fafc;
                    opacity: 0.6;
                }
                
                .step-error {
                    border-color: #ef4444;
                    background: linear-gradient(135deg, #fee2e2 0%, #ffffff 100%);
                }
                
                .step-running {
                    border-color: #f59e0b;
                    background: linear-gradient(135deg, #fef3c7 0%, #ffffff 100%);
                    animation: pulse-border 2s ease-in-out infinite;
                }
                
                @keyframes pulse-border {
                    0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4); }
                    50% { box-shadow: 0 0 0 8px rgba(245, 158, 11, 0); }
                }
                
                .step-header {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    margin-bottom: 16px;
                }
                
                .step-header h4 {
                    margin: 0;
                    font-size: 20px;
                    color: #0f172a;
                    font-weight: 700;
                    display: flex;
                    align-items: center;
                    gap: 12px;
                }
                
                .step-status-badge {
                    padding: 6px 12px;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                }
                
                .badge-pending {
                    background: #f1f5f9;
                    color: #64748b;
                }
                
                .badge-running {
                    background: #fef3c7;
                    color: #f59e0b;
                }
                
                .badge-completed {
                    background: #dcfce7;
                    color: #16a34a;
                }
                
                .badge-error {
                    background: #fee2e2;
                    color: #dc2626;
                }
                
                .step-markdown-section {
                    margin: 20px 0;
                }
                
                .step-markdown-section summary {
                    cursor: pointer;
                    font-weight: 600;
                    padding: 12px 16px;
                    background: #f8fafc;
                    border-radius: 8px;
                    border: 1px solid #e2e8f0;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    transition: all 0.2s;
                }
                
                .step-markdown-section summary:hover {
                    background: #f1f5f9;
                    border-color: #cbd5e1;
                }
                
                .step-markdown-section[open] summary {
                    background: #eff6ff;
                    border-color: #3b82f6;
                    margin-bottom: 16px;
                }
                
                .step-markdown-content {
                    padding: 16px;
                    background: white;
                    border-radius: 8px;
                    border: 1px solid #e2e8f0;
                    line-height: 1.7;
                }
                
                .step-markdown-content h2,
                .step-markdown-content h3 {
                    color: #0f172a;
                    margin-top: 24px;
                    margin-bottom: 12px;
                }
                
                .step-markdown-content h2 {
                    font-size: 24px;
                    font-weight: 700;
                }
                
                .step-markdown-content h3 {
                    font-size: 18px;
                    font-weight: 600;
                }
                
                .step-markdown-content ul,
                .step-markdown-content ol {
                    margin-left: 20px;
                    margin-bottom: 16px;
                }
                
                .step-markdown-content li {
                    margin-bottom: 8px;
                }
                
                .step-markdown-content code {
                    background: #f1f5f9;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 14px;
                    color: #dc2626;
                }
                
                .step-markdown-content pre {
                    background: #1e293b;
                    color: #e2e8f0;
                    padding: 16px;
                    border-radius: 8px;
                    overflow-x: auto;
                    margin: 16px 0;
                }
                
                .step-markdown-content pre code {
                    background: none;
                    color: inherit;
                    padding: 0;
                }
                
                .step-commands {
                    margin: 20px 0;
                    padding: 16px;
                    background: #f8fafc;
                    border-radius: 8px;
                    border: 1px solid #e2e8f0;
                }
                
                .step-commands h5 {
                    margin: 0 0 12px 0;
                    font-size: 14px;
                    color: #64748b;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                    font-weight: 600;
                }
                
                .step-commands ul {
                    list-style: none;
                    margin: 0;
                    padding: 0;
                }
                
                .step-commands li {
                    margin-bottom: 8px;
                    padding: 10px 12px;
                    background: white;
                    border-radius: 6px;
                    border: 1px solid #e2e8f0;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 13px;
                    display: flex;
                    align-items: flex-start;
                    gap: 8px;
                    flex-wrap: wrap;
                }
                
                .step-commands li code {
                    color: #0f172a;
                    white-space: pre-wrap;
                    word-break: break-word;
                }
                
                .step-commands li .collapse-note {
                    color: #64748b;
                    font-size: 11px;
                    font-style: italic;
                }
                
                .execute-step-button {
                    width: 100%;
                    padding: 14px 24px;
                    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.2s;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    margin-top: 20px;
                }
                
                .execute-step-button:hover:not(:disabled) {
                    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
                    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
                    transform: translateY(-1px);
                }
                
                .execute-step-button:disabled {
                    background: #cbd5e1;
                    cursor: not-allowed;
                    box-shadow: none;
                    transform: none;
                }
                
                .view-results-button:hover {
                    background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
                    box-shadow: 0 6px 16px rgba(102, 126, 234, 0.5);
                    transform: translateY(-2px);
                }
                
                .step-output {
                    margin-top: 20px;
                }
                
                .output-container {
                    background: #1e293b;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                }
                
                .output-header {
                    background: #334155;
                    padding: 10px 16px;
                    display: flex;
                    align-items: flex-start;
                    justify-content: space-between;
                    border-bottom: 1px solid #475569;
                    flex-wrap: wrap;
                    gap: 8px;
                }
                
                .output-header-title {
                    color: #e2e8f0;
                    font-size: 13px;
                    font-weight: 600;
                    font-family: 'Consolas', 'Monaco', monospace;
                    white-space: pre-wrap;
                    word-break: break-word;
                    flex: 1;
                }
                
                .output-header-toggle {
                    cursor: pointer;
                    color: #94a3b8;
                    font-size: 11px;
                    user-select: none;
                    transition: color 0.2s;
                }
                
                .output-header-toggle:hover {
                    color: #cbd5e1;
                }
                
                .command-output {
                    background: #1e293b;
                    color: #e2e8f0;
                    padding: 16px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 13px;
                    line-height: 1.6;
                    overflow-x: auto;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                    max-height: 400px;
                    overflow-y: auto;
                }
                
                .command-preview {
                    background: #f8fafc;
                    color: #475569;
                    padding: 16px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 13px;
                    line-height: 1.6;
                    overflow-x: auto;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                    border: 1px solid #e2e8f0;
                    border-radius: 6px;
                }
                
                .command-output.collapsed {
                    max-height: 60px;
                    overflow: hidden;
                    position: relative;
                }
                
                .command-output.collapsed::after {
                    content: '';
                    position: absolute;
                    bottom: 0;
                    left: 0;
                    right: 0;
                    height: 30px;
                    background: linear-gradient(transparent, #1e293b);
                }
                
                .output-success {
                    color: #86efac;
                }
                
                .output-error {
                    color: #fca5a5;
                    background: #450a0a;
                    padding: 16px;
                    border-radius: 8px;
                    border: 1px solid #991b1b;
                }
                
                .step-progress-bar {
                    margin-bottom: 30px;
                    padding: 20px;
                    background: white;
                    border-radius: 12px;
                    border: 1px solid #e2e8f0;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }
                
                .progress-bar {
                    display: flex;
                    gap: 8px;
                    margin-bottom: 12px;
                }
                
                .progress-segment {
                    flex: 1;
                    height: 8px;
                    background: #e2e8f0;
                    border-radius: 4px;
                    transition: all 0.3s ease;
                }
                
                .progress-segment.completed {
                    background: linear-gradient(90deg, #22c55e 0%, #16a34a 100%);
                }
                
                .progress-segment.current {
                    background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
                    animation: pulse-progress 2s ease-in-out infinite;
                }
                
                @keyframes pulse-progress {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.6; }
                }
                
                .progress-text {
                    text-align: center;
                    color: #64748b;
                    font-size: 14px;
                    font-weight: 600;
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
            html.Img(src=f"{requests_pathname_prefix}assets/logo.png", className="header-logo"),
        ], className="header"),
        
        html.Div([
            dcc.Tabs(id="tabs", value="home", children=[
                dcc.Tab(label="🧠 Learn", value="home", className="custom-tab"),
                dcc.Tab(label="🪄 Demos", value="demos", className="custom-tab"),
                dcc.Tab(label="⚡ Run Benchmark", value="run-benchmark", className="custom-tab"),
                dcc.Tab(label="📊 View Results", value="view-results", className="custom-tab"),
            ], className="tabs-container"),
            
            html.Div(id="tab-content", className="tab-content"),
        ], className="main-content"),
        
        # Stores for tracking state
        dcc.Store(id="execution-state", data={"running": False, "result": None}),
        dcc.Store(id="benchmark-state", data={"running": False, "result": None}),
        # Stores for View Results tab (must be in main layout for callbacks)
        dcc.Store(id="selected-runs", data=[]),
        dcc.Store(id="comparison-swap-state", data=False),
        dcc.Store(id="trigger-auto-compare", data=0),
        
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


def render_home_tab():
    """Render the home tab content with documentation."""
    # Navigate to project root (up from src/mdbpl/frontend/dash_app.py)
    project_root = Path(__file__).parent.parent.parent.parent
    home_path = project_root / "docs" / "HOME.md"
    
    try:
        if home_path.exists():
            home_content = home_path.read_text(encoding='utf-8')
        else:
            home_content = "# Welcome\n\nWelcome to MongoDB Performance Lab!"
    except Exception as e:
        home_content = f"# Welcome\n\nError loading content: {e}"
    
    return html.Div([
        dcc.Markdown(
            home_content,
            className="demo-markdown",
            dangerously_allow_html=True,
            highlight_config={
                "theme": "dark"
            }
        )
    ], style={"maxWidth": "900px", "margin": "0 auto"})


def render_demos_tab():
    """Render the demos tab content with step-by-step execution."""
    return html.Div([
        html.H3("Interactive Demos", style={"marginBottom": "20px", "color": "#0f172a"}),
        html.P("Learn MongoDB performance concepts through hands-on interactive demos. Execute each step at your own pace.", 
               style={"marginBottom": "30px", "color": "#64748b"}),
        
        # Demo selector
        html.Div(id="demo-list", className="demo-list"),
        dcc.Store(id="selected-demo", data=None),
        
        # Step-by-step execution area
        html.Div(id="demo-steps-container", children=[]),
        
        # Stores for tracking step execution
        dcc.Store(id="demo-execution-state", data={}),
        
        # Interval for polling step execution
        dcc.Interval(
            id="step-poll-interval",
            interval=500,  # Poll every 500ms
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
                className="run-button",
                style={"marginRight": "12px"}
            ),
            html.Button(
                "🗑️ Delete All Results",
                id="delete-all-results-button",
                n_clicks=0,
                className="run-button",
                style={
                    "backgroundColor": "#ef4444",
                    "marginLeft": "auto"
                }
            ),
        ], style={"marginBottom": "20px", "marginTop": "20px", "display": "flex", "alignItems": "center"}),
        
        # Confirmation dialog for delete
        dcc.ConfirmDialog(
            id="confirm-delete-dialog",
            message="Are you sure you want to delete all benchmark results? This action cannot be undone."
        ),
        
        # List of benchmark results with checkboxes
        html.Div(id="results-list", children=[]),
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
        if tab == "home":
            return render_home_tab()
        elif tab == "demos":
            return render_demos_tab()
        elif tab == "run-benchmark":
            return render_run_benchmark_tab()
        elif tab == "view-results":
            return render_view_results_tab()
        return html.Div("Select a tab")
    
    # Demo tab callbacks
    @app.callback(
        Output("demo-list", "children"),
        Input("demo-list", "id")
    )
    def load_demo_list(_):
        """Load available demos and display as clickable cards."""
        try:
            demos = list_demos()
            demo_cards = []
            
            for demo in demos:
                card = html.Div([
                    html.Div([
                        html.H4(demo['title'], style={"marginBottom": "8px", "color": "#0f172a"}),
                        html.P(demo['description'], style={"color": "#64748b", "fontSize": "14px", "marginBottom": "0"}),
                    ], style={"flex": "1"}),
                    html.Button(
                        "Select →",
                        id={"type": "demo-select-btn", "index": demo['name']},
                        n_clicks=0,
                        style={
                            "background": "#3b82f6",
                            "color": "white",
                            "border": "none",
                            "padding": "8px 16px",
                            "borderRadius": "6px",
                            "cursor": "pointer",
                            "fontSize": "14px",
                            "fontWeight": "600"
                        }
                    )
                ], className="demo-card", style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "20px",
                    "padding": "20px",
                    "background": "#f8fafc",
                    "borderRadius": "8px",
                    "border": "1px solid #e2e8f0",
                    "marginBottom": "12px",
                    "cursor": "pointer",
                    "transition": "all 0.2s"
                })
                demo_cards.append(card)
            
            return demo_cards
        except Exception as e:
            return html.Div(f"Error loading demos: {e}", style={"color": "#ef4444"})
    
    @app.callback(
        Output("selected-demo", "data"),
        Input({"type": "demo-select-btn", "index": ALL}, "n_clicks"),
        prevent_initial_call=True
    )
    def select_demo(n_clicks):
        """Handle demo selection from button clicks."""
        if not callback_context.triggered:
            return no_update
        
        # Get which button was clicked
        triggered_id = callback_context.triggered[0]["prop_id"]
        if not triggered_id or triggered_id == ".":
            return no_update
        
        # Parse the button ID to get demo name
        button_id = json.loads(triggered_id.split(".")[0])
        demo_name = button_id["index"]
        
        return demo_name
    
    @app.callback(
        [Output("demo-steps-container", "children"),
         Output("demo-execution-state", "data")],
        Input("selected-demo", "data"),
        prevent_initial_call=False  # Need to allow initial call to clear when no demo selected
    )
    def render_demo_steps(demo_name):
        """Render step-by-step execution interface when demo is selected."""
        if not demo_name:
            return [], {}
        
        try:
            # Clear any previous demo execution state
            global _demo_execution_state
            keys_to_clear = [k for k in _demo_execution_state.keys() if k.startswith("step_")]
            for key in keys_to_clear:
                del _demo_execution_state[key]
            
            demo = get_demo(demo_name)
            steps = demo.steps()
            
            # Initialize execution state
            initial_state = {
                "demo_name": demo_name,
                "current_step": 0,
                "total_steps": len(steps),
                "step_results": {},
                "running_step": None,
                "auto_execute": False  # Flag for auto-execution mode
            }
            
            # Progress bar with Run All Steps button
            progress_bar = html.Div([
                html.Div([
                    html.Div([
                        html.Div([
                            html.Div(
                                className=f"progress-segment",
                                id={"type": "progress-segment", "index": idx}
                            ) for idx in range(len(steps))
                        ], className="progress-bar"),
                        html.Div(f"Step 0 of {len(steps)} completed", className="progress-text", id="progress-text")
                    ], style={"flex": "1"}),
                    html.Button(
                        "▶ Run All Steps",
                        id="run-all-steps-button",
                        n_clicks=0,
                        className="run-all-button",
                        style={
                            "padding": "10px 20px",
                            "fontSize": "14px",
                            "fontWeight": "600",
                            "background": "#3b82f6",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "6px",
                            "cursor": "pointer",
                            "whiteSpace": "nowrap",
                            "marginLeft": "20px"
                        }
                    )
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "20px"})
            ], className="step-progress-bar")
            
            # Auto-execution interval timer
            auto_exec_interval = dcc.Interval(
                id="auto-exec-interval",
                interval=500,  # Check every 500ms
                n_intervals=0,
                disabled=True  # Disabled by default
            )
            
            step_cards = [progress_bar, auto_exec_interval]
            
            # Render each step
            for idx, step in enumerate(steps):
                # Step status badge
                badge = html.Span("Pending", className="step-status-badge badge-pending", 
                                id={"type": "step-badge", "index": idx})
                
                # Markdown section (collapsible)
                markdown_section = html.Details([
                    html.Summary(["📖 ", html.Span("Learn about this step")]),
                    html.Div([
                        dcc.Markdown(step.markdown, className="step-markdown-content")
                    ])
                ], open=(idx == 0), className="step-markdown-section")
                
                # Pre-render command boxes showing what will be executed
                command_boxes = []
                for cmd_idx, cmd in enumerate(step.commands):
                    cmd_text = cmd.raw if hasattr(cmd, 'raw') else str(cmd)
                    cmd_type = cmd.type if hasattr(cmd, 'type') else 'shell'
                    is_collapsed = cmd.collapse_output if hasattr(cmd, 'collapse_output') else False
                    
                    # Show command type badge
                    if cmd_type == "mongosh":
                        type_badge = html.Span([
                            html.Span("🍃 ", style={"marginRight": "4px"}),
                            "mongosh"
                        ], style={
                            "display": "inline-block",
                            "padding": "2px 8px",
                            "background": "#00684a",
                            "color": "white",
                            "borderRadius": "4px",
                            "fontSize": "11px",
                            "fontWeight": "600",
                            "marginRight": "8px",
                            "textTransform": "uppercase",
                            "letterSpacing": "0.05em"
                        })
                        cmd_display = f"$ mongosh --quiet\\n{cmd_text}"
                    else:
                        type_badge = html.Span([
                            html.Span("⚡ ", style={"marginRight": "4px"}),
                            "shell"
                        ], style={
                            "display": "inline-block",
                            "padding": "2px 8px",
                            "background": "#3b82f6",
                            "color": "white",
                            "borderRadius": "4px",
                            "fontSize": "11px",
                            "fontWeight": "600",
                            "marginRight": "8px",
                            "textTransform": "uppercase",
                            "letterSpacing": "0.05em"
                        })
                        cmd_display = f"$ {cmd_text}"
                    
                    # Build command preview box
                    if is_collapsed:
                        preview_content = html.Details([
                            html.Summary("Click to expand command"),
                            html.Pre(cmd_display, className="command-preview")
                        ], open=False)
                    else:
                        preview_content = html.Pre(cmd_display, className="command-preview")
                    
                    command_boxes.append(
                        html.Div([
                            html.Div([
                                type_badge,
                                html.Span("⏳ Ready to execute", style={
                                    "color": "#64748b",
                                    "fontSize": "12px",
                                    "fontStyle": "italic"
                                })
                            ], style={"marginBottom": "8px"}),
                            preview_content
                        ], style={"marginBottom": "16px"})
                    )
                
                commands_section = html.Div(command_boxes, className="step-commands", 
                                          id={"type": "step-commands", "index": idx})
                
                # Execute button
                execute_btn = html.Button(
                    f"▶ Execute Step {idx + 1}",
                    id={"type": "execute-step-btn", "index": idx},
                    n_clicks=0,  # Explicitly set to 0
                    disabled=(idx != 0),  # Only first step enabled initially
                    className="execute-step-button"
                )
                
                # Output area (will be populated by callback after execution)
                output_area = html.Div(
                    id={"type": "step-output", "index": idx},
                    className="step-output",
                    style={"display": "none"}  # Hidden until execution completes
                )
                
                # Build step card
                step_card = html.Div([
                    html.Div([
                        html.H4([
                            html.Span("⏸️" if idx != 0 else "▶️"),
                            html.Span(f" Step {idx + 1}: {step.title}")
                        ]),
                        badge
                    ], className="step-header"),
                    html.P(step.description, style={"color": "#64748b", "marginBottom": "16px"}),
                    markdown_section,
                    execute_btn,
                    commands_section,  # Commands shown before execution
                    output_area  # Output shown after execution
                ], className=f"step-card {'step-current' if idx == 0 else 'step-locked'}", 
                   id={"type": "step-card", "index": idx})
                
                step_cards.append(step_card)
            
            # Add completion card (content will be populated dynamically)
            completion_card = html.Div(
                id="completion-card",
                className="step-card",
                style={"display": "none"}  # Hidden until all steps complete
            )
            step_cards.append(completion_card)
            
            return step_cards, initial_state
            
        except Exception as e:
            return [html.Div(f"Error loading demo: {e}", style={"color": "#ef4444"})], {}
    
    @app.callback(
        [Output("demo-execution-state", "data", allow_duplicate=True),
         Output("step-poll-interval", "disabled")],
        Input({"type": "execute-step-btn", "index": ALL}, "n_clicks"),
        [State("demo-execution-state", "data"),
         State({"type": "execute-step-btn", "index": ALL}, "id")],
        prevent_initial_call=True
    )
    def execute_step_handler(n_clicks_list, exec_state, button_ids):
        """Handle execute step button clicks."""
        if not callback_context.triggered or not exec_state:
            return no_update, no_update
        
        # Check if any button was actually clicked (not just initial render)
        if not n_clicks_list or not any(n_clicks_list):
            return no_update, no_update
        
        # Determine which button was clicked
        triggered_id = callback_context.triggered[0]["prop_id"]
        if not triggered_id or triggered_id == "." or ".n_clicks" not in triggered_id:
            return no_update, no_update
        
        button_id = json.loads(triggered_id.split(".")[0])
        step_index = button_id["index"]
        
        # Verify this button actually has clicks
        if step_index >= len(n_clicks_list) or not n_clicks_list[step_index]:
            return no_update, no_update
        
        # Check if this step is already running or completed
        if exec_state.get("running_step") is not None:
            return no_update, no_update
        
        # JSON serialization converts int keys to strings
        if str(step_index) in exec_state.get("step_results", {}):
            return no_update, no_update
        
        # Verify this is the current step (not a future step)
        if step_index != exec_state.get("current_step", 0):
            return no_update, no_update
        
        # Start step execution in background thread
        demo_name = exec_state["demo_name"]
        demo = get_demo(demo_name)
        
        def run_step():
            """Execute step in background."""
            global _demo_execution_state
            try:
                step, success = demo.execute_step(step_index)
                # Store result in global state for polling callback to pick up
                step_key = f"step_{demo_name}_{step_index}"
                _demo_execution_state[step_key] = {
                    "step": step.to_dict(),
                    "success": success,
                    "completed": True
                }
            except Exception as e:
                step_key = f"step_{demo_name}_{step_index}"
                _demo_execution_state[step_key] = {
                    "error": str(e),
                    "success": False,
                    "completed": True
                }
        
        thread = threading.Thread(target=run_step, daemon=True)
        thread.start()
        
        # Update state to show step is running
        new_state = exec_state.copy()
        new_state["running_step"] = step_index
        
        return new_state, False  # Enable polling
    
    @app.callback(
        [Output({"type": "step-output", "index": MATCH}, "children"),
         Output({"type": "step-output", "index": MATCH}, "style"),
         Output({"type": "step-commands", "index": MATCH}, "style"),
         Output({"type": "step-card", "index": MATCH}, "className"),
         Output({"type": "step-badge", "index": MATCH}, "children"),
         Output({"type": "step-badge", "index": MATCH}, "className"),
         Output({"type": "execute-step-btn", "index": MATCH}, "disabled"),
         Output("demo-execution-state", "data", allow_duplicate=True),
         Output({"type": "progress-segment", "index": MATCH}, "className"),
         Output("progress-text", "children"),
         Output("step-poll-interval", "disabled", allow_duplicate=True)],
        [Input("step-poll-interval", "n_intervals"),
         Input({"type": "step-output", "index": MATCH}, "id")],
        [State("demo-execution-state", "data"),
         State({"type": "step-card", "index": MATCH}, "id")],
        prevent_initial_call=True
    )
    def update_step_execution(n_intervals, output_id, exec_state, card_id):
        """Poll for step execution completion and update UI."""
        step_index = output_id["index"]
        
        # Debug: show which step callback is running
        if exec_state:
            running_step = exec_state.get("running_step")
            if running_step is not None and step_index in [running_step - 1, running_step, running_step + 1]:
                print(f"DEBUG: update_step_execution callback for step {step_index}, running_step={running_step}")
        
        # Only update if this step is currently running
        if not exec_state or exec_state.get("running_step") != step_index:
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
        
        demo_name = exec_state.get("demo_name")
        if not demo_name:
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
        
        step_key = f"step_{demo_name}_{step_index}"
        
        # Check if step has completed
        if step_key not in _demo_execution_state:
            # Still running - don't update UI yet
            if step_index == exec_state.get("running_step"):
                # Only log for the actually running step to reduce spam
                print(f"DEBUG: Step {step_index} still running, step_key '{step_key}' not in global state. Keys present: {list(_demo_execution_state.keys())}")
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
        
        step_result = _demo_execution_state.pop(step_key)  # Remove from global state
        
        if not step_result.get("completed"):
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
        
        # Build output display
        output_components = []
        
        if step_result.get("error"):
            # Error occurred
            output_components.append(
                html.Div([
                    html.Div("❌ Error executing step", style={"fontWeight": "600", "marginBottom": "8px", "color": "#ef4444"}),
                    html.Pre(step_result["error"], className="output-error")
                ])
            )
            card_class = "step-card step-error"
            badge_text = "Error"
            badge_class = "step-status-badge badge-error"
        else:
            # Success
            step_data = step_result["step"]
            
            # Render each command output
            for cmd_idx, output in enumerate(step_data.get("outputs", [])):
                cmd = step_data["commands"][cmd_idx]
                is_collapsed = cmd.get("collapse_output", False)
                cmd_text = cmd.get("command", f"Command {cmd_idx + 1}")
                cmd_type = cmd.get("type", "shell")
                
                # Extract stdout and stderr from output dict
                stdout = output.get("stdout", "")
                stderr = output.get("stderr", "")
                exit_code = output.get("exit_code", 0)
                
                # Combine stdout and stderr for display
                combined_output = ""
                if stdout:
                    combined_output += stdout
                if stderr:
                    if combined_output:
                        combined_output += "\n\n"
                    combined_output += f"[stderr]\n{stderr}"
                
                if not combined_output:
                    combined_output = f"[Command exited with code {exit_code}]"
                
                # Build output element
                if is_collapsed:
                    output_element = html.Details([
                        html.Summary("Click to expand output"),
                        html.Pre(combined_output, className="command-output")
                    ], open=False)
                else:
                    output_element = html.Pre(combined_output, className="command-output")
                
                # Show command type badge and appropriate icon
                if cmd_type == "mongosh":
                    type_badge = html.Span([
                        html.Span("🍃 ", style={"marginRight": "4px"}),
                        "mongosh"
                    ], style={
                        "display": "inline-block",
                        "padding": "2px 8px",
                        "background": "#00684a",
                        "color": "white",
                        "borderRadius": "4px",
                        "fontSize": "11px",
                        "fontWeight": "600",
                        "marginRight": "8px",
                        "textTransform": "uppercase",
                        "letterSpacing": "0.05em"
                    })
                    cmd_display = f"$ mongosh --quiet\n{cmd_text}"
                else:
                    type_badge = html.Span([
                        html.Span("⚡ ", style={"marginRight": "4px"}),
                        "shell"
                    ], style={
                        "display": "inline-block",
                        "padding": "2px 8px",
                        "background": "#3b82f6",
                        "color": "white",
                        "borderRadius": "4px",
                        "fontSize": "11px",
                        "fontWeight": "600",
                        "marginRight": "8px",
                        "textTransform": "uppercase",
                        "letterSpacing": "0.05em"
                    })
                    cmd_display = f"$ {cmd_text}"
                
                output_div = html.Div([
                    html.Div([
                        type_badge,
                        html.Span(cmd_display, className="output-header-title")
                    ], className="output-header"),
                    output_element
                ], className="output-container", style={"marginBottom": "12px"})
                
                output_components.append(output_div)
            
            card_class = "step-card step-completed"
            badge_text = "Completed"
            badge_class = "step-status-badge badge-completed"
        
        # Update execution state
        new_state = exec_state.copy()
        new_state["running_step"] = None
        new_state.setdefault("step_results", {})[step_index] = step_result
        new_state["current_step"] = step_index + 1
        
        print(f"DEBUG: Storing step_result for step {step_index}, has_error={step_result.get('error') is not None}, success={step_result.get('success')}")
        
        # Auto-execute next step if enabled
        auto_execute = exec_state.get("auto_execute", False)
        total_steps = exec_state.get("total_steps", 0)
        next_step_index = step_index + 1
        
        print(f"DEBUG: Step {step_index} completed. auto_execute={auto_execute}, next_step={next_step_index}, total={total_steps}")
        
        if auto_execute and next_step_index < total_steps:
            # Start next step immediately
            demo_name = exec_state.get("demo_name")
            print(f"DEBUG: Auto-executing next step {next_step_index} for demo {demo_name}")
            
            def run_next_step():
                """Execute next step in background."""
                global _demo_execution_state
                try:
                    print(f"DEBUG: Thread started for step {next_step_index}")
                    demo = get_demo(demo_name)
                    step, success = demo.execute_step(next_step_index)
                    step_key = f"step_{demo_name}_{next_step_index}"
                    _demo_execution_state[step_key] = {
                        "step": step.to_dict(),
                        "success": success,
                        "completed": True
                    }
                    print(f"DEBUG: Step {next_step_index} completed in thread, success={success}")
                except Exception as e:
                    print(f"DEBUG: Error in step {next_step_index} thread: {e}")
                    step_key = f"step_{demo_name}_{next_step_index}"
                    _demo_execution_state[step_key] = {
                        "error": str(e),
                        "success": False,
                        "completed": True
                    }
            
            thread = threading.Thread(target=run_next_step, daemon=True)
            thread.start()
            print(f"DEBUG: Thread spawned for step {next_step_index}")
            
            new_state["running_step"] = next_step_index
        else:
            print(f"DEBUG: Not auto-executing: auto_execute={auto_execute}, next<total={next_step_index < total_steps}")
        
        # Parse run IDs from benchmark outputs for auto-comparison
        if not step_result.get("error"):
            step_data = step_result["step"]
            for output in step_data.get("outputs", []):
                stdout = output.get("stdout", "")
                # Look for "Run ID: <id>" patterns - run IDs are integers
                import re
                # Look for "Run ID: <number>"
                run_id_match = re.search(r'Run ID:\s+(\d+)', stdout, re.IGNORECASE)
                
                if run_id_match:
                    run_id = int(run_id_match.group(1))  # Convert to int for storage lookup
                    new_state.setdefault("benchmark_run_ids", []).append(run_id)
                    print(f"DEBUG: Parsed run ID: {run_id}")
                else:
                    # Debug: print first 300 chars of stdout to see what we're missing
                    if "benchmark" in stdout.lower() or "run" in stdout.lower() or "ops" in stdout.lower():
                        print(f"DEBUG: No run ID found in output: {stdout[:300]}...")
        
        # Update progress text
        completed = step_index + 1
        total = new_state["total_steps"]
        progress_text = f"Step {completed} of {total} completed"
        
        # Determine if we should disable polling
        # Keep polling enabled if auto-execute is on, otherwise disable until next manual click
        auto_execute = new_state.get("auto_execute", False)
        disable_polling = not auto_execute
        
        print(f"DEBUG: Returning from update_step_execution, disable_polling={disable_polling}, auto_execute={auto_execute}")
        
        return (
            output_components,
            {"display": "block"},  # Show output area
            {"display": "none"},   # Hide command preview
            card_class,
            badge_text,
            badge_class,
            True,  # Disable this step's button
            new_state,
            "progress-segment completed",
            progress_text,
            disable_polling
        )
    
    # Handle Run All Steps button
    @app.callback(
        [Output("demo-execution-state", "data", allow_duplicate=True),
         Output("auto-exec-interval", "disabled"),
         Output("step-poll-interval", "disabled"),
         Output("run-all-steps-button", "disabled")],
        Input("run-all-steps-button", "n_clicks"),
        State("demo-execution-state", "data"),
        prevent_initial_call=True
    )
    def start_auto_execute(n_clicks, exec_state):
        """Start auto-execution of all steps."""
        if not n_clicks or not exec_state:
            return no_update, no_update, no_update, no_update
        
        print(f"DEBUG: Run All Steps clicked. n_clicks={n_clicks}, current_step={exec_state.get('current_step')}")
        
        # Enable auto-execute mode and start first step
        new_state = exec_state.copy()
        new_state["auto_execute"] = True
        
        print(f"DEBUG: Set auto_execute=True in state")
        
        # If no step is running and we're at step 0, trigger first step
        if new_state.get("running_step") is None and new_state.get("current_step", 0) == 0:
            demo_name = new_state["demo_name"]
            demo = get_demo(demo_name)
            
            print(f"DEBUG: Starting first step for demo {demo_name}")
            
            def run_step():
                """Execute step in background."""
                global _demo_execution_state
                try:
                    print(f"DEBUG: Thread started for step 0")
                    step, success = demo.execute_step(0)
                    step_key = f"step_{demo_name}_0"
                    _demo_execution_state[step_key] = {
                        "step": step.to_dict(),
                        "success": success,
                        "completed": True
                    }
                    print(f"DEBUG: Step 0 completed in thread, success={success}")
                except Exception as e:
                    print(f"DEBUG: Error in step 0 thread: {e}")
                    step_key = f"step_{demo_name}_0"
                    _demo_execution_state[step_key] = {
                        "error": str(e),
                        "success": False,
                        "completed": True
                    }
            
            thread = threading.Thread(target=run_step, daemon=True)
            thread.start()
            print(f"DEBUG: Thread spawned for step 0")
            
            new_state["running_step"] = 0
        
        print(f"DEBUG: Returning state with auto_execute={new_state.get('auto_execute')}, running_step={new_state.get('running_step')}")
        return new_state, False, False, True  # Enable both intervals (auto-exec and step-poll), disable button
    
    # Auto-execute next step when previous completes (simplified - kept for monitoring)
    @app.callback(
        [Output("demo-execution-state", "data", allow_duplicate=True),
         Output("auto-exec-interval", "disabled", allow_duplicate=True)],
        Input("auto-exec-interval", "n_intervals"),
        State("demo-execution-state", "data"),
        prevent_initial_call=True
    )
    def monitor_auto_execution(n_intervals, exec_state):
        """Monitor auto-execution and disable interval when complete."""
        if not exec_state or not exec_state.get("auto_execute"):
            return no_update, True  # Disable interval if not auto-executing
        
        current_step = exec_state.get("current_step", 0)
        total_steps = exec_state.get("total_steps", 0)
        
        # If all steps complete, disable auto-execute
        if current_step >= total_steps:
            new_state = exec_state.copy()
            new_state["auto_execute"] = False
            return new_state, True  # Disable interval
        
        return no_update, False  # Keep interval enabled
    
    # Update Run All Steps button state
    @app.callback(
        [Output("run-all-steps-button", "children"),
         Output("run-all-steps-button", "disabled", allow_duplicate=True),
         Output("run-all-steps-button", "style")],
        Input("demo-execution-state", "data"),
        prevent_initial_call=True
    )
    def update_run_all_button(exec_state):
        """Update Run All Steps button based on execution state."""
        if not exec_state:
            return no_update, no_update, no_update
        
        auto_execute = exec_state.get("auto_execute", False)
        current_step = exec_state.get("current_step", 0)
        total_steps = exec_state.get("total_steps", 0)
        
        print(f"DEBUG: update_run_all_button - auto_execute={auto_execute}, current={current_step}, total={total_steps}")
        
        base_style = {
            "padding": "10px 20px",
            "fontSize": "14px",
            "fontWeight": "600",
            "color": "white",
            "border": "none",
            "borderRadius": "6px",
            "cursor": "pointer",
            "whiteSpace": "nowrap",
            "marginLeft": "20px"
        }
        
        # If auto-executing
        if auto_execute:
            style = base_style.copy()
            style["background"] = "#f59e0b"  # Orange during execution
            print(f"DEBUG: Button shows 'Running...'")
            return "⏸ Running...", True, style
        
        # If all steps complete
        if current_step >= total_steps:
            style = base_style.copy()
            style["background"] = "#22c55e"  # Green when complete
            return "✓ Complete", True, style
        
        # Default ready state
        style = base_style.copy()
        style["background"] = "#3b82f6"  # Blue when ready
        return "▶ Run All Steps", False, style
    
    # Enable next step button after current step completes
    @app.callback(
        Output({"type": "execute-step-btn", "index": ALL}, "disabled"),
        [Input("demo-execution-state", "data"),
         Input({"type": "execute-step-btn", "index": ALL}, "id")]
    )
    def update_step_buttons(exec_state, button_ids):
        """Enable/disable step buttons based on execution state."""
        if not exec_state or not button_ids:
            return [no_update] * len(button_ids)
        
        current_step = exec_state.get("current_step", 0)
        running_step = exec_state.get("running_step")
        step_results = exec_state.get("step_results", {})
        auto_execute = exec_state.get("auto_execute", False)
        
        disabled_states = []
        for button_id in button_ids:
            step_index = button_id["index"]
            
            # Disable if:
            # 1. Already completed
            # 2. A step is currently running
            # 3. Not the current step
            # 4. Auto-execute mode is enabled
            # JSON serialization converts int keys to strings
            if str(step_index) in step_results:
                disabled_states.append(True)
            elif running_step is not None:
                disabled_states.append(True)
            elif auto_execute:
                disabled_states.append(True)  # Disable all during auto-execute
            elif step_index != current_step:
                disabled_states.append(True)
            else:
                disabled_states.append(False)
        
        return disabled_states
    
    # Update step cards styling based on progress
    @app.callback(
        Output({"type": "step-card", "index": ALL}, "className"),
        [Input("demo-execution-state", "data"),
         Input({"type": "step-card", "index": ALL}, "id")],
        prevent_initial_call=True
    )
    def update_step_cards_styling(exec_state, card_ids):
        """Update step card styling based on execution state."""
        if not exec_state or not card_ids:
            return [no_update] * len(card_ids)
        
        current_step = exec_state.get("current_step", 0)
        running_step = exec_state.get("running_step")
        step_results = exec_state.get("step_results", {})
        
        class_names = []
        for card_id in card_ids:
            step_index = card_id["index"]
            # JSON serialization converts int keys to strings
            step_key = str(step_index)
            
            if step_key in step_results:
                if step_results[step_key].get("error"):
                    class_names.append("step-card step-error")
                else:
                    class_names.append("step-card step-completed")
            elif step_index == running_step:
                class_names.append("step-card step-running")
            elif step_index == current_step:
                class_names.append("step-card step-current")
            else:
                class_names.append("step-card step-locked")
        
        return class_names
    
    # Update step badges based on progress
    @app.callback(
        [Output({"type": "step-badge", "index": ALL}, "children"),
         Output({"type": "step-badge", "index": ALL}, "className")],
        [Input("demo-execution-state", "data"),
         Input({"type": "step-badge", "index": ALL}, "id")],
        prevent_initial_call=True
    )
    def update_step_badges(exec_state, badge_ids):
        """Update step badges based on execution state."""
        if not exec_state or not badge_ids:
            return [no_update] * len(badge_ids), [no_update] * len(badge_ids)
        
        current_step = exec_state.get("current_step", 0)
        running_step = exec_state.get("running_step")
        step_results = exec_state.get("step_results", {})
        
        print(f"DEBUG: update_step_badges - current={current_step}, running={running_step}, step_results keys={list(step_results.keys())}")
        
        badge_texts = []
        badge_classes = []
        
        for badge_id in badge_ids:
            step_index = badge_id["index"]
            # JSON serialization converts int keys to strings
            step_key = str(step_index)
            
            if step_key in step_results:
                if step_results[step_key].get("error"):
                    badge_texts.append("Error")
                    badge_classes.append("step-status-badge badge-error")
                else:
                    badge_texts.append("Completed")
                    badge_classes.append("step-status-badge badge-completed")
                    print(f"DEBUG: Badge for step {step_index} set to Completed")
            elif step_index == running_step:
                badge_texts.append("Running")
                badge_classes.append("step-status-badge badge-running")
                print(f"DEBUG: Badge for step {step_index} set to Running")
            else:
                badge_texts.append("Pending")
                badge_classes.append("step-status-badge badge-pending")
                print(f"DEBUG: Badge for step {step_index} set to Pending (not in results, not running)")
        
        return badge_texts, badge_classes
    
    # Show completion card when all steps are done
    @app.callback(
        [Output("completion-card", "children"),
         Output("completion-card", "style")],
        Input("demo-execution-state", "data"),
        prevent_initial_call=True
    )
    def show_completion_card(exec_state):
        """Show completion card when all demo steps are complete."""
        if not exec_state:
            return [], {"display": "none"}
        
        total_steps = exec_state.get("total_steps", 0)
        step_results = exec_state.get("step_results", {})
        
        # Check if all steps are complete (and successful)
        if len(step_results) == total_steps:
            all_successful = all(not result.get("error") for result in step_results.values())
            if all_successful:
                # Get benchmark run IDs if available
                run_ids = exec_state.get("benchmark_run_ids", [])
                
                # Build completion card content
                card_content = [
                    html.Div([
                        html.H4("🎉 Demo Complete!"),
                        html.P("All steps have been executed successfully.", style={"color": "#64748b", "marginTop": "8px"})
                    ], style={"textAlign": "center", "marginBottom": "24px"})
                ]
                
                # Debug: print run IDs
                print(f"DEBUG: Completion card - run_ids: {run_ids}")
                
                # If we have exactly 2 benchmark runs, use comparison button
                if len(run_ids) == 2:
                    print(f"DEBUG: Creating comparison button with baseline={run_ids[0]}, optimized={run_ids[1]}")
                    button = html.Button(
                        "📊 Compare Benchmark Results",
                        id={"type": "view-comparison", "baseline": run_ids[0], "optimized": run_ids[1]},
                        className="view-results-button",
                        style={
                            "padding": "12px 24px",
                            "fontSize": "16px",
                            "fontWeight": "600",
                            "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "8px",
                            "cursor": "pointer",
                            "boxShadow": "0 4px 12px rgba(102, 126, 234, 0.4)",
                            "transition": "all 0.3s ease"
                        },
                        n_clicks=0
                    )
                else:
                    # Fallback to simple view results button
                    button = html.Button(
                        "📊 View Results",
                        id="view-results-button",
                        className="view-results-button",
                        style={
                            "padding": "12px 24px",
                            "fontSize": "16px",
                            "fontWeight": "600",
                            "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "8px",
                            "cursor": "pointer",
                            "boxShadow": "0 4px 12px rgba(102, 126, 234, 0.4)",
                            "transition": "all 0.3s ease"
                        },
                        n_clicks=0
                    )
                
                card_content.append(html.Div([button], style={"textAlign": "center"}))
                
                return card_content, {"display": "block"}
        
        return [], {"display": "none"}
    
    # Navigate to results tab when View Results button is clicked
    @app.callback(
        Output("tabs", "value"),
        Input("view-results-button", "n_clicks"),
        prevent_initial_call=True
    )
    def navigate_to_results(n_clicks):
        """Navigate to the results tab when View Results button is clicked."""
        if n_clicks:
            return "view-results"
        return no_update
    
    # Benchmark tab callbacks
    @app.callback(
        Output("workload-selector", "options"),
        Input("workload-selector", "id")
    )
    def load_workloads(_):
        """Load available workloads."""
        try:
            workloads = ["read-heavy", "balanced", "write-heavy", "range-scan"]
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
            workload_descriptions = {
                "read-heavy": "95% reads, 5% updates (YCSB Workload B)",
                "balanced": "50% reads, 50% updates (YCSB Workload A)",
                "write-heavy": "10% reads, 90% updates (YCSB Workload E)",
                "range-scan": "80% range queries, 20% point reads"
            }
            description = html.Div([
                html.P(workload_descriptions.get(workload_name, "No description available")),
                html.P(f"Distribution: zipfian", 
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
            # Load Python benchmark
            if workload_name == "read-heavy":
                from mdbpl import create_read_heavy_benchmark
                workload = create_read_heavy_benchmark()
            elif workload_name == "balanced":
                from mdbpl import create_balanced_benchmark
                workload = create_balanced_benchmark()
            elif workload_name == "write-heavy":
                from mdbpl import create_write_heavy_benchmark
                workload = create_write_heavy_benchmark()
            elif workload_name == "range-scan":
                from mdbpl import create_range_scan_benchmark
                workload = create_range_scan_benchmark()
            else:
                raise ValueError(f"Unknown workload: {workload_name}")
            
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
        [Output("comparison-from-results", "children"),
         Output("comparison-swap-state", "data")],
        [Input("compare-selected-button", "n_clicks"),
         Input({"type": "swap-comparison", "index": ALL}, "n_clicks"),
         Input("trigger-auto-compare", "data")],
        [State("selected-runs", "data"),
         State("comparison-swap-state", "data")],
        prevent_initial_call=True
    )
    def compare_selected_runs(compare_clicks, swap_clicks, auto_trigger, selected_runs, is_swapped):
        """Compare two selected runs."""
        ctx = callback_context
        
        # Check if swap button was clicked
        if ctx.triggered:
            trigger_id = ctx.triggered[0]["prop_id"]
            if "swap-comparison" in trigger_id:
                is_swapped = not is_swapped
        
        if not selected_runs or len(selected_runs) != 2:
            return html.Div(), is_swapped
        
        try:
            # Get the two runs
            run1 = storage.get_run_by_id(selected_runs[0])
            run2 = storage.get_run_by_id(selected_runs[1])
            
            if not run1 or not run2:
                return html.Div("❌ Could not find selected runs.", className="error"), is_swapped
            
            # Swap order if requested
            if is_swapped:
                first_run = run2
                second_run = run1
                first_label = f"Run 2 ({run2.get('tag', 'untagged')})"
                second_label = f"Run 1 ({run1.get('tag', 'untagged')})"
            else:
                first_run = run1
                second_run = run2
                first_label = f"Run 1 ({run1.get('tag', 'untagged')})"
                second_label = f"Run 2 ({run2.get('tag', 'untagged')})"
            
            first_run['throughput'] = first_run.get('operations_per_second', 0)
            second_run['throughput'] = second_run.get('operations_per_second', 0)
            
            # Calculate deltas
            def calculate_delta(val1, val2):
                if val1 == 0:
                    return 0.0
                return ((val2 - val1) / val1) * 100
            
            improvements = {
                'throughput_percent': calculate_delta(first_run['operations_per_second'], second_run['operations_per_second']),
                'latency_p50_percent': calculate_delta(first_run['latency_p50'], second_run['latency_p50']),
                'latency_p95_percent': calculate_delta(first_run['latency_p95'], second_run['latency_p95']),
                'latency_p99_percent': calculate_delta(first_run['latency_p99'], second_run['latency_p99']),
            }
            
            comparison_normalized = {'improvements': improvements}
            
            throughput_change = improvements['throughput_percent']
            latency_change = improvements['latency_p95_percent']
            
            # Calculate query efficiency metrics
            def calc_efficiency(examined, returned):
                if examined == 0 or returned == 0:
                    return None
                return (returned / examined) * 100
            
            first_efficiency = calc_efficiency(
                first_run.get('total_docs_examined', 0),
                first_run.get('total_docs_returned', 0)
            )
            second_efficiency = calc_efficiency(
                second_run.get('total_docs_examined', 0),
                second_run.get('total_docs_returned', 0)
            )
            
            # Create comparison display
            return html.Div([
                # Header with swap button
                html.Div([
                    html.H3("📊 Comparison Results", className="results-title", style={"marginTop": "0px", "marginBottom": "0px"}),
                    html.Button(
                        "⇄ Swap Order",
                        id={"type": "swap-comparison", "index": 0},
                        n_clicks=0,
                        style={
                            "padding": "8px 16px",
                            "backgroundColor": "#f1f5f9",
                            "color": "#475569",
                            "border": "1px solid #cbd5e1",
                            "borderRadius": "6px",
                            "cursor": "pointer",
                            "fontSize": "14px",
                            "fontWeight": "500",
                            "transition": "all 0.2s"
                        }
                    )
                ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "20px"}),
                
                # Run details
                html.Div([
                    html.Div("Comparing Runs", className="summary-title"),
                    html.Div([
                        html.Div([
                            html.Div(first_label, style={"fontSize": "12px", "color": "#64748b", "marginBottom": "4px", "textTransform": "uppercase", "fontWeight": "600"}),
                            html.Div(f"{first_run['workload_name']}", style={"fontSize": "16px", "fontWeight": "600", "marginBottom": "4px"}),
                            html.Div(f"Tag: {first_run.get('tag', 'untagged')}", style={"fontSize": "14px", "color": "#64748b"}),
                            html.Div(f"Run ID: {first_run['id']}", style={"fontSize": "12px", "color": "#94a3b8"}),
                        ], style={"padding": "12px", "backgroundColor": "#f8fafc", "borderRadius": "6px", "border": "1px solid #e2e8f0"}),
                        html.Div([
                            html.Div(second_label, style={"fontSize": "12px", "color": "#64748b", "marginBottom": "4px", "textTransform": "uppercase", "fontWeight": "600"}),
                            html.Div(f"{second_run['workload_name']}", style={"fontSize": "16px", "fontWeight": "600", "marginBottom": "4px"}),
                            html.Div(f"Tag: {second_run.get('tag', 'untagged')}", style={"fontSize": "14px", "color": "#64748b"}),
                            html.Div(f"Run ID: {second_run['id']}", style={"fontSize": "12px", "color": "#94a3b8"}),
                        ], style={"padding": "12px", "backgroundColor": "#f8fafc", "borderRadius": "6px", "border": "1px solid #e2e8f0"}),
                    ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginTop": "12px"}),
                ], style={"marginBottom": "20px", "padding": "16px", "backgroundColor": "white", "borderRadius": "8px", "border": "1px solid #e2e8f0"}),
                
                # Summary
                html.Div([
                    html.Div("Comparison Summary", className="summary-title"),
                    html.Div([
                        html.Div([
                            html.Div("Throughput Change", className="summary-label"),
                            html.Div(f"{first_run['operations_per_second']:.1f} → {second_run['operations_per_second']:.1f} ops/sec", className="summary-value"),
                            html.Div(f"{'+' if throughput_change > 0 else ''}{throughput_change:.1f}%", className="summary-change"),
                        ], className="summary-item"),
                        html.Div([
                            html.Div("Latency P95 Change", className="summary-label"),
                            html.Div(f"{first_run['latency_p95']:.2f} → {second_run['latency_p95']:.2f} ms", className="summary-value"),
                            html.Div(f"{'-' if latency_change < 0 else '+'}{abs(latency_change):.1f}%", className="summary-change"),
                        ], className="summary-item"),
                    ], className="summary-grid"),
                ], className="summary-box"),
                
                # Query Efficiency Metrics
                html.Div([
                    html.Div("Query Efficiency", className="summary-title"),
                    html.Div([
                        html.Div([
                            html.Div(first_label, style={"fontSize": "12px", "color": "#64748b", "marginBottom": "8px", "fontWeight": "600"}),
                            html.Div(f"Docs Examined: {first_run.get('total_docs_examined', 0):,}", style={"fontSize": "14px", "marginBottom": "4px", "color": "#64748b"}),
                            html.Div(f"Docs Returned: {first_run.get('total_docs_returned', 0):,}", style={"fontSize": "14px", "marginBottom": "4px", "color": "#64748b"}),
                            html.Div([
                                html.Span("Efficiency: ", style={"fontSize": "14px", "color": "#64748b"}),
                                html.Span(
                                    f"{first_efficiency:.1f}%" if first_efficiency else "N/A",
                                    style={
                                        "fontSize": "16px",
                                        "fontWeight": "600",
                                        "color": "#22c55e" if first_efficiency and first_efficiency > 80 else "#f59e0b" if first_efficiency and first_efficiency > 50 else "#ef4444"
                                    }
                                )
                            ]),
                            html.Div(f"Index Scans: {first_run.get('index_scans', 0)} | Collection Scans: {first_run.get('collection_scans', 0)}",
                                    style={"fontSize": "12px", "color": "#64748b", "marginTop": "8px"}),
                        ], style={"padding": "12px", "backgroundColor": "#f8fafc", "borderRadius": "6px", "border": "1px solid #e2e8f0"}),
                        html.Div([
                            html.Div(second_label, style={"fontSize": "12px", "color": "#64748b", "marginBottom": "8px", "fontWeight": "600"}),
                            html.Div(f"Docs Examined: {second_run.get('total_docs_examined', 0):,}", style={"fontSize": "14px", "marginBottom": "4px", "color": "#64748b"}),
                            html.Div(f"Docs Returned: {second_run.get('total_docs_returned', 0):,}", style={"fontSize": "14px", "marginBottom": "4px", "color": "#64748b"}),
                            html.Div([
                                html.Span("Efficiency: ", style={"fontSize": "14px", "color": "#64748b"}),
                                html.Span(
                                    f"{second_efficiency:.1f}%" if second_efficiency else "N/A",
                                    style={
                                        "fontSize": "16px",
                                        "fontWeight": "600",
                                        "color": "#22c55e" if second_efficiency and second_efficiency > 80 else "#f59e0b" if second_efficiency and second_efficiency > 50 else "#ef4444"
                                    }
                                )
                            ]),
                            html.Div(f"Index Scans: {second_run.get('index_scans', 0)} | Collection Scans: {second_run.get('collection_scans', 0)}",
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
                    create_metrics_table(first_run, second_run, comparison_normalized, baseline_label=first_label, optimized_label=second_label),
                ]),
            ], style={"marginBottom": "30px"}), is_swapped
            
        except Exception as e:
            return html.Div(f"❌ Error comparing runs: {e}", className="error"), is_swapped

    # Handle view comparison button from demo tab
    @app.callback(
        [Output("tabs", "value"),
         Output("selected-runs", "data"),
         Output("trigger-auto-compare", "data")],
        Input({"type": "view-comparison", "baseline": ALL, "optimized": ALL}, "n_clicks"),
        State("trigger-auto-compare", "data"),
        prevent_initial_call=True
    )
    def navigate_to_comparison(n_clicks, current_trigger):
        """Navigate to Results tab and auto-compare runs when view comparison button is clicked."""
        ctx = callback_context
        
        if not ctx.triggered or not any(n_clicks):
            return no_update, no_update, no_update
        
        # Extract baseline and optimized IDs from button id
        trigger_id = ctx.triggered[0]["prop_id"]
        # Parse the JSON id from the prop_id string
        id_str = trigger_id.split(".")[0]
        button_id = json.loads(id_str)
        
        baseline_id = button_id["baseline"]
        optimized_id = button_id["optimized"]
        
        # Switch to results tab, select both runs, and trigger comparison
        return "view-results", [baseline_id, optimized_id], current_trigger + 1

    # Handle delete all results button click
    @app.callback(
        Output("confirm-delete-dialog", "displayed"),
        Input("delete-all-results-button", "n_clicks"),
        prevent_initial_call=True
    )
    def show_delete_confirmation(n_clicks):
        """Show confirmation dialog when delete button is clicked."""
        if n_clicks > 0:
            return True
        return False
    
    # Handle confirmation dialog result
    @app.callback(
        Output("results-list", "children", allow_duplicate=True),
        Input("confirm-delete-dialog", "submit_n_clicks"),
        prevent_initial_call=True
    )
    def delete_all_results(submit_clicks):
        """Delete all results when user confirms."""
        if submit_clicks:
            try:
                storage.reset_db()
                return html.Div(
                    "✅ All results deleted successfully. Click Refresh to reload.",
                    style={
                        "padding": "20px",
                        "backgroundColor": "#dcfce7",
                        "border": "1px solid #86efac",
                        "borderRadius": "8px",
                        "color": "#166534",
                        "textAlign": "center"
                    }
                )
            except Exception as e:
                return html.Div(
                    f"❌ Error deleting results: {e}",
                    style={
                        "padding": "20px",
                        "backgroundColor": "#fee2e2",
                        "border": "1px solid #fca5a5",
                        "borderRadius": "8px",
                        "color": "#991b1b",
                        "textAlign": "center"
                    }
                )
        return no_update


def extract_changes(steps: list) -> list:
    """Extract what changed during the demo from the steps."""
    changes = []
    
    for step in steps:
        if "load" in step["id"].lower():
            if step.get("result") and "records" in step["result"]:
                changes.append({
                    "step": "Data Preparation",
                    "detail": f"Loaded {step['result']['records']:,} test records into MongoDB"
                })
        elif "create" in step["id"].lower() and "index" in step["id"].lower():
            if step.get("result") and "index" in step["result"]:
                changes.append({
                    "step": "Index Creation",
                    "detail": f"Created index: {step['result']['index']}"
                })
        elif "drop" in step["id"].lower() and "index" in step["id"].lower():
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
    latency_sign = "-" if latency_change < 0 else "+"  # Negative change = improvement for latency
    
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


def create_metrics_table(baseline: dict, optimized: dict, comparison: dict, baseline_label: str = "Run 1", optimized_label: str = "Run 2") -> html.Div:
    """Create detailed metrics comparison table."""
    
    improvements = comparison.get("improvements", {}) if comparison else {}
    
    rows = [
        html.Tr([
            html.Th("Metric"),
            html.Th(baseline_label),
            html.Th(optimized_label),
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
                    f"{change:+.1f}%",  # Use :+ format to show sign correctly
                    className="improvement" if change < 0 else "degradation"  # Negative change = improvement for latency
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

