# Workload DSL Specification

## Overview

The workload DSL is a declarative YAML format for defining benchmark workloads. It abstracts MongoDB query syntax to enable reproducible, database-agnostic benchmarks.

## Workload File Structure

```yaml
name: "workload-name"
description: "What this workload tests"
database: "perflab"
collection: "usertable"

# Distribution for selecting documents
distribution:
  type: "zipfian"  # zipfian | uniform | latest
  
# Operations to run
operations:
  - name: "point-read"
    weight: 50  # Relative frequency (50%)
    operation: "find"
    filter:
      field: "_id"
      operator: "eq"
      value: 
        type: "param"
        param: "userId"
    projection:
      field0: 1
      field1: 1
    limit: 1
    
  - name: "range-scan"
    weight: 30
    operation: "find"
    filter:
      field: "field0"
      operator: "gte"
      value:
        type: "param"
        param: "rangeStart"
    limit: 10
    
  - name: "update"
    weight: 20
    operation: "update"
    filter:
      field: "_id"
      operator: "eq"
      value:
        type: "param"
        param: "userId"
    update:
      $set:
        field0:
          type: "random"
          length: 100
```

## Operations

### Find

```yaml
operation: "find"
filter: <filter_spec>
projection: <field_map>
sort: <sort_spec>
limit: <number>
```

### Insert

```yaml
operation: "insert"
document:
  field1:
    type: "random"
    length: 100
  field2:
    type: "counter"
```

### Update

```yaml
operation: "update"
filter: <filter_spec>
update:
  $set:
    field0: <value_spec>
  $inc:
    counter: 1
```

### Delete

```yaml
operation: "delete"
filter: <filter_spec>
```

### Aggregate

```yaml
operation: "aggregate"
pipeline:
  - $match: <filter_spec>
  - $group:
      _id: "$field0"
      count: { $sum: 1 }
  - $sort:
      count: -1
  - $limit: 10
```

## Filter Specifications

### Simple Filter

```yaml
filter:
  field: "fieldName"
  operator: "eq"  # eq | ne | gt | gte | lt | lte | in | nin | regex | exists | type | all | elemMatch | size
  value:
    type: "param"
    param: "paramName"
```

### Compound Filter (AND)

```yaml
filter:
  and:
    - field: "field0"
      operator: "gte"
      value: { type: "literal", value: "a" }
    - field: "field1"
      operator: "lt"
      value: { type: "literal", value: "z" }
```

### Compound Filter (OR)

```yaml
filter:
  or:
    - field: "field0"
      operator: "eq"
      value: { type: "param", param: "value1" }
    - field: "field1"
      operator: "eq"
      value: { type: "param", param: "value2" }
```

## Value Types

### Parameter (runtime-provided)

```yaml
value:
  type: "param"
  param: "userId"  # Will be generated based on distribution
```

### Literal (static)

```yaml
value:
  type: "literal"
  value: "static_value"
```

### Random (generated)

```yaml
value:
  type: "random"
  length: 100
```

### Counter (auto-increment)

```yaml
value:
  type: "counter"
  start: 1000
```

## Advanced Operators for Production Workloads

### Array Queries

```yaml
# All elements match
filter:
  field: "tags"
  operator: "all"
  value:
    type: "literal"
    value: ["mongodb", "database"]

# Array contains element matching condition
filter:
  field: "items"
  operator: "elemMatch"
  value:
    type: "literal"
    value: { price: { $gt: 100 } }

# Array size
filter:
  field: "items"
  operator: "size"
  value:
    type: "literal"
    value: 5
```

### Field Existence & Type

```yaml
# Field exists
filter:
  field: "optionalField"
  operator: "exists"
  value:
    type: "literal"
    value: true

# Field type checking
filter:
  field: "timestamp"
  operator: "type"
  value:
    type: "literal"
    value: "date"
```

### Not In (nin)

```yaml
filter:
  field: "status"
  operator: "nin"
  value:
    type: "literal"
    value: ["cancelled", "refunded"]
```

## Built-in Workloads

The system provides YCSB-style workloads out of the box:

- `read-heavy`: 95% reads, 5% updates
- `write-heavy`: 50% reads, 50% updates
- `read-only`: 100% reads
- `scan-heavy`: 50% scans, 50% updates
- `balanced`: 50% reads, 50% writes

## Custom Workloads

Place custom workload YAML files in the `workloads/` directory:

```bash
workloads/
  my-custom-workload.yaml
  production-replica.yaml
```

Run with:

```bash
mdbpl run --workload workloads/my-custom-workload.yaml
```
