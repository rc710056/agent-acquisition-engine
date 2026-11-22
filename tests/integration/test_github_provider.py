import pytest
import io
import zipfile
from pathlib import Path
from providers.github.provider import GitHubProvider, parse_github_url
from packages.source_classifier.classifier import SourceClassifier
from providers.registry import provider_registry
from packages.shared_schemas.models import SourceType, SecurityStatus


def test_parse_github_url():
    owner, repo, branch, subpath = parse_github_url("https://github.com/rc710056/agent-acquisition-engine")
    assert owner == "rc710056"
    assert repo == "agent-acquisition-engine"
    assert branch is None
    assert subpath is None

    owner, repo, branch, subpath = parse_github_url("https://github.com/rc710056/agent-acquisition-engine.git")
    assert owner == "rc710056"
    assert repo == "agent-acquisition-engine"

    owner, repo, branch, subpath = parse_github_url("https://github.com/rc710056/agent-acquisition-engine/tree/feature-branch/src")
    assert owner == "rc710056"
    assert repo == "agent-acquisition-engine"
    assert branch == "feature-branch"
    assert subpath == "src"

    owner, repo, branch, subpath = parse_github_url("https://github.com/rc710056/agent-acquisition-engine/archive/refs/heads/main.zip")
    assert owner == "rc710056"
    assert repo == "agent-acquisition-engine"
    assert branch == "main"

    owner, repo, branch, subpath = parse_github_url("https://github.com/login")
    assert owner is None
    assert repo is None


def test_github_can_handle():
    provider = GitHubProvider()
    assert provider.can_handle("https://github.com/rc710056/agent-acquisition-engine")
    assert provider.can_handle("https://github.com/torvalds/linux")
    assert not provider.can_handle("https://github.com/features")
    assert not provider.can_handle("https://google.com")


@pytest.mark.asyncio
async def test_github_inspect_and_classify():
    # Test classifier integration
    classification = await SourceClassifier.classify("https://github.com/rc710056/agent-acquisition-engine")
    assert classification.provider_id == "github"
    assert classification.source_type == SourceType.MEDIA_COLLECTION
    assert classification.security_status == SecurityStatus.SAFE

    # Test provider registry resolution
    provider, cls_res = await provider_registry.resolve_provider_with_classifier("https://github.com/rc710056/agent-acquisition-engine")
    assert provider is not None
    assert provider.provider_id == "github"

    # Test inspect
    inspection = await provider.inspect("https://github.com/rc710056/agent-acquisition-engine")
    assert inspection.is_permitted is True
    assert inspection.provider_id == "github"
    assert inspection.title == "rc710056/agent-acquisition-engine"
    assert len(inspection.formats) >= 2
    assert inspection.formats[0].format_id == "archive_zip"
    assert inspection.formats[0].category == "recommended"
    assert inspection.formats[1].format_id == "archive_tar_gz"
    assert inspection.formats[1].category == "alternate"
    assert inspection.requires_approval is False
    assert inspection.metadata["owner"] == "rc710056"
    assert inspection.metadata["repo"] == "agent-acquisition-engine"


@pytest.mark.asyncio
async def test_github_acquire(tmp_path):
    provider = GitHubProvider()
    dest = tmp_path / "main.zip"
    
    # Download archive
    result = await provider.acquire(
        url="https://github.com/rc710056/agent-acquisition-engine",
        format_id="archive_zip",
        destination_path=dest
    )
    
    assert dest.exists()
    assert result["is_verified"] is True
    assert result["filename"] == "main.zip"
    assert result["mime_type"] == "application/zip"
    assert result["transferred_bytes"] > 0
    assert len(result["sha256"]) == 64
    assert "files_count" in result.get("archive_metadata", {})
