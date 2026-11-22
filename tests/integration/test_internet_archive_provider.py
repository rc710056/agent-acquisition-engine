import pytest
import httpx
from providers.internet_archive.provider import InternetArchiveProvider, extract_ia_identifier_and_file
from packages.shared_schemas.models import SourceType, SecurityStatus, SourceAccessStatus

def test_extract_ia_identifier():
    ident, f = extract_ia_identifier_and_file("https://archive.org/details/night_of_the_living_dead")
    assert ident == "night_of_the_living_dead"
    assert f is None

    ident, f = extract_ia_identifier_and_file("https://archive.org/download/ElephantsDream/ed_hd.mp4")
    assert ident == "ElephantsDream"
    assert f == "ed_hd.mp4"

    ident, f = extract_ia_identifier_and_file("https://archive.org/metadata/test_item")
    assert ident == "test_item"

@pytest.mark.asyncio
async def test_ia_inspect_mock(monkeypatch):
    provider = InternetArchiveProvider()
    assert provider.can_handle("https://archive.org/details/ElephantsDream")

    sample_meta = {
        "metadata": {
            "title": "Elephants Dream",
            "description": "The premier open source film by Blender Foundation.",
            "year": "2006",
            "creator": "Blender Foundation"
        },
        "files": [
            {
                "name": "ed_hd.mp4",
                "format": "h.264",
                "size": "67801890"
            },
            {
                "name": "ed_hd.ogv",
                "format": "Ogg Video",
                "size": "45657884"
            },
            {
                "name": "ed_soundtrack.mp3",
                "format": "VBR MP3",
                "size": "8280576"
            },
            {
                "name": "ed_script.pdf",
                "format": "Text PDF",
                "size": "1048576"
            },
            {
                "name": "ed_meta.xml",
                "format": "Metadata",
                "size": "1234"
            }
        ]
    }

    class MockResponse:
        status_code = 200
        url = "https://archive.org/metadata/ElephantsDream"
        def json(self):
            return sample_meta

    async def mock_get(client, url, headers=None, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = await provider.inspect("https://archive.org/details/ElephantsDream")
    assert res.is_permitted is True
    assert res.source_type == SourceType.MEDIA_COLLECTION
    assert res.provider_id == "internet_archive"
    assert "Elephants Dream" in res.title
    assert len(res.formats) == 4  # xml was filtered out
    # Best video should be recommended
    assert res.formats[0].file_type == "video"
    assert res.formats[0].category == "recommended"
    assert res.formats[0].download_url == "https://archive.org/download/ElephantsDream/ed_hd.mp4"
    assert res.formats[0].estimated_size_bytes == 67801890
    assert res.formats[0].has_video is True
    assert res.formats[0].has_audio is True
