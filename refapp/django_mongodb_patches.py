"""
Monkey patch for django-mongodb-backend to support dotted path field aliasing.

This patch enables using db_column with dotted paths like "address.city" to map
Django model fields to nested MongoDB document fields.

Features:
- Supports nested field access in MongoDB documents
- Hash-based verification to ensure compatibility with django-mongodb-backend
- Automatic detection of incompatible changes in the original methods

Usage:
    # In your Django settings or app initialization:
    from refapp import django_mongodb_patches
    django_mongodb_patches.apply_patches()

    # To skip verification (not recommended):
    django_mongodb_patches.apply_patches(verify=False)

    # To force patches even if verification fails (risky):
    django_mongodb_patches.apply_patches(force=True)

    # To update hashes after django-mongodb-backend update:
    django_mongodb_patches.update_method_hashes()
"""

import hashlib
import inspect
import logging
import warnings
from collections import defaultdict

from django.core.exceptions import EmptyResultSet, FullResultSet
from django.db.models.expressions import Col, Value
from django_mongodb_backend.compiler import SQLCompiler, SQLInsertCompiler

logger = logging.getLogger(__name__)


def _nested_set(d, keys, value):
    """Build nested dicts inside *d* from an iterable *keys*."""
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _nested_get(d, keys):
    """Safe access using dotted path; returns None if any segment is missing."""
    for k in keys:
        if d is None:
            return None
        d = d.get(k)
    return d


# Expected method hashes and signatures for verification
EXPECTED_METHOD_HASHES = {
    "SQLCompiler.get_project_fields": "a34d78e10485502d18567fdd909e030b4b9b2991250312c9471783ea18084e14",
    "SQLCompiler._make_result": "5e0aa9a3e05c83c352be6c9f4241747d0d750cc7d68cb5655bcee8ca6c111b3f",
    "SQLInsertCompiler.insert": "cb9f98a7f155f51a1f625025d979577daa7a65d2578a42d028e8ee4f96e43200",
}

EXPECTED_METHOD_SIGNATURES = {
    "SQLCompiler.get_project_fields": ["self", "columns", "ordering", "force_expression"],
    "SQLCompiler._make_result": ["self", "entity", "columns"],
    "SQLInsertCompiler.insert": ["self", "docs", "returning_fields"],
}


def verify_method_compatibility(method, method_name, expected_hash, expected_params):
    """
    Verify a method hasn't changed by checking its hash and signature.

    Returns:
        tuple: (is_compatible, error_message)
    """
    try:
        # Get method source and calculate hash
        source = inspect.getsource(method)
        actual_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()

        # Get method signature
        sig = inspect.signature(method)
        actual_params = list(sig.parameters.keys())

        # Check hash first
        if actual_hash != expected_hash:
            return False, (
                f"Method {method_name} source code has changed.\n"
                f"  Expected hash: {expected_hash[:16]}...\n"
                f"  Actual hash:   {actual_hash[:16]}...\n"
                f"  This may indicate django-mongodb-backend has been updated."
            )

        # Check signature
        if actual_params != expected_params:
            return False, (
                f"Method {method_name} signature has changed.\n"
                f"  Expected parameters: {expected_params}\n"
                f"  Actual parameters:   {actual_params}"
            )

        return True, None

    except Exception as e:
        return False, f"Failed to verify {method_name}: {str(e)}"


def apply_patches(verify=True, force=False):
    """
    Apply all monkey patches to django-mongodb-backend.

    Args:
        verify: Whether to verify method compatibility (default: True)
        force: Force apply patches even if verification fails (default: False)

    Raises:
        RuntimeError: If verification fails and force is False
    """

    # If verify is enabled, check method compatibility
    if verify:
        methods_to_verify = [
            (SQLCompiler.get_project_fields, "SQLCompiler.get_project_fields"),
            (SQLCompiler._make_result, "SQLCompiler._make_result"),
            (SQLInsertCompiler.insert, "SQLInsertCompiler.insert"),
        ]

        verification_errors = []
        for method, name in methods_to_verify:
            expected_hash = EXPECTED_METHOD_HASHES[name]
            expected_params = EXPECTED_METHOD_SIGNATURES[name]

            is_compatible, error_msg = verify_method_compatibility(
                method, name, expected_hash, expected_params
            )

            if not is_compatible:
                verification_errors.append(error_msg)

        if verification_errors:
            error_message = (
                "Monkey patch verification failed!\n\n"
                + "\n\n".join(verification_errors)
                + "\n\nThe original methods have changed. This could mean:\n"
                "1. django-mongodb-backend has been updated\n"
                "2. The patches may no longer work correctly\n\n"
                "Options:\n"
                "- Update the patches to match the new implementation\n"
                "- Use apply_patches(force=True) to skip verification (risky)\n"
                "- Use apply_patches(verify=False) to disable verification"
            )

            if force:
                warnings.warn(
                    f"{error_message}\n\nForcing patch application as requested.",
                    RuntimeWarning,
                    stacklevel=2,
                )
            else:
                raise RuntimeError(error_message)

    # Store original methods
    _original_get_project_fields = SQLCompiler.get_project_fields
    _original_make_result = SQLCompiler._make_result
    _original_insert = SQLInsertCompiler.insert

    # Apply patches
    SQLCompiler.get_project_fields = get_project_fields_with_dots
    SQLCompiler._make_result = make_result_with_dots
    SQLInsertCompiler.insert = insert_with_dots

    logger.info("✓ Dotted path patches applied to django-mongodb-backend")


def update_method_hashes():
    """
    Utility function to calculate current method hashes.
    Use this when django-mongodb-backend is updated and patches need to be adjusted.
    """
    print("Current method hashes:")
    print("-" * 80)

    methods = [
        (SQLCompiler.get_project_fields, "SQLCompiler.get_project_fields"),
        (SQLCompiler._make_result, "SQLCompiler._make_result"),
        (SQLInsertCompiler.insert, "SQLInsertCompiler.insert"),
    ]

    new_hashes = {}
    new_signatures = {}

    for method, name in methods:
        try:
            # Get source and hash
            source = inspect.getsource(method)
            hash_value = hashlib.sha256(source.encode("utf-8")).hexdigest()

            # Get signature
            sig = inspect.signature(method)
            params = list(sig.parameters.keys())

            new_hashes[name] = hash_value
            new_signatures[name] = params

            print(f"\n{name}:")
            print(f"  Hash: '{hash_value}'")
            print(f"  Signature: {params}")

        except Exception as e:
            print(f"\nError processing {name}: {e}")

    print("\n" + "-" * 80)
    print("\nUpdate EXPECTED_METHOD_HASHES with:")
    print("EXPECTED_METHOD_HASHES = {")
    for name, hash_value in new_hashes.items():
        print(f"    '{name}': '{hash_value}',")
    print("}")

    print("\nUpdate EXPECTED_METHOD_SIGNATURES with:")
    print("EXPECTED_METHOD_SIGNATURES = {")
    for name, params in new_signatures.items():
        print(f"    '{name}': {params},")
    print("}")


# Patch 1: Pipeline construction to handle dotted paths in projections
def get_project_fields_with_dots(self, columns=None, ordering=None, force_expression=False):
    if not columns:
        return {}

    fields = defaultdict(dict)
    for name, expr in columns + (ordering or ()):
        collection = expr.alias if isinstance(expr, Col) else None
        try:
            fields[collection][name] = (
                1
                # For brevity/simplicity, project {"field_name": 1}
                # instead of {"field_name": "$field_name"}.
                if isinstance(expr, Col) and name == expr.target.column and not force_expression
                else expr.as_mql(self, self.connection)
            )
        except EmptyResultSet:
            empty_result_set_value = getattr(expr, "empty_result_set_value", NotImplemented)
            value = False if empty_result_set_value is NotImplemented else empty_result_set_value
            fields[collection][name] = Value(value).as_mql(self, self.connection)
        except FullResultSet:
            fields[collection][name] = Value(True).as_mql(self, self.connection)

    # Convert flat fields with dots to nested structure
    nested_fields = defaultdict(dict)
    for collection, collection_fields in fields.items():
        nested_collection_fields = {}
        for name, value in collection_fields.items():
            if "." in name:
                _nested_set(nested_collection_fields, name.split("."), value)
            else:
                nested_collection_fields[name] = value
        nested_fields[collection] = nested_collection_fields

    # Annotations (stored in None) and the main collection's fields
    # should appear in the top-level of the fields dict.
    result = {}
    result.update(nested_fields.pop(None, {}))
    result.update(nested_fields.pop(self.collection_name, {}))
    # Add remaining collections
    result.update(nested_fields)

    # Convert defaultdict to dict so it doesn't appear as
    # "defaultdict(<CLASS 'dict'>, ..." in query logging.
    return dict(result)


# Patch 2: Result decoding to handle nested field access
def make_result_with_dots(self, entity, columns):
    """
    Decode values for the given fields from the database entity.

    The entity is assumed to be a dict using field database column
    names as keys. This version handles dotted paths for nested fields.
    """
    result = []
    for name, col in columns:
        column_alias = getattr(col, "alias", None)
        obj = (
            # Use the related object...
            entity.get(column_alias, {})
            # ...if this column refers to an object for select_related().
            if column_alias is not None and column_alias != self.collection_name
            else entity
        )
        # Handle dotted paths for nested field access
        if "." in name:
            result.append(_nested_get(obj, name.split(".")))
        else:
            result.append(obj.get(name))
    return result


# Patch 3: Insert handling to create nested documents
def insert_with_dots(self, docs, returning_fields=None):
    """Store a list of documents using field columns as element names."""
    # Transform docs to handle nested fields
    nested_docs = []
    for doc in docs:
        nested_doc = {}
        for key, value in doc.items():
            if "." in key:
                _nested_set(nested_doc, key.split("."), value)
            else:
                nested_doc[key] = value
        nested_docs.append(nested_doc)

    # Call original with transformed docs
    inserted_ids = self.collection.insert_many(nested_docs).inserted_ids
    return [(x,) for x in inserted_ids] if returning_fields else []
