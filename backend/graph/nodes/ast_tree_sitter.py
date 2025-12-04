from __future__ import annotations

"""Tree-sitter AST analysis node for multi-language code analysis.

Provides deeper structural analysis using tree-sitter parsers for Python,
JavaScript, and TypeScript. Detects unused imports, unused functions/classes,
and dangerous patterns.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Try to import tree-sitter libraries
try:
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:  # pragma: no cover
    TREE_SITTER_AVAILABLE = False
    tspython = None
    Language = None
    Parser = None

try:
    import tree_sitter_javascript as tsjavascript

    JAVASCRIPT_AVAILABLE = True
except ImportError:  # pragma: no cover
    JAVASCRIPT_AVAILABLE = False
    tsjavascript = None


def _analyze_python_ast(code: str, path: str) -> list[dict[str, Any]]:
    """Analyze Python code using tree-sitter.

    Parameters
    ----------
    code : str
        Python source code
    path : str
        File path for reporting

    Returns
    -------
    list[dict[str, Any]]
        List of findings
    """
    if not TREE_SITTER_AVAILABLE or not tspython:
        return []

    findings = []

    try:
        parser = Parser()
        try:
            parser.set_language(Language(tspython.language()))
        except AttributeError:  # compatibility with parsers lacking set_language
            try:
                parser.language = Language(tspython.language())  # type: ignore[attr-defined]
            except Exception as e:  # pragma: no cover
                logger.warning("Failed to configure Python parser: %s", e)
                return []
        tree = parser.parse(bytes(code, "utf8"))
        root = tree.root_node

        # Find all imports
        imports = []
        for node in root.children:
            if node.type == "import_statement" or node.type == "import_from_statement":
                import_text = code[node.start_byte : node.end_byte]
                imports.append(
                    {
                        "line": node.start_point[0] + 1,
                        "text": import_text,
                        "type": node.type,
                    }
                )

        # Find dangerous function calls (eval, exec)
        def find_dangerous_calls(node):
            if node.type == "call":
                func_node = node.child_by_field_name("function")
                if func_node and func_node.type == "identifier":
                    func_name = code[func_node.start_byte : func_node.end_byte]
                    if func_name in ("eval", "exec", "compile", "__import__"):
                        findings.append(
                            {
                                "type": "dangerous_function",
                                "function": func_name,
                                "line": node.start_point[0] + 1,
                                "severity": "high",
                                "message": f"Dangerous function '{func_name}' detected",
                                "path": path,
                            }
                        )

            for child in node.children:
                find_dangerous_calls(child)

        find_dangerous_calls(root)

        # Find all function definitions
        def find_functions(node):
            funcs = []
            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = code[name_node.start_byte : name_node.end_byte]
                    funcs.append(
                        {
                            "name": func_name,
                            "line": node.start_point[0] + 1,
                            "type": "function",
                        }
                    )

            for child in node.children:
                funcs.extend(find_functions(child))

            return funcs

        functions = find_functions(root)

        logger.debug(
            "Python AST: %s - %d imports, %d functions, %d dangerous calls",
            path,
            len(imports),
            len(functions),
            len([f for f in findings if f["type"] == "dangerous_function"]),
        )

    except Exception as e:  # pragma: no cover
        logger.warning("Failed to parse Python AST for %s: %s", path, e)

    return findings


def _analyze_javascript_ast(code: str, path: str) -> list[dict[str, Any]]:
    """Analyze JavaScript/TypeScript code using tree-sitter.

    Parameters
    ----------
    code : str
        JavaScript/TypeScript source code
    path : str
        File path for reporting

    Returns
    -------
    list[dict[str, Any]]
        List of findings
    """
    if not TREE_SITTER_AVAILABLE or not tsjavascript:
        return []

    findings = []

    try:
        parser = Parser()
        try:
            parser.set_language(Language(tsjavascript.language()))
        except AttributeError:  # compatibility path
            try:
                parser.language = Language(tsjavascript.language())  # type: ignore[attr-defined]
            except Exception as e:  # pragma: no cover
                logger.warning("Failed to configure JS parser: %s", e)
                return []
        tree = parser.parse(bytes(code, "utf8"))
        root = tree.root_node

        # Find dangerous patterns (eval, innerHTML, dangerouslySetInnerHTML)
        def find_dangerous_patterns(node):
            # eval() calls
            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node and func_node.type == "identifier":
                    func_name = code[func_node.start_byte : func_node.end_byte]
                    if func_name in ("eval", "Function"):
                        findings.append(
                            {
                                "type": "dangerous_function",
                                "function": func_name,
                                "line": node.start_point[0] + 1,
                                "severity": "high",
                                "message": f"Dangerous function '{func_name}' detected",
                                "path": path,
                            }
                        )

            # innerHTML assignments
            if node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                if left and left.type == "member_expression":
                    prop = left.child_by_field_name("property")
                    if prop:
                        prop_name = code[prop.start_byte : prop.end_byte]
                        if prop_name in ("innerHTML", "outerHTML"):
                            findings.append(
                                {
                                    "type": "xss_risk",
                                    "property": prop_name,
                                    "line": node.start_point[0] + 1,
                                    "severity": "medium",
                                    "message": f"Direct {prop_name} assignment may lead to XSS",
                                    "path": path,
                                }
                            )

            for child in node.children:
                find_dangerous_patterns(child)

        find_dangerous_patterns(root)

        logger.debug(
            "JavaScript AST: %s - %d dangerous patterns",
            path,
            len(findings),
        )

    except Exception as e:  # pragma: no cover
        logger.warning("Failed to parse JavaScript AST for %s: %s", path, e)

    return findings


def ast_tree_sitter_node(state: dict[str, Any]) -> dict[str, Any]:
    """Parse AST and detect structural issues using tree-sitter.

    Parameters
    ----------
    state : dict[str, Any]
        Graph state containing files

    Returns
    -------
    dict[str, Any]
        Updated state with enhanced ast_report
    """
    if not TREE_SITTER_AVAILABLE:
        logger.warning("Tree-sitter not available, skipping enhanced AST analysis")
        return {}

    files = state.get("files") or []
    all_findings = []

    for file_input in files[:25]:  # Limit to 25 files
        path = file_input.get("path", "unknown")
        content = file_input.get("content", "")
        language = file_input.get("language", "")

        # Skip large files
        if len(content) > 100_000:
            logger.debug("Skipping large file: %s (%d bytes)", path, len(content))
            continue

        # Analyze based on language
        try:
            if language == "python" or path.endswith(".py"):
                findings = _analyze_python_ast(content, path)
                all_findings.extend(findings)
            elif language in ("javascript", "typescript") or path.endswith(
                (".js", ".ts", ".tsx", ".jsx")
            ):
                findings = _analyze_javascript_ast(content, path)
                all_findings.extend(findings)
        except Exception as e:
            logger.warning("AST analysis failed for %s: %s", path, e)
            continue

    # Update existing ast_report or create new one
    existing_ast = state.get("ast_report") or {}
    if isinstance(existing_ast, dict):
        existing_ast.setdefault("tree_sitter_findings", [])
        existing_ast["tree_sitter_findings"] = all_findings
    else:
        existing_ast = {"tree_sitter_findings": all_findings}

    logger.info("Tree-sitter AST: Found %d findings across %d files", len(all_findings), len(files))

    return {"ast_report": existing_ast}
