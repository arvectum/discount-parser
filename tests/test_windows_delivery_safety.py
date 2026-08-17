from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_build_removes_smoke_database_before_installer() -> None:
    script = (ROOT / 'scripts' / 'build_windows.ps1').read_text(encoding='utf-8')
    assert 'Remove-Item .\\discount_parser.db' in script
    assert 'Smoke database must not be packaged' in script


def test_windows_ci_removes_smoke_database_before_upload() -> None:
    script = (ROOT / 'scripts' / 'build_windows_ci.ps1').read_text(encoding='utf-8')
    workflow = (ROOT / '.github' / 'workflows' / 'build-delivery.yml').read_text(encoding='utf-8')

    assert 'Remove-Item .\\discount_parser.db' in script
    assert 'Smoke database must not be packaged' in script
    assert script.index('Smoke database must not be packaged') < script.index('Compiling installer with Inno Setup')

    invocation = './scripts/build_windows_ci.ps1'
    assert invocation in workflow
    assert workflow.index(invocation) < workflow.index('Upload delivery package')


def test_user_guide_has_windows_and_linux_install_sections() -> None:
    guide = (ROOT / 'docs' / 'USER_GUIDE_RU.md').read_text(encoding='utf-8')
    assert '## 2. Установка на Windows' in guide
    assert 'DiscountParser-Setup.exe' in guide
    assert '## 4. Установка на сервер Linux' in guide
    assert 'discount-parser-web.service' in guide
    assert 'DP_ENV_FILE=/var/lib/discount-parser/.env' in guide
    assert 'ssh -L 8765:127.0.0.1:8765' in guide
