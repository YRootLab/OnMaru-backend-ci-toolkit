from pipeline_toolkit.contracts import Deployment, Release, validate

def compare_release_identity(release: Release, deployment: Deployment, require_distinct: bool = False) -> dict:
    validate(release)
    validate(deployment)
    if release.image_digest != deployment.image_digest:
        raise ValueError("deployment image digest does not match release")
    if release.tag != deployment.release_tag:
        raise ValueError("deployment release tag does not match release")
    if require_distinct and release.tag == deployment.release_tag:
        raise ValueError("baseline and candidate release must be distinct")
    return {"match": True}
