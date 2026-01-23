import html
import re


def _extract_plain_text_from_html(html_text):
    """Extract plain text from HTML CDATA content.

    Args:
        html_text: HTML string, possibly wrapped in CDATA

    Returns:
        Plain text string with HTML tags removed
    """
    if not html_text:
        return ""

    # Remove CDATA wrapper if present
    text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', html_text, flags=re.DOTALL)

    # Remove <style>...</style> blocks (including CSS content)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove <head>...</head> blocks
    text = re.sub(r'<head[^>]*>.*?</head>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove all HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Decode HTML entities
    text = html.unescape(text)

    # Clean up whitespace
    text = ' '.join(text.split())

    return text.strip()


def convert_qt_html_to_tkhtmlview(qt_html: str) -> str:
    """Convert Qt RichText HTML to tkhtmlview-compatible HTML.

    Qt HTML uses:
    - DOCTYPE, meta tags, <head>, <style> blocks
    - Qt-specific CSS properties (-qt-block-indent, etc.)
    - Complex CSS in style attributes

    tkhtmlview supports:
    - Basic tags: a, b, br, code, div, em, h1-h6, i, img, li, ol, p, pre, span, strong, ul
    - Simple inline styles: color, font-family, font-size, font-weight, font-style
    - No <style> blocks, no complex CSS

    Args:
        qt_html: Qt RichText HTML string

    Returns:
        Simplified HTML compatible with tkhtmlview
    """
    import re
    import html as html_module

    # Remove CDATA wrapper if present
    html_str = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', qt_html, flags=re.DOTALL)

    # Remove DOCTYPE declaration
    html_str = re.sub(r'<!DOCTYPE[^>]*>', '', html_str, flags=re.IGNORECASE)

    # Remove <head>...</head> entirely (includes meta tags and style blocks)
    html_str = re.sub(r'<head[^>]*>.*?</head>', '', html_str, flags=re.DOTALL | re.IGNORECASE)

    # Remove standalone <style>...</style> blocks (in case they're outside <head>)
    html_str = re.sub(r'<style[^>]*>.*?</style>', '', html_str, flags=re.DOTALL | re.IGNORECASE)

    # Extract styles from <body> tag and remove it
    body_styles = {}
    body_match = re.search(r'<body([^>]*)>', html_str, re.IGNORECASE)
    if body_match:
        body_attrs = body_match.group(1)
        # Extract style attribute
        style_match = re.search(r'style\s*=\s*["\']([^"\']*)["\']', body_attrs, re.IGNORECASE)
        if style_match:
            style_str = style_match.group(1)
            # Parse CSS properties
            for prop in style_str.split(';'):
                if ':' in prop:
                    key, value = prop.split(':', 1)
                    body_styles[key.strip()] = value.strip()

        # Remove <body> and </body> tags
        html_str = re.sub(r'<body[^>]*>', '', html_str, flags=re.IGNORECASE)
        html_str = re.sub(r'</body>', '', html_str, flags=re.IGNORECASE)

    # Remove <html> tags
    html_str = re.sub(r'</?html[^>]*>', '', html_str, flags=re.IGNORECASE)

    # Clean up Qt-specific CSS properties from style attributes
    # Remove properties like -qt-block-indent, -qt-list-indent, -qt-paragraph-type
    def clean_style_attr(match):
        style_str = match.group(1)
        # Split into individual properties
        props = []
        for prop in style_str.split(';'):
            if ':' not in prop:
                continue
            key, value = prop.split(':', 1)
            key = key.strip()
            value = value.strip()

            # Skip Qt-specific properties
            if key.startswith('-qt-'):
                continue

            # Skip properties tkhtmlview doesn't support well
            if key in ['letter-spacing', 'margin-top', 'margin-bottom', 'margin-left',
                       'margin-right', 'text-indent', 'border-width']:
                continue

            # Keep supported properties: color, font-family, font-size, font-weight, font-style, background-color
            if key in ['color', 'font-family', 'font-size', 'font-weight', 'font-style',
                       'background-color', 'text-decoration', 'vertical-align']:
                # Convert font-size from pt to px (tkhtmlview only supports px and %)
                if key == 'font-size' and value.endswith('pt'):
                    value = value[:-2] + 'px'
                props.append(f'{key}: {value}')

        if props:
            return f'style="{"; ".join(props)}"'
        else:
            return ''

    html_str = re.sub(r'style\s*=\s*"([^"]*)"', clean_style_attr, html_str, flags=re.IGNORECASE)

    # Apply body styles to the root element by wrapping in a div
    if body_styles:
        # Build style string from body_styles
        style_parts = []
        for key, value in body_styles.items():
            if not key.startswith('-qt-') and key not in ['letter-spacing']:
                style_parts.append(f'{key}: {value}')

        if style_parts:
            style_attr = '; '.join(style_parts)
            html_str = f'<div style="{style_attr}">{html_str}</div>'

    # Clean up whitespace
    html_str = html_str.strip()

    # Remove empty style attributes
    html_str = re.sub(r'\s*style\s*=\s*""\s*', '', html_str)

    return html_str
