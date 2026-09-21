import ast


class SecurityError(Exception):
    """Exception raised when code violates sandbox security policies."""
    pass


class ImportSecurityValidator(ast.NodeVisitor):
    """AST visitor that validates imports against an allowlist."""
    def __init__(self, authorized_imports: list[str]) -> None:
        super().__init__()
        self.authorized_imports = authorized_imports

    def _is_module_allowed(self, module_name: str) -> bool:
        """Check if a module name matches the authorized imports allowlist."""
        for pattern in self.authorized_imports:
            if pattern == module_name:
                return True
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if (prefix == module_name or
                        module_name.startswith(f"{prefix}.")):
                    return True
        return False

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if not self._is_module_allowed(alias.name):
                raise SecurityError("Unauthorized import detected: "
                                    f"'{alias.name}' (line {node.lineno})")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level > 0:
            raise SecurityError("Relative imports not allowed")
        if node.level == 0:
            if node.module and not self._is_module_allowed(node.module):
                raise SecurityError(f"{node.module} is a forbidden module.")
        self.generic_visit(node)
