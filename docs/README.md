# Documentation Directory

This directory contains all markdown documentation for the MongoDB Performance Lab.

## Structure

```
docs/
├── README.md              # This file
├── DSL-SPEC.md           # Domain-Specific Language specification
├── DSL-IMPLEMENTATION.md # DSL implementation details
├── METRICS.md            # Performance metrics guide
├── SNAPSHOT-MODE.md      # Snapshot mode documentation
└── demos/                # Demo-specific educational content
    ├── index-performance.md  # Index performance demo docs
    └── overindexing.md       # Over-indexing demo docs
```

## Accessing Documentation

### API Endpoints

**List all docs:**
```
GET /api/docs
```

**Get specific doc:**
```
GET /api/docs/{path}
```

Examples:
- `GET /api/docs/METRICS.md` - Main metrics guide
- `GET /api/docs/demos/index-performance.md` - Demo-specific docs
- `GET /api/docs/DSL-SPEC.md` - DSL specification

**Demo-specific shortcut:**
```
GET /api/demos/{demo_name}/docs
```

Example:
- `GET /api/demos/index-performance/docs` - Same as `/api/docs/demos/index-performance.md`

### In Code

Demo classes reference markdown files by filename:

```python
class IndexPerformanceDemo(Demo):
    name = "index-performance"
    title = "Index Performance Impact"
    markdown_file = "index-performance.md"  # Looks in docs/demos/
```

The system automatically:
- Resolves to `docs/demos/index-performance.md`
- Loads content with UTF-8 encoding
- Falls back to `description` if file not found

## Adding New Documentation

### For General Docs

1. Create markdown file in `docs/` directory
2. Use clear filename (e.g., `CACHING-GUIDE.md`)
3. Access via `/api/docs/CACHING-GUIDE.md`

### For Demo Docs

1. Create markdown file in `docs/demos/` directory
2. Name it to match demo name (e.g., `sharding-demo.md`)
3. Reference in demo class: `markdown_file = "sharding-demo.md"`
4. Access via `/api/demos/sharding-demo/docs` or `/api/docs/demos/sharding-demo.md`
