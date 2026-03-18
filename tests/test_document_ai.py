from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.tools import WorkspaceTools


def _write_pdf(path: Path, payload: bytes = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n") -> None:
    path.write_bytes(payload)


def _write_png(path: Path, payload: bytes = b"\x89PNG\r\n\x1a\n") -> None:
    path.write_bytes(payload)


def _make_tools(tmp_path: Path, **overrides: object) -> WorkspaceTools:
    defaults: dict[str, object] = {
        "root": tmp_path,
        "mistral_api_key": "mistral-key",
        "mistral_document_ai_use_shared_key": True,
        "max_file_chars": 20_000,
        "max_observation_chars": 20_000,
    }
    defaults.update(overrides)
    return WorkspaceTools(**defaults)


class TestDocumentAiTools:
    def test_document_ocr_success_returns_wrapped_response(self, tmp_path: Path) -> None:
        pdf = tmp_path / "sample.pdf"
        _write_pdf(pdf)
        tools = _make_tools(tmp_path)
        observed: dict[str, object] = {}

        def fake_request(*, url: str, body: dict[str, object], request_label: str) -> dict[str, object]:
            observed["url"] = url
            observed["body"] = body
            observed["request_label"] = request_label
            return {
                "model": "mistral-ocr-latest",
                "pages": [
                    {
                        "index": 0,
                        "markdown": "# Title\nHello world",
                        "images": [],
                    }
                ],
                "usage_info": {"pages_processed": 1},
            }

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(tools, "_mistral_document_ai_request", fake_request)
            raw = tools.document_ocr(
                "sample.pdf",
                include_images=True,
                pages=[0, 0, 2],
                model="mistral-ocr-latest",
            )

        parsed = json.loads(raw)
        assert parsed["provider"] == "mistral"
        assert parsed["operation"] == "ocr"
        assert parsed["path"] == "sample.pdf"
        assert parsed["text"] == "# Title\nHello world"
        assert parsed["options"]["include_images"] is True
        assert parsed["options"]["pages"] == [0, 2]
        body = observed["body"]
        assert isinstance(body, dict)
        assert body["document"]["type"] == "document_url"
        assert body["include_image_base64"] is True
        assert body["pages"] == [0, 2]
        assert str(body["document"]["document_url"]).startswith("data:application/pdf;base64,")

    def test_document_ocr_supports_local_images(self, tmp_path: Path) -> None:
        image = tmp_path / "scan.png"
        _write_png(image)
        tools = _make_tools(tmp_path)
        captured: dict[str, object] = {}

        def fake_request(*, url: str, body: dict[str, object], request_label: str) -> dict[str, object]:
            captured["body"] = body
            return {"pages": [{"index": 0, "markdown": "receipt"}], "model": "mistral-ocr-latest"}

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(tools, "_mistral_document_ai_request", fake_request)
            raw = tools.document_ocr("scan.png")

        parsed = json.loads(raw)
        assert parsed["file"]["source_type"] == "image_url"
        body = captured["body"]
        assert isinstance(body, dict)
        assert body["document"]["type"] == "image_url"
        assert str(body["document"]["image_url"]).startswith("data:image/png;base64,")

    def test_document_annotations_requires_schema(self, tmp_path: Path) -> None:
        pdf = tmp_path / "sample.pdf"
        _write_pdf(pdf)
        tools = _make_tools(tmp_path)
        out = tools.document_annotations("sample.pdf")
        assert "requires document_schema" in out

    def test_document_annotations_wraps_schema_and_prompt(self, tmp_path: Path) -> None:
        pdf = tmp_path / "sample.pdf"
        _write_pdf(pdf)
        tools = _make_tools(tmp_path)
        captured: dict[str, object] = {}

        def fake_request(*, url: str, body: dict[str, object], request_label: str) -> dict[str, object]:
            captured["body"] = body
            return {
                "document_annotation": "{\"invoice_number\": \"INV-42\"}",
                "pages": [{"index": 0, "images": []}],
                "model": "mistral-ocr-latest",
            }

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(tools, "_mistral_document_ai_request", fake_request)
            raw = tools.document_annotations(
                "sample.pdf",
                document_schema={
                    "type": "object",
                    "properties": {"invoice_number": {"type": "string"}},
                    "required": ["invoice_number"],
                },
                instruction="Extract the invoice number.",
            )

        parsed = json.loads(raw)
        assert parsed["operation"] == "annotations"
        assert parsed["document_annotation"]["invoice_number"] == "INV-42"
        body = captured["body"]
        assert isinstance(body, dict)
        assert body["document_annotation_prompt"] == "Extract the invoice number."
        assert body["document_annotation_format"]["type"] == "json_schema"

    def test_document_annotations_truncates_oversized_annotation_fields(
        self, tmp_path: Path
    ) -> None:
        pdf = tmp_path / "sample.pdf"
        _write_pdf(pdf)
        tools = _make_tools(
            tmp_path,
            max_file_chars=700,
            max_observation_chars=700,
        )

        def fake_request(*, url: str, body: dict[str, object], request_label: str) -> dict[str, object]:
            return {
                "document_annotation": json.dumps(
                    {
                        "invoice_number": "INV-42",
                        "notes": "x" * 4_000,
                    }
                ),
                "pages": [
                    {
                        "index": 0,
                        "images": [
                            {
                                "bbox_annotation": {
                                    "label": "stamp",
                                    "details": "y" * 3_000,
                                }
                            }
                        ],
                    }
                ],
                "model": "mistral-ocr-latest",
            }

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(tools, "_mistral_document_ai_request", fake_request)
            raw = tools.document_annotations(
                "sample.pdf",
                document_schema={
                    "type": "object",
                    "properties": {"invoice_number": {"type": "string"}},
                },
                bbox_schema={
                    "type": "object",
                    "properties": {"label": {"type": "string"}},
                },
            )

        assert len(raw) <= 700
        parsed = json.loads(raw)
        assert parsed["truncation"]["applied"] is True
        assert "bbox_annotations" not in parsed
        assert "document_annotation" not in parsed
        assert (
            parsed["truncation"].get("details_omitted", 0) > 0
            or parsed["truncation"].get("omitted_document_annotation_json_chars", 0) > 0
        )
        if "response" in parsed:
            assert "document_annotation" not in parsed["response"]

    def test_document_qa_requires_pdf(self, tmp_path: Path) -> None:
        image = tmp_path / "receipt.png"
        _write_png(image)
        tools = _make_tools(tmp_path)
        out = tools.document_qa("receipt.png", question="What is the total?")
        assert "supports only local PDF files" in out

    def test_document_qa_respects_override_mode(self, tmp_path: Path) -> None:
        pdf = tmp_path / "sample.pdf"
        _write_pdf(pdf)
        tools = _make_tools(
            tmp_path,
            mistral_api_key=None,
            mistral_document_ai_api_key="docai-key",
            mistral_document_ai_use_shared_key=False,
        )

        def fake_request(*, url: str, body: dict[str, object], request_label: str) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": "The total is 42 dollars.",
                        }
                    }
                ]
            }

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(tools, "_mistral_document_ai_request", fake_request)
            raw = tools.document_qa("sample.pdf", question="What is the total?")

        parsed = json.loads(raw)
        assert parsed["operation"] == "qa"
        assert parsed["text"] == "The total is 42 dollars."

    def test_document_qa_path_escape_blocked(self, tmp_path: Path) -> None:
        tools = _make_tools(tmp_path)
        out = tools.document_qa("../../etc/passwd.pdf", question="Nope")
        assert "escapes workspace" in out
