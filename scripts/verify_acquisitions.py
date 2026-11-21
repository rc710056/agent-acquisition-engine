import asyncio
import hashlib
from pathlib import Path
import filetype

from apps.api.app.models.database import init_db, async_session_factory
from apps.api.app.models.entities import User, Source, SourceOption, AcquisitionJob, Artifact
from packages.shared_schemas.models import JobState
from providers.registry import provider_registry
from services.acquisition_worker.worker import AcquisitionWorker
from apps.api.app.services.verification import FileVerifier

async def run_acquisition_verifications():
    await init_db()
    worker = AcquisitionWorker()

    print("=" * 80)
    print("AGENT ACQUISITION ENGINE - LIVE AUTHORIZED ACQUISITION & INTEGRITY AUDIT")
    print("=" * 80)

    # Test 1: Direct Video Acquisition (MP4)
    print("\n[TEST A] Acquiring Direct MP4 Video...")
    # Using public sample MP4 from W3C / HTML5 video sample
    video_url = "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"
    provider, classif = await provider_registry.resolve_provider_with_classifier(video_url)
    print(f" -> Classifier SourceType: {classif.source_type.value}, Provider: {provider.provider_id}")
    insp = await provider.inspect(video_url)
    print(f" -> Inspected MIME: {insp.mime_type}, Estimated Size: {insp.estimated_size_bytes} bytes")
    dest_video = Path("storage/temp/verified_flower.mp4")
    acq_video = await provider.acquire(video_url, "original", dest_video)
    
    # Verification
    v_res = FileVerifier.verify_file(dest_video, expected_mime="video/mp4", expected_sha256=acq_video["sha256"])
    kind_v = filetype.guess(str(dest_video))
    print(f" -> Downloaded Size: {acq_video['transferred_bytes']} bytes")
    print(f" -> Computed SHA-256: {acq_video['sha256']}")
    print(f" -> Magic Byte Detection: {kind_v.mime if kind_v else 'unknown'} (Extension: {kind_v.extension if kind_v else 'none'})")
    print(f" -> Integrity Valid: {v_res.is_valid}")
    assert v_res.is_valid is True
    assert kind_v and "video" in kind_v.mime
    print(" -> RESULT: PASS (True MP4 video file, NOT HTML)")
    dest_video.unlink(missing_ok=True)

    # Test 2: Direct PDF Document Acquisition
    print("\n[TEST B] Acquiring Direct PDF Document...")
    pdf_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
    provider, classif = await provider_registry.resolve_provider_with_classifier(pdf_url)
    print(f" -> Classifier SourceType: {classif.source_type.value}, Provider: {provider.provider_id}")
    dest_pdf = Path("storage/temp/verified_dummy.pdf")
    acq_pdf = await provider.acquire(pdf_url, "original", dest_pdf)
    v_pdf = FileVerifier.verify_file(dest_pdf, expected_mime="application/pdf", expected_sha256=acq_pdf["sha256"])
    kind_p = filetype.guess(str(dest_pdf))
    print(f" -> Downloaded Size: {acq_pdf['transferred_bytes']} bytes")
    print(f" -> Computed SHA-256: {acq_pdf['sha256']}")
    print(f" -> Magic Byte Detection: {kind_p.mime if kind_p else 'unknown'} (Extension: {kind_p.extension if kind_p else 'none'})")
    print(f" -> Integrity Valid: {v_pdf.is_valid}")
    assert v_pdf.is_valid is True
    assert kind_p and "pdf" in kind_p.mime
    print(" -> RESULT: PASS (True PDF document, NOT HTML)")
    dest_pdf.unlink(missing_ok=True)

    # Test 3: Pinterest Pin Media Acquisition
    print("\n[TEST C] Acquiring Pinterest Video Media...")
    pin_url = "https://pin.it/zRhGMggGP"
    pin_provider = provider_registry.get_provider("pinterest")
    pin_insp = await pin_provider.inspect(pin_url)
    print(f" -> Resolved Canonical URL: {pin_insp.resolved_url}")
    print(f" -> Formats Discovered: {len(pin_insp.formats)}")
    for f in pin_insp.formats[:3]:
        print(f"    * Format: {f.format_id} | Quality: {f.quality_label} | MIME: {f.mime_type} | URL: {f.download_url[:60]}...")
    target_fmt = pin_insp.formats[0]
    dest_pin = Path("storage/temp/verified_pinterest_media.mp4")
    acq_pin = await pin_provider.acquire(pin_url, target_fmt.format_id, dest_pin)
    v_pin = FileVerifier.verify_file(dest_pin, expected_sha256=acq_pin["sha256"])
    kind_pin = filetype.guess(str(dest_pin))
    print(f" -> Downloaded Size: {acq_pin['transferred_bytes']} bytes")
    print(f" -> Computed SHA-256: {acq_pin['sha256']}")
    print(f" -> Magic Byte Detection: {kind_pin.mime if kind_pin else 'unknown'} (Extension: {kind_pin.extension if kind_pin else 'none'})")
    print(f" -> Integrity Valid: {v_pin.is_valid}")
    assert v_pin.is_valid is True
    assert kind_pin and ("video" in kind_pin.mime or "image" in kind_pin.mime)
    # Check that file does NOT start with <!DOCTYPE html or <html
    with open(dest_pin, "rb") as f:
        head_sample = f.read(512)
        assert b"<!DOCTYPE" not in head_sample
        assert b"<html" not in head_sample
    print(" -> RESULT: PASS (Acquired media stream has valid media signatures; NOT an HTML webpage!)")
    dest_pin.unlink(missing_ok=True)

    print("\n" + "=" * 80)
    print("ALL LIVE AUTHORIZED ACQUISITIONS VERIFIED SUCCESSFULLY")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_acquisition_verifications())
