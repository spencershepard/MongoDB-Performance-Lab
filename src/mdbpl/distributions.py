"""Distribution generators for realistic workload patterns.

Provides statistical distributions commonly used in database benchmarking:
- Zipfian: 80/20 rule (small percentage of keys accessed frequently)
- Uniform: Equal probability for all keys
- Latest: Recent keys accessed more frequently

Based on YCSB distribution patterns.
"""

import random
import math
from typing import Optional


class ZipfianGenerator:
    """Generates Zipfian-distributed integers for realistic access patterns.
    
    Zipfian distribution follows an 80/20 rule where ~20% of keys receive ~80% of accesses.
    This models real-world scenarios like:
    - Popular products in e-commerce
    - Active users in social networks
    - Hot data in caching systems
    
    Example:
        >>> dist = ZipfianGenerator(10000)
        >>> hot_keys = [dist.next() for _ in range(1000)]
        >>> # Most values will be < 2000 (top 20%)
    """
    
    def __init__(self, record_count: int, theta: float = 0.99):
        """Initialize Zipfian generator.
        
        Args:
            record_count: Total number of records (0 to record_count-1)
            theta: Zipfian constant (0.99 = strong skew, 0.0 = uniform)
        """
        self.record_count = record_count
        self.theta = theta
        
        # Pre-compute constants for performance
        self._zeta_n = self._zeta(record_count, theta)
        self._eta = (1 - pow(2.0 / record_count, 1 - theta)) / (1 - self._zeta_2 / self._zeta_n)
        
        # State for random number generation
        self._last_value = None
    
    @property
    def _zeta_2(self) -> float:
        """Zeta constant for n=2 (cached)."""
        return 1 + pow(0.5, self.theta)
    
    def _zeta(self, n: int, theta: float) -> float:
        """Calculate zeta value (generalized harmonic number).
        
        This is the normalization constant for the Zipfian distribution.
        """
        zeta_value = 0.0
        for i in range(1, n + 1):
            zeta_value += 1.0 / pow(i, theta)
        return zeta_value
    
    def next(self) -> int:
        """Generate next Zipfian-distributed integer.
        
        Returns:
            Integer in range [0, record_count)
        """
        u = random.random()
        uz = u * self._zeta_n
        
        if uz < 1.0:
            return 0
        
        if uz < 1.0 + pow(0.5, self.theta):
            return 1
        
        # General case
        value = int(self.record_count * pow(self._eta * u - self._eta + 1, 1.0 / (1.0 - self.theta)))
        
        # Clamp to valid range
        return max(0, min(value, self.record_count - 1))
    
    def __repr__(self) -> str:
        return f"ZipfianGenerator(record_count={self.record_count}, theta={self.theta})"


class UniformGenerator:
    """Generates uniformly-distributed random integers.
    
    Each key has equal probability of being accessed. Useful for:
    - Testing worst-case scenarios (no caching benefits)
    - Baseline comparisons
    - Load testing without hot spots
    
    Example:
        >>> dist = UniformGenerator(10000)
        >>> keys = [dist.next() for _ in range(1000)]
        >>> # Values evenly distributed across 0-9999
    """
    
    def __init__(self, record_count: int):
        """Initialize uniform generator.
        
        Args:
            record_count: Total number of records (0 to record_count-1)
        """
        self.record_count = record_count
    
    def next(self) -> int:
        """Generate next uniformly-distributed integer.
        
        Returns:
            Integer in range [0, record_count)
        """
        return random.randint(0, self.record_count - 1)
    
    def __repr__(self) -> str:
        return f"UniformGenerator(record_count={self.record_count})"


class LatestGenerator:
    """Generates integers with bias toward recently inserted records.
    
    Useful for modeling workloads where newest data is accessed most frequently:
    - Social media timelines
    - Recent orders in e-commerce
    - Latest log entries
    
    Example:
        >>> dist = LatestGenerator(10000)
        >>> recent_keys = [dist.next() for _ in range(1000)]
        >>> # Most values will be near 9999 (most recent)
    """
    
    def __init__(self, record_count: int):
        """Initialize latest generator.
        
        Args:
            record_count: Total number of records (0 to record_count-1)
        """
        self.record_count = record_count
        # Use Zipfian for the distribution shape, but reverse the range
        self._zipfian = ZipfianGenerator(record_count)
    
    def next(self) -> int:
        """Generate next integer biased toward recent records.
        
        Returns:
            Integer in range [0, record_count), skewed toward record_count-1
        """
        # Reverse the Zipfian output so high values are more common
        return self.record_count - self._zipfian.next() - 1
    
    def __repr__(self) -> str:
        return f"LatestGenerator(record_count={self.record_count})"


# Convenience factory functions for cleaner API

def zipfian(record_count: int, theta: float = 0.99) -> ZipfianGenerator:
    """Create a Zipfian distribution generator.
    
    Args:
        record_count: Total number of records
        theta: Skew factor (0.99 = strong skew, 0.0 = uniform)
        
    Returns:
        ZipfianGenerator instance
        
    Example:
        >>> dist = zipfian(10000)
        >>> user_id = dist.next()  # Usually returns low numbers (hot keys)
    """
    return ZipfianGenerator(record_count, theta)


def uniform(record_count: int) -> UniformGenerator:
    """Create a uniform distribution generator.
    
    Args:
        record_count: Total number of records
        
    Returns:
        UniformGenerator instance
        
    Example:
        >>> dist = uniform(10000)
        >>> user_id = dist.next()  # Equal chance of any value 0-9999
    """
    return UniformGenerator(record_count)


def latest(record_count: int) -> LatestGenerator:
    """Create a latest-biased distribution generator.
    
    Args:
        record_count: Total number of records
        
    Returns:
        LatestGenerator instance
        
    Example:
        >>> dist = latest(10000)
        >>> user_id = dist.next()  # Usually returns high numbers (recent keys)
    """
    return LatestGenerator(record_count)
