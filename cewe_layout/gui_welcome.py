"""Welcome window for QLayout.

Contains welcome window creation/management and README markdown display rendering.
"""

from __future__ import annotations

import os
import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from tkinter.filedialog import askopenfilename
from tkinter import scrolledtext

from .menu_manager import MenuManager


def _configure_markdown_tags(text_widget: scrolledtext.ScrolledText) -> None:
    """Configure text tags used by the basic markdown renderer."""
    base_font = tkfont.nametofont('TkTextFont').copy()
    base_font.configure(size=max(11, int(base_font.cget('size'))))
    text_widget.configure(font=base_font, padx=10, pady=8, spacing2=1)

    bold_font = base_font.copy()
    bold_font.configure(weight='bold')

    italic_font = base_font.copy()
    italic_font.configure(slant='italic')

    heading_1 = base_font.copy()
    heading_1.configure(size=20, weight='bold')
    heading_2 = base_font.copy()
    heading_2.configure(size=18, weight='bold')
    heading_3 = base_font.copy()
    heading_3.configure(size=16, weight='bold')
    heading_4 = base_font.copy()
    heading_4.configure(size=14, weight='bold')
    heading_5 = base_font.copy()
    heading_5.configure(size=13, weight='bold')
    heading_6 = base_font.copy()
    heading_6.configure(size=12, weight='bold')

    code_font = tkfont.nametofont('TkFixedFont').copy()
    code_font.configure(size=max(10, int(code_font.cget('size'))))

    text_widget.tag_configure('h1', font=heading_1, spacing1=14, spacing3=8)
    text_widget.tag_configure('h2', font=heading_2, spacing1=12, spacing3=7)
    text_widget.tag_configure('h3', font=heading_3, spacing1=10, spacing3=6)
    text_widget.tag_configure('h4', font=heading_4, spacing1=9, spacing3=5)
    text_widget.tag_configure('h5', font=heading_5, spacing1=8, spacing3=4)
    text_widget.tag_configure('h6', font=heading_6, spacing1=7, spacing3=4)

    text_widget.tag_configure('paragraph', spacing1=0, spacing3=4)
    text_widget.tag_configure('list_item', lmargin1=20, lmargin2=38, spacing3=2)
    text_widget.tag_configure('blockquote', lmargin1=28, lmargin2=28, spacing1=3, spacing3=3)

    text_widget.tag_configure('bold', font=bold_font)
    text_widget.tag_configure('italic', font=italic_font)
    text_widget.tag_configure('code_inline', font=code_font)
    text_widget.tag_configure('code_block', font=code_font, lmargin1=20, lmargin2=20, spacing1=6, spacing3=6)
    text_widget.tag_configure('link', underline=True)


def _insert_inline_markdown(text_widget: scrolledtext.ScrolledText, text: str, base_tags: tuple[str, ...]) -> None:
    """Insert a single line of basic inline markdown into the text widget.

    Supported inline syntax:
    - **bold**
    - *italic*
    - `code`
    - [label](url) (displayed as: label (url))
    """
    pattern = re.compile(r'(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))')
    position = 0

    for match in pattern.finditer(text):
        start, end = match.span()
        if start > position:
            text_widget.insert('end', text[position:start], base_tags)

        token = match.group(0)
        tags = list(base_tags)

        if token.startswith('**') and token.endswith('**'):
            token_text = token[2:-2]
            tags.append('bold')
        elif token.startswith('*') and token.endswith('*'):
            token_text = token[1:-1]
            tags.append('italic')
        elif token.startswith('`') and token.endswith('`'):
            token_text = token[1:-1]
            tags.append('code_inline')
        elif token.startswith('['):
            link_match = re.match(r'^\[([^\]]+)\]\(([^)]+)\)$', token)
            if link_match:
                token_text = f"{link_match.group(1)} ({link_match.group(2)})"
                tags.append('link')
            else:
                token_text = token
        else:
            token_text = token

        text_widget.insert('end', token_text, tuple(tags))
        position = end

    if position < len(text):
        text_widget.insert('end', text[position:], base_tags)


def _render_markdown(text_widget: scrolledtext.ScrolledText, markdown_text: str) -> None:
    """Render basic markdown into a Text widget using tags."""
    _configure_markdown_tags(text_widget)

    in_code_block = False

    for line in markdown_text.splitlines():
        stripped = line.strip()

        if stripped.startswith('```'):
            in_code_block = not in_code_block
            text_widget.insert('end', '\n')
            continue

        if in_code_block:
            text_widget.insert('end', f'{line}\n', ('code_block',))
            continue

        heading_match = re.match(r'^(#{1,6})\s+(.*)$', line)
        if heading_match:
            level = len(heading_match.group(1))
            content = heading_match.group(2)
            _insert_inline_markdown(text_widget, content, (f'h{level}',))
            text_widget.insert('end', '\n')
            continue

        list_match = re.match(r'^\s*([-*])\s+(.*)$', line)
        if list_match:
            text_widget.insert('end', '• ', ('list_item',))
            _insert_inline_markdown(text_widget, list_match.group(2), ('list_item',))
            text_widget.insert('end', '\n')
            continue

        ordered_match = re.match(r'^\s*(\d+\.)\s+(.*)$', line)
        if ordered_match:
            text_widget.insert('end', f"{ordered_match.group(1)} ", ('list_item',))
            _insert_inline_markdown(text_widget, ordered_match.group(2), ('list_item',))
            text_widget.insert('end', '\n')
            continue

        quote_match = re.match(r'^\s*>\s?(.*)$', line)
        if quote_match:
            _insert_inline_markdown(text_widget, quote_match.group(1), ('blockquote',))
            text_widget.insert('end', '\n')
            continue

        if stripped == '':
            text_widget.insert('end', '\n')
            continue

        _insert_inline_markdown(text_widget, line, ('paragraph',))
        text_widget.insert('end', '\n')


def _load_readme_content(app_root: str) -> str:
    """Load README.md from app root."""
    readme_path = os.path.join(app_root, 'README.md')
    try:
        with open(readme_path, 'r', encoding='utf-8') as readme_file:
            return readme_file.read()
    except Exception as exc:
        return f'Unable to load README.md from {readme_path}.\n\nError: {exc}'


def create_welcome_window(root: tk.Tk, recent_albums_mgr, on_open_album, on_quit, app_root: str) -> tk.Toplevel:
    """Create and configure the QLayout welcome window.

    Args:
        root: Hidden root Tk instance.
        recent_albums_mgr: RecentAlbumsManager used by menus.
        on_open_album: Callback(album_path) to open an album.
        on_quit: Callback() to quit application.
        app_root: Absolute path to application root where README.md is located.

    Returns:
        Configured welcome Toplevel window.
    """
    welcome_win = tk.Toplevel(root)
    welcome_win.title('Welcome to QLayout')
    welcome_win.geometry('900x700')

    welcome_frame = ttk.Frame(welcome_win)
    welcome_frame.pack(expand=True, fill='both')

    def on_welcome_close():
        """Handle welcome window close button - hide window, app stays running."""
        welcome_win.withdraw()

    def open_album_from_button():
        """Called when Open Album button clicked."""
        album_file = askopenfilename(
            title='Open CEWE Album (.mcf file inside .xmcf bundle, or standalone .mcf)',
            parent=welcome_win,
        )
        if album_file:
            on_open_album(album_file)

    welcome_win.protocol('WM_DELETE_WINDOW', on_welcome_close)

    welcome_menu = MenuManager(welcome_win, recent_albums_mgr, tk_root=root)
    welcome_menu.create_welcome_menu(
        on_open_album=on_open_album,
        on_quit=on_quit,
    )

    top_bar = ttk.Frame(welcome_frame, padding=(12, 10, 12, 8))
    top_bar.pack(fill='x')

    ttk.Label(top_bar, text='QLayout', font=('TkDefaultFont', 16, 'bold')).pack(side='left')

    ttk.Button(
        top_bar,
        text='Open Album...',
        command=open_album_from_button,
        width=20,
    ).pack(side='right')

    ttk.Separator(welcome_frame, orient='horizontal').pack(fill='x', padx=12, pady=(0, 8))

    readme_view = scrolledtext.ScrolledText(
        welcome_frame,
        wrap='word',
        state='normal',
        relief='solid',
        borderwidth=1,
    )
    readme_view.pack(fill='both', expand=True, padx=12, pady=(0, 12))

    readme_content = _load_readme_content(app_root)
    _render_markdown(readme_view, readme_content)
    readme_view.config(state='disabled')

    return welcome_win
