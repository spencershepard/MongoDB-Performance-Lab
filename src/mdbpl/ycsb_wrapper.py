"""YCSB wrapper that calls Java directly instead of using Python 2 launcher."""

import os
import subprocess
import sys
from pathlib import Path


def run_ycsb(args):
    """
    Execute YCSB by calling Java directly.
    
    This bypasses the Python 2 launcher script that comes with YCSB.
    """
    ycsb_home = os.getenv('YCSB_HOME', '/opt/ycsb')
    ycsb_path = Path(ycsb_home)
    
    if not ycsb_path.exists():
        print(f"Error: YCSB not found at {ycsb_home}", file=sys.stderr)
        return 1
    
    # Build classpath from YCSB jars
    lib_dir = ycsb_path / 'lib'
    classpath = ':'.join([
        str(jar) for jar in lib_dir.glob('*.jar')
    ])
    
    # Add database-specific bindings if specified
    if len(args) > 1:
        binding = args[1]  # e.g., 'mongodb'
        binding_dir = ycsb_path / binding / 'lib'
        if binding_dir.exists():
            classpath += ':' + ':'.join([
                str(jar) for jar in binding_dir.glob('*.jar')
            ])
    
    # Construct Java command
    java_cmd = [
        'java',
        '-cp', classpath,
        'site.ycsb.Client',
    ] + args
    
    # Execute
    try:
        result = subprocess.run(java_cmd, check=False)
        return result.returncode
    except Exception as e:
        print(f"Error executing YCSB: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(run_ycsb(sys.argv[1:]))
