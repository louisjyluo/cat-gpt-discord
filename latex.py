"""Best-effort Unicode for inline LaTeX in Discord text replies."""
import re

_SYMBOLS = {
  "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
  "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν",
  "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ",
  "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
  "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
  "cdot": "·", "times": "×", "div": "÷", "pm": "±", "mp": "∓", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥",
  "neq": "≠", "ne": "≠", "approx": "≈", "equiv": "≡", "sim": "∼", "propto": "∝", "infty": "∞",
  "partial": "∂", "nabla": "∇", "sum": "∑", "prod": "∏", "int": "∫", "oint": "∮", "to": "→",
  "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒", "Leftarrow": "⇐", "leftrightarrow": "↔",
  "Leftrightarrow": "⇔", "implies": "⇒", "iff": "⇔", "mapsto": "↦", "in": "∈", "notin": "∉", "ni": "∋",
  "subset": "⊂", "subseteq": "⊆", "supset": "⊃", "supseteq": "⊇", "cup": "∪", "cap": "∩",
  "emptyset": "∅", "varnothing": "∅", "forall": "∀", "exists": "∃", "neg": "¬", "lnot": "¬", "land": "∧",
  "wedge": "∧", "lor": "∨", "vee": "∨", "circ": "∘", "degree": "°", "ldots": "…", "dots": "…", "cdots": "⋯",
  "prime": "′", "angle": "∠", "perp": "⊥", "parallel": "∥", "hbar": "ℏ", "ell": "ℓ", "star": "⋆",
  "ast": "∗", "langle": "⟨", "rangle": "⟩", "lfloor": "⌊", "rfloor": "⌋", "lceil": "⌈", "rceil": "⌉",
  "sqrt": "√", "quad": " ", "qquad": "  ",
  **{f: f for f in ("sin", "cos", "tan", "sec", "csc", "cot", "arcsin", "arccos", "arctan", "sinh", "cosh",
                    "tanh", "log", "ln", "exp", "lim", "max", "min", "sup", "inf", "det", "gcd", "mod")},
  "left": "", "right": "", "big": "", "Big": "", "bigg": "", "Bigg": "",
}
_SUPERSCRIPTS = dict(zip(
  "0123456789+-=()abcdefghijklmnoprstuvwxyzABDEGHIJKLMNOPRTUVW",
  "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂ",
))
_SUPERSCRIPTS.update({"′": "′", "∗": "*", " ": ""})
_SUBSCRIPTS = dict(zip("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"))
_SUBSCRIPTS[" "] = ""

_TEXT_CMD_RE = re.compile(r"\\(?:text|mathrm|mathit|mathbf|mathsf|textbf|textit|operatorname)\s*\{([^{}]*)\}")
_FRAC_RE = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_SQRT_RE = re.compile(r"√\s*\{([^{}]*)\}")
_SCRIPT_RE = re.compile(r"([\^_])(?:\{([^{}]*)\}|([^\s{}\\]))")
_COMMAND_RE = re.compile(r"\\([A-Za-z]+)")
_ESCAPE_RE = re.compile(r"\\([%$#&{}_ ,;:!|])")


def clean_tex(tex):
  tex = re.sub(r"\\(?:displaystyle|textstyle)\b", "", tex)
  tex = re.sub(r"\\[dt]frac\b", r"\\frac", tex)
  return re.sub(r"\s+", " ", tex).strip()


def latex_to_unicode(tex):
  """Best-effort plain-text rendering, e.g. `E = mc^2` -> `E = mc²`. Returns None if it can't be done faithfully."""
  tex = _TEXT_CMD_RE.sub(r"\1", clean_tex(tex))

  def command(m):
    return _SYMBOLS.get(m.group(1), m.group(0))
  tex = _COMMAND_RE.sub(command, tex)
  tex = _ESCAPE_RE.sub(lambda m: m.group(1) if m.group(1) in "%$#&{}_|" else " ", tex)

  def wrap(s):
    s = s.strip()
    return s if len(s) == 1 or re.fullmatch(r"\w+", s) else f"({s})"

  def binds_after(m):
    nxt = m.string[m.end():m.end() + 1]
    return bool(nxt) and (nxt.isalnum() or nxt in "^_({√")

  def frac(m):
    # Keep the fraction grouped when something binds to it, so `\frac{2}{3}^2` reads (2/3)², not 2/3².
    prv = m.string[m.start() - 1:m.start()]
    s = f"{wrap(m.group(1))}/{wrap(m.group(2))}"
    return f"({s})" if binds_after(m) or (prv and (prv.isalnum() or prv in ")}/")) else s

  def sqrt(m):
    s = f"√{wrap(m.group(1))}"
    return f"({s})" if binds_after(m) else s

  for _ in range(10):  # innermost first, so nested fracs/roots/scripts unwind one level per pass
    before = tex
    tex = _FRAC_RE.sub(frac, tex)
    tex = _SQRT_RE.sub(sqrt, tex)
    tex = _SCRIPT_RE.sub(_script, tex)
    if tex == before:
      break

  tex = tex.replace("{", "").replace("}", "")
  if re.search(r"[\\^_\x00]", tex):
    return None
  return re.sub(r"\s+", " ", tex).strip()


def _script(m):
  table = _SUPERSCRIPTS if m.group(1) == "^" else _SUBSCRIPTS
  body = m.group(2) if m.group(2) is not None else m.group(3)
  if body and all(c in table for c in body):
    return "".join(table[c] for c in body)
  return "\x00"  # unconvertible (nested script, Greek subscript, ...) poisons the result
