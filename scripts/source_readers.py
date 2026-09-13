from __future__ import annotations

import io
import json
import posixpath
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


SUPPORTED_SOURCE_FORMATS = {
    ".md": "markdown",
    ".pdf": "pdf",
    ".pptx": "pptx",
    ".xmind": "xmind",
}
SOURCE_UNIT_LABELS = {
    "markdown": "document",
    "pdf": "page",
    "pptx": "slide",
    "xmind": "sheet",
}

PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CORE_TITLE = "{http://purl.org/dc/elements/1.1/}title"


class SourceReadError(ValueError):
    pass


def source_format(path: Path) -> str:
    try:
        return SUPPORTED_SOURCE_FORMATS[path.suffix.lower()]
    except KeyError as error:
        supported = ", ".join(sorted(SUPPORTED_SOURCE_FORMATS))
        raise SourceReadError(
            f"Unsupported Source format {path.suffix or '<none>'}: {path}. "
            f"Supported extensions: {supported}"
        ) from error


def _xml(archive: zipfile.ZipFile, member: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(archive.read(member))
    except KeyError as error:
        raise SourceReadError(f"Archive member is missing: {member}") from error
    except ElementTree.ParseError as error:
        raise SourceReadError(f"Archive member contains invalid XML: {member}") from error


def _core_title(archive: zipfile.ZipFile) -> str | None:
    if "docProps/core.xml" not in archive.namelist():
        return None
    title = _xml(archive, "docProps/core.xml").findtext(CORE_TITLE)
    return title.strip() if title and title.strip() else None


def _relationship_targets(
    archive: zipfile.ZipFile,
    relationship_path: str,
    source_directory: str,
) -> dict[str, tuple[str, str]]:
    if relationship_path not in archive.namelist():
        return {}
    result: dict[str, tuple[str, str]] = {}
    for relationship in _xml(archive, relationship_path):
        relationship_id = relationship.attrib.get("Id")
        target = relationship.attrib.get("Target")
        relationship_type = relationship.attrib.get("Type", "")
        if not relationship_id or not target or relationship.attrib.get("TargetMode") == "External":
            continue
        normalized = posixpath.normpath(
            posixpath.join(source_directory, target.lstrip("/"))
        )
        result[relationship_id] = (normalized, relationship_type)
    return result


def _numbered_member_key(path: str) -> tuple[int, str]:
    match = re.search(r"(\d+)(?=\.xml$)", path)
    return (int(match.group(1)) if match else 10**9, path)


def _pptx_slide_paths(archive: zipfile.ZipFile) -> list[str]:
    presentation_path = "ppt/presentation.xml"
    relationships = _relationship_targets(
        archive,
        "ppt/_rels/presentation.xml.rels",
        "ppt",
    )
    if presentation_path in archive.namelist() and relationships:
        root = _xml(archive, presentation_path)
        ordered: list[str] = []
        for slide_id in root.findall(f".//{{{PRESENTATION_NS}}}sldId"):
            relationship_id = slide_id.attrib.get(f"{{{RELATIONSHIP_NS}}}id")
            target = relationships.get(relationship_id or "")
            if target and target[0] in archive.namelist():
                ordered.append(target[0])
        if ordered:
            return ordered
    return sorted(
        (
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        ),
        key=_numbered_member_key,
    )


def _pptx_notes_path(archive: zipfile.ZipFile, slide_path: str) -> str | None:
    slide_directory = posixpath.dirname(slide_path)
    relationship_path = posixpath.join(
        slide_directory,
        "_rels",
        f"{posixpath.basename(slide_path)}.rels",
    )
    relationships = _relationship_targets(
        archive,
        relationship_path,
        slide_directory,
    )
    return next(
        (
            target
            for target, relationship_type in relationships.values()
            if relationship_type.endswith("/notesSlide") and target in archive.namelist()
        ),
        None,
    )


def _pptx_paragraphs(root: ElementTree.Element) -> list[str]:
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{{{DRAWING_NS}}}p"):
        parts = [
            node.text or ""
            for node in paragraph.iter(f"{{{DRAWING_NS}}}t")
        ]
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "cNvPr":
            continue
        for attribute in ("title", "descr"):
            value = node.attrib.get(attribute, "").strip()
            if value and value not in paragraphs:
                paragraphs.append(f"[Visual description] {value}")
    return paragraphs


def _pptx_inspection(path: Path, raw: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            slide_paths = _pptx_slide_paths(archive)
            if not slide_paths:
                raise SourceReadError("PPTX contains no slides")
            first_slide = _pptx_paragraphs(_xml(archive, slide_paths[0]))
            title = _core_title(archive) or (first_slide[0] if first_slide else path.stem)
            return {"title": title, "unit_count": len(slide_paths)}
    except (zipfile.BadZipFile, OSError) as error:
        raise SourceReadError(f"Invalid PPTX archive: {path}") from error


def _xmind_json_sheets(archive: zipfile.ZipFile) -> list[dict[str, Any]]:
    if "content.json" not in archive.namelist():
        return []
    try:
        value = json.loads(archive.read("content.json").decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceReadError("XMind content.json is invalid") from error
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    raise SourceReadError("XMind content.json has an unsupported root value")


def _local_name(node: ElementTree.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _direct_child(node: ElementTree.Element, name: str) -> ElementTree.Element | None:
    return next((child for child in node if _local_name(child) == name), None)


def _direct_text(node: ElementTree.Element, name: str) -> str:
    child = _direct_child(node, name)
    return "" if child is None else "".join(child.itertext()).strip()


def _xmind_xml_sheets(archive: zipfile.ZipFile) -> list[ElementTree.Element]:
    if "content.xml" not in archive.namelist():
        return []
    root = _xml(archive, "content.xml")
    return [node for node in root if _local_name(node) == "sheet"]


def _xmind_inspection(path: Path, raw: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            json_sheets = _xmind_json_sheets(archive)
            if json_sheets:
                first = json_sheets[0]
                root_topic = first.get("rootTopic") or {}
                title = root_topic.get("title") or first.get("title") or path.stem
                return {"title": str(title).strip() or path.stem, "unit_count": len(json_sheets)}
            xml_sheets = _xmind_xml_sheets(archive)
            if xml_sheets:
                first_topic = _direct_child(xml_sheets[0], "topic")
                title = _direct_text(first_topic, "title") if first_topic is not None else ""
                return {"title": title or _direct_text(xml_sheets[0], "title") or path.stem, "unit_count": len(xml_sheets)}
            raise SourceReadError("XMind contains neither content.json nor content.xml")
    except (zipfile.BadZipFile, OSError) as error:
        raise SourceReadError(f"Invalid XMind archive: {path}") from error


def _pdf_reader(value: Path | io.BytesIO) -> Any:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise SourceReadError(
            "PDF text extraction requires pypdf or the pdftotext command"
        ) from error
    try:
        return PdfReader(value)
    except Exception as error:
        raise SourceReadError("PDF could not be opened") from error


def _pdf_inspection(path: Path, raw: bytes) -> dict[str, Any]:
    if not raw.startswith(b"%PDF-"):
        raise SourceReadError(f"Invalid PDF signature: {path}")
    try:
        reader = _pdf_reader(io.BytesIO(raw))
    except SourceReadError as error:
        if "requires pypdf" in str(error):
            return {"title": path.stem}
        raise
    metadata = reader.metadata or {}
    title = str(metadata.get("/Title") or "").strip() or path.stem
    return {"title": title, "unit_count": len(reader.pages)}


def inspect_source(path: Path, raw: bytes | None = None) -> dict[str, Any]:
    format_name = source_format(path)
    payload = path.read_bytes() if raw is None else raw
    result: dict[str, Any] = {
        "format": format_name,
        "unit_label": SOURCE_UNIT_LABELS[format_name],
        "title": path.stem,
        "status": "empty" if not payload else "ready",
    }
    if not payload:
        return result
    try:
        if format_name == "markdown":
            content = payload.decode("utf-8-sig")
            result["title"] = next(
                (
                    line[2:].strip()
                    for line in content.splitlines()
                    if line.startswith("# ") and line[2:].strip()
                ),
                path.stem,
            )
            result["unit_count"] = 1
        elif format_name == "pdf":
            result.update(_pdf_inspection(path, payload))
        elif format_name == "pptx":
            result.update(_pptx_inspection(path, payload))
        elif format_name == "xmind":
            result.update(_xmind_inspection(path, payload))
    except (SourceReadError, UnicodeDecodeError):
        result["status"] = "unreadable"
    return result


def _selected_units(total: int, unit: int | None, label: str) -> list[int]:
    if unit is None:
        return list(range(total))
    if unit < 1 or unit > total:
        raise SourceReadError(f"{label.capitalize()} {unit} is outside 1..{total}")
    return [unit - 1]


def _extract_pptx(path: Path, unit: int | None) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            slide_paths = _pptx_slide_paths(archive)
            title = _core_title(archive) or path.stem
            sections = [f"# Presentation: {title}"]
            for index in _selected_units(len(slide_paths), unit, "slide"):
                slide_path = slide_paths[index]
                paragraphs = _pptx_paragraphs(_xml(archive, slide_path))
                slide_title = paragraphs[0] if paragraphs else "Untitled"
                sections.append(f"\n## Slide {index + 1}: {slide_title}")
                sections.extend(paragraphs)
                notes_path = _pptx_notes_path(archive, slide_path)
                if notes_path:
                    notes = _pptx_paragraphs(_xml(archive, notes_path))
                    if notes:
                        sections.append("\n### Speaker notes")
                        sections.extend(notes)
            return "\n".join(sections).strip() + "\n"
    except (zipfile.BadZipFile, OSError) as error:
        raise SourceReadError(f"Invalid PPTX archive: {path}") from error


def _topic_note(topic: dict[str, Any]) -> str | None:
    notes = topic.get("notes")
    if not isinstance(notes, dict):
        return None
    for key in ("plain", "html"):
        value = notes.get(key)
        if isinstance(value, dict) and value.get("content"):
            return str(value["content"]).strip()
    return None


def _json_topic_lines(topic: dict[str, Any], depth: int = 0) -> list[str]:
    title = str(topic.get("title") or "Untitled topic").strip()
    lines = [f"{'  ' * depth}- {title}"]
    labels = topic.get("labels")
    if isinstance(labels, list) and labels:
        lines.append(f"{'  ' * (depth + 1)}Labels: {', '.join(map(str, labels))}")
    note = _topic_note(topic)
    if note:
        lines.append(f"{'  ' * (depth + 1)}Note: {' '.join(note.split())}")
    children = topic.get("children")
    if isinstance(children, dict):
        for group in ("attached", "detached"):
            values = children.get(group) or []
            if isinstance(values, list):
                for child in values:
                    if isinstance(child, dict):
                        lines.extend(_json_topic_lines(child, depth + 1))
    return lines


def _xml_topic_lines(topic: ElementTree.Element, depth: int = 0) -> list[str]:
    title = _direct_text(topic, "title") or "Untitled topic"
    lines = [f"{'  ' * depth}- {title}"]
    notes = _direct_child(topic, "notes")
    if notes is not None:
        note = " ".join("".join(notes.itertext()).split())
        if note:
            lines.append(f"{'  ' * (depth + 1)}Note: {note}")
    children = _direct_child(topic, "children")
    if children is not None:
        for topics in children:
            if _local_name(topics) != "topics":
                continue
            for child in topics:
                if _local_name(child) == "topic":
                    lines.extend(_xml_topic_lines(child, depth + 1))
    return lines


def _extract_xmind(path: Path, unit: int | None) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            json_sheets = _xmind_json_sheets(archive)
            sections = [f"# XMind: {path.stem}"]
            if json_sheets:
                for index in _selected_units(len(json_sheets), unit, "sheet"):
                    sheet = json_sheets[index]
                    title = str(sheet.get("title") or f"Sheet {index + 1}").strip()
                    sections.append(f"\n## Sheet {index + 1}: {title}")
                    root_topic = sheet.get("rootTopic")
                    if isinstance(root_topic, dict):
                        sections.extend(_json_topic_lines(root_topic))
                return "\n".join(sections).strip() + "\n"

            xml_sheets = _xmind_xml_sheets(archive)
            if not xml_sheets:
                raise SourceReadError("XMind contains neither content.json nor content.xml")
            for index in _selected_units(len(xml_sheets), unit, "sheet"):
                sheet = xml_sheets[index]
                title = _direct_text(sheet, "title") or f"Sheet {index + 1}"
                sections.append(f"\n## Sheet {index + 1}: {title}")
                root_topic = _direct_child(sheet, "topic")
                if root_topic is not None:
                    sections.extend(_xml_topic_lines(root_topic))
            return "\n".join(sections).strip() + "\n"
    except (zipfile.BadZipFile, OSError) as error:
        raise SourceReadError(f"Invalid XMind archive: {path}") from error


def _extract_pdf_with_pypdf(path: Path, unit: int | None) -> str:
    reader = _pdf_reader(path)
    title = str((reader.metadata or {}).get("/Title") or "").strip() or path.stem
    sections = [f"# PDF: {title}"]
    for index in _selected_units(len(reader.pages), unit, "page"):
        try:
            text = reader.pages[index].extract_text() or ""
        except Exception as error:
            raise SourceReadError(f"Could not extract PDF page {index + 1}") from error
        content = text.strip() or "[No extractable text. Visual inspection or OCR is required.]"
        sections.append(f"\n## Page {index + 1}\n{content}")
    return "\n".join(sections).strip() + "\n"


def _extract_pdf_with_pdftotext(path: Path, unit: int | None) -> str:
    executable = shutil.which("pdftotext")
    if not executable:
        raise SourceReadError("PDF text extraction requires pypdf or pdftotext")
    command = [executable, "-layout"]
    if unit is not None:
        command.extend(["-f", str(unit), "-l", str(unit)])
    command.extend([str(path), "-"])
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise SourceReadError(f"pdftotext failed: {message}")
    content = result.stdout.decode("utf-8", errors="replace").strip()
    heading = f"# PDF: {path.stem}"
    if unit is not None:
        heading += f"\n\n## Page {unit}"
    return f"{heading}\n{content}\n"


def _extract_pdf(path: Path, unit: int | None) -> str:
    try:
        return _extract_pdf_with_pypdf(path, unit)
    except SourceReadError as error:
        if "requires pypdf" not in str(error):
            raise
        return _extract_pdf_with_pdftotext(path, unit)


def extract_source_text(path: Path, *, unit: int | None = None) -> str:
    format_name = source_format(path)
    if format_name == "markdown":
        if unit not in (None, 1):
            raise SourceReadError("Markdown has only document unit 1")
        return path.read_text(encoding="utf-8-sig")
    if format_name == "pdf":
        return _extract_pdf(path, unit)
    if format_name == "pptx":
        return _extract_pptx(path, unit)
    if format_name == "xmind":
        return _extract_xmind(path, unit)
    raise AssertionError(f"Unhandled Source format: {format_name}")

