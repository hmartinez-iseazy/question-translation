import io
import logging
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from typing import BinaryIO

from src.services.translator import TranslatorService

logger = logging.getLogger(__name__)

# Sheet to process
SHEET_NAME = "Questions"
PROCESS_SHEET_NAME = "Questions_process"
CONFIG_SHEET_NAME = "Configuration"

# Columns to translate (D=Question, E=Correct Answer, F=Option1, G=Option2, H=Option3)
COLUMNS_TO_TRANSLATE = ["D", "E", "F", "G", "H"]

# Row where data starts (after headers)
DATA_START_ROW = 7

# Language cell
LANGUAGE_CELL = "C3"

# Questions_process column mapping: process_col_index -> questions_col_index
# None means the value is computed (not a direct reference)
PROCESS_COL_MAPPING = {
    1: 1,      # A: Id              <- Questions col A
    2: 4,      # B: Question        <- Questions col D
    3: 5,      # C: Correct Answer  <- Questions col E
    4: 6,      # D: Answer 2        <- Questions col F
    5: 7,      # E: Answer 3        <- Questions col G
    6: 8,      # F: Answer 4        <- Questions col H
    7: None,   # G: Category code   (lookup)
    8: None,   # H: Lang            (from C3)
    9: 3,      # I: Question Type   <- Questions col C
    10: 10,    # J: Start Date      <- Questions col J
}

# Configuration named ranges for category lookup
CATEGORY_CODE_RANGE = (2, 3, 33)  # col B, rows 3-33
CATEGORY_NAME_RANGE = (3, 3, 33)  # col C, rows 3-33


class ExcelProcessor:
    def __init__(self, translator: TranslatorService):
        self.translator = translator

    async def process_excel(
        self,
        file_content: BinaryIO,
        target_lang_internal: str,
        target_lang_deepl: str,
        glossary_id: str | None = None,
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
            glossary_id: Optional DeepL glossary ID to use for translation

        Returns:
            tuple: (translated_excel_bytes, source_language, rows_translated)
        """
        # Load workbook preserving everything (no data_only)
        wb = load_workbook(filename=file_content)

        # Also load with data_only to read cached values for formula cells
        file_content.seek(0) if hasattr(file_content, 'seek') else None
        wb_data = load_workbook(filename=file_content, data_only=True)

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
                source_lang=source_lang,
                glossary_id=glossary_id,
            )

            # Write translated texts back to cells
            for (row_idx, col_letter), translated_text in zip(cell_positions, translated_texts):
                ws[f"{col_letter}{row_idx}"] = translated_text

            # Count unique rows translated
            rows_translated = len(set(pos[0] for pos in cell_positions))

        # Update language cell C3 with internal language code (as provided)
        ws[LANGUAGE_CELL] = target_lang_internal

        # Resolve Questions_process formulas with computed values
        ws_data = wb_data[SHEET_NAME] if SHEET_NAME in wb_data.sheetnames else None
        if PROCESS_SHEET_NAME in wb.sheetnames:
            self._resolve_process_sheet(wb, ws, target_lang_internal, ws_data)
        else:
            logger.debug(f"Sheet '{PROCESS_SHEET_NAME}' not found, skipping resolution")

        # Save to bytes (preserves all other sheets, formatting, etc.)
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return output.getvalue(), source_lang, rows_translated

    def _build_category_lookup(self, wb) -> dict[str, str]:
        """Build CategoryName -> CategoryCode lookup from Configuration sheet."""
        if CONFIG_SHEET_NAME not in wb.sheetnames:
            logger.warning(f"Sheet '{CONFIG_SHEET_NAME}' not found, category codes will be empty")
            return {}

        ws_config = wb[CONFIG_SHEET_NAME]
        lookup = {}
        code_col, start_row, end_row = CATEGORY_CODE_RANGE
        name_col = CATEGORY_NAME_RANGE[0]

        for row in range(start_row, end_row + 1):
            name = ws_config.cell(row=row, column=name_col).value
            code = ws_config.cell(row=row, column=code_col).value
            if name and code:
                lookup[str(name).strip()] = str(code).strip()

        return lookup

    def _resolve_process_sheet(
        self, wb, ws_questions: Worksheet, target_lang: str, ws_questions_data: Worksheet | None = None
    ):
        """Replace formulas in Questions_process with computed values.

        Uses ws_questions for translated values and ws_questions_data (data_only) as
        fallback when cells contain formulas instead of plain values.
        """
        ws_process = wb[PROCESS_SHEET_NAME]
        category_lookup = self._build_category_lookup(wb)
        row_offset = DATA_START_ROW - 2  # Process row 2 = Questions row 7, offset = 5

        rows_resolved = 0

        for process_row in range(2, ws_process.max_row + 1):
            questions_row = process_row + row_offset

            # Check if the Questions row has data (columns B, C, D, E non-blank)
            has_data = all(
                ws_questions.cell(row=questions_row, column=col).value is not None
                and str(ws_questions.cell(row=questions_row, column=col).value).strip()
                for col in [2, 3, 4, 5]  # B, C, D, E
            )

            if not has_data:
                # Write empty values for rows without data
                for col in range(1, 11):
                    ws_process.cell(row=process_row, column=col).value = ""
                continue

            rows_resolved += 1

            for process_col, questions_col in PROCESS_COL_MAPPING.items():
                cell = ws_process.cell(row=process_row, column=process_col)

                if process_col == 7:  # Category code
                    cat_name = ws_questions.cell(row=questions_row, column=2).value  # Questions col B
                    cell.value = category_lookup.get(str(cat_name).strip(), "") if cat_name else ""
                elif process_col == 8:  # Lang
                    cell.value = target_lang
                elif questions_col is not None:  # Direct reference
                    source_val = ws_questions.cell(row=questions_row, column=questions_col).value
                    # If the cell contains a formula, use the cached value from data_only
                    if isinstance(source_val, str) and source_val.startswith("=") and ws_questions_data:
                        source_val = ws_questions_data.cell(row=questions_row, column=questions_col).value
                    cell.value = source_val if source_val is not None else ""

        logger.info(f"Resolved {rows_resolved} rows in {PROCESS_SHEET_NAME}")


def get_excel_processor(translator: TranslatorService) -> ExcelProcessor:
    return ExcelProcessor(translator)
