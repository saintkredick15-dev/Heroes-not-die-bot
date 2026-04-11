from __future__ import annotations

import re
import time

import discord

ROLE_LOT_RE = re.compile(r"<@&(\d+)>")
DEFAULT_AUCTION_STEP_PRESETS = [100, 1000, 5000]


def get_auction_min_increment(eco: dict) -> int:
    value = eco.get("auction_min_increment", 100)
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 100
    return max(1, value)


def get_auction_step_presets(eco: dict) -> list[int]:
    raw = eco.get("auction_step_presets", DEFAULT_AUCTION_STEP_PRESETS)
    presets: list[int] = []

    if isinstance(raw, str):
        raw = [chunk.strip() for chunk in raw.split(",")]

    if isinstance(raw, list):
        for item in raw:
            try:
                value = int(item)
            except (TypeError, ValueError):
                continue
            if value > 0:
                presets.append(value)

    if not presets:
        presets = list(DEFAULT_AUCTION_STEP_PRESETS)

    return sorted(dict.fromkeys(presets))[:3]


def normalize_bid_history(history: list[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    for entry in history or []:
        if not isinstance(entry, dict):
            continue
        try:
            amount = int(entry.get("amount", 0))
            user_id = int(entry.get("user_id", 0))
        except (TypeError, ValueError):
            continue
        if amount <= 0 or user_id <= 0:
            continue
        ts = int(entry.get("timestamp", 0) or 0)
        normalized.append(
            {
                "user_id": user_id,
                "amount": amount,
                "timestamp": ts,
                "source": str(entry.get("source") or "unknown"),
            }
        )
    return normalized


def infer_role_id(raw: str | None) -> int | None:
    if not raw:
        return None
    match = ROLE_LOT_RE.search(raw)
    if match:
        return int(match.group(1))
    stripped = str(raw).strip()
    if stripped.isdigit() and len(stripped) >= 17:
        return int(stripped)
    return None


def normalize_auction_lot(lot: dict | None) -> dict:
    src = dict(lot or {})
    role_id = src.get("role_id")
    if role_id is not None:
        try:
            role_id = int(role_id)
        except (TypeError, ValueError):
            role_id = None

    raw_name = str(src.get("name") or src.get("title") or "").strip()
    if role_id is None:
        role_id = infer_role_id(raw_name)

    lot_type = src.get("type")
    if lot_type not in {"role", "text"}:
        lot_type = "role" if role_id else "text"

    title = str(src.get("title") or raw_name or "Невідомий лот").strip()
    if lot_type == "role" and role_id and (not title or title == raw_name):
        title = f"Роль {role_id}"

    description = str(src.get("description") or src.get("desc") or "Опис відсутній.").strip()

    try:
        start_bid = int(src.get("start_bid", 0))
    except (TypeError, ValueError):
        start_bid = 0
    start_bid = max(1, start_bid)

    try:
        duration_seconds = int(src.get("duration_seconds", src.get("duration", 0)))
    except (TypeError, ValueError):
        duration_seconds = 0
    duration_seconds = max(10, duration_seconds)

    display_label = str(src.get("display_label") or "").strip()
    if not display_label:
        display_label = f"<@&{role_id}>" if lot_type == "role" and role_id else title

    try:
        created_by = int(src.get("created_by", 0) or 0)
    except (TypeError, ValueError):
        created_by = 0

    try:
        created_at = int(src.get("created_at", 0) or 0)
    except (TypeError, ValueError):
        created_at = 0

    return {
        "id": str(src.get("id") or f"lot-{int(time.time())}"),
        "type": lot_type,
        "title": title,
        "description": description,
        "start_bid": start_bid,
        "duration_seconds": duration_seconds,
        "status": str(src.get("status") or "queued"),
        "role_id": role_id,
        "display_label": display_label,
        "created_by": created_by,
        "created_at": created_at,
    }


def normalize_auction_queue(queue: list[dict] | None) -> list[dict]:
    return [normalize_auction_lot(item) for item in queue or [] if isinstance(item, dict)]


def normalize_active_auction_doc(doc: dict | None, eco: dict) -> dict | None:
    if not doc:
        return None

    normalized = dict(doc)
    lot = normalize_auction_lot(doc.get("lot_snapshot") or doc.get("lot"))
    min_increment = get_auction_min_increment(eco)
    try:
        current_bid = int(doc.get("current_bid", lot["start_bid"]))
    except (TypeError, ValueError):
        current_bid = lot["start_bid"]

    highest_bidder = doc.get("highest_bidder")
    try:
        highest_bidder = int(highest_bidder) if highest_bidder else None
    except (TypeError, ValueError):
        highest_bidder = None

    normalized.update(
        {
            "lot": lot,
            "lot_snapshot": lot,
            "current_bid": max(lot["start_bid"], current_bid),
            "highest_bidder": highest_bidder,
            "end_time": float(doc.get("end_time", time.time() + lot["duration_seconds"])),
            "anti_snipe": int(doc.get("anti_snipe", eco.get("auction_anti_snipe_seconds", 30)) or 0),
            "min_increment": int(doc.get("min_increment", min_increment) or min_increment),
            "started_at": int(doc.get("started_at", 0) or 0),
            "started_by": int(doc.get("started_by", 0) or 0),
            "bid_history": normalize_bid_history(doc.get("bid_history")),
            "status": str(doc.get("status") or "live"),
        }
    )
    return normalized


def lot_public_label(lot: dict, guild: discord.Guild | None = None) -> str:
    lot = normalize_auction_lot(lot)
    if lot["type"] == "role" and lot.get("role_id"):
        if guild:
            role = guild.get_role(lot["role_id"])
            if role:
                return role.mention
        return f"<@&{lot['role_id']}>"
    return lot["title"]


def lot_plain_label(lot: dict, guild: discord.Guild | None = None) -> str:
    lot = normalize_auction_lot(lot)
    if lot["type"] == "role" and lot.get("role_id"):
        if guild:
            role = guild.get_role(lot["role_id"])
            if role:
                return f"@{role.name}"
        return lot["title"]
    return lot["title"]


def lot_preview_text(lot: dict, guild: discord.Guild | None = None) -> str:
    lot = normalize_auction_lot(lot)
    duration = lot["duration_seconds"]
    if duration >= 3600:
        duration_text = f"{duration // 3600}г {(duration % 3600) // 60}хв" if duration % 3600 else f"{duration // 3600}г"
    elif duration >= 60:
        duration_text = f"{duration // 60}хв"
    else:
        duration_text = f"{duration}с"
    return f"{lot_plain_label(lot, guild)} • старт `{lot['start_bid']:,}` • {duration_text}"
