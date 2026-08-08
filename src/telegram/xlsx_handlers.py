from __future__ import annotations

import tempfile
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from src.modules.xlsx.service import export_offers_xlsx, import_offer_corrections
from src.shared.config import get_settings

router = Router(name="discount-parser-xlsx")
MAX_IMPORT_BYTES = 20 * 1024 * 1024


def _is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in get_settings().telegram_admin_id_set)


@router.message(Command("export"))
async def export_command(message: Message) -> None:
    if not _is_admin(message):
        await message.answer("Нет доступа")
        return

    with tempfile.NamedTemporaryFile(prefix="discount_parser_", suffix=".xlsx", delete=False) as handle:
        path = Path(handle.name)
    try:
        export_offers_xlsx(path)
        await message.answer_document(
            FSInputFile(path, filename="offers.xlsx"),
            caption="Экспорт предложений. Для ручной коррекции изменяйте только category/subcategory.",
        )
    finally:
        path.unlink(missing_ok=True)


@router.message(Command("import"))
async def import_command(message: Message) -> None:
    if not _is_admin(message):
        await message.answer("Нет доступа")
        return
    await message.answer("Отправьте исправленный XLSX следующим сообщением.")


@router.message(F.document)
async def import_document(message: Message, bot: Bot) -> None:
    if not _is_admin(message):
        await message.answer("Нет доступа")
        return
    document = message.document
    filename = (document.file_name or "").lower()
    if not filename.endswith(".xlsx"):
        await message.answer("Поддерживается только .xlsx")
        return
    if document.file_size and document.file_size > MAX_IMPORT_BYTES:
        await message.answer("XLSX слишком большой для импорта (максимум 20 MB).")
        return

    with tempfile.NamedTemporaryFile(prefix="discount_parser_import_", suffix=".xlsx", delete=False) as handle:
        path = Path(handle.name)
    try:
        await bot.download(document, destination=path)
        report = import_offer_corrections(path)
        text = (
            "Импорт завершён\n"
            f"Строк просмотрено: {report.rows_seen}\n"
            f"Изменено: {report.rows_changed}\n"
            f"Manual overrides: {report.overrides_written}\n"
            f"Правил создано: {report.rules_created}\n"
            f"Пропущено: {report.rows_skipped}\n"
            f"Ошибок: {len(report.errors)}"
        )
        if report.errors:
            text += "\n\n" + "\n".join(report.errors[:10])
        await message.answer(text)
    except Exception as exc:
        await message.answer(f"Импорт не выполнен: {type(exc).__name__}: {exc}")
    finally:
        path.unlink(missing_ok=True)
