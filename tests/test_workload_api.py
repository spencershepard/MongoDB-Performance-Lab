"""Tests for Python workload API."""

import pytest
from mdbpl import Benchmark, zipfian, uniform, latest


def test_benchmark_creation():
    """Test basic benchmark creation."""
    benchmark = Benchmark(
        name="test",
        database="testdb",
        collection="testcol",
        description="Test benchmark"
    )
    
    assert benchmark.name == "test"
    assert benchmark.database == "testdb"
    assert benchmark.collection == "testcol"
    assert benchmark.description == "Test benchmark"
    assert len(benchmark.operations) == 0


def test_operation_decorator():
    """Test operation registration via decorator."""
    benchmark = Benchmark("test", "testdb", "testcol")
    
    @benchmark.operation(weight=80, name="read")
    def read_op(collection):
        return collection.find_one({})
    
    @benchmark.operation(weight=20, name="write")
    def write_op(collection):
        return collection.insert_one({})
    
    assert len(benchmark.operations) == 2
    assert benchmark.operations[0].name == "read"
    assert benchmark.operations[0].weight == 80
    assert benchmark.operations[1].name == "write"
    assert benchmark.operations[1].weight == 20


def test_total_weight():
    """Test total weight calculation."""
    benchmark = Benchmark("test", "testdb", "testcol")
    
    @benchmark.operation(weight=70)
    def op1(collection):
        pass
    
    @benchmark.operation(weight=30)
    def op2(collection):
        pass
    
    assert benchmark.get_total_weight() == 100


def test_validation_no_operations():
    """Test validation fails with no operations."""
    benchmark = Benchmark("test", "testdb", "testcol")
    
    with pytest.raises(ValueError, match="no operations"):
        benchmark.validate()


def test_validation_success():
    """Test validation succeeds with operations."""
    benchmark = Benchmark("test", "testdb", "testcol")
    
    @benchmark.operation(weight=100)
    def op(collection):
        pass
    
    assert benchmark.validate() is True


def test_zipfian_generator():
    """Test Zipfian distribution generator."""
    dist = zipfian(1000)
    
    # Generate 100 values
    values = [dist.next() for _ in range(100)]
    
    # All values should be in valid range
    assert all(0 <= v < 1000 for v in values)
    
    # With Zipfian, most values should be in lower range (hot keys)
    # At least 60% should be in bottom 20%
    hot_keys = sum(1 for v in values if v < 200)
    assert hot_keys >= 60  # Expect strong skew


def test_uniform_generator():
    """Test uniform distribution generator."""
    dist = uniform(1000)
    
    # Generate 100 values
    values = [dist.next() for _ in range(100)]
    
    # All values should be in valid range
    assert all(0 <= v < 1000 for v in values)
    
    # With uniform distribution, values should be spread out
    # Standard deviation should be reasonably high
    import statistics
    std = statistics.stdev(values)
    assert std > 200  # Expect good spread


def test_latest_generator():
    """Test latest-biased distribution generator."""
    dist = latest(1000)
    
    # Generate 100 values
    values = [dist.next() for _ in range(100)]
    
    # All values should be in valid range
    assert all(0 <= v < 1000 for v in values)
    
    # With latest distribution, most values should be in upper range
    # At least 60% should be in top 20%
    recent_keys = sum(1 for v in values if v >= 800)
    assert recent_keys >= 60  # Expect bias toward recent


def test_built_in_workload_imports():
    """Test that built-in workloads can be imported."""
    from mdbpl import create_read_heavy_benchmark, create_balanced_benchmark
    
    read_heavy = create_read_heavy_benchmark()
    assert read_heavy.name == "read-heavy"
    assert len(read_heavy.operations) == 2
    assert read_heavy.get_total_weight() == 100
    
    balanced = create_balanced_benchmark()
    assert balanced.name == "balanced"
    assert len(balanced.operations) == 2
    assert balanced.get_total_weight() == 100
