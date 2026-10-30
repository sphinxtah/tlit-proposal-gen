"""Formatting-preserving text replacement for Word (w:p) and PowerPoint (a:p) paragraphs.

A value is often split across several runs (Word splits text on every edit). Replacement
writes the new text into the run where the match begins and trims the matched characters
from the following runs, so every surrounding character keeps its original formatting.
"""
import copy
import re

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'


def _ns(element):
    return element.tag[:element.tag.index('}') + 1]


def paragraphs(root):
    """Every Word or DrawingML paragraph under root, including those in text boxes and tables."""
    return [e for e in root.iter() if isinstance(e.tag, str) and e.tag in (W + 'p', A + 'p')]


def _texts(p):
    """Text nodes that belong to p itself, not to a paragraph nested inside it (Word text boxes)."""
    ttag = _ns(p) + 't'
    out = []
    for t in p.iter(ttag):
        owner = t.getparent()
        while owner is not None and owner.tag != p.tag:
            owner = owner.getparent()
        if owner is p:
            out.append(t)
    return out


def text(p):
    return ''.join(t.text or '' for t in _texts(p))


def replace(p, old, new):
    """Replace every occurrence of old inside paragraph p. Returns the number of replacements."""
    count, start = 0, 0
    while True:
        nodes = _texts(p)
        full = ''.join(t.text or '' for t in nodes)
        i = full.find(old, start)
        if i < 0 or not old:
            return count
        end, pos, first = i + len(old), 0, True
        for t in nodes:
            s = t.text or ''
            a, b = pos, pos + len(s)
            pos = b
            if b <= i or a >= end:
                continue
            lo, hi = max(i, a) - a, min(end, b) - a
            if first:
                t.text = s[:lo] + new + s[hi:]
                first = False
            else:
                t.text = s[:lo] + s[hi:]
            if t.tag == W + 't':
                t.set(XML_SPACE, 'preserve')
        count += 1
        start = i + len(new)


def replace_regex(p, pattern, new, count=0):
    """Replace regex matches (within the paragraph's combined text) while keeping run formatting."""
    done = 0
    for match in list(re.finditer(pattern, text(p))):
        done += replace(p, match.group(0), new)
        if count and done >= count:
            break
    return done


def replace_all(root, old, new):
    return sum(replace(p, old, new) for p in paragraphs(root) if old in text(p))


def fill_lines(p, token, lines):
    """Replace token with lines[0] and add one copy of the paragraph per extra line, in order."""
    lines = list(lines) or ['']
    clones = [copy.deepcopy(p) for _ in lines[1:]]
    replace(p, token, lines[0])
    anchor = p
    for clone, line in zip(clones, lines[1:]):
        replace(clone, token, line)
        anchor.addnext(clone)
        anchor = clone
    return [p] + clones
