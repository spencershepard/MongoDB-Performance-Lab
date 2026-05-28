"""SQLite storage for benchmark results."""

import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import asdict

from .executor import BenchmarkResult


class BenchmarkStorage:
    """Manages SQLite storage for benchmark results."""
    
    def __init__(self, db_path: str = "/data/benchmarks.db"):
        """
        Initialize storage.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        
        # Ensure directory exists
        try:
            db_dir = Path(db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)
            print(f"Database directory: {db_dir} (exists: {db_dir.exists()})")
        except Exception as e:
            print(f"ERROR: Failed to create database directory: {e}")
            raise
        
        # Initialize database
        try:
            self._init_db()
            print(f"Database initialized: {db_path}")
        except Exception as e:
            print(f"ERROR: Failed to initialize database: {e}")
            print(f"  Path: {db_path}")
            print(f"  Dir exists: {Path(db_path).parent.exists()}")
            print(f"  Dir writable: {os.access(Path(db_path).parent, os.W_OK)}")
            raise
    
    def _init_db(self):
        """Create database schema if it doesn't exist."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
        
            # Runs table - stores overall benchmark metadata
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workload_name TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    duration_seconds REAL NOT NULL,
                    total_operations INTEGER NOT NULL,
                    successful_operations INTEGER NOT NULL,
                    failed_operations INTEGER NOT NULL,
                    operations_per_second REAL NOT NULL,
                    latency_p50 REAL NOT NULL,
                    latency_p95 REAL NOT NULL,
                    latency_p99 REAL NOT NULL,
                    total_docs_examined INTEGER DEFAULT 0,
                    total_docs_returned INTEGER DEFAULT 0,
                    operations_with_explain INTEGER DEFAULT 0,
                    index_scans INTEGER DEFAULT 0,
                    collection_scans INTEGER DEFAULT 0,
                    collection_size INTEGER DEFAULT 0,
                    schema_name TEXT DEFAULT NULL,
                    source TEXT DEFAULT NULL,
                    collection_name TEXT DEFAULT NULL,
                    database_name TEXT DEFAULT NULL,
                    workflow_name TEXT DEFAULT NULL,
                    workflow_title TEXT DEFAULT NULL
                )
            """)
            
            # Operation metrics table - stores per-operation breakdown
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operation_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    operation_name TEXT NOT NULL,
                    operation_count INTEGER NOT NULL,
                    avg_latency REAL NOT NULL,
                    p50_latency REAL NOT NULL,
                    p95_latency REAL NOT NULL,
                    p99_latency REAL NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs (id)
                )
            """)
            
            # Create indexes for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_tag ON runs(tag)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON runs(timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_operation_metrics_run_id 
                ON operation_metrics(run_id)
            """)
            
            # Migrate existing databases to add new columns if they don't exist
            self._migrate_schema(cursor)
            
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            print(f"ERROR: SQLite error during database initialization: {e}")
            raise
        except Exception as e:
            print(f"ERROR: Unexpected error during database initialization: {e}")
            raise
    
    def _migrate_schema(self, cursor):
        """Add new columns to existing tables if they don't exist."""
        try:
            # Check if new columns exist
            cursor.execute("PRAGMA table_info(runs)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Add missing columns
            if 'collection_size' not in columns:
                cursor.execute("ALTER TABLE runs ADD COLUMN collection_size INTEGER DEFAULT 0")
            if 'schema_name' not in columns:
                cursor.execute("ALTER TABLE runs ADD COLUMN schema_name TEXT DEFAULT NULL")
            if 'source' not in columns:
                cursor.execute("ALTER TABLE runs ADD COLUMN source TEXT DEFAULT NULL")
            if 'collection_name' not in columns:
                cursor.execute("ALTER TABLE runs ADD COLUMN collection_name TEXT DEFAULT NULL")
            if 'database_name' not in columns:
                cursor.execute("ALTER TABLE runs ADD COLUMN database_name TEXT DEFAULT NULL")
            if 'workflow_name' not in columns:
                cursor.execute("ALTER TABLE runs ADD COLUMN workflow_name TEXT DEFAULT NULL")
            if 'workflow_title' not in columns:
                cursor.execute("ALTER TABLE runs ADD COLUMN workflow_title TEXT DEFAULT NULL")
        except Exception as e:
            print(f"Warning: Schema migration failed: {e}")
    
    def reset_db(self):
        """Delete the database file to start fresh."""
        db_path = Path(self.db_path)
        if db_path.exists():
            db_path.unlink()
            # Reinitialize with new schema
            self._init_db()
            return True
        return False
    
    def save_result(self, result: BenchmarkResult, tag: str, collection_size: int = 0, 
                    schema_name: Optional[str] = None, source: Optional[str] = None, 
                    collection_name: Optional[str] = None, database_name: Optional[str] = None,
                    workflow_name: Optional[str] = None, workflow_title: Optional[str] = None) -> int:
        """
        Save a benchmark result to the database.
        
        Args:
            result: Benchmark result to save
            tag: Tag for this benchmark run
            collection_size: Number of documents in collection at benchmark time
            schema_name: Name of schema used (e.g., 'videogame', 'ecommerce', 'default')
            source: Source of benchmark ('demo', 'mcp', 'cli')
            collection_name: Name of MongoDB collection
            database_name: Name of MongoDB database
            
        Returns:
            Run ID of the saved result
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.utcnow().isoformat()
        
        # Insert run
        cursor.execute("""
            INSERT INTO runs (
                workload_name, tag, timestamp, duration_seconds,
                total_operations, successful_operations, failed_operations,
                operations_per_second, latency_p50, latency_p95, latency_p99,
                total_docs_examined, total_docs_returned, operations_with_explain,
                index_scans, collection_scans, collection_size, schema_name, source,
                collection_name, database_name, workflow_name, workflow_title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.workload_name,
            tag,
            timestamp,
            result.duration_seconds,
            result.total_operations,
            result.successful_operations,
            result.failed_operations,
            result.operations_per_second,
            result.latency_p50,
            result.latency_p95,
            result.latency_p99,
            result.total_docs_examined,
            result.total_docs_returned,
            result.operations_with_explain,
            result.index_scans,
            result.collection_scans,
            collection_size,
            schema_name,
            source,
            collection_name,
            database_name,
            workflow_name,
            workflow_title
        ))
        
        run_id = cursor.lastrowid
        if run_id is None:
            raise RuntimeError("Failed to get run_id after insert")
        
        # Insert operation metrics
        for op_name, latencies in result.operation_metrics.items():
            if not latencies:
                continue
            
            sorted_latencies = sorted(latencies)
            n = len(sorted_latencies)
            
            avg = sum(latencies) / len(latencies)
            p50 = sorted_latencies[int(n * 0.50)]
            p95 = sorted_latencies[int(n * 0.95)]
            p99 = sorted_latencies[int(n * 0.99)]
            
            cursor.execute("""
                INSERT INTO operation_metrics (
                    run_id, operation_name, operation_count,
                    avg_latency, p50_latency, p95_latency, p99_latency
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                op_name,
                len(latencies),
                avg,
                p50,
                p95,
                p99
            ))
        
        conn.commit()
        conn.close()
        
        return run_id
    
    def get_run_by_id(self, run_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a benchmark run by ID.
        
        Args:
            run_id: Run ID to retrieve
            
        Returns:
            Run data with operation metrics, or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get run
        cursor.execute("""
            SELECT * FROM runs WHERE id = ?
        """, (run_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        
        run_data = dict(row)
        
        # Get operation metrics
        cursor.execute("""
            SELECT * FROM operation_metrics WHERE run_id = ?
        """, (run_id,))
        
        operations = []
        for op_row in cursor.fetchall():
            operations.append(dict(op_row))
        
        run_data['operations'] = operations
        
        conn.close()
        return run_data
    
    def get_run_by_tag(self, tag: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent benchmark run with a given tag.
        
        Args:
            tag: Tag to search for
            
        Returns:
            Run data with operation metrics, or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get most recent run with tag
        cursor.execute("""
            SELECT * FROM runs 
            WHERE tag = ? 
            ORDER BY timestamp DESC 
            LIMIT 1
        """, (tag,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        
        run_data = dict(row)
        
        # Get operation metrics
        cursor.execute("""
            SELECT * FROM operation_metrics WHERE run_id = ?
        """, (run_data['id'],))
        
        operations = []
        for op_row in cursor.fetchall():
            operations.append(dict(op_row))
        
        run_data['operations'] = operations
        
        conn.close()
        return run_data
    
    def get_last_run(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent benchmark run.
        
        Returns:
            Run data with operation metrics, or None if no runs exist
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get most recent run
        cursor.execute("""
            SELECT * FROM runs 
            ORDER BY timestamp DESC 
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        
        run_data = dict(row)
        
        # Get operation metrics
        cursor.execute("""
            SELECT * FROM operation_metrics WHERE run_id = ?
        """, (run_data['id'],))
        
        operations = []
        for op_row in cursor.fetchall():
            operations.append(dict(op_row))
        
        run_data['operations'] = operations
        
        conn.close()
        return run_data
    
    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        List recent benchmark runs.
        
        Args:
            limit: Maximum number of runs to return
            
        Returns:
            List of run data (without detailed operation metrics)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM runs 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        
        runs = []
        for row in cursor.fetchall():
            runs.append(dict(row))
        
        conn.close()
        return runs
    
    def list_tags(self) -> List[str]:
        """
        List all unique tags.
        
        Returns:
            List of unique tags
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT tag FROM runs ORDER BY tag
        """)
        
        tags = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        return tags
    
    def compare_runs(self, tag1: str, tag2: str) -> Dict[str, Any]:
        """
        Compare two benchmark runs by tag.
        
        Args:
            tag1: First tag to compare
            tag2: Second tag to compare
            
        Returns:
            Comparison data with deltas
        """
        run1 = self.get_run_by_tag(tag1)
        run2 = self.get_run_by_tag(tag2)
        
        if not run1:
            raise ValueError(f"No run found with tag: {tag1}")
        if not run2:
            raise ValueError(f"No run found with tag: {tag2}")
        
        # Calculate deltas
        def calculate_delta(val1, val2):
            """Calculate percentage change."""
            if val1 == 0:
                return 0.0
            return ((val2 - val1) / val1) * 100
        
        comparison = {
            'run1': run1,
            'run2': run2,
            'deltas': {
                'throughput': calculate_delta(
                    run1['operations_per_second'],
                    run2['operations_per_second']
                ),
                'latency_p50': calculate_delta(
                    run1['latency_p50'],
                    run2['latency_p50']
                ),
                'latency_p95': calculate_delta(
                    run1['latency_p95'],
                    run2['latency_p95']
                ),
                'latency_p99': calculate_delta(
                    run1['latency_p99'],
                    run2['latency_p99']
                ),
            }
        }
        
        # Compare per-operation metrics
        operations_comparison = {}
        
        # Build operation lookup for run1
        run1_ops = {op['operation_name']: op for op in run1['operations']}
        run2_ops = {op['operation_name']: op for op in run2['operations']}
        
        # Compare common operations
        for op_name in set(run1_ops.keys()) | set(run2_ops.keys()):
            op1 = run1_ops.get(op_name)
            op2 = run2_ops.get(op_name)
            
            if op1 and op2:
                operations_comparison[op_name] = {
                    'run1': op1,
                    'run2': op2,
                    'deltas': {
                        'avg_latency': calculate_delta(
                            op1['avg_latency'],
                            op2['avg_latency']
                        ),
                        'p50_latency': calculate_delta(
                            op1['p50_latency'],
                            op2['p50_latency']
                        ),
                        'p95_latency': calculate_delta(
                            op1['p95_latency'],
                            op2['p95_latency']
                        ),
                    }
                }
            elif op1:
                operations_comparison[op_name] = {
                    'run1': op1,
                    'run2': None,
                    'deltas': {}
                }
            else:
                operations_comparison[op_name] = {
                    'run1': None,
                    'run2': op2,
                    'deltas': {}
                }
        
        comparison['operations'] = operations_comparison
        
        return comparison
