"""Adapts LLM markdown to what Discord can actually render.

Discord handles bold/italic, `code`, fenced code, `#`-`###` headings, lists and `>` quotes natively,
but shows tables, `####`+ headings, horizontal rules and LaTeX as raw text, and treats `__x__` as underline
instead of bold. Replies with no markdown are left untouched.
The text fallback shows display LaTeX in code blocks and converts inline LaTeX to Unicode where possible.
"""
import re
import unicodedata
from dataclasses import dataclass

from latex import latex_to_unicode

DISCORD_MESSAGE_LIMIT = 2000

_LATEX_BLOCK_RE = re.compile(
  r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|"
  r"\\begin\{(?P<env>(?:align(?:ed)?|gather(?:ed)?|multline|equation)\*?)\}.*?\\end\{(?P=env)\}",
  re.S,
)
_MARKDOWN_PATTERNS = [
  re.compile(r"^#{1,6}\s+\S", re.M),                     # heading
  re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S", re.M),       # list item
  re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__"),            # bold
  re.compile(r"`"),                                      # inline/fenced code
  re.compile(r"^\s*>", re.M),                            # blockquote
  re.compile(r"!?\[[^\]\n]+\]\([^)\s]+\)"),              # link/image
  re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?\s*$", re.M),  # table separator row
  re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$", re.M),     # horizontal rule
  _LATEX_BLOCK_RE,
  re.compile(r"\$\$|\\\(|\\\["),                         # LaTeX delimiters
  re.compile(r"\$(?=\S)[^$\n]*[\\^_{}=][^$\n]*?(?<=\S)\$(?!\d)"),  # inline LaTeX
]
_FENCE_RE = re.compile(r"^```.*?^```[ \t]*$", re.M | re.S)
_LATEX_INLINE_RE = re.compile(r"\\\((.+?)\\\)|\$(?=\S)([^$\n]+?)(?<=\S)\$(?!\d)")
_LATEX_HINT_RE = re.compile(r"[\\^_{}=]")
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)[^\n]+?(?<!`)\1(?!`)")  # also ``double`` spans containing a `
_URL = r"((?:[^()\s<>]|\([^()\s]*\))+)"  # allows one level of balanced parens, e.g. Wikipedia links
_IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\(" + _URL + r"\)")
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(<?" + _URL + r">?\)")
_BARE_URL_RE = re.compile(r"https?://[^\s<>]+")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
_HR_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
_TASK_RE = re.compile(r"^(\s*)[-*+]\s+\[([ xX])\]\s+")
_DOUBLE_UNDERSCORE_RE = re.compile(r"(?<![\w_])__(?=\S)([^_\n]+?)(?<=\S)__(?![\w_])")
_PLACEHOLDER_RE = re.compile("\x00(\\d+)\x00")
_EQUATION_RE = re.compile("\x01(\\d+)\x01")
_MARKDOWN_CHAR_RE = re.compile(r"([*_~|`\\])")


@dataclass(frozen=True)
class Equation:
  tex: str
  display: bool


def has_markdown(text):
  return bool(text) and any(p.search(text) for p in _MARKDOWN_PATTERNS)


def render_for_discord(text):
  """Returns `text` unchanged if it has no markdown, else rewritten into Discord-renderable markdown (equations as code blocks)."""
  text, equations = _render(text)
  if not equations:
    return text
  return "\n".join(
    f"```\n{part.tex}\n```" if isinstance(part, Equation) else part.strip()
    for part in equation_parts(text, equations)
    if isinstance(part, Equation) or part.strip()
  )


def proof_markup(text):
  """Returns the proof Markdown with math placeholders, or None for a reply without display math."""
  if not _LATEX_BLOCK_RE.search(text):
    return None
  markup, equations = _render(text, keep_inline_math=True)
  if any(eq.display for eq in equations):
    return markup, equations


def equation_parts(text, equations):
  """Yields text spans and equations in their original reading order."""
  for i, chunk in enumerate(_EQUATION_RE.split(text)):
    if i % 2:
      yield equations[int(chunk)]
    elif chunk:
      yield chunk


def _render(text, keep_inline_math=False):
  """Returns (rewritten text, equations); display equations are left as \\x01<index>\\x01 tokens."""
  if not has_markdown(text):
    return text, []

  protected = []
  equations = []

  def equation(source, tex, display=True):
    if "\x00" in tex:  # spans a protected code snippet, so it isn't really an equation
      return source
    equations.append(Equation(tex.strip(), display))
    return f"\x01{len(equations) - 1}\x01"

  def protect(snippet):
    protected.append(snippet)
    return f"\x00{len(protected) - 1}\x00"

  text = text.replace("\r\n", "\n").replace("\x00", "\uFFFD").replace("\x01", "\uFFFD")
  text = _FENCE_RE.sub(lambda m: protect(m.group(0)), text)
  text = _convert_tables(text, protect)  # before equations, so math inside a table stays in its code block
  text = _INLINE_CODE_RE.sub(lambda m: protect(m.group(0)), text)  # before equations, so `$$x$$` stays code
  text = _LATEX_BLOCK_RE.sub(lambda m: equation(m.group(0), m.group(1) or m.group(2) or m.group(0)), text)
  text = _LATEX_INLINE_RE.sub(_inline_latex(protect, equation if keep_inline_math else None), text)
  text = _IMAGE_RE.sub(lambda m: protect(f"[{m.group(1).strip() or 'image'}]({m.group(2)})"), text)
  text = _LINK_RE.sub(lambda m: protect(_format_link(m.group(1), m.group(2))), text)
  text = _BARE_URL_RE.sub(lambda m: protect(m.group(0)), text)  # keep `__`/`*` inside URLs from becoming formatting
  text = "\n".join(_convert_line(line) for line in text.split("\n"))
  text = _DOUBLE_UNDERSCORE_RE.sub(r"**\1**", text)
  text = re.sub(r"\n{3,}", "\n\n", text).strip()

  # Placeholders can nest (e.g. inline code inside a link label), so restore until stable.
  while _PLACEHOLDER_RE.search(text):
    text = _PLACEHOLDER_RE.sub(lambda m: protected[int(m.group(1))], text)
  return text, equations


def _inline_latex(protect, equation):
  def replace(m):
    tex = m.group(1) if m.group(1) is not None else m.group(2)
    # Bare `$...$` only counts as LaTeX if it looks like math, so prices like "$5 or $10" survive.
    if m.group(1) is None and not _LATEX_HINT_RE.search(tex):
      if equation is None or len(tex.split()) != 1:
        return m.group(0)
    if equation is not None:
      return equation(m.group(0), tex, display=False)
    plain = latex_to_unicode(tex)
    return protect(_MARKDOWN_CHAR_RE.sub(r"\\\1", plain) if plain else f"`{tex.strip()}`")
  return replace


def _format_link(label, url):
  label = label.strip()
  # Discord rejects masked links whose label is itself a URL, so show the bare URL instead.
  if label == url or re.match(r"https?://", label):
    return url
  return f"[{label}]({url})"


def _convert_line(line):
  if _HR_RE.match(line):
    return ""
  heading = _HEADING_RE.match(line)
  if heading:
    level, title = len(heading.group(1)), heading.group(2)
    # Discord only renders #, ## and ###; anything deeper shows the hashes literally.
    return f"{heading.group(1)} {title}" if level <= 3 else f"**{title}**"
  task = _TASK_RE.match(line)
  if task:
    box = "☐" if task.group(2) == " " else "☑"
    return f"{task.group(1)}- {box} {line[task.end():]}"
  # Discord doesn't nest quotes, so `> > x` would show a literal `>`.
  quote = re.match(r"^\s*>\s*>[>\s]*", line)
  if quote and not line.startswith(">>> "):
    return f"> {line[quote.end():]}"
  return line


def _split_row(line):
  line = line.strip()
  if line.startswith("|"):
    line = line[1:]
  if line.endswith("|") and not line.endswith("\\|"):
    line = line[:-1]
  return [_plain_cell(cell) for cell in re.split(r"(?<!\\)\|", line)]


def _plain_cell(cell):
  cell = cell.replace("\\|", "|").strip()
  cell = _LINK_RE.sub(r"\1", cell)
  cell = re.sub(r"(\*\*|__|~~|`)", "", cell)
  return re.sub(r"(?<!\w)[*_](\S(?:.*?\S)?)[*_](?!\w)", r"\1", cell)


def _display_width(s):
  return sum(2 if unicodedata.east_asian_width(c) in "WF" else 0 if unicodedata.combining(c) else 1 for c in s)


def _pad(s, width):
  return s + " " * (width - _display_width(s))


def _convert_tables(text, protect):
  """Markdown tables render as raw pipes in Discord, so they become aligned monospace code blocks."""
  lines = text.split("\n")
  out = []
  i = 0
  while i < len(lines):
    is_table = (
      i + 1 < len(lines)
      and "|" in lines[i]
      and "|" in lines[i + 1]
      and _TABLE_SEPARATOR_RE.match(lines[i + 1])
    )
    if not is_table:
      out.append(lines[i])
      i += 1
      continue

    rows = [_split_row(lines[i])]
    i += 2
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
      rows.append(_split_row(lines[i]))
      i += 1

    columns = max(len(r) for r in rows)
    rows = [r + [""] * (columns - len(r)) for r in rows]
    widths = [max(_display_width(r[c]) for r in rows) for c in range(columns)]
    rendered = [" | ".join(_pad(cell, widths[c]) for c, cell in enumerate(r)).rstrip() for r in rows]
    rendered.insert(1, "-+-".join("-" * w for w in widths))
    out.append(protect("```\n" + "\n".join(rendered) + "\n```"))
  return "\n".join(out)


def split_message(text, limit=DISCORD_MESSAGE_LIMIT):
  """Splits on line boundaries into chunks under `limit`, closing and reopening code fences across chunks."""
  if len(text) <= limit:
    return [text]

  chunks = []
  current = ""
  fence = None  # the opening ``` line of the code block we're inside, if any

  def flush():
    nonlocal current
    body = current.rstrip("\n")
    if fence:
      body += "\n```"
    if body.strip() and body.strip() != fence:
      chunks.append(body)
    current = f"{fence}\n" if fence else ""

  for line in text.split("\n"):
    # Room for a closing "\n```", including when this line opens a fence, since flush() would have to close it.
    reserve = 4 if fence or line.startswith("```") else 0
    while len(current) + len(line) + 1 + reserve > limit:
      room = limit - len(current) - reserve - 1
      if current.strip() and current.strip() != fence:
        flush()
        continue
      # A single line longer than a whole message: hard-split it.
      current += line[:room] + "\n"
      line = line[room:]
      flush()
    current += line + "\n"
    if line.startswith("```"):
      fence = None if fence else line.strip()
  flush()
  return chunks
