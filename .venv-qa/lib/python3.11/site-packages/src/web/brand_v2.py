from __future__ import annotations

import html

from src.web.brand import ARVECTUM_LOGO_SVG, BRAND_STYLE

# The customer-facing navigation intentionally contains only the most common
# tasks. Technical pages remain reachable from /settings.
_NAV = (
    ('/home', 'Главная'),
    ('/review', 'Проверка'),
    ('/offers', 'Предложения'),
    ('/settings', 'Настройки'),
    ('/help', 'Помощь'),
)


def brand_header(path: str) -> str:
    links: list[str] = []
    for href, label in _NAV:
        active = path == href or (href != '/home' and path.startswith(href + '/'))
        links.append(f'<a href="{href}" class="{"active" if active else ""}">{html.escape(label)}</a>')
    return f'''<header class="arv-header"><div class="arv-header-inner"><div class="arv-brand-row"><div>{ARVECTUM_LOGO_SVG}<div class="arv-product">Discount Parser</div></div></div><nav class="arv-nav">{"".join(links)}</nav></div></header>'''


def brand_footer() -> str:
    # Deliberately keep the footer compact: legal address belongs in contracts
    # and legal documents, not in the operational control panel.
    return '''<footer class="arv-footer"><div class="arv-footer-inner"><div class="arv-footer-top"></div><div class="arv-footer-grid"><div><strong>ООО «Арвектум»</strong><div>ИИ-Автоматизация</div><div style="margin-top:8px"><a href="https://arvectum.com" target="_blank" rel="noopener">arvectum.com</a> · <a href="mailto:info@arvectum.com">info@arvectum.com</a></div></div><div class="mono">ИНН 7716261422 · КПП 771601001<br>ОГРН 1267700213725</div></div><div class="arv-copyright">© 2026 ООО «Арвектум». Все права защищены.</div></div></footer>'''


__all__ = ['BRAND_STYLE', 'brand_header', 'brand_footer']
