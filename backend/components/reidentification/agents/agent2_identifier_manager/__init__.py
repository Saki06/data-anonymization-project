"""
Agent 2: Identifier Manager

All logic lives in identifier_manager.py.
User-mode only: validates user-provided QI lists and column mappings.
"""

from .identifier_manager import ColumnListValidator, IdentifierManager, IdentifierMapper

# Backward-compatible alias used by older imports.
QIValidator = ColumnListValidator

__all__ = ["IdentifierManager", "IdentifierMapper", "ColumnListValidator", "QIValidator"]
