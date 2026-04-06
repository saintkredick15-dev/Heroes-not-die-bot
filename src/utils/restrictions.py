from __future__ import annotations


COMMAND_RESTRICTION_RENAMES = {
    "economy": "wallet",
}


def normalize_command_restrictions(restrictions: dict | None) -> dict[str, list[int]]:
    if not isinstance(restrictions, dict):
        return {}

    normalized: dict[str, list[int]] = {}
    for raw_name, raw_channels in restrictions.items():
        if not isinstance(raw_name, str):
            continue
        if not isinstance(raw_channels, list):
            continue

        command_name = COMMAND_RESTRICTION_RENAMES.get(raw_name, raw_name)
        channels = [channel_id for channel_id in raw_channels if isinstance(channel_id, int)]
        if not channels:
            continue

        if command_name in normalized:
            merged = normalized[command_name] + channels
            normalized[command_name] = list(dict.fromkeys(merged))
        else:
            normalized[command_name] = list(dict.fromkeys(channels))

    return normalized


def normalize_role_ids(role_ids: list | None) -> list[int]:
    if not isinstance(role_ids, list):
        return []

    normalized: list[int] = []
    for role_id in role_ids:
        if isinstance(role_id, int) and role_id > 0 and role_id not in normalized:
            normalized.append(role_id)
    return normalized
