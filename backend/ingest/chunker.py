import re
from dataclasses import dataclass

_CHARS_PER_TOKEN = 4
DEFAULT_MAX_TOKENS = 800
DEFAULT_OVERLAP_TOKENS = 80

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def count_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _joined_tokens(parts: list[str], sep_len: int = 2) -> int:
    total = sum(len(p) for p in parts) + sep_len * (len(parts) - 1)
    return max(1, total // _CHARS_PER_TOKEN)


@dataclass
class Chunk:
    chunk_index: int
    content: str
    metadata: dict


def _parse_sections(markdown: str) -> list[tuple[str, list[str]]]:
    """Group blocks into (section_path, blocks); heading lines stay in content."""
    stack: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    blocks: list[str] = []
    path = ""

    def flush() -> None:
        if blocks:
            sections.append((path, list(blocks)))
            blocks.clear()

    for block in re.split(r"\n{2,}", markdown.strip()):
        block = block.strip()
        if not block:
            continue
        match = _HEADING_RE.match(block)
        if match:
            flush()
            level = len(match.group(1))
            del stack[level - 1 :]
            stack.append(match.group(2).strip())
            path = " > ".join(stack)
        blocks.append(block)
    flush()
    return sections


def _split_oversized(block: str, max_tokens: int) -> list[str]:
    if count_tokens(block) <= max_tokens:
        return [block]
    units = block.split("\n") if "\n" in block else _SENTENCE_RE.split(block)
    pieces: list[str] = []
    cur: list[str] = []
    for unit in units:
        if count_tokens(unit) > max_tokens:
            step = max_tokens * _CHARS_PER_TOKEN
            unit_pieces = [unit[i : i + step] for i in range(0, len(unit), step)]
        else:
            unit_pieces = [unit]
        for piece in unit_pieces:
            if cur and _joined_tokens(cur + [piece], sep_len=1) > max_tokens:
                pieces.append(" ".join(cur))
                cur = []
            cur.append(piece)
    if cur:
        pieces.append(" ".join(cur))
    return pieces


def _pack(blocks: list[str], max_tokens: int, overlap_tokens: int) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    for block in blocks:
        for piece in _split_oversized(block, max_tokens):
            if cur and _joined_tokens(cur + [piece]) > max_tokens:
                chunks.append("\n\n".join(cur))
                tail: list[str] = []
                for prev in reversed(cur):
                    if _joined_tokens([prev] + tail) > overlap_tokens:
                        break
                    tail.insert(0, prev)
                cur = tail
                while cur and _joined_tokens(cur + [piece]) > max_tokens:
                    cur = cur[1:]
            cur.append(piece)
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def chunk_markdown(
    markdown: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path, blocks in _parse_sections(markdown):
        for content in _pack(blocks, max_tokens, overlap_tokens):
            chunks.append(
                Chunk(
                    chunk_index=len(chunks),
                    content=content,
                    metadata={"section_path": path, "token_count": count_tokens(content)},
                )
            )
    return chunks
