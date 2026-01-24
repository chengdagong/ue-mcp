"""
UE5 Python API Search Script.

This script performs runtime introspection of the 'unreal' module to search
and query Python APIs. It supports multiple modes:
- list_classes: List all classes (with optional wildcard pattern)
- list_functions: List functions/methods
- class_info: Get detailed class information
- member_info: Get specific member details
- search: Fuzzy search across all names

Parameters (via sys.argv):
    mode: Query mode
    query: Search query or pattern
    include_inherited: Include inherited members (for class_info)
    include_private: Include private members (_underscore)
    limit: Maximum results to return
"""

import argparse
import inspect
import json
import re

import unreal


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="UE5 Python API Search - Perform runtime introspection of the 'unreal' module"
    )
    parser.add_argument(
        "--mode",
        default="list_classes",
        choices=["list_classes", "list_functions", "class_info", "member_info", "search"],
        help="Query mode (default: list_classes)"
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Search query or pattern"
    )
    parser.add_argument(
        "--include-inherited",
        action="store_true",
        default=True,
        help="Include inherited members (for class_info mode)"
    )
    parser.add_argument(
        "--no-include-inherited",
        dest="include_inherited",
        action="store_false",
        help="Exclude inherited members"
    )
    parser.add_argument(
        "--include-private",
        action="store_true",
        default=False,
        help="Include private members (_underscore)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum results to return (default: 100)"
    )
    return parser.parse_args()


# Parse arguments
args = parse_args()
mode = args.mode
query = args.query
include_inherited = args.include_inherited
include_private = args.include_private
limit = args.limit


def output_result(data):
    """Output result as pure JSON (will be parsed as last line)."""
    print(json.dumps(data, default=str))


def parse_ue_property_doc(doc):
    """Parse UE property docstring: '(Type): [Read-Only/Read-Write] description'"""
    if not doc:
        return None, "read-write", ""
    match = re.match(r'\(([^)]+)\):\s*(?:\[([^\]]+)\])?\s*(.*)', doc, re.DOTALL)
    if match:
        prop_type = match.group(1)
        access_str = match.group(2) or ""
        desc = match.group(3) or ""
        access = "read-only" if "Read-Only" in access_str else "read-write"
        return prop_type, access, desc.split('\n')[0][:150]
    return None, "read-write", doc.split('\n')[0][:150]


def matches_word(term, name):
    """Check if term matches as a word in CamelCase or snake_case name."""
    normalized = re.sub(r'([a-z])([A-Z])', r'\1_\2', name)
    words = [w.lower() for w in normalized.split('_') if w]
    return term in words or any(term in w for w in words)


def list_classes():
    """List all classes, optionally filtered by wildcard pattern."""
    import fnmatch

    result = []
    for name, obj in inspect.getmembers(unreal):
        if inspect.isclass(obj) and (not name.startswith('_') or include_private):
            if query and not fnmatch.fnmatch(name, query):
                continue
            doc = (obj.__doc__ or '').split('\n')[0][:200]
            result.append({"name": name, "type": "class", "docstring": doc})

    result.sort(key=lambda x: x["name"])
    output_result({
        "success": True,
        "results": result[:limit],
        "count": len(result),
        "truncated": len(result) > limit,
        "pattern": query
    })


def list_functions():
    """List functions/methods with multiple query formats supported."""
    import fnmatch

    result = []

    if query is None or '.' not in query:
        # Mode 1: Module-level functions
        pattern = query
        for name, obj in inspect.getmembers(unreal):
            if callable(obj) and not inspect.isclass(obj) and (not name.startswith('_') or include_private):
                if pattern and not fnmatch.fnmatch(name, pattern):
                    continue
                try:
                    sig = str(inspect.signature(obj))
                except (ValueError, TypeError):
                    sig = "()"
                doc = (getattr(obj, '__doc__', '') or '').split('\n')[0][:200]
                result.append({
                    "name": name,
                    "type": "function",
                    "signature": f"def {name}{sig}",
                    "docstring": doc
                })

        result.sort(key=lambda x: x["name"])
        output_result({
            "success": True,
            "results": result[:limit],
            "count": len(result),
            "truncated": len(result) > limit,
            "pattern": pattern,
            "scope": "module"
        })
    else:
        # Mode 2 or 3: Class methods
        parts = query.split('.', 1)
        class_pattern = parts[0]
        method_pattern = parts[1] if len(parts) > 1 else '*'

        # Get classes to search
        if '*' in class_pattern or '?' in class_pattern:
            # Mode 3: Search multiple classes
            classes_to_search = [
                (name, cls) for name, cls in inspect.getmembers(unreal, inspect.isclass)
                if fnmatch.fnmatch(name, class_pattern) and (not name.startswith('_') or include_private)
            ]
        else:
            # Mode 2: Single class
            cls = getattr(unreal, class_pattern, None)
            if cls is None:
                output_result({"success": False, "error": f"Class '{class_pattern}' not found"})
                return
            classes_to_search = [(class_pattern, cls)]

        for cls_name, cls in classes_to_search:
            for mem_name, mem in inspect.getmembers(cls):
                if mem_name.startswith('_') and not include_private:
                    continue
                if not fnmatch.fnmatch(mem_name, method_pattern):
                    continue
                if callable(mem) and not inspect.isclass(mem):
                    try:
                        sig = str(inspect.signature(mem))
                    except:
                        sig = "(self)"
                    doc = (mem.__doc__ or '').split('\n')[0][:200]
                    result.append({
                        "name": f"{cls_name}.{mem_name}",
                        "type": "method",
                        "signature": f"def {mem_name}{sig}",
                        "docstring": doc,
                        "class": cls_name
                    })
                if len(result) >= limit * 2:
                    break
            if len(result) >= limit * 2:
                break

        result.sort(key=lambda x: x["name"])
        output_result({
            "success": True,
            "results": result[:limit],
            "count": len(result),
            "truncated": len(result) > limit,
            "class_pattern": class_pattern,
            "method_pattern": method_pattern,
            "scope": "class"
        })


def class_info():
    """Get detailed information about a class."""
    class_name = query
    cls = getattr(unreal, class_name, None)

    if cls is None:
        output_result({"success": False, "error": f"Class '{class_name}' not found in unreal module"})
        return

    bases = [b.__name__ for b in cls.__mro__[1:5] if hasattr(b, '__name__')]
    docstring = (cls.__doc__ or "")[:2000]

    properties = []
    methods = []
    inherited_from = {}

    for name, obj in inspect.getmembers(cls):
        if name.startswith('_') and not include_private:
            continue

        # Find defining class
        defining_class = None
        for parent in cls.__mro__:
            if name in getattr(parent, '__dict__', {}):
                defining_class = parent.__name__
                break

        type_name = type(obj).__name__

        # Check for UE5 properties (getset_descriptor) or Python properties
        if type_name == 'getset_descriptor' or isinstance(obj, property):
            doc = getattr(obj, '__doc__', '') or ''
            if type_name == 'getset_descriptor':
                prop_type, access, desc = parse_ue_property_doc(doc)
                properties.append({
                    "name": name,
                    "type": prop_type,
                    "access": access,
                    "docstring": desc
                })
            else:
                properties.append({
                    "name": name,
                    "type": None,
                    "access": "read-write" if obj.fset else "read-only",
                    "docstring": ""
                })
            if defining_class and defining_class != class_name:
                inherited_from[name] = defining_class
        elif callable(obj) and not inspect.isclass(obj):
            try:
                sig = str(inspect.signature(obj))
            except:
                sig = "(self)"
            doc = (obj.__doc__ or '').split('\n')[0][:200]
            methods.append({
                "name": name,
                "signature": f"def {name}{sig}",
                "docstring": doc
            })
            if defining_class and defining_class != class_name:
                inherited_from[name] = defining_class

    result = {
        "success": True,
        "class_name": class_name,
        "base_classes": bases,
        "docstring": docstring,
        "properties": properties[:limit],
        "methods": methods[:limit],
        "property_count": len(properties),
        "method_count": len(methods),
    }
    if include_inherited:
        result["inherited_from"] = inherited_from

    output_result(result)


def member_info():
    """Get detailed information about a specific member."""
    parts = query.split('.', 1)

    if len(parts) == 1:
        # Module-level lookup
        name = parts[0]
        obj = getattr(unreal, name, None)

        if obj is None:
            output_result({"success": False, "error": f"'{name}' not found in unreal module"})
        elif inspect.isclass(obj):
            output_result({
                "success": True,
                "member_name": name,
                "member_type": "class",
                "signature": f"class {name}",
                "docstring": obj.__doc__ or ""
            })
        elif callable(obj):
            try:
                sig = str(inspect.signature(obj))
            except:
                sig = "()"
            output_result({
                "success": True,
                "member_name": name,
                "member_type": "function",
                "signature": f"def {name}{sig}",
                "docstring": obj.__doc__ or ""
            })
        else:
            output_result({
                "success": True,
                "member_name": name,
                "member_type": "constant",
                "signature": f"{name}: {type(obj).__name__}",
                "docstring": ""
            })
    else:
        class_name, member_name = parts
        cls = getattr(unreal, class_name, None)

        if cls is None:
            output_result({"success": False, "error": f"Class '{class_name}' not found"})
            return

        obj = getattr(cls, member_name, None)
        if obj is None:
            output_result({"success": False, "error": f"Member '{member_name}' not found in '{class_name}'"})
            return

        type_name = type(obj).__name__

        if type_name == 'getset_descriptor':
            doc = getattr(obj, '__doc__', '') or ''
            prop_type, access, desc = parse_ue_property_doc(doc)
            output_result({
                "success": True,
                "member_name": member_name,
                "member_type": "property",
                "property_type": prop_type,
                "access": access,
                "signature": f"{member_name}: {prop_type or 'Unknown'} ({access})",
                "docstring": desc
            })
        elif isinstance(obj, property):
            doc = (obj.fget.__doc__ if obj.fget else "") or ""
            access = "read-write" if obj.fset else "read-only"
            output_result({
                "success": True,
                "member_name": member_name,
                "member_type": "property",
                "access": access,
                "signature": f"{member_name} ({access})",
                "docstring": doc
            })
        elif callable(obj):
            try:
                sig = str(inspect.signature(obj))
            except:
                sig = "(self)"
            output_result({
                "success": True,
                "member_name": member_name,
                "member_type": "method",
                "signature": f"def {member_name}{sig}",
                "docstring": obj.__doc__ or ""
            })
        else:
            output_result({
                "success": True,
                "member_name": member_name,
                "member_type": "attribute",
                "signature": f"{member_name}: {type(obj).__name__}",
                "docstring": ""
            })


def search():
    """Fuzzy search across all names."""
    search_term = query.lower()
    results = []

    # Search module-level items
    for name, obj in inspect.getmembers(unreal):
        if name.startswith('_') and not include_private:
            continue
        if search_term in name.lower() or matches_word(search_term, name):
            if inspect.isclass(obj):
                doc = (obj.__doc__ or '').split('\n')[0][:100]
                results.append({"name": name, "type": "class", "docstring": doc})
            elif callable(obj):
                results.append({"name": name, "type": "function"})

    # Search class members (limit classes for performance)
    class_count = 0
    for cls_name, cls in inspect.getmembers(unreal, inspect.isclass):
        if cls_name.startswith('_'):
            continue
        class_count += 1
        if class_count > 50:
            break
        for mem_name, mem in inspect.getmembers(cls):
            if mem_name.startswith('_') and not include_private:
                continue
            if search_term in mem_name.lower() or matches_word(search_term, mem_name):
                if isinstance(mem, property):
                    results.append({
                        "name": f"{cls_name}.{mem_name}",
                        "type": "property",
                        "parent_class": cls_name
                    })
                elif callable(mem) and not inspect.isclass(mem):
                    results.append({
                        "name": f"{cls_name}.{mem_name}",
                        "type": "method",
                        "parent_class": cls_name
                    })
                if len(results) >= limit * 2:
                    break
        if len(results) >= limit * 2:
            break

    results.sort(key=lambda x: (x["type"] != "class", x["name"]))
    truncated = len(results) > limit
    output_result({
        "success": True,
        "results": results[:limit],
        "count": len(results),
        "truncated": truncated
    })


# Main execution
mode_handlers = {
    'list_classes': list_classes,
    'list_functions': list_functions,
    'class_info': class_info,
    'member_info': member_info,
    'search': search,
}

handler = mode_handlers.get(mode)
if handler:
    handler()
else:
    output_result({"success": False, "error": f"Unknown mode: {mode}"})
