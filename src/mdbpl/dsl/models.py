"""DSL models and schemas for workload definitions."""

from typing import Dict, List, Literal, Optional, Union, Any
from pydantic import BaseModel, Field


class ValueSpec(BaseModel):
    """Specification for a value in the DSL."""
    type: Literal["param", "literal", "random", "counter"]
    param: Optional[str] = None
    value: Optional[Any] = None
    length: Optional[int] = None
    start: Optional[int] = None


class FilterCondition(BaseModel):
    """A single filter condition."""
    field: str
    operator: Literal[
        "eq", "ne", "gt", "gte", "lt", "lte", "in", "nin", "regex",
        "exists", "type", "all", "elemMatch", "size"
    ]
    value: Optional[ValueSpec] = None  # Optional for exists operator


class CompoundFilter(BaseModel):
    """Compound filter with AND/OR logic."""
    and_: Optional[List[FilterCondition]] = Field(None, alias="and")
    or_: Optional[List[FilterCondition]] = Field(None, alias="or")


FilterSpec = Union[FilterCondition, CompoundFilter]


class OperationSpec(BaseModel):
    """Specification for a single operation in a workload."""
    name: str
    weight: int
    operation: Literal["find", "insert", "update", "delete", "aggregate"]
    filter: Optional[Union[FilterCondition, CompoundFilter]] = None
    projection: Optional[Dict[str, int]] = None
    sort: Optional[Dict[str, int]] = None
    limit: Optional[int] = None
    update: Optional[Dict[str, Any]] = None
    document: Optional[Dict[str, Any]] = None
    pipeline: Optional[List[Dict[str, Any]]] = None


class DistributionSpec(BaseModel):
    """Distribution for parameter generation."""
    type: Literal["zipfian", "uniform", "latest"] = "zipfian"


class WorkloadSpec(BaseModel):
    """Complete workload specification."""
    name: str
    description: str
    database: str = "perflab"
    collection: str = "usertable"
    distribution: DistributionSpec
    operations: List[OperationSpec]
    
    class Config:
        populate_by_name = True
