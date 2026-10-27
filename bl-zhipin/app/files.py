"""只识别简历格式并私有保存，不执行文档或解压到文件系统。"""

import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree

import olefile

from .common import fail

MAX_FILE_SIZE = 10_000_000
MIME_TYPES = {".pdf": "application/pdf", ".doc": "application/msword",
              ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def filename(value):
    name = Path((value or "").replace("\\", "/")).name
    if not name or len(name) > 180 or any(ord(c) < 32 for c in name):
        fail("简历文件名无效或超过 180 个字符")
    if Path(name).suffix.lower() not in MIME_TYPES:
        fail("简历仅支持 PDF、DOC、DOCX 格式")
    return name


def validate_file(path, extension):
    try:
        if extension == ".pdf":
            with path.open("rb") as file:
                header = file.read(8)
                file.seek(max(0, path.stat().st_size - 2048))
                tail = file.read()
            valid = header.startswith(b"%PDF-") and b"%%EOF" in tail
        elif extension == ".doc":
            with olefile.OleFileIO(path) as doc:
                valid = doc.exists("WordDocument") and doc.openstream("WordDocument").read(2) == b"\xec\xa5"
        else:
            with zipfile.ZipFile(path) as doc:
                required = ["[Content_Types].xml", "word/document.xml"]
                valid = all(doc.getinfo(name).file_size < 5_000_000 for name in required)
                if valid:
                    types = ElementTree.fromstring(doc.read(required[0]))
                    document = ElementTree.fromstring(doc.read(required[1]))
                    valid = document.tag == "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document"
                    valid = valid and any(
                        child.attrib.get("ContentType") ==
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
                        for child in types
                    )
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError, RuntimeError, EOFError, zlib.error):
        valid = False
    if not valid:
        fail("简历文件格式与扩展名不符，或文件已损坏")
