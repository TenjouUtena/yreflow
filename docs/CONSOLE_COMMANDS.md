# Console Commands

Console commands are entered in the Console tab and operate outside of any specific character context.

## help

List all available console commands.

| Aliases | `help` |
|---------|--------|
| Syntax  | `help` |

## lookupname

Search for characters by name and display their full name and ID.

| Aliases | `lookupname` |
|---------|--------------|
| Syntax  | `lookupname <name>` |

Uses fuzzy name matching (exact then prefix, case-insensitive). Returns all matches rather than requiring a unique result.

```
lookupname zari
```
