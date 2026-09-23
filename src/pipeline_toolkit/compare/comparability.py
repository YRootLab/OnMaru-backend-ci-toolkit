def comparable(baseline: dict, candidate: dict) -> dict:
    for key, reason in (("environment", "environment_mismatch"), ("runner", "runner_mismatch"), ("suite", "suite_mismatch"), ("config_hash", "config_mismatch"), ("cache", "cache_mode_mismatch")):
        if key in baseline and key in candidate and baseline[key] != candidate[key]:
            return {"comparable": False, "reason": reason}
    return {"comparable": True, "reason": "matched_conditions"}
