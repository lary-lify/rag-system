"""
Document Parser Service - Intelligent document parsing.
Supports table extraction, image OCR, formula recognition.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def extract_tables_from_docx(file_path: str) -> list[dict[str, Any]]:
    """
    Extract tables from DOCX file.

    Returns:
        List of tables, each table is a list of rows,
        each row is a list of cell values.
    """
    try:
        from docx import Document as DocxDocument

        doc = DocxDocument(file_path)
        tables = []

        for table in doc.tables:
            table_data = []
            for row in table.rows:
                row_data = [cell.text.strip() for cell in row.cells]
                table_data.append(row_data)
            if table_data:
                tables.append({
                    "type": "table",
                    "data": table_data,
                    "markdown": _table_to_markdown(table_data),
                })

        return tables
    except Exception as e:
        logger.warning(f"Failed to extract tables from DOCX: {e}")
        return []


def extract_tables_from_html(html_content: str) -> list[dict[str, Any]]:
    """Extract tables from HTML content."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, 'html.parser')
        tables = []

        for table in soup.find_all('table'):
            rows = []
            for tr in table.find_all('tr'):
                cells = []
                for td in tr.find_all(['td', 'th']):
                    cells.append(td.get_text(strip=True))
                if cells:
                    rows.append(cells)
            if rows:
                tables.append({
                    "type": "table",
                    "data": rows,
                    "markdown": _table_to_markdown(rows),
                })

        return tables
    except ImportError:
        logger.warning("BeautifulSoup not installed, skipping HTML table extraction")
        return []


def _table_to_markdown(table_data: list[list[str]]) -> str:
    """Convert table data to Markdown format."""
    if not table_data:
        return ""

    # Header
    header = table_data[0]
    separator = ["---"] * len(header)

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]

    # Rows
    for row in table_data[1:]:
        # Pad row if needed
        while len(row) < len(header):
            row.append("")
        lines.append("| " + " | ".join(row[:len(header)]) + " |")

    return "\n".join(lines)


def extract_code_blocks(text: str) -> list[dict[str, Any]]:
    """
    Extract code blocks from text (Markdown format).

    Returns:
        List of code blocks with language and content.
    """
    pattern = r'```(\w+)?\s*\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)

    blocks = []
    for lang, code in matches:
        blocks.append({
            "type": "code",
            "language": lang or "unknown",
            "content": code.strip(),
        })

    return blocks


def extract_formulas(text: str) -> list[dict[str, Any]]:
    """
    Extract mathematical formulas from text.
    Supports LaTeX inline ($...$) and display ($$...$$) formulas.

    Returns:
        List of formulas with type and content.
    """
    formulas = []

    # Display formulas ($$...$$)
    display_pattern = r'\$\$(.*?)\$\$'
    for match in re.finditer(display_pattern, text, re.DOTALL):
        formulas.append({
            "type": "display_formula",
            "content": match.group(1).strip(),
            "latex": match.group(0),
        })

    # Inline formulas ($...$)
    inline_pattern = r'(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)'
    for match in re.finditer(inline_pattern, text):
        formulas.append({
            "type": "inline_formula",
            "content": match.group(1).strip(),
            "latex": match.group(0),
        })

    return formulas


def extract_images_from_docx(file_path: str) -> list[dict[str, Any]]:
    """
    Extract image information from DOCX file.
    Note: This extracts metadata, not the actual image data.

    Returns:
        List of image metadata.
    """
    try:
        from docx import Document as DocxDocument

        doc = DocxDocument(file_path)
        images = []

        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                images.append({
                    "type": "image",
                    "content_type": rel.target_ref,
                    "description": f"Image: {os.path.basename(rel.target_ref)}",
                })

        return images
    except Exception as e:
        logger.warning(f"Failed to extract images from DOCX: {e}")
        return []


def parse_document_intelligently(
    file_path: str,
    file_type: str,
    include_metadata: bool = True,
) -> dict[str, Any]:
    """
    Intelligently parse document with structure preservation.

    Args:
        file_path: Path to the document file
        file_type: File extension (pdf, docx, html, etc.)
        include_metadata: Whether to include extracted metadata

    Returns:
        Dict with 'text', 'tables', 'code_blocks', 'formulas', 'images'
    """
    result = {
        "text": "",
        "tables": [],
        "code_blocks": [],
        "formulas": [],
        "images": [],
    }

    file_type = file_type.lower()

    # Extract based on file type
    if file_type in ("docx", "doc"):
        # Extract tables
        result["tables"] = extract_tables_from_docx(file_path)

        # Extract images metadata
        if include_metadata:
            result["images"] = extract_images_from_docx(file_path)

        # Get text content
        try:
            from docx import Document as DocxDocument
            doc = DocxDocument(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            result["text"] = "\n\n".join(paragraphs)
        except Exception as e:
            logger.warning(f"Failed to extract text from DOCX: {e}")

    elif file_type in ("html", "htm"):
        # Extract tables from HTML
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()
            result["tables"] = extract_tables_from_html(html_content)

            # Extract text
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            result["text"] = soup.get_text(separator="\n", strip=True)
        except ImportError:
            logger.warning("BeautifulSoup not installed")
        except Exception as e:
            logger.warning(f"Failed to parse HTML: {e}")

    elif file_type in ("txt", "md"):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            result["text"] = content

            # Extract code blocks and formulas from Markdown
            if file_type == "md":
                result["code_blocks"] = extract_code_blocks(content)
                result["formulas"] = extract_formulas(content)
        except Exception as e:
            logger.warning(f"Failed to read text file: {e}")

    elif file_type == "pdf":
        # PDF parsing would require additional libraries
        # For now, fall back to basic text extraction
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            texts = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    texts.append(t)
            result["text"] = "\n\n".join(texts)
        except Exception as e:
            logger.warning(f"Failed to parse PDF: {e}")

    # Add metadata
    if include_metadata:
        result["metadata"] = {
            "file_type": file_type,
            "has_tables": len(result["tables"]) > 0,
            "has_code_blocks": len(result["code_blocks"]) > 0,
            "has_formulas": len(result["formulas"]) > 0,
            "has_images": len(result["images"]) > 0,
            "table_count": len(result["tables"]),
            "code_block_count": len(result["code_blocks"]),
            "formula_count": len(result["formulas"]),
            "image_count": len(result["images"]),
        }

    return result


def format_structured_content(parsed: dict[str, Any]) -> str:
    """
    Format parsed document content into structured text for chunking.
    Preserves table structure and adds markers for special content.
    """
    parts = []

    # Main text
    if parsed.get("text"):
        parts.append(parsed["text"])

    # Tables
    for table in parsed.get("tables", []):
        parts.append(f"\n[表格]\n{table.get('markdown', '')}\n[/表格]\n")

    # Code blocks
    for block in parsed.get("code_blocks", []):
        lang = block.get("language", "")
        content = block.get("content", "")
        parts.append(f"\n[代码块:{lang}]\n{content}\n[/代码块]\n")

    # Formulas
    for formula in parsed.get("formulas", []):
        parts.append(f"\n[公式]\n{formula.get('latex', '')}\n[/公式]\n")

    return "\n".join(parts)
