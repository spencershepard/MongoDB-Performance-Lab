"""YCSB integration for data loading and benchmarking."""

import os
import subprocess
import tempfile
from pathlib import Path


def load_ycsb_data(
    mongodb_uri: str,
    record_count: int,
    distribution: str = 'zipfian',
    field_count: int = 10,
    field_length: int = 100,
    database: str = 'perflab',
    collection: str = 'usertable',
    drop_existing: bool = False
):
    """
    Load YCSB dataset into MongoDB.
    
    Args:
        mongodb_uri: MongoDB connection string
        record_count: Number of records to generate
        distribution: Key distribution (zipfian, uniform, latest)
        field_count: Number of fields per document
        field_length: Length of each field value
        database: Target database name
        collection: Target collection name
        drop_existing: Drop the collection before loading
    """
    ycsb_home = os.getenv('YCSB_HOME', '/opt/ycsb')
    ycsb_path = Path(ycsb_home)
    
    if not ycsb_path.exists():
        raise RuntimeError(f"YCSB not found at {ycsb_home}")
    
    # Drop collection if requested
    if drop_existing:
        from pymongo import MongoClient
        print("Dropping existing collection...")
        client = MongoClient(mongodb_uri)
        client[database][collection].drop()
        client.close()
        print("✓ Collection dropped")
        print()
    
    # Create workload properties file
    workload_config = f"""
recordcount={record_count}
operationcount={record_count}
workload=site.ycsb.workloads.CoreWorkload

fieldcount={field_count}
fieldlength={field_length}
requestdistribution={distribution}
insertorder=ordered

readallfields=true
readproportion=0
updateproportion=0
scanproportion=0
insertproportion=1
"""
    
    # Write to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.properties', delete=False) as f:
        f.write(workload_config.strip())
        workload_file = f.name
    
    try:
        # Build MongoDB connection properties
        mongodb_props = [
            f'-p', f'mongodb.url={mongodb_uri}/{database}',
            f'-p', f'mongodb.database={database}',
            f'-p', f'mongodb.collection={collection}',
        ]
        
        # Build classpath
        lib_dir = ycsb_path / 'lib'
        mongodb_dir = ycsb_path / 'mongodb-binding' / 'lib'
        
        classpath_parts = []
        
        # Add core YCSB jars
        if lib_dir.exists():
            classpath_parts.extend([str(jar) for jar in lib_dir.glob('*.jar')])
        
        # Add MongoDB binding jars
        if mongodb_dir.exists():
            classpath_parts.extend([str(jar) for jar in mongodb_dir.glob('*.jar')])
        else:
            # Try alternate location
            alt_mongodb_dir = ycsb_path / 'mongodb' / 'lib'
            if alt_mongodb_dir.exists():
                classpath_parts.extend([str(jar) for jar in alt_mongodb_dir.glob('*.jar')])
        
        if not classpath_parts:
            raise RuntimeError(f"No YCSB jars found in {lib_dir}")
        
        classpath = ':'.join(classpath_parts)
        
        # Build Java command
        java_cmd = [
            'java',
            '-cp', classpath,
            'site.ycsb.Client',
            '-load',
            '-db', 'site.ycsb.db.MongoDbClient',
            '-P', workload_file,
        ] + mongodb_props
        
        print(f"Loading data with YCSB...")
        print(f"Command: java -cp ... site.ycsb.Client -load -db site.ycsb.db.MongoDbClient")
        print()
        
        # Execute YCSB load
        result = subprocess.run(
            java_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False
        )
        
        # Parse output for progress
        for line in result.stdout.split('\n'):
            # Show progress lines
            if 'Loading records' in line or 'Completed' in line or '[INSERT]' in line:
                print(line)
            # Show errors
            elif 'ERROR' in line or 'Exception' in line:
                print(line)
        
        if result.returncode != 0:
            raise RuntimeError(f"YCSB load failed with exit code {result.returncode}")

    finally:
        if os.path.exists(workload_file):
            os.unlink(workload_file)

    # Add sequential numeric score field (0..record_count-1).
    # score is a first-class part of the dataset: range-scan and group-by
    # default to it, and it serves as a reliable numeric field for index demos.
    print()
    print("Adding score field...")
    from pymongo import MongoClient, UpdateOne
    client = MongoClient(mongodb_uri)
    coll = client[database][collection]
    batch = []
    for i, doc in enumerate(coll.find({}, {"_id": 1})):
        batch.append(UpdateOne({"_id": doc["_id"]}, {"$set": {"score": i}}))
        if len(batch) >= 1000:
            coll.bulk_write(batch)
            batch = []
    if batch:
        coll.bulk_write(batch)
    client.close()
    print(f"✓ Added score field (0–{record_count - 1})")


def run_ycsb_workload(
    mongodb_uri: str,
    workload_name: str,
    operation_count: int,
    database: str = 'perflab',
    collection: str = 'usertable'
):
    """
    Run a YCSB workload for benchmarking.
    
    This is for future use - currently we'll use our own DSL-based workloads.
    """
    # TODO: Implement workload execution
    pass
