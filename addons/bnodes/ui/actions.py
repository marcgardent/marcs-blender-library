"""What the operators do, kept apart from them so tests can call it without a UI."""

import bpy

from ..host import build_source, export_tree
from ..host.builder import LINE
from ..lang import BnError
from ..lang.format import format_source

EXT = ".bn"

# Per text name, for the panel: errors of the last build, warnings of the last export.
# Runtime only: they are not saved with the file.
DIAGNOSTICS = {}
WARNINGS = {}


def is_bn(text):
    return text is not None and text.name.endswith(EXT)


def linked_trees(text):
    return [g for g in bpy.data.node_groups if g.bnodes_text == text]


def text_to_tree(text):
    """Build every graph of the text and link the trees to it. Raises BnError."""
    DIAGNOSTICS.pop(text.name, None)
    try:
        trees = build_source(text.as_string(), text.name)
    except BnError as e:
        DIAGNOSTICS[text.name] = e.diagnostics
        first = e.diagnostics[0]
        text.cursor_set(first.line - 1, character=max(0, first.col - 1))
        raise
    for tree in trees:
        tree.bnodes_text = text
    return trees


def format_text(text):
    """Rewrite the text in the canonical layout. True when it changed; raises BnError.

    Its linked trees are built again, so that their nodes keep pointing at the right lines.
    """
    source = text.as_string()
    DIAGNOSTICS.pop(text.name, None)
    try:
        formatted = format_source(source, text.name)
    except BnError as e:
        DIAGNOSTICS[text.name] = e.diagnostics
        first = e.diagnostics[0]
        text.cursor_set(first.line - 1, character=max(0, first.col - 1))
        raise
    if formatted == source:
        return False
    line, char = text.current_line_index, text.current_character
    text.from_string(formatted)
    line = min(line, len(text.lines) - 1)
    text.cursor_set(line, character=min(char, len(text.lines[line].body)))
    if linked_trees(text):
        try:
            text_to_tree(text)
        except BnError:
            pass  # the panel lists the errors; the text is formatted all the same
    return True


def tree_to_text(tree):
    """Write the tree (and the groups it calls) into its text, created when needed."""
    source, warnings = export_tree(tree)
    text = tree.bnodes_text or bpy.data.texts.get(tree.name + EXT)
    if text is None:
        text = bpy.data.texts.new(tree.name + EXT)
    text.from_string(source)
    text.cursor_set(0)
    tree.bnodes_text = text
    WARNINGS[text.name] = warnings
    DIAGNOSTICS.pop(text.name, None)
    return text, warnings


def node_line(node):
    """1-based source line of a node, or None for a node the text did not build."""
    return node.get(LINE)


def nodes_on_line(tree, line):
    return [n for n in tree.nodes if n.get(LINE) == line]
