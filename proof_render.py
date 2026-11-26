"""Typeset a reply's prose and LaTeX on a single page for Discord."""

import io
import logging
import math
import re
import threading
from xml.etree import ElementTree as ET

from markdown_it import MarkdownIt
from PIL import Image, PngImagePlugin
from resvg_py import svg_to_bytes
from ziamath import Latex, Math

from md_render import Equation, equation_parts, proof_markup

PROOF_FILENAME = "proof.png"
_SOURCE_KEY = "CatGPT reply"
_ALT_TEXT_LIMIT = 1024

_WIDTH = 560
_MARGIN = 24
_TEXT_SIZE = 20
_MAX_HEIGHT = 4096
_MAX_SOURCE_LENGTH = 10_000
_render_lock = threading.Lock()  # Ziamath shares a font cache between renders.
_markdown = MarkdownIt("commonmark", {"html": False})
_log = logging.getLogger(__name__)


def proof_alt_text(text):
  # Keep within the attachment limit even when characters take two UTF-16 code units.
  encoded = text.encode("utf-16-le")
  if len(encoded) <= 2 * _ALT_TEXT_LIMIT:
    return text
  return encoded[:2 * (_ALT_TEXT_LIMIT - 1)].decode("utf-16-le", errors="ignore") + "…"


def read_proof_source(png):
  with Image.open(io.BytesIO(png), formats=["PNG"]) as image:
    return image.info.get(_SOURCE_KEY)


def needs_proof_source(description):
  return description and description.endswith("…") and len(description.encode("utf-16-le")) >= 2 * (_ALT_TEXT_LIMIT - 1)


def render_proof_png(text):
  """Returns one PNG for replies with display math, or None to send the text fallback."""
  if not text or len(text) > _MAX_SOURCE_LENGTH:
    return None
  marked = proof_markup(text)
  if marked is None:
    return None

  try:
    with _render_lock:
      svg = _layout(*marked)
    if svg is None:
      return None
    png = svg_to_bytes(svg_string=ET.tostring(svg, encoding="unicode"),
                       zoom=2, background="white", skip_system_fonts=True)
    if proof_alt_text(text) == text:
      return png
    # Discord's alt text is capped. Store the full reply in the original PNG for chat history.
    metadata = PngImagePlugin.PngInfo()
    metadata.add_itxt(_SOURCE_KEY, text)
    buf = io.BytesIO()
    with Image.open(io.BytesIO(png)) as image:
      image.save(buf, format="PNG", pnginfo=metadata)
    return buf.getvalue()
  except Exception:
    _log.debug("Could not render the LaTeX reply", exc_info=True)
    return None


def _text_shape(text, size, style="normal"):
  node = ET.Element("math")
  ET.SubElement(node, "mtext", mathvariant=style).text = text
  return Math(node, size=size)


def _inline_shapes(tokens, equations, size, heading):
  bold = int(heading)
  italic = 0
  for token in tokens:
    if token.type == "strong_open":
      bold += 1
    elif token.type == "strong_close":
      bold -= 1
    elif token.type == "em_open":
      italic += 1
    elif token.type == "em_close":
      italic -= 1
    elif token.type == "hardbreak":
      yield None, False
    elif token.type == "softbreak":
      yield " ", False
    elif token.type in {"text", "code_inline", "image"}:
      style = "bold-italic" if bold and italic else "bold" if bold else "italic" if italic else "normal"
      if token.type == "code_inline":
        yield _text_shape(token.content, size, "monospace"), False
        continue
      for part in equation_parts(token.content, equations):
        if isinstance(part, Equation):
          equation = Latex(part.tex, size=size, inline=not part.display)
          if any((node.text or "").startswith("\\") for node in equation.mathml.iter("mi")):
            raise ValueError("Unsupported LaTeX command")
          yield equation, part.display
        else:
          for word in re.findall(r"\s+|\S+", part):
            yield (" " if word.isspace() else _text_shape(word, size, style)), False


def _draw_line(svg, line, top, width, left, centered=False):
  last_x, last_shape = line[-1]
  line_width = last_x + last_shape.getsize()[0]
  scale = min(1, width / max(1, line_width))
  ascent = max(shape.getsize()[1] + shape.getyofst() for _, shape in line)
  descent = max(-shape.getyofst() for _, shape in line)
  x = left + (width - line_width * scale) / 2 if centered else left
  group = ET.SubElement(svg, "g", transform=f"translate({x} {top}) scale({scale})")
  for offset, shape in line:
    shape.drawon(group, offset, ascent)
  return top + max(_TEXT_SIZE, (ascent + descent) * scale) + 5


def _draw_paragraph(svg, tokens, equations, top, indent, marker, heading):
  size = _TEXT_SIZE + 5 if heading else _TEXT_SIZE
  left = _MARGIN + indent
  width = _WIDTH - left - _MARGIN
  line = []
  used = gap = 0
  if marker:
    _text_shape(marker, size).drawon(svg, left - size, top + size * 0.75)

  for shape, display in _inline_shapes(tokens, equations, size, heading):
    if shape == " ":
      gap = size / 4 if line else 0
      continue
    if display or shape is None or (gap and used + gap + shape.getsize()[0] > width):
      if line:
        top = _draw_line(svg, line, top, width, left)
      line = []
      used = gap = 0
    if display:
      top = _draw_line(svg, [(0, shape)], top + 4, width, left, centered=True) + 4
    elif shape is not None:
      line.append((used + gap, shape))
      used += gap + shape.getsize()[0]
      gap = 0
  return _draw_line(svg, line, top, width, left) if line else top


def _layout(markup, equations):
  svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", width=str(_WIDTH))
  top = _MARGIN
  heading = False
  indent = 0
  marker = ""
  for token in _markdown.parse(markup):
    if token.type == "heading_open":
      heading = True
    elif token.type in {"list_item_open", "blockquote_open"}:
      indent += 26
      marker = f"{token.info}." if token.info else "•" if token.type == "list_item_open" else "›"
    elif token.type in {"list_item_close", "blockquote_close"}:
      indent -= 26
      marker = ""
    elif token.type == "inline":
      top = _draw_paragraph(svg, token.children, equations, top, min(indent, 104), marker, heading) + 8
      heading = False
      marker = ""
    elif token.type in {"code_block", "fence"}:
      for line in token.content.expandtabs(4).splitlines():
        shape = _text_shape(line, _TEXT_SIZE, "monospace")
        top = _draw_line(svg, [(0, shape)], top, _WIDTH - 2 * _MARGIN, _MARGIN)
      top += 8
    if top + _MARGIN > _MAX_HEIGHT:
      return None
  svg.set("height", str(math.ceil(top + _MARGIN)))
  return svg
