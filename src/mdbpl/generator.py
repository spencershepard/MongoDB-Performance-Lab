"""Python-native document generator — replaces YCSB for test data loading."""

import json
import random
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import MongoClient


@dataclass
class FieldSpec:
    name: str
    type: str  # "string" | "int" | "float" | "date" | "bool" | "choice"
    length: int = 20        # string: character count
    min_val: float = 0      # int/float: lower bound (inclusive)
    max_val: float = 1_000_000  # int/float: upper bound (exclusive)
    choices: List[Any] = field(default_factory=list)  # type="choice": pool to sample
    sequential: bool = False  # if True, value equals the document's insertion index


@dataclass
class SchemaSpec:
    name: str
    fields: List[FieldSpec]  # _id is always ObjectId; list excludes it


class DocumentGenerator:
    _CHARS = string.ascii_lowercase + string.digits

    def __init__(self, schema: SchemaSpec, record_count: int) -> None:
        self._schema = schema
        self._record_count = record_count

    def generate(self, index: int) -> Dict[str, Any]:
        doc: Dict[str, Any] = {"_id": ObjectId()}
        for spec in self._schema.fields:
            doc[spec.name] = self._value(spec, index)
        return doc

    def generate_batch(self, start: int, n: int) -> List[Dict[str, Any]]:
        return [self.generate(start + i) for i in range(n)]

    def _value(self, spec: FieldSpec, index: int) -> Any:
        if spec.sequential:
            return index
        t = spec.type
        if t == "string":
            return "".join(random.choices(self._CHARS, k=spec.length))
        if t == "int":
            return random.randint(int(spec.min_val), int(spec.max_val) - 1)
        if t == "float":
            return round(random.uniform(spec.min_val, spec.max_val), 2)
        if t == "bool":
            return random.random() < 0.5
        if t == "date":
            now = datetime.now(tz=timezone.utc)
            delta = timedelta(seconds=random.randint(0, 365 * 2 * 24 * 3600))
            return now - delta
        if t == "choice":
            return random.choice(spec.choices)
        raise ValueError(f"Unknown field type: {t!r}")


# ---------------------------------------------------------------------------
# Built-in presets
# ---------------------------------------------------------------------------

SCHEMA_PRESETS: Dict[str, SchemaSpec] = {
    "default": SchemaSpec(
        name="default",
        fields=[
            FieldSpec("field0", "string", length=100),
            FieldSpec("field1", "string", length=100),
            FieldSpec("field2", "string", length=100),
            FieldSpec("field3", "string", length=100),
            FieldSpec("field4", "string", length=100),
            FieldSpec("field5", "string", length=100),
            FieldSpec("field6", "string", length=100),
            FieldSpec("field7", "string", length=100),
            FieldSpec("field8", "string", length=100),
            FieldSpec("field9", "string", length=100),
            FieldSpec("score", "int", sequential=True),
        ],
    ),
    "ecommerce": SchemaSpec(
        name="ecommerce",
        fields=[
            FieldSpec("customerId", "string", length=16),
            FieldSpec("amount", "float", min_val=1.0, max_val=5000.0),
            FieldSpec("status", "choice", choices=["pending", "processing", "shipped", "delivered", "cancelled"]),
            FieldSpec("region", "choice", choices=["us-east", "us-west", "eu-west", "eu-central", "ap-southeast"]),
            FieldSpec("productId", "string", length=12),
            FieldSpec("createdAt", "date"),
            FieldSpec("score", "int", sequential=True),
        ],
    ),
    "iot": SchemaSpec(
        name="iot",
        fields=[
            FieldSpec("deviceId", "string", length=16),
            FieldSpec("sensorType", "choice", choices=["temperature", "humidity", "pressure", "vibration", "current"]),
            FieldSpec("value", "float", min_val=0.0, max_val=100.0),
            FieldSpec("unit", "choice", choices=["celsius", "percent", "hpa", "mm/s", "amps"]),
            FieldSpec("timestamp", "date"),
            FieldSpec("score", "int", sequential=True),
        ],
    ),
    "events": SchemaSpec(
        name="events",
        fields=[
            FieldSpec("userId", "string", length=16),
            FieldSpec("eventType", "choice", choices=["click", "view", "purchase", "signup", "logout", "search"]),
            FieldSpec("sessionId", "string", length=24),
            FieldSpec("page", "choice", choices=["/home", "/product", "/cart", "/checkout", "/account", "/search"]),
            FieldSpec("timestamp", "date"),
            FieldSpec("score", "int", sequential=True),
        ],
    ),
    "videogame": SchemaSpec(
        name="videogame",
        fields=[
            FieldSpec("playerId", "string", length=16),
            FieldSpec("username", "string", length=12),
            FieldSpec("level", "int", min_val=1, max_val=101),
            FieldSpec("xp", "int", min_val=0, max_val=1_000_000),
            FieldSpec("rank", "choice", choices=["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "Grandmaster"]),
            FieldSpec("region", "choice", choices=["NA", "EU", "APAC", "SA", "OCE"]),
            FieldSpec("character", "choice", choices=["Warrior", "Mage", "Rogue", "Paladin", "Ranger", "Necromancer", "Druid", "Monk"]),
            FieldSpec("weaponPrimary", "choice", choices=["Sword", "Staff", "Bow", "Axe", "Dagger", "Wand", "Hammer", "Spear"]),
            FieldSpec("gamesPlayed", "int", min_val=0, max_val=10_000),
            FieldSpec("wins", "int", min_val=0, max_val=5_000),
            FieldSpec("kills", "int", min_val=0, max_val=100_000),
            FieldSpec("deaths", "int", min_val=0, max_val=50_000),
            FieldSpec("assists", "int", min_val=0, max_val=80_000),
            FieldSpec("headshots", "int", min_val=0, max_val=50_000),
            FieldSpec("kdr", "float", min_val=0.0, max_val=10.0),
            FieldSpec("winRate", "float", min_val=0.0, max_val=1.0),
            FieldSpec("avgMatchDuration", "int", min_val=300, max_val=3_600),
            FieldSpec("lastSeen", "date"),
            FieldSpec("accountCreated", "date"),
            FieldSpec("score", "int", sequential=True),
        ],
    ),
}


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_generated_data(
    mongodb_uri: str,
    record_count: int,
    schema: SchemaSpec,
    database: str = "perflab",
    collection: str = "usertable",
    drop_existing: bool = True,
    batch_size: int = 1000,
) -> None:
    """Generate and insert documents into MongoDB, replacing load_ycsb_data()."""
    client = MongoClient(mongodb_uri)
    coll = client[database][collection]

    if drop_existing:
        coll.drop()
        print("✓ Collection dropped")
        print()

    gen = DocumentGenerator(schema, record_count)
    inserted = 0
    report_every = max(batch_size, 10_000 - (10_000 % batch_size))

    print(f"Generating {record_count:,} documents (schema: {schema.name})...")
    while inserted < record_count:
        n = min(batch_size, record_count - inserted)
        docs = gen.generate_batch(inserted, n)
        coll.insert_many(docs, ordered=False)
        inserted += n
        if inserted % report_every == 0 or inserted == record_count:
            pct = inserted / record_count * 100
            print(f"  {inserted:,} / {record_count:,} ({pct:.0f}%)")

    client.close()
    print(f"✓ Loaded {inserted:,} documents into {database}.{collection}")


def schema_from_json(path: str) -> SchemaSpec:
    """Load a SchemaSpec from a JSON file."""
    data = json.loads(Path(path).read_text())
    fields = [FieldSpec(**f) for f in data["fields"]]
    return SchemaSpec(name=data["name"], fields=fields)


def resolve_schema(schema_arg: str) -> SchemaSpec:
    """Return a SchemaSpec from a preset name or JSON file path."""
    if schema_arg in SCHEMA_PRESETS:
        return SCHEMA_PRESETS[schema_arg]
    if Path(schema_arg).exists():
        return schema_from_json(schema_arg)
    raise ValueError(
        f"Unknown schema {schema_arg!r}. "
        f"Available presets: {', '.join(SCHEMA_PRESETS)}"
    )
