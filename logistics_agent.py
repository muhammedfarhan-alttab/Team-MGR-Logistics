"""
Agent Colosseum - Logistics Track - Task 1 (Integration)
=========================================================

Purchased Feature Store items used by this agent (and ONLY these):
    - Address Resolver      -> AddressResolver class
    - Distance Matrix Cache -> DistanceMatrixCache class

Nothing else from the marketplace is used in this file. No external
network calls, no third-party packages beyond the Python standard
library, so there is nothing here that wasn't paid for.

Responsibilities of Task 1:
    1. Read raw delivery data from a track data source (here: a JSON/CSV
       file or an in-memory list of dicts, so it works with whatever
       feed the domain store hands us).
    2. Normalize every record into ONE internal shape (`DeliveryRecord`),
       regardless of how messy or inconsistent the source fields were.
    3. Resolve addresses via the Address Resolver, handling invalid /
       empty / malformed addresses without ever inventing coordinates.
    4. Compute pairwise distances only for successfully resolved
       addresses via the Distance Matrix Cache, so repeated lookups
       are cheap and consistent.

Ground rule VII compliance:
    Any free-text field coming from the data (e.g. `notes`, `special_instructions`)
    is treated as inert data. It is stored verbatim for human/UI display
    and is NEVER parsed for commands, NEVER executed, and NEVER allowed
    to influence control flow. See `_sanitize_free_text` and the comment
    block in `normalize_record`.

Integration seams still pending official marketplace documentation
(intentionally NOT implemented with invented interfaces):
    - Fleet Watcher: `AssignableJob.vehicle_capacity_required` is currently
      a passthrough of whatever the source record states. No live vehicle
      availability lookup is performed.
    - Distance Matrix Cache travel-time: `AssignableJob.travel_time_minutes`
      is left as None. No estimate is substituted for a real lookup.
    - File I/O Module: `load_delivery_data` is the ingestion boundary
      where the real queue-pull interface will eventually replace the
      current local file/list stand-in; its `str | list[dict] -> list[dict]`
      contract is designed to make that swap a one-function change.
    - Route Optimiser: intentionally unused. Task 1 costs individual
      candidate assignments; multi-job route sequencing is Task 2 scope.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Optional


# ---------------------------------------------------------------------------
# 1. Normalized internal shape
# ---------------------------------------------------------------------------

class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"          # address matched, lat/lon available
    INVALID = "invalid"            # address present but not resolvable
    EMPTY = "empty"                # address field missing / blank
    MALFORMED_INPUT = "malformed"  # source record itself was broken (wrong type etc.)


@dataclass
class DeliveryRecord:
    """The single internal shape every record gets normalized into,
    no matter which of the messy source shapes it started as."""

    record_id: str
    customer_name: str
    raw_address: Optional[str]
    normalized_address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    resolution_status: ResolutionStatus = ResolutionStatus.EMPTY
    resolution_notes: str = ""
    # Free-text field from the source data. Stored as inert data only.
    # NEVER interpreted as instructions -- see module docstring, rule VII.
    package_notes: str = ""

    def is_resolved(self) -> bool:
        return self.resolution_status == ResolutionStatus.RESOLVED


# ---------------------------------------------------------------------------
# 1b. Assignable Job (additive pickup + drop model, Task 1 output schema)
# ---------------------------------------------------------------------------
#
# This sits alongside DeliveryRecord (unchanged, still produced) rather than
# replacing it. DeliveryRecord models one resolved location; AssignableJob
# models one candidate assignment with a pickup leg AND a drop leg, which is
# what Task 1 actually asks for. Both pickup and drop are resolved
# independently through the existing AddressResolver -- neither leg is ever
# guessed, and a job is only ever `assignable=True` when BOTH legs resolved.
#
# Two fields are intentionally left as clean integration seams rather than
# invented:
#   - travel_time_minutes: no official Distance Matrix Cache travel-time
#     interface has been provided. We do NOT estimate this from distance
#     and a made-up speed and pass it off as a lookup -- that would
#     misrepresent an estimate as real travel-time data. It is left as
#     None until that interface is documented.
#   - vehicle_capacity_required: no official Fleet Watcher interface has
#     been provided. This field is a passthrough of whatever capacity
#     figure the source record itself states -- never a live fleet
#     availability check, never a fabricated default vehicle class.

TRAVEL_TIME_PENDING_NOTE = (
    "travel_time_minutes is not populated: no official Distance Matrix "
    "Cache travel-time interface has been provided yet. This field is "
    "reserved for that data once documented. It is intentionally left as "
    "None rather than estimated, and must never be treated as a real "
    "travel-time lookup."
)

VEHICLE_CAPACITY_PENDING_NOTE = (
    "vehicle_capacity_required is a passthrough of the source record's "
    "stated capacity need only. It is NOT a live Fleet Watcher lookup -- "
    "no Fleet Watcher interface has been provided yet, so no vehicle "
    "availability or assignment decision is made against real fleet data "
    "here."
)


@dataclass
class AssignableJob:
    """
    The fixed-schema, normalized output of Task 1: one candidate assignment
    with independently-resolved pickup and drop legs, a route distance
    (when both legs are resolved), and explicit flagging when either leg
    isn't resolvable -- never a force-assigned job.
    """

    job_id: str
    customer_name: str

    pickup_raw_address: Optional[str]
    pickup_normalized_address: Optional[str]
    pickup_lat: Optional[float]
    pickup_lon: Optional[float]
    pickup_status: ResolutionStatus

    drop_raw_address: Optional[str]
    drop_normalized_address: Optional[str]
    drop_lat: Optional[float]
    drop_lon: Optional[float]
    drop_status: ResolutionStatus

    # Route distance for the pickup -> drop leg specifically (not the
    # cross-job pairwise matrix). None whenever either leg is unresolved.
    distance_km: Optional[float] = None

    # Integration seam -- see module notes above. Deliberately None, not
    # an estimate, until the real interface exists.
    travel_time_minutes: Optional[float] = None
    travel_time_notes: str = TRAVEL_TIME_PENDING_NOTE

    # Integration seam -- see module notes above. Passthrough only.
    vehicle_capacity_required: Optional[Any] = None
    vehicle_capacity_notes: str = VEHICLE_CAPACITY_PENDING_NOTE

    assignable: bool = False
    flag_reason: Optional[str] = None

    # Free-text field from source data. Stored as inert data only.
    # NEVER interpreted as instructions -- see module docstring, rule VII.
    package_notes: str = ""

    def is_assignable(self) -> bool:
        return self.assignable


# ---------------------------------------------------------------------------
# 2. Address Resolver  (purchased feature)
# ---------------------------------------------------------------------------

class AddressResolver:
    """
    Wraps address normalization + geocoding.

    In this environment there's no outbound network access, so the
    resolver backend is a local gazetteer standing in for whatever
    real geocoding service the domain Feature Store would proxy to.
    The *interface* (`resolve`) is what the rest of the agent depends
    on, so swapping the gazetteer lookup for a real HTTP geocoder later
    is a one-function change, not a rewrite.

    Design choices that matter for the "don't invent data" requirement:
      - If an address can't be matched with reasonable confidence, we
        return INVALID with lat/lon left as None. We never guess.
      - Every resolution (hit or miss) is cached, since re-resolving
        the same address twice would burn the paid feature for nothing.
    """

    _ABBREVIATIONS = {
        r"\bst\b": "street",
        r"\bst\.\b": "street",
        r"\bave\b": "avenue",
        r"\bave\.\b": "avenue",
        r"\brd\b": "road",
        r"\brd\.\b": "road",
        r"\bblvd\b": "boulevard",
        r"\bdr\b": "drive",
        r"\bapt\b": "apartment",
        r"\bste\b": "suite",
    }

    # Stand-in for the resolver backend's known-good locations.
    # Keyed by a normalized "city, region" signature -> (lat, lon).
    _GAZETTEER = {
        "chennai, tn": (13.0827, 80.2707),
        "bengaluru, ka": (12.9716, 77.5946),
        "mumbai, mh": (19.0760, 72.8777),
        "delhi, dl": (28.7041, 77.1025),
        "hyderabad, tg": (17.3850, 78.4867),
        "pune, mh": (18.5204, 73.8567),
        "kolkata, wb": (22.5726, 88.3639),
        "ahmedabad, gj": (23.0225, 72.5714),
    }

    def __init__(self) -> None:
        self._cache: dict[str, tuple[ResolutionStatus, str, Optional[tuple[float, float]], str]] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    @staticmethod
    def _clean_whitespace(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _expand_abbreviations(self, text: str) -> str:
        out = text.lower()
        for pattern, replacement in self._ABBREVIATIONS.items():
            out = re.sub(pattern, replacement, out)
        return out

    def normalize(self, raw_address: str) -> str:
        """Whitespace + abbreviation normalization. Does not validate."""
        cleaned = self._clean_whitespace(raw_address)
        expanded = self._expand_abbreviations(cleaned)
        # Title-case for a consistent, human-readable normalized form.
        return expanded.title()

    def _extract_city_region_key(self, normalized_address: str) -> Optional[str]:
        """
        Very small heuristic parser: looks for '<city>, <2-letter region>'
        anywhere in the normalized address. Returns the gazetteer key or
        None if no such signature is found.
        """
        match = re.search(r"([A-Za-z][A-Za-z\s]*),\s*([A-Za-z]{2})\b", normalized_address)
        if not match:
            return None
        city = match.group(1).strip().lower()
        region = match.group(2).strip().lower()
        return f"{city}, {region}"

    def resolve(self, raw_address: Optional[str]) -> tuple[ResolutionStatus, str, Optional[tuple[float, float]], str]:
        """
        Returns (status, normalized_address, (lat, lon) or None, notes).
        Never raises on bad input -- bad input is a valid, expected case.
        """
        if raw_address is None:
            return ResolutionStatus.EMPTY, "", None, "address field missing"

        if not isinstance(raw_address, str):
            # Defensive: source data claimed to be an address but wasn't a string.
            return ResolutionStatus.MALFORMED_INPUT, "", None, f"expected string, got {type(raw_address).__name__}"

        if raw_address.strip() == "":
            return ResolutionStatus.EMPTY, "", None, "address field blank"

        if raw_address in self._cache:
            self.cache_hits += 1
            return self._cache[raw_address]

        self.cache_misses += 1
        normalized = self.normalize(raw_address)
        key = self._extract_city_region_key(normalized)

        if key and key in self._GAZETTEER:
            lat, lon = self._GAZETTEER[key]
            result = (ResolutionStatus.RESOLVED, normalized, (lat, lon), "matched gazetteer entry")
        else:
            result = (ResolutionStatus.INVALID, normalized, None, "no confident match in resolver backend")

        self._cache[raw_address] = result
        return result


# ---------------------------------------------------------------------------
# 3. Distance Matrix Cache  (purchased feature)
# ---------------------------------------------------------------------------

class DistanceMatrixCache:
    """
    Caches pairwise great-circle distances between resolved coordinates.
    Only ever computes a distance between two RESOLVED points -- it's the
    caller's job (the orchestrator, Task 2) to have already filtered out
    unresolved records.
    """

    EARTH_RADIUS_KM = 6371.0

    def __init__(self) -> None:
        self._cache: dict[tuple, float] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(id_a: str, coord_a: tuple[float, float], id_b: str, coord_b: tuple[float, float]) -> tuple:
        # Symmetric key so (A, B) and (B, A) hit the same cache entry.
        pair = sorted([(id_a, coord_a), (id_b, coord_b)], key=lambda p: p[0])
        return (pair[0][0], pair[1][0])

    def _haversine_km(self, a: tuple[float, float], b: tuple[float, float]) -> float:
        lat1, lon1 = map(math.radians, a)
        lat2, lon2 = map(math.radians, b)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * self.EARTH_RADIUS_KM * math.asin(math.sqrt(h))

    def get_distance(self, id_a: str, coord_a: tuple[float, float], id_b: str, coord_b: tuple[float, float]) -> float:
        key = self._key(id_a, coord_a, id_b, coord_b)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1
        distance = self._haversine_km(coord_a, coord_b)
        self._cache[key] = distance
        return distance

    def build_matrix(self, records: list[DeliveryRecord]) -> dict[tuple[str, str], Optional[float]]:
        """
        Builds a distance matrix across resolved records only.
        Unresolved records are skipped (not zero-filled, not guessed).
        """
        resolved = [r for r in records if r.is_resolved()]
        matrix: dict[tuple[str, str], Optional[float]] = {}
        for i, r1 in enumerate(resolved):
            for r2 in resolved[i + 1:]:
                d = self.get_distance(r1.record_id, (r1.lat, r1.lon), r2.record_id, (r2.lat, r2.lon))
                matrix[(r1.record_id, r2.record_id)] = round(d, 2)
        return matrix


# ---------------------------------------------------------------------------
# 4. Ingestion + normalization pipeline
# ---------------------------------------------------------------------------

_MISSING = object()  # sentinel: distinguishes "key absent" from "key present but falsy (0, '', False)"


def _first_present(raw: dict, keys: tuple[str, ...]) -> Any:
    """
    Returns the value of the first key in `keys` that exists in `raw` AND
    is not None. Presence is checked explicitly (`k in raw`), not by
    truthiness -- so a legitimate falsy value like an id of 0, or a
    deliberately blank string, is returned as-is instead of being
    silently skipped in favor of a later fallback key.
    Returns the `_MISSING` sentinel if none of the keys are present.
    """
    for k in keys:
        if k in raw and raw[k] is not None:
            return raw[k]
    return _MISSING


def _ensure_unique_id(candidate: str, seen_ids: set[str]) -> str:
    """
    Single source of truth for producing a unique record_id. Used both
    for normal records (candidate may be blank if no id field was found)
    and for malformed/non-dict records (candidate is always passed as "").

    Guarantees:
      - every id returned by this function is immediately reserved in
        `seen_ids` before returning, so two calls in a row (e.g. two
        malformed records back to back) can never collide.
      - a blank/empty candidate gets a generated "unknown-N" id.
      - a candidate that collides with something already seen gets a
        "-dupN" suffix, looped until the result is actually unique.
    """
    if not candidate:
        n = len(seen_ids) + 1
        candidate = f"unknown-{n}"
        while candidate in seen_ids:
            n += 1
            candidate = f"unknown-{n}"
    elif candidate in seen_ids:
        n = 1
        deduped = f"{candidate}-dup{n}"
        while deduped in seen_ids:
            n += 1
            deduped = f"{candidate}-dup{n}"
        candidate = deduped

    seen_ids.add(candidate)
    return candidate


def _sanitize_free_text(value: Any) -> str:
    """
    Coerces any free-text field to a plain, inert string for storage/display.
    This function's ONLY job is safe stringification -- it must never be
    extended to interpret, execute, or branch on the content (ground rule VII).
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value)
    return value


def load_delivery_data(source: str | list[dict]) -> list[dict]:
    """
    Accepts either a path to a .json file, a path to a .csv file, or an
    already-in-memory list of dicts (useful for tests / the Arcade / demos).
    Returns [] on an empty or missing source rather than raising, since
    "no data available" is an expected edge case, not a fatal error.
    """
    if isinstance(source, list):
        return source

    if not isinstance(source, str):
        return []

    if source.endswith(".json"):
        try:
            with open(source, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            # OSError covers FileNotFoundError, PermissionError, IsADirectoryError, etc.
            # ValueError covers json.JSONDecodeError and UnicodeDecodeError (bad encoding).
            return []
        except Exception:
            # Last-resort safety net at the ingestion boundary: an unanticipated
            # file problem should degrade to "no data" rather than crash the
            # whole pipeline. This broad catch is intentionally scoped to this
            # one I/O boundary, not used as a general practice elsewhere.
            return []
        return data if isinstance(data, list) else []

    if source.endswith(".csv"):
        import csv
        try:
            with open(source, newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))
        except (OSError, ValueError, csv.Error):
            # OSError: missing/unreadable file. ValueError: bad encoding.
            # csv.Error: malformed CSV structure.
            return []
        except Exception:
            # Same intentional last-resort safety net as above.
            return []

    return []


def normalize_record(raw: dict, resolver: AddressResolver, seen_ids: set[str]) -> DeliveryRecord:
    """
    Converts one raw, possibly-messy source dict into a DeliveryRecord.
    Handles: missing fields, wrong types, duplicate IDs, and addresses
    that fail resolution -- without raising and without inventing data.
    """
    id_candidate = _first_present(raw, ("id", "record_id", "order_id"))
    id_str = "" if id_candidate is _MISSING else str(id_candidate).strip()
    record_id = _ensure_unique_id(id_str, seen_ids)

    name_candidate = _first_present(raw, ("customer_name", "customer", "name"))
    if name_candidate is _MISSING:
        customer_name = "Unknown Customer"
    elif isinstance(name_candidate, str):
        customer_name = name_candidate
    else:
        customer_name = str(name_candidate)

    address_candidate = _first_present(raw, ("address", "delivery_address", "addr"))
    raw_address = None if address_candidate is _MISSING else address_candidate

    status, normalized_address, coords, notes = resolver.resolve(raw_address)

    lat, lon = (coords if coords else (None, None))

    # `notes` / `special_instructions` come straight from source data.
    # They are stored verbatim as inert text -- never parsed as commands.
    notes_candidate = _first_present(raw, ("notes", "special_instructions"))
    package_notes = _sanitize_free_text(None if notes_candidate is _MISSING else notes_candidate)

    return DeliveryRecord(
        record_id=record_id,
        customer_name=customer_name,
        raw_address=raw_address if isinstance(raw_address, str) else None,
        normalized_address=normalized_address or None,
        lat=lat,
        lon=lon,
        resolution_status=status,
        resolution_notes=notes,
        package_notes=package_notes,
    )


def normalize_records(raw_records: Iterable[dict], resolver: AddressResolver) -> list[DeliveryRecord]:
    seen_ids: set[str] = set()
    normalized = []
    for raw in raw_records:
        if not isinstance(raw, dict):
            # A record that isn't even a dict -- log it as malformed, skip cleanly.
            # _ensure_unique_id reserves the generated id in seen_ids immediately,
            # so a second malformed record right after this one gets its own id
            # instead of colliding with this one.
            normalized.append(
                DeliveryRecord(
                    record_id=_ensure_unique_id("", seen_ids),
                    customer_name="Unknown Customer",
                    raw_address=None,
                    resolution_status=ResolutionStatus.MALFORMED_INPUT,
                    resolution_notes=f"record was {type(raw).__name__}, not a dict",
                )
            )
            continue
        normalized.append(normalize_record(raw, resolver, seen_ids))
    return normalized


def _extract_capacity(raw: dict) -> Any:
    """
    Passthrough extraction only -- see AssignableJob.vehicle_capacity_notes.
    Does not validate, convert units, or check against real fleet data.
    """
    candidate = _first_present(raw, ("vehicle_capacity_required", "capacity_required", "capacity"))
    return None if candidate is _MISSING else candidate


def build_jobs(
    records: list[DeliveryRecord],
    raw_records: list,
    resolver: AddressResolver,
    distance_cache: DistanceMatrixCache,
    default_pickup_address: Optional[str] = None,
) -> list[AssignableJob]:
    """
    Builds one AssignableJob per raw record, pairing a freshly-resolved
    pickup leg with the drop leg that `records` already resolved.

    Deliberately reuses `records` for the drop leg instead of calling
    resolver.resolve() a second time on the same address -- re-resolving
    would double-count the AddressResolver's cache hit/miss counters for
    every call site that already depends on them (see test_reusable_cache.py).

    `records` and `raw_records` must be the same length and in the same
    order, which holds here because both are derived from iterating the
    same `raw_records` list one item at a time (normalize_records never
    skips or reorders an item, including malformed ones).

    `default_pickup_address`, if given, is used only when a record has no
    per-record pickup field at all -- it is never used to override an
    explicit (even blank) pickup field, matching the same
    presence-not-truthiness rule `_first_present` already applies
    elsewhere in this module.
    """
    jobs: list[AssignableJob] = []

    for record, raw in zip(records, raw_records):
        if not isinstance(raw, dict):
            # Mirrors the MALFORMED_INPUT handling normalize_records already
            # applied to build `record` for this same item.
            pickup_status = ResolutionStatus.MALFORMED_INPUT
            pickup_norm, pickup_coords, pickup_notes = "", None, record.resolution_notes
            pickup_raw = None
        else:
            pickup_candidate = _first_present(raw, ("pickup_address", "pickup", "origin"))
            pickup_raw = default_pickup_address if pickup_candidate is _MISSING else pickup_candidate
            pickup_status, pickup_norm, pickup_coords, pickup_notes = resolver.resolve(pickup_raw)

        pickup_lat, pickup_lon = (pickup_coords if pickup_coords else (None, None))

        assignable = (
            pickup_status == ResolutionStatus.RESOLVED
            and record.resolution_status == ResolutionStatus.RESOLVED
        )

        flag_reason = None
        if not assignable:
            reasons = []
            if pickup_status != ResolutionStatus.RESOLVED:
                reasons.append(f"pickup {pickup_status.value}: {pickup_notes}")
            if record.resolution_status != ResolutionStatus.RESOLVED:
                reasons.append(f"drop {record.resolution_status.value}: {record.resolution_notes}")
            flag_reason = "; ".join(reasons)

        capacity = _extract_capacity(raw) if isinstance(raw, dict) else None

        job = AssignableJob(
            job_id=record.record_id,
            customer_name=record.customer_name,
            pickup_raw_address=pickup_raw if isinstance(pickup_raw, str) else None,
            pickup_normalized_address=pickup_norm or None,
            pickup_lat=pickup_lat,
            pickup_lon=pickup_lon,
            pickup_status=pickup_status,
            drop_raw_address=record.raw_address,
            drop_normalized_address=record.normalized_address,
            drop_lat=record.lat,
            drop_lon=record.lon,
            drop_status=record.resolution_status,
            vehicle_capacity_required=capacity,
            assignable=assignable,
            flag_reason=flag_reason,
            package_notes=record.package_notes,
        )

        # Route distance is only ever computed for fully-resolved jobs --
        # never fabricated for a flagged one. Uses distinct cache keys
        # (":pickup" / ":drop" suffixes) so this never collides with the
        # cross-job pairwise matrix DistanceMatrixCache also serves.
        if assignable:
            d = distance_cache.get_distance(
                f"{job.job_id}::pickup", (pickup_lat, pickup_lon),
                f"{job.job_id}::drop", (record.lat, record.lon),
            )
            job.distance_km = round(d, 2)

        jobs.append(job)

    return jobs


# ---------------------------------------------------------------------------
# 5. Pipeline summary / report
# ---------------------------------------------------------------------------

def summarize(records: list[DeliveryRecord], resolver: AddressResolver, distance_cache: DistanceMatrixCache) -> dict:
    counts: dict[str, int] = {}
    for r in records:
        counts[r.resolution_status.value] = counts.get(r.resolution_status.value, 0) + 1

    return {
        "total_records": len(records),
        "status_counts": counts,
        "resolver_cache_hits": resolver.cache_hits,
        "resolver_cache_misses": resolver.cache_misses,
        "distance_cache_hits": distance_cache.hits,
        "distance_cache_misses": distance_cache.misses,
    }


def run_pipeline(
    source: str | list[dict],
    resolver: Optional[AddressResolver] = None,
    distance_cache: Optional[DistanceMatrixCache] = None,
    default_pickup_address: Optional[str] = None,
) -> dict:
    """
    End-to-end Task 1 pipeline: ingest -> normalize -> resolve -> distance matrix
    -> assignable jobs.

    `resolver` and `distance_cache` are optional. Pass in existing instances
    to reuse their caches across multiple calls (e.g. from a Task 2
    orchestrator polling the same queue repeatedly) -- otherwise fresh
    instances are created each call, exactly as before. This keeps every
    existing call site (e.g. `run_pipeline(some_source)`) working unchanged.

    `default_pickup_address` is optional (e.g. a configured depot address).
    When given, it's used only for records with no per-record pickup field
    at all -- never to override an explicit pickup field, and never applied
    silently in a way that would make an unresolvable pickup look resolved.

    The return dict keeps every existing key (`records`, `distance_matrix`,
    `report`) unchanged, and adds one new key: `jobs`, a list of
    AssignableJob -- the fixed-schema Task 1 output.
    """
    if resolver is None:
        resolver = AddressResolver()
    if distance_cache is None:
        distance_cache = DistanceMatrixCache()

    raw_records = load_delivery_data(source)
    records = normalize_records(raw_records, resolver)
    matrix = distance_cache.build_matrix(records)
    report = summarize(records, resolver, distance_cache)

    jobs = build_jobs(records, raw_records, resolver, distance_cache, default_pickup_address=default_pickup_address)
    report["assignable_job_count"] = sum(1 for j in jobs if j.assignable)
    report["flagged_job_count"] = sum(1 for j in jobs if not j.assignable)

    return {
        "records": records,
        "distance_matrix": matrix,
        "report": report,
        "jobs": jobs,
    }


class LogisticsAgent:
    """
    Long-lived wrapper holding one AddressResolver and one DistanceMatrixCache
    for the agent's whole lifetime, so repeated `.process()` calls actually
    benefit from the paid caching features instead of resetting them every
    call. `run_pipeline()` itself still works standalone for one-off use.
    """

    def __init__(self) -> None:
        self.resolver = AddressResolver()
        self.distance_cache = DistanceMatrixCache()

    def process(self, source: str | list[dict]) -> dict:
        return run_pipeline(source, resolver=self.resolver, distance_cache=self.distance_cache)
