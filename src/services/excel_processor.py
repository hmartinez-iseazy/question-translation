import io
from openpyxl import load_workbook
from typing import BinaryIO

from src.services.translator import TranslatorService


# Sheet to process
SHEET_NAME = "Questions"

# Columns to translate (D=Question, E=Correct Answer, F=Option1, G=Option2, H=Option3)
COLUMNS_TO_TRANSLATE = ["D", "E", "F", "G", "H"]

# Row where data starts (after headers)
DATA_START_ROW = 7

# Language cell
LANGUAGE_CELL = "C3"


class ExcelProcessor:
    def __init__(self, translator: TranslatorService):
        self.translator = translator

    async def process_excel(
        self,
        file_content: BinaryIO,
        target_lang_internal: str,
        target_lang_deepl: str,
    ) -> tuple[bytes, str | None, int]:
        """
        Process Excel file and translate specified columns in Questions sheet.

        Modifies the original Excel in place:
        - Translates columns D, E, F, G, H (Question + Answers) starting from row 7
        - Updates cell C3 with target language code (internal format)
        - Preserves all formatting, formulas in other sheets, etc.

        Args:
            file_content: Excel file bytes
            target_lang_internal: Internal language code (e.g., 'en', 'pt_BR') - written to C3
            target_lang_deepl: DeepL API code (e.g., 'EN-US', 'PT-BR') - used for translation

        Returns:
            tuple: (translated_excel_bytes, source_language, rows_translated)
        """
        # Load workbook preserving everything (no data_only)
        wb = load_workbook(filename=file_content)

        # Check if the sheet exists
        if SHEET_NAME not in wb.sheetnames:
            raise ValueError(
                f"Sheet '{SHEET_NAME}' not found. Available sheets: {wb.sheetnames}"
            )

        ws = wb[SHEET_NAME]

        # Get source language from C3
        source_lang = None
        lang_cell = ws[LANGUAGE_CELL]
        if lang_cell.value:
            source_lang = str(lang_cell.value).strip()

        # Find last row with data (check column A for row number)
        last_row_with_data = DATA_START_ROW - 1
        for row_idx in range(DATA_START_ROW, ws.max_row + 1):
            cell_a = ws.cell(row=row_idx, column=1)  # Column A
            if cell_a.value is not None and str(cell_a.value).strip():
                last_row_with_data = row_idx

        if last_row_with_data < DATA_START_ROW:
            # No data to translate
            output = io.BytesIO()
            wb.save(output)
            output.seek(0)
            return output.getvalue(), source_lang, 0

        # Collect all texts to translate
        texts_to_translate = []
        cell_positions = []  # (row, column_letter) tuples

        for row_idx in range(DATA_START_ROW, last_row_with_data + 1):
            # Check if row has data (column A has value)
            if ws.cell(row=row_idx, column=1).value is None:
                continue

            for col_letter in COLUMNS_TO_TRANSLATE:
                cell = ws[f"{col_letter}{row_idx}"]
                if cell.value and str(cell.value).strip():
                    texts_to_translate.append(str(cell.value))
                    cell_positions.append((row_idx, col_letter))

        rows_translated = 0
        if texts_to_translate:
            # Batch translate all texts using DeepL code
            translated_texts = await self.translator.translate_batch(
                texts_to_translate,
                target_lang=target_lang_deepl,
                source_lang=source_lang
            )

            # Write translated texts back to cells
            for (row_idx, col_letter), translated_text in zip(cell_positions, translated_texts):
                ws[f"{col_letter}{row_idx}"] = translated_text

            # Count unique rows translated
            rows_translated = len(set(pos[0] for pos in cell_positions))

        # Update language cell C3 with internal language code (as provided)
        ws[LANGUAGE_CELL] = target_lang_internal

        # Save to bytes (preserves all other sheets, formatting, etc.)
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return output.getvalue(), source_lang, rows_translated


def get_excel_processor(translator: TranslatorService) -> ExcelProcessor:
    return ExcelProcessor(translator)
