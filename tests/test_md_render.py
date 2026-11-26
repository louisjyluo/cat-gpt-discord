import unittest

from latex import latex_to_unicode
from md_render import Equation, equation_parts, has_markdown, proof_markup, render_for_discord, split_message
from proof_render import render_proof_png


class HasMarkdownTests(unittest.TestCase):
  def test_plain_text_is_not_markdown(self):
    for text in ["Meow! Strawberry has three r's, human.", "It costs $5 or $10, mrow.", "snake_case_name", ""]:
      self.assertFalse(has_markdown(text), text)

  def test_detects_common_markdown(self):
    for text in ["# Title", "- item", "**bold**", "use `x`", "> quote", "[a](https://a.com)", "a | b\n--|--", "---", "$$x^2$$"]:
      self.assertTrue(has_markdown(text), text)


class RenderTests(unittest.TestCase):
  def test_plain_text_is_unchanged(self):
    text = "Mrow, *purrs*. Prices: $5-$10. See https://example.com"
    self.assertEqual(render_for_discord(text), text)

  def test_supported_markdown_is_kept(self):
    text = "## Cats\n- **fluffy**\n- *sleepy*\n> wise words"
    self.assertEqual(render_for_discord(text), text)

  def test_deep_headings_become_bold(self):
    self.assertEqual(render_for_discord("#### Deep\ntext"), "**Deep**\ntext")
    self.assertEqual(render_for_discord("### Learn C#"), "### Learn C#")

  def test_horizontal_rules_are_removed(self):
    self.assertEqual(render_for_discord("# A\n\n---\n\nB"), "# A\n\nB")

  def test_table_becomes_code_block(self):
    text = "Cats:\n\n| Name | **Age** |\n|:-----|----:|\n| Tom | 3 |\n| Whiskers | 12 |\n\nmeow"
    expected = (
      "Cats:\n\n```\n"
      "Name     | Age\n"
      "---------+----\n"
      "Tom      | 3\n"
      "Whiskers | 12\n"
      "```\n\nmeow"
    )
    self.assertEqual(render_for_discord(text), expected)

  def test_links(self):
    # Previews are suppressed at send time (suppress_embeds), so links pass through.
    self.assertEqual(render_for_discord("- [Cats](https://a.com/x)"), "- [Cats](https://a.com/x)")
    self.assertEqual(render_for_discord("- [Cats](<https://a.com/x>)"), "- [Cats](https://a.com/x)")
    self.assertEqual(render_for_discord("- [https://a.com](https://a.com)"), "- https://a.com")
    self.assertEqual(render_for_discord("- see https://a.com/__x__/y."), "- see https://a.com/__x__/y.")

  def test_links_with_parens(self):
    url = "https://en.wikipedia.org/wiki/Cat_(animal)"
    self.assertEqual(render_for_discord(f"**[Cat]({url})**"), f"**[Cat]({url})**")

  def test_code_spans_keep_display_math(self):
    for text in ["- try `$$x^2$$` here", "- try ``a ` $$x^2$$`` here"]:
      self.assertEqual(render_for_discord(text), text)
      self.assertIsNone(proof_markup(text))

  def test_code_is_left_alone(self):
    text = "**Code:**\n```py\n#### not a heading\n__init__ | x\n---\n```\nand `__x__ https://a.com`"
    self.assertEqual(render_for_discord(text), text)

  def test_double_underscore_means_bold(self):
    self.assertEqual(render_for_discord("- __big__ cat"), "- **big** cat")

  def test_latex_becomes_code(self):
    self.assertEqual(render_for_discord("Area: $$\\pi r^2$$"), "Area:\n```\n\\pi r^2\n```")
    self.assertEqual(render_for_discord("**E** is \\(mc^2\\)"), "**E** is mc²")
    self.assertEqual(render_for_discord("**x** $a^2$ costs $5 or $10"), "**x** a² costs $5 or $10")
    self.assertEqual(render_for_discord("Mrow $e^{-x^2}$"), "Mrow `e^{-x^2}`")  # nested superscript: no Unicode form

  def test_task_lists_and_nested_quotes(self):
    self.assertEqual(render_for_discord("- [ ] nap\n- [x] eat"), "- ☐ nap\n- ☑ eat")
    self.assertEqual(render_for_discord("> > nested"), "> nested")


class LatexUnicodeTests(unittest.TestCase):
  def test_converts_simple_math(self):
    cases = {
      "E = mc^2": "E = mc²",
      "a_{ij} \\leq x_1": "aᵢⱼ ≤ x₁",
      "\\frac{\\pi}{2}": "π/2",
      "\\frac{a+b}{2}": "(a+b)/2",
      "\\sqrt{x^2 + 1}": "√(x² + 1)",
      "\\text{area} = \\pi r^2": "area = π r²",
      "\\left( x \\right)\\,\\cdot y": "( x ) · y",
      "\\sin \\theta": "sin θ",
      "\\frac{2}{3}^2": "(2/3)²",
      "\\frac{1}{2}x": "(1/2)x",
      "x\\frac{1}{2}": "x(1/2)",
      "y = \\frac{1}{2} x": "y = 1/2 x",
      "\\sqrt{x}^2": "(√x)²",
    }
    for tex, expected in cases.items():
      self.assertEqual(latex_to_unicode(tex), expected, tex)

  def test_gives_up_when_unfaithful(self):
    for tex in ["e^{-x^2}", "x_\\alpha", "\\begin{pmatrix}1\\end{pmatrix}", "\\unknowncmd x", "a \\\\ b"]:
      self.assertIsNone(latex_to_unicode(tex), tex)


class EquationPartsTests(unittest.TestCase):
  def test_plain_and_inline_only_replies_remain_text(self):
    for text in ["meow", "Let \\(x^2\\) be a square."]:
      self.assertIsNone(proof_markup(text))

  def test_proof_preserves_prose_and_both_kinds_of_math_in_order(self):
    markup, equations = proof_markup(r"**Area:** for $r$ use $$\pi r^2$$ or \[xy\] as needed.")
    self.assertEqual(
      list(equation_parts(markup, equations)),
      ["**Area:** for ", Equation("r", False), " use ", Equation(r"\pi r^2", True),
       " or ", Equation("xy", True), " as needed."],
    )

  def test_math_in_code_or_tables_does_not_trigger_proof_rendering(self):
    text = "| a | b |\n|---|---|\n| $$x$$ | 1 |\n\n```\n$$y$$\n```"
    self.assertIsNone(proof_markup(text))


class ProofImageTests(unittest.TestCase):
  def test_renders_aligned_steps_and_matrices_on_the_same_page(self):
    text = (
      r"**Proof.** Take \(A=I\). "
      "\n" r"\begin{align*}A^2 &= I^2 \\ &= I\end{align*}" "\n"
      r"where \[I = \begin{pmatrix}1 & 0 \\ 0 & 1\end{pmatrix}.\]"
    )
    self.assertTrue(render_proof_png(text).startswith(b"\x89PNG"))

  def test_unsupported_returns_none(self):
    self.assertIsNone(render_proof_png(r"$$\madeupcommand{x}$$"))


class SplitTests(unittest.TestCase):
  def test_short_text_is_one_chunk(self):
    self.assertEqual(split_message("meow"), ["meow"])

  def test_splits_on_lines_under_limit(self):
    text = "\n".join(f"line {i}" for i in range(100))
    chunks = split_message(text, limit=50)
    self.assertTrue(all(len(c) <= 50 for c in chunks))
    self.assertEqual("\n".join(chunks), text)

  def test_code_fences_are_reopened(self):
    text = "intro\n```py\n" + "\n".join(f"x = {i}" for i in range(30)) + "\n```\nouttro"
    chunks = split_message(text, limit=60)
    self.assertTrue(all(len(c) <= 60 for c in chunks))
    for chunk in chunks:
      self.assertEqual(chunk.count("```") % 2, 0, chunk)

  def test_fences_fit_at_the_limit(self):
    for n in range(1985, 2001):
      for text in ["a" * n + "\n```py\nx = 1\n```", "a" * n + "\n```py\n" + "y" * 1990 + "\n```\nz"]:
        chunks = split_message(text)
        self.assertTrue(all(len(c) <= 2000 for c in chunks), (n, [len(c) for c in chunks]))
        for chunk in chunks:
          self.assertEqual(chunk.count("```") % 2, 0, n)

  def test_hard_splits_long_lines(self):
    chunks = split_message("a" * 250, limit=100)
    self.assertTrue(all(len(c) <= 100 for c in chunks))
    self.assertEqual("".join(chunks), "a" * 250)


if __name__ == "__main__":
  unittest.main()
