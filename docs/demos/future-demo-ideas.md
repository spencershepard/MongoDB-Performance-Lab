# Future Demo Ideas - Video Game Data 🎮

Ideas for additional MongoDB performance demos using gaming domain concepts.

---

## Implemented Demos

✅ **Index Performance** - Range queries with/without indexes  
✅ **Over-Indexing** - Write performance degradation with too many indexes  
🚧 **Join Performance** - Embedded vs Referenced (Player Match History) - *In Progress*

---

## Backlog - Video Game Themed Demos

### 1. **Inventory System - Document Size Limits**

**Concept:** Player inventory with items

**Scenario:**
- **Embedded Approach:** Store all items in player document array
- **Referenced Approach:** Separate `items` collection

**What It Demonstrates:**
- When embedding hits 16MB document limit
- Impact of growing arrays on document relocation
- Query performance difference (single query vs $lookup)
- Update performance (modifying one item in 10k item array)

**Example Data:**
```javascript
// Embedded (can hit limits)
{ 
  playerId: "p123", 
  inventory: [ 
    { itemId: "sword_001", durability: 100, enchantments: [...] },
    // ... thousands of items
  ] 
}

// Referenced (scales better)
{ playerId: "p123", inventoryCount: 2543 }
{ playerId: "p123", itemId: "sword_001", slot: 1, durability: 100 }
```

---

### 2. **Leaderboard Rankings - Materialized Views**

**Concept:** Global player rankings

**Scenario:**
- **Real-time Calculation:** Aggregate across all players on every request
- **Materialized View:** Pre-computed rankings updated periodically
- **Indexed Collection:** Separate leaderboard collection with optimized indexes

**What It Demonstrates:**
- Cost of complex aggregations on large datasets
- Trade-offs: Real-time accuracy vs query performance
- Update strategies (incremental vs full refresh)
- Index-only queries (covered queries)

**Example Data:**
```javascript
// players collection (10M+ documents)
{ playerId: "p123", totalScore: 89234, wins: 523 }

// leaderboard collection (top 10k only)
{ rank: 1, playerId: "p999", totalScore: 2543234, lastUpdated: "..." }
```

---

### 3. **Guild/Clan Members - Array Query Performance**

**Concept:** Guild membership management

**Scenario:**
- **Embedded Members:** Store member list in guild document
- **Referenced Members:** Separate guild_members collection
- **Bidirectional:** Store both guildId in players AND members in guilds

**What It Demonstrates:**
- Query performance on large arrays (`$elemMatch`, `$in`)
- Index performance on array fields
- Array update operations ($push, $pull, $addToSet)
- Document size growth issues

**Example Data:**
```javascript
// Embedded approach
{ 
  guildId: "g123", 
  name: "Dragon Knights",
  members: [
    { playerId: "p001", role: "leader", joinedAt: "..." },
    // ... 1000s of members
  ]
}

// Referenced approach  
{ guildId: "g123", name: "Dragon Knights", memberCount: 2543 }
{ guildId: "g123", playerId: "p001", role: "leader", joinedAt: "..." }
```

---

### 4. **Achievement System - Sparse Indexes**

**Concept:** Player achievements tracking

**Scenario:**
- Track which players have earned specific achievements
- Most players haven't earned rare achievements
- Query patterns: "Who has X achievement?" vs "What achievements does player have?"

**What It Demonstrates:**
- Sparse indexes (only index documents with field present)
- Storage efficiency with sparse vs regular indexes
- Query performance on rare conditions
- Boolean field indexing strategies

**Example Data:**
```javascript
// Only 1% of players have "Legendary Hero" achievement
{ 
  playerId: "p123", 
  achievements: {
    firstWin: true,
    level50: true,
    legendaryHero: true  // Very rare!
  }
}

// Sparse index only stores legendary heroes
db.players.createIndex(
  { "achievements.legendaryHero": 1 }, 
  { sparse: true }
)
```

---

### 5. **Time-Series Data - Match History Bucketing**

**Concept:** Storing match/game session history

**Scenario:**
- **Single Collection:** All matches in one collection
- **Bucketed by Time:** Separate collections per month
- **Time-Series Collection:** MongoDB's native time-series collections (5.0+)

**What It Demonstrates:**
- Query performance on time-range queries
- TTL indexes for automatic data expiration
- Collection maintenance (dropping old collections)
- Aggregation performance across time periods

**Example Data:**
```javascript
// Time-series collection
db.createCollection("match_history", {
  timeseries: {
    timeField: "timestamp",
    metaField: "playerId",
    granularity: "minutes"
  }
})

{ 
  timestamp: ISODate("2026-05-15T10:30:00Z"),
  playerId: "p123",
  matchId: "m001",
  kills: 12,
  deaths: 3,
  duration: 1847  // seconds
}
```

---

### 6. **Compound Indexes - Multi-Field Queries**

**Concept:** Filtering matches by multiple criteria

**Scenario:**
- Query patterns: "Recent wins by player", "High-kill matches in timeframe"
- Compare single-field indexes vs compound indexes
- Index prefix usage

**What It Demonstrates:**
- Compound index performance vs multiple single-field indexes
- Index prefix queries (using part of compound index)
- Index intersection
- Sort optimization with indexes

**Example Queries:**
```javascript
// Needs compound index: { playerId: 1, timestamp: -1 }
db.matches.find({ playerId: "p123" }).sort({ timestamp: -1 })

// Needs compound index: { result: 1, kills: -1 }
db.matches.find({ result: "win" }).sort({ kills: -1 })

// Can use prefix of first index
db.matches.find({ playerId: "p123" })
```

---

### 7. **Geospatial Queries - Server Location Matching**

**Concept:** Matchmaking based on server location

**Scenario:**
- Find players near specific game servers
- Region-based matchmaking
- Proximity searches

**What It Demonstrates:**
- 2dsphere indexes for geospatial queries
- `$near`, `$geoWithin` query performance
- Use case for specialized index types

**Example Data:**
```javascript
{
  playerId: "p123",
  currentServer: "us-east-1",
  location: {
    type: "Point",
    coordinates: [-73.935242, 40.730610]  // NYC
  }
}

// Find players within 500km
db.players.find({
  location: {
    $near: {
      $geometry: { type: "Point", coordinates: [-74.0060, 40.7128] },
      $maxDistance: 500000  // meters
    }
  }
})
```

---

## Implementation Priority

**High Priority:**
1. Join Performance (Player Match History) - *In Progress*
2. Inventory System (Document Size Limits) - Practical and common issue
3. Leaderboard Rankings (Materialized Views) - Real-world pattern

**Medium Priority:**
4. Guild Members (Array Query Performance)
5. Achievement System (Sparse Indexes)
6. Compound Indexes (Multi-Field Queries)

**Lower Priority:**
7. Time-Series Data (Match History Bucketing) - Advanced feature
8. Geospatial Queries (Server Location) - Specialized use case

---

## Notes

- All demos should follow the existing pattern: load data → benchmark baseline → apply optimization → benchmark again → compare
- Include educational markdown docs in `docs/demos/` for each
- Use consistent collection naming: `players`, `matches`, `guilds`, `items`, etc.
- Generate realistic gaming data distributions (follow Pareto principle - most players are casual, few are hardcore)
- Target 10k-100k documents for meaningful performance comparisons
