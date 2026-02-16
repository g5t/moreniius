"""Path-based navigation utility for NeXus Structure JSON.

NeXus Structure JSON uses a verbose hierarchical format with 'children' arrays,
making navigation cumbersome. This module provides a wrapper that enables
path-based access like: ns['/entry/instrument/component_name/field']

Attributes can be accessed with '@' prefix: ns['/entry/@NX_class']

Supports chainable navigation: ns['entry']['instrument']['component']

Quick Start:
    >>> from moreniius import to_nexus_structure, NexusStructureNavigator
    >>> structure = to_nexus_structure(instr)
    >>> nav = NexusStructureNavigator(structure)
    >>> 
    >>> # Path-based access (instead of structure['children'][0]['children'][0])
    >>> entry = nav['/entry']
    >>> instrument = nav['/entry/instrument']
    >>> component = nav['/entry/instrument/component_name']
    >>> 
    >>> # Chainable navigation (each returns a Navigator)
    >>> component = nav['entry']['instrument']['component_name']
    >>> 
    >>> # Access attributes with '@' prefix (returns raw dict)
    >>> nx_class = nav['/entry/@NX_class']
    >>> vector_attr = nav['/entry/instrument/something/@vector']
    >>> 
    >>> # Get the underlying dictionary
    >>> raw_dict = nav['entry'].dict()
    >>> # or use the property
    >>> raw_dict = nav['entry'].structure
    >>> 
    >>> # Check existence
    >>> if nav.exists('/entry/instrument/mon0'):
    ...     mon0 = nav['/entry/instrument/mon0']
    >>> 
    >>> # Safe access with default
    >>> value = nav.get('/entry/instrument/missing', default=None)
    >>> 
    >>> # Find elements by name
    >>> monitors = nav.find_all('mon0')
    >>> 
    >>> # Find attributes by name
    >>> all_nx_classes = nav.find_all('NX_class', include_attributes=True)
    >>> 
    >>> # Reverse lookup
    >>> path = nav.get_path(component.structure)  # Returns '/entry/instrument/component_name'
"""

from __future__ import annotations
from typing import Any


class NexusStructureNavigator:
    """Provides path-based navigation for NeXus Structure JSON.
    
    NeXus Structure JSON has the format:
    {
        'children': [
            {
                'name': 'entry',
                'type': 'group',
                'children': [
                    {
                        'name': 'instrument',
                        'type': 'group',
                        'children': [...]
                    }
                ]
            }
        ]
    }
    
    This class allows navigation using paths like '/entry/instrument/component'
    instead of nested dictionary access. Accessing groups returns new Navigator
    instances for chaining, while accessing attributes or leaf nodes returns
    raw dictionaries.
    
    Example:
        >>> ns = NexusStructureNavigator(nexus_structure_dict)
        >>> # Returns a new Navigator
        >>> component = ns['/entry/instrument/mon0']
        >>> # Can also chain
        >>> component = ns['entry']['instrument']['mon0']
        >>> # Get raw dictionary
        >>> raw = component.dict()
        >>> # Access attributes (returns raw dict)
        >>> nx_class = ns['/entry/instrument/mon0/@NX_class']
    """
    
    def __init__(self, structure: dict):
        """Initialize with a NeXus Structure JSON dictionary.
        
        Args:
            structure: The root NeXus Structure JSON dict (with 'children' key)
        """
        self._structure = structure
    
    def __getitem__(self, path: str) -> 'NexusStructureNavigator' | dict | Any:
        """Access elements by path.
        
        Args:
            path: A forward-slash separated path like '/entry/instrument/mon0'
                  or '/entry/instrument/mon0/@attribute_name' for attributes.
                  Leading slash is optional. Attributes are prefixed with '@'.
                  Can also be a single component name like 'entry' for chaining.
        
        Returns:
            NexusStructureNavigator if the result has children (for chaining),
            otherwise the dict/value at the specified path
            
        Raises:
            KeyError: If the path doesn't exist
        """
        if not path:
            return self
        
        # Normalize path: remove leading/trailing slashes and split
        path = path.strip('/')
        if not path:
            return self
        
        parts = path.split('/')
        result = self._navigate(self._structure, parts)
        
        # If result is a structure node (has 'children'), wrap in Navigator for chaining
        if isinstance(result, dict) and 'children' in result:
            return NexusStructureNavigator(result)
        
        # Otherwise return the raw result (attributes, datasets, etc.)
        return result
    
    def _navigate(self, current: dict, parts: list[str]) -> dict | Any:
        """Recursively navigate through the structure.
        
        Args:
            current: Current position in the structure
            parts: Remaining path parts to navigate
            
        Returns:
            The found element
            
        Raises:
            KeyError: If path doesn't exist
        """
        if not parts:
            return current
        
        target_name = parts[0]
        remaining = parts[1:]
        
        # Check if this is an attribute access (starts with '@')
        if target_name.startswith('@'):
            attr_name = target_name[1:]  # Remove '@' prefix
            if remaining:
                raise KeyError(f"Attributes must be at the end of the path: {target_name}")
            
            # Look in 'attributes' array
            attributes = current.get('attributes', [])
            for attr in attributes:
                if attr.get('name') == attr_name:
                    return attr
            
            # Attribute not found
            raise KeyError(f"Attribute '@{attr_name}' not found")
        
        # Look in 'children' array for the named element
        children = current.get('children', [])
        for child in children:
            # Match by 'name' key for groups
            if child.get('name') == target_name:
                return self._navigate(child, remaining)
            
            # For datasets (module='dataset'), check config name
            if child.get('module') == 'dataset':
                config = child.get('config', {})
                if config.get('name') == target_name:
                    return self._navigate(child, remaining)
            
            # For links (module='link'), check config name
            if child.get('module') == 'link':
                config = child.get('config', {})
                if config.get('name') == target_name:
                    return self._navigate(child, remaining)
        
        # Path not found
        path_so_far = '/'.join(parts[:len(parts) - len(remaining)])
        raise KeyError(f"Path component '{target_name}' not found at /{path_so_far}")
    
    def get(self, path: str, default: Any = None) -> dict | Any:
        """Get element by path with a default value.
        
        Args:
            path: A forward-slash separated path
            default: Value to return if path doesn't exist
            
        Returns:
            The element at the path, or default if not found
        """
        try:
            return self[path]
        except KeyError:
            return default
    
    def exists(self, path: str) -> bool:
        """Check if a path exists.
        
        Args:
            path: A forward-slash separated path
            
        Returns:
            True if the path exists, False otherwise
        """
        try:
            self[path]
            return True
        except KeyError:
            return False
    
    def find_all(self, name: str, include_attributes: bool = False) -> list[dict]:
        """Find all elements with a given name anywhere in the structure.
        
        Args:
            name: The name to search for (without '@' prefix for attributes)
            include_attributes: If True, also search in attributes arrays
            
        Returns:
            List of all matching elements
        """
        results = []
        self._find_recursive(self._structure, name, results, include_attributes)
        return results
    
    def _find_recursive(self, current: dict, name: str, results: list, include_attributes: bool = False):
        """Recursively search for elements by name."""
        # Check if current element matches
        if current.get('name') == name:
            results.append(current)
        
        # Check dataset/link config names
        if current.get('module') in ('dataset', 'link'):
            config = current.get('config', {})
            if config.get('name') == name:
                results.append(current)
        
        # Check attributes if requested
        if include_attributes:
            for attr in current.get('attributes', []):
                if attr.get('name') == name:
                    results.append(attr)
        
        # Recurse into children
        for child in current.get('children', []):
            self._find_recursive(child, name, results, include_attributes)
    
    def get_path(self, element: dict) -> str | None:
        """Get the path to an element (reverse lookup).
        
        Args:
            element: The element dict to find
            
        Returns:
            The path as a string, or None if not found
        """
        path_parts = []
        if self._build_path(self._structure, element, path_parts):
            return '/' + '/'.join(path_parts) if path_parts else '/'
        return None
    
    def _build_path(self, current: dict, target: dict, path: list[str]) -> bool:
        """Recursively build path to target element."""
        if current is target:
            return True
        
        # Check attributes
        for attr in current.get('attributes', []):
            if attr is target:
                attr_name = attr.get('name')
                if attr_name:
                    path.append(f'@{attr_name}')
                    return True
        
        # Check children
        for child in current.get('children', []):
            # Get the name of this child
            name = child.get('name')
            if not name and child.get('module') in ('dataset', 'link'):
                name = child.get('config', {}).get('name')
            
            if name:
                path.append(name)
                if self._build_path(child, target, path):
                    return True
                path.pop()
        
        return False
    
    @property
    def structure(self) -> dict:
        """Get the underlying structure dictionary."""
        return self._structure
    
    def dict(self) -> dict:
        """Get the underlying structure dictionary.
        
        This is a convenience method that's equivalent to the .structure property.
        Useful when you want the raw JSON dictionary representation.
        
        Returns:
            The underlying structure dictionary
        """
        return self._structure
    
    def __repr__(self) -> str:
        """Return a readable representation of the navigator."""
        # Get the name if this structure has one
        name = self._structure.get('name', 'root')
        node_type = self._structure.get('type', 'structure')
        return f"NexusStructureNavigator(name='{name}', type='{node_type}')"
