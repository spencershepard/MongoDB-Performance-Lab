# Welcome to MongoDB Performance Lab

Benchmark MongoDB queries and compare performance across different configurations, indexes, and workloads.

## Interactive Demos

Pre-built scenarios that demonstrate common MongoDB performance patterns:

- **Index Performance** - See the impact of proper indexing on range queries and scans
- **Over-Indexing** - Understand the write performance penalties of too many indexes

Select a demo from the dropdown, click **Run**, and watch real-time execution progress. Each demo automatically saves results for comparison.

## Custom Benchmarks

Run your own workloads in the **Run Benchmark** tab:
1. Choose a workload type (read-heavy, write-heavy, balanced, etc.)
2. Set duration and add a descriptive tag
3. View throughput, latency percentiles, and query metrics

## Compare Results

The **View Results** tab shows all saved benchmark runs:
- Select any two runs to see side-by-side comparisons
- Analyze throughput improvements and latency changes
- Examine detailed metrics: collection scans, index usage, documents examined
- Use the **Swap** button to flip comparison order

Results are automatically tagged (e.g., "no-index", "with-index") for easy identification.

---

💡 **Beyond the UI:** This project also includes a CLI for scripting and CI/CD integration. Run `mdbpl --help` in the container to explore automation options.


---

# MongoDB & NoSQL Concepts

A comprehensive guide to MongoDB fundamentals, NoSQL principles, and performance optimization strategies.

---

## Table of Contents

1. [What is MongoDB?](#what-is-mongodb)
2. [NoSQL Database Concepts](#nosql-database-concepts)
3. [What Makes MongoDB Unique](#what-makes-mongodb-unique)
4. [Data Modeling in MongoDB](#data-modeling-in-mongodb)
5. [Common Misconfigurations & Performance Bottlenecks](#common-misconfigurations--performance-bottlenecks)
6. [Best Practices for Production](#best-practices-for-production)

---

## What is MongoDB?

MongoDB is a **document-oriented NoSQL database** designed for scalability, flexibility, and developer productivity. Instead of storing data in rows and columns (like traditional SQL databases), MongoDB stores data as **JSON-like documents** with dynamic schemas.

### Key Characteristics

- **Document Model**: Data is stored as BSON (Binary JSON) documents
- **Schema Flexibility**: Documents in the same collection can have different fields
- **Horizontal Scalability**: Built-in sharding for distributing data across multiple servers
- **Rich Query Language**: Powerful aggregation framework and query capabilities
- **High Availability**: Replica sets provide automatic failover and data redundancy

### When to Use MongoDB

✅ **Good Fit:**
- Rapidly evolving schemas (startups, prototyping)
- Complex hierarchical data structures
- High-volume read/write operations
- Real-time analytics and aggregations
- Content management systems
- IoT and time-series data (with time-series collections)
- Mobile and gaming applications

❌ **Not Ideal For:**
- Complex multi-document transactions (though supported since 4.0)
- Highly normalized data with many relationships
- Financial systems requiring ACID guarantees across all operations
- Applications heavily dependent on SQL joins

---

## NoSQL Database Concepts

### The CAP Theorem

In distributed systems, you can only guarantee **two out of three** properties:

- **Consistency**: All nodes see the same data at the same time
- **Availability**: Every request gets a response (success or failure)
- **Partition Tolerance**: System continues operating despite network failures

**MongoDB prioritizes:** CP (Consistency + Partition Tolerance) in its default configuration, though you can tune read/write concerns for AP (Availability + Partition Tolerance).

### NoSQL Database Types

1. **Document Stores** (MongoDB, CouchDB)
   - Store semi-structured documents
   - Flexible schemas
   - Nested data structures

2. **Key-Value Stores** (Redis, DynamoDB)
   - Simplest model: key → value
   - Extremely fast lookups
   - Limited query capabilities

3. **Column-Family Stores** (Cassandra, HBase)
   - Organize data by columns instead of rows
   - Optimized for write-heavy workloads
   - Good for time-series data

4. **Graph Databases** (Neo4j, ArangoDB)
   - Store relationships between entities
   - Optimized for traversing connections
   - Social networks, recommendation engines

### BASE vs ACID

**ACID (Traditional SQL):**
- **A**tomicity: All or nothing transactions
- **C**onsistency: Data integrity constraints enforced
- **I**solation: Transactions don't interfere
- **D**urability: Committed data persists

**BASE (NoSQL):**
- **B**asically **A**vailable: System available most of the time
- **S**oft state: State may change over time (eventual consistency)
- **E**ventual consistency: System becomes consistent eventually

MongoDB supports **both models** depending on configuration:
- Multi-document ACID transactions (since 4.0)
- Eventual consistency with read preferences
- Tunable consistency via read/write concerns

---

## What Makes MongoDB Unique

### 1. Flexible Schema Design

Unlike SQL databases with rigid schemas, MongoDB allows:

```javascript
// Document 1
{
  _id: 1,
  name: "John Doe",
  email: "john@example.com"
}

// Document 2 - different structure, same collection!
{
  _id: 2,
  name: "Jane Smith",
  email: "jane@example.com",
  phone: "+1-555-1234",
  preferences: {
    newsletter: true,
    notifications: ["email", "sms"]
  }
}
```

**Benefits:**
- Rapid development and iteration
- Easy to add new fields without migrations
- Natural representation of complex data

**Trade-offs:**
- No schema enforcement by default (use JSON Schema validation if needed)
- Risk of inconsistent data if not careful
- Application code must handle missing fields

### 2. Rich Document Model

MongoDB documents can contain:
- **Nested Objects**: Hierarchical data structures
- **Arrays**: Lists of values or embedded documents
- **Mixed Types**: Different data types in the same field (discouraged in practice)

```javascript
{
  _id: ObjectId("..."),
  user: "john_doe",
  orders: [
    {
      orderId: 1001,
      items: [
        { product: "Laptop", price: 999.99, qty: 1 },
        { product: "Mouse", price: 29.99, qty: 2 }
      ],
      total: 1059.97,
      shippedAt: ISODate("2026-05-10T14:30:00Z")
    }
  ],
  address: {
    street: "123 Main St",
    city: "Boston",
    state: "MA",
    zip: "02101"
  }
}
```

### 3. Powerful Aggregation Framework

MongoDB's aggregation pipeline allows complex data transformations:

```javascript
db.orders.aggregate([
  { $match: { status: "completed" } },
  { $unwind: "$items" },
  { $group: {
      _id: "$items.product",
      totalRevenue: { $sum: { $multiply: ["$items.price", "$items.qty"] } },
      totalSold: { $sum: "$items.qty" }
  }},
  { $sort: { totalRevenue: -1 } },
  { $limit: 10 }
])
```

### 4. Horizontal Scalability with Sharding

**Sharding** distributes data across multiple servers:

```
          ┌─────────────┐
          │   mongos    │  ← Query router
          └──────┬──────┘
                 │
        ┬────────┴────────┬
        │                 │
   ┌────▼────┐      ┌────▼────┐
   │ Shard 1 │      │ Shard 2 │  ← Data distributed
   │ (A-M)   │      │ (N-Z)   │     by shard key
   └─────────┘      └─────────┘
```

**Benefits:**
- Distribute load across multiple servers
- Store datasets larger than a single machine
- Increase throughput by parallelizing operations

**Considerations:**
- Choose shard key carefully (can't change later!)
- Avoid "hot" shards with uneven data distribution
- Cross-shard queries are slower

### 5. Replica Sets for High Availability

**Replica sets** provide redundancy and automatic failover:

```
   ┌─────────┐
   │ Primary │  ← All writes go here
   └────┬────┘
        │
   ┬────┴────┬
   │         │
┌──▼──┐  ┌──▼──┐
│Sec 1│  │Sec 2│  ← Replicate data, can serve reads
└─────┘  └─────┘
```

**Features:**
- Automatic failover if primary fails (30 seconds typically)
- Read scaling by reading from secondaries
- Zero downtime for maintenance (rolling upgrades)
- Geographic distribution for disaster recovery

### 6. Native JSON/BSON Support

MongoDB stores data in **BSON** (Binary JSON):

**Advantages over JSON:**
- More data types: Date, ObjectId, Binary, Decimal128, etc.
- Efficient encoding/decoding
- Supports fast array indexing
- Smaller on disk (usually)

**Example:**
```javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),  // 12-byte unique identifier
  createdAt: ISODate("2026-05-15T10:30:00Z"), // Native date type
  balance: NumberDecimal("1234.56"),          // Precise decimal for currency
  profilePic: BinData(0, "..."),             // Binary data
  tags: ["mongodb", "nosql", "database"]      // Array
}
```

---

## Data Modeling in MongoDB

### Embed vs Reference

**Embedding** (Denormalization):
```javascript
// User document with embedded orders
{
  _id: 1,
  name: "John",
  orders: [
    { orderId: 101, total: 99.99, items: [...] },
    { orderId: 102, total: 149.99, items: [...] }
  ]
}
```

✅ Pros: Single query, better performance, atomic updates  
❌ Cons: Document size limits (16MB), data duplication, harder to query embedded data

**Referencing** (Normalization):
```javascript
// User document
{ _id: 1, name: "John" }

// Separate orders collection
{ _id: 101, userId: 1, total: 99.99, items: [...] }
{ _id: 102, userId: 1, total: 149.99, items: [...] }
```

✅ Pros: No duplication, smaller documents, flexible querying  
❌ Cons: Multiple queries or $lookup (like JOIN), more complex

### Decision Guidelines

**Embed when:**
- Data is accessed together (one-to-few relationship)
- Child data doesn't need to be queried independently
- Updates are infrequent
- Related data is small and bounded

**Reference when:**
- Data is large or grows unbounded (one-to-many, many-to-many)
- Child documents need independent queries
- Updates are frequent (avoid duplicating frequently changed data)
- Need to enforce size limits

---

## Common Misconfigurations & Performance Bottlenecks

### 🔴 1. Missing Indexes on Frequent Queries

**Problem:**
```javascript
// Collection scan - examines ALL documents!
db.users.find({ email: "john@example.com" })
```

**Symptoms:**
- Slow queries (>100ms for simple lookups)
- High CPU usage
- `executionStats.totalDocsExamined` >> `nReturned`

**Solution:**
```javascript
// Create index on queried field
db.users.createIndex({ email: 1 })

// Verify index is used
db.users.find({ email: "john@example.com" }).explain("executionStats")
// Should show: executionStages.stage = "IXSCAN"
```

**Best Practices:**
- Index fields used in `find()`, `sort()`, and `match` stages
- Use compound indexes for multi-field queries: `{ field1: 1, field2: 1 }`
- Index prefix must match query patterns

### 🔴 2. Over-Indexing (Too Many Indexes)

**Problem:**
```javascript
// 15 indexes on a collection with frequent writes!
db.users.getIndexes()
```

**Symptoms:**
- Slow writes (inserts, updates, deletes)
- High disk I/O
- Excessive index maintenance overhead

**Impact:**
- Each write must update ALL indexes
- 10 indexes = 10x index update overhead
- Wasted disk space and memory

**Solution:**
```javascript
// Audit index usage
db.users.aggregate([ { $indexStats: {} } ])

// Remove unused indexes
db.users.dropIndex("rarely_used_field_1")

// Use compound indexes instead of multiple single-field indexes
// Bad:  index1: {a:1}, index2: {b:1}, index3: {a:1, b:1}
// Good: index1: {a:1, b:1}  (covers all three patterns)
```

**Best Practices:**
- Review index usage monthly with `$indexStats`
- Drop indexes with zero accesses
- Use covered queries (query + projection entirely from index)
- Typical collection should have 3-7 indexes, not 15+

### 🔴 3. Inefficient Query Patterns

**Problem: Unbounded Queries**
```javascript
// Returns ALL users - could be millions!
db.users.find({})
```

**Solution:**
```javascript
// Always use limits and pagination
db.users.find({}).limit(100).skip(0)

// Better: Cursor-based pagination
db.users.find({ _id: { $gt: lastSeenId } }).limit(100)
```

**Problem: Regex Without Anchors**
```javascript
// Can't use index - full collection scan
db.users.find({ name: /john/ })
```

**Solution:**
```javascript
// Anchor at start - CAN use index
db.users.find({ name: /^john/i })

// Or use text search index
db.users.createIndex({ name: "text" })
db.users.find({ $text: { $search: "john" } })
```

**Problem: $nin and $ne Queries**
```javascript
// Can't efficiently use index
db.orders.find({ status: { $ne: "cancelled" } })
```

**Solution:**
```javascript
// Query for what you want, not what you don't
db.orders.find({ status: { $in: ["pending", "completed", "shipped"] } })
```

### 🔴 4. Large Documents and Array Growth

**Problem:**
```javascript
// Document keeps growing unbounded
{
  _id: 1,
  user: "john",
  logs: [
    // 10,000 log entries... keeps growing!
    { timestamp: "...", action: "..." },
    { timestamp: "...", action: "..." },
    // ... eventually hits 16MB limit or causes performance issues
  ]
}
```

**Symptoms:**
- Document size approaching 16MB limit
- Slow updates due to document relocation
- Memory pressure from loading large documents
- Inefficient array operations

**Solution:**
```javascript
// Option 1: Bucketing (time-series pattern)
{ _id: "2026-05-15", user: "john", logs: [/* today's logs only */] }

// Option 2: Separate collection
// users collection
{ _id: 1, user: "john" }
// user_logs collection
{ userId: 1, timestamp: "...", action: "..." }

// Option 3: Capped arrays with $slice
db.users.updateOne(
  { _id: 1 },
  { 
    $push: { 
      recentActivity: { 
        $each: [newActivity],
        $slice: -100  // Keep only last 100 items
      }
    }
  }
)
```

### 🔴 5. Inappropriate Read/Write Concerns

**Problem: Too Strict (Unnecessary Latency)**
```javascript
// Every write waits for majority acknowledgment
db.collection.insertOne(
  { ... },
  { writeConcern: { w: "majority", j: true } }
)
// Adds 10-50ms latency per write!
```

**Problem: Too Loose (Risk of Data Loss)**
```javascript
// Write not acknowledged - could be lost!
db.collection.insertOne(
  { ... },
  { writeConcern: { w: 0 } }
)
```

**Solution:**
```javascript
// Default (w: 1) is usually right - acknowledged by primary
db.collection.insertOne({ ... })

// Use majority only for critical data
db.financialTransactions.insertOne(
  { ... },
  { writeConcern: { w: "majority" } }
)

// Use w: 0 only for non-critical logs
db.analytics.insertOne(
  { ... },
  { writeConcern: { w: 0 } }
)
```

### 🔴 6. Reading from Secondaries Inappropriately

**Problem:**
```javascript
// Always reading from secondary - might see stale data!
db.collection.find({}).readPref("secondary")
```

**Issues:**
- **Replication lag**: Secondaries can be seconds (or minutes!) behind
- **Inconsistent reads**: Read your own write problem
- **Not actually reducing primary load**: Primary still handles all writes

**Solution:**
```javascript
// Default: Read from primary (consistent)
db.collection.find({})

// Use secondary ONLY for:
// 1. Analytics queries (staleness acceptable)
db.analytics.aggregate([...]).readPref("secondary")

// 2. Geographic distribution (read from nearest)
db.collection.find({}).readPref("nearest")

// 3. Offload read-heavy reporting
db.reports.find({}).readPref("secondaryPreferred")
```

### 🔴 7. Not Using Projection (Fetching Entire Documents)

**Problem:**
```javascript
// Fetches ALL fields including large arrays/nested objects
const user = db.users.findOne({ _id: 1 })
console.log(user.email)  // Only needed email!
```

**Impact:**
- Wasted bandwidth
- Wasted memory
- Slower query execution
- Application processes unnecessary data

**Solution:**
```javascript
// Only fetch what you need
const user = db.users.findOne(
  { _id: 1 },
  { projection: { email: 1, name: 1, _id: 0 } }
)

// Especially important with large fields
db.users.findOne(
  { _id: 1 },
  { projection: { profilePicture: 0, activityHistory: 0 } }  // Exclude large fields
)
```

### 🔴 8. Connection Pool Exhaustion

**Problem:**
```javascript
// Opening new connection for every request!
app.get('/users', (req, res) => {
  const client = new MongoClient(uri)
  await client.connect()  // ❌ Very expensive!
  // ... query ...
  await client.close()
})
```

**Symptoms:**
- Slow response times under load
- Connection timeouts
- "Too many connections" errors
- High connection churn

**Solution:**
```javascript
// Create ONE client at app startup
const client = new MongoClient(uri, {
  maxPoolSize: 50,      // Default: 100
  minPoolSize: 10,
  maxIdleTimeMS: 60000
})
await client.connect()  // Once at startup!

// Reuse connection throughout app lifetime
app.get('/users', async (req, res) => {
  const db = client.db('myapp')
  const users = await db.collection('users').find({}).toArray()
  res.json(users)
})
```

**Best Practices:**
- One connection pool per application instance
- Size pool based on concurrent operations (not total users)
- Monitor with `db.serverStatus().connections`

### 🔴 9. Not Monitoring and Profiling

**Problem:**
- No visibility into slow queries
- Don't know which indexes are used
- Can't identify bottlenecks

**Solution:**
```javascript
// 1. Enable query profiler (captures slow queries)
db.setProfilingLevel(1, { slowms: 100 })  // Log queries >100ms

// 2. Review slow queries
db.system.profile.find({ millis: { $gt: 100 } }).sort({ ts: -1 }).limit(10)

// 3. Use explain for query analysis
db.collection.find({ field: value }).explain("executionStats")

// 4. Monitor index usage
db.collection.aggregate([ { $indexStats: {} } ])

// 5. Check server stats
db.serverStatus()
```

### 🔴 10. Ignoring Document Growth Patterns

**Problem:**
```javascript
// Document starts small
{ _id: 1, name: "John", email: "john@example.com" }

// But grows over time with $push, $set
// MongoDB must relocate entire document on disk!
// Causes fragmentation and slower performance
```

**Solution:**
```javascript
// Pre-allocate space for expected growth
db.users.insertOne({
  _id: 1,
  name: "John",
  email: "john@example.com",
  preferences: {},           // Empty but present
  recentOrders: [],          // Empty array
  activityLog: []
})

// Use padding factor (older versions)
db.runCommand({
  collMod: "users",
  usePowerOf2Sizes: true
})
```

---

## Best Practices for Production

### Performance

✅ **Always use indexes for queries**
- Index fields in `find()`, `$match`, `sort()`
- Create compound indexes for multi-field queries
- Use covered queries when possible

✅ **Monitor index effectiveness**
- Use `explain()` to verify index usage
- Check `$indexStats` monthly
- Drop unused indexes

✅ **Limit result sets**
- Never fetch unbounded results
- Use pagination (cursor-based preferred)
- Apply reasonable limits (100-1000)

✅ **Use projections**
- Only fetch fields you need
- Exclude large fields when not needed

✅ **Optimize schema for access patterns**
- Embed frequently accessed together data
- Reference large or unbounded data
- Consider query patterns first, normalization second

### Reliability

✅ **Use replica sets (minimum 3 nodes)**
- Provides high availability
- Automatic failover
- Data redundancy

✅ **Configure appropriate write concerns**
- `w: 1` (default) for most operations
- `w: "majority"` for critical data
- `j: true` for durability guarantees

✅ **Implement connection pooling**
- Reuse connections
- Size pools appropriately
- Monitor connection health

✅ **Handle errors gracefully**
- Retry transient errors (network issues)
- Use change streams for real-time updates
- Implement circuit breakers

### Monitoring

✅ **Track key metrics**
- Query performance (slow query log)
- Index hit ratio
- Connection pool usage
- Replication lag
- Disk I/O and CPU

✅ **Set up alerts**
- Replication lag > 10 seconds
- Slow queries > 100ms
- Connection pool exhaustion
- Disk space < 20%

### Security

✅ **Enable authentication and authorization**
- Use role-based access control (RBAC)
- Create specific users per application
- Use strong passwords or x.509 certificates

✅ **Encrypt data**
- Enable encryption at rest
- Use TLS for network traffic
- Encrypt backups

✅ **Regular backups**
- Automated backups with `mongodump` or cloud provider
- Test restore procedures
- Keep backups in separate location

---

## Learn More

### Official MongoDB Documentation
- [MongoDB Manual](https://www.mongodb.com/docs/manual/)
- [Performance Best Practices](https://www.mongodb.com/docs/manual/administration/analyzing-mongodb-performance/)
- [Data Modeling Guide](https://www.mongodb.com/docs/manual/core/data-modeling-introduction/)
- [Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/)

---

## Next Steps

Ready to experiment? Run the MongoDB Performance Lab demos to see these concepts in action! 🚀
