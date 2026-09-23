def verify_image_digest(expected: str, deployed: str) -> bool:
    return bool(expected and deployed and expected.startswith("sha256:") and expected == deployed)
