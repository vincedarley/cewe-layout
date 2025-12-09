# Keyboard Shortcuts

The QLayout GUI supports keyboard shortcuts for common operations.

## Platform-Specific Modifier Key

- **macOS**: ⌘ (Command key)
- **Windows/Linux**: Ctrl

In the documentation below, we use `Cmd` to represent the platform-appropriate modifier key.

## Available Shortcuts

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Cmd+S` | Save Modified | Save all modified pages to the MCF file |
| `Cmd+P` | Export PDF | Export current page to PDF (like "Print") |
| `Cmd+Z` | Undo | Revert to previous layout variant |
| `Cmd+R` | Generate Layout | Run the selected layout algorithm ("Run") |
| `Cmd+Shift+N` | New Text Box | Add a new text box to the current page |
| `Cmd+W` | Close Window | Close the application (macOS only) |
| `←` (Left Arrow) | Previous Page | Navigate to the previous page |
| `→` (Right Arrow) | Next Page | Navigate to the next page |

## macOS Menu Bar

On macOS, QLayout provides a native menu bar with the following menus:

### File Menu
- Save Modified (Cmd+S)
- Export PDF... (Cmd+P)
- Close Window (Cmd+W)

### Edit Menu
- Undo Layout (Cmd+Z)
- Use Original Page

### Layout Menu
- Generate Layout (Cmd+R)
- New Text Box (Cmd+Shift+N)

### Window Menu
The standard macOS Window menu is included, which automatically manages window switching and minimizing.

### About Menu
The macOS About menu provides application information.

**Important Notes**:
- The menu bar appears on **both the Page window and Controls window**, so it's always accessible regardless of which window is frontmost.
- When running from the command line (rather than as a bundled .app), macOS will show "Python" as the application name in the menu bar. This is a limitation of running Python scripts directly. To show "QLayout" in the menu bar, the application would need to be packaged as a proper macOS .app bundle.

## Implementation Details

The keyboard shortcut system is designed to be platform-aware and modular:

- **Platform detection**: `is_macos()` helper function
- **Modifier key**: `get_modifier_key()` returns 'Command' or 'Control'
- **Modifier symbol**: `get_modifier_symbol()` returns '⌘' or 'Ctrl+' for button labels
- **macOS menu**: Automatically created only when running on macOS
- **Extensibility**: Easy to add Windows/Linux-specific menus by following the macOS pattern

All shortcuts are defined in the `_setup_keyboard_shortcuts()` method in `gui.py`.
