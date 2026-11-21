import pytest
from packages.source_classifier.classifier import SourceClassifier, SourceType, AcquisitionPermission

@pytest.mark.asyncio
async def test_classifier_recognizes_markdown_and_plain_text():
    classifier = SourceClassifier()
    
    # Live GitHub README markdown URL tested by Base44
    md_url = "https://raw.githubusercontent.com/rc710056/agent-acquisition-engine/main/README.md"
    result = await classifier.classify(md_url)
    assert result.acquisition_permission == AcquisitionPermission.PERMITTED
    assert result.source_type == SourceType.DIRECT_FILE
    assert result.provider_id == "direct_http"
    assert result.mime_type in {"text/plain", "text/markdown"}
