"""Geometric PDF text redaction, followed by extractable replacement text."""
import pymupdf
from itertools import groupby
from .base import FileResult, FileProcessingError, compute_edits

MIN_FONT_SIZE = 5.0


def _line_chars(page):
    raw = page.get_text('rawdict')
    for block_index, block in enumerate(raw['blocks']):
        if block.get('type') != 0: continue
        for line in block['lines']:
            chars = [dict(c, size=span['size'], color=span['color']) for span in line['spans'] for c in span['chars']]
            if chars: yield dict(line, block_index=block_index), chars


def _text_units(lines, transform):
    """Recognize aligned table rows without flattening unrelated page text.

    PDF creators often put all cells in one block, with wrapped cell text in
    multiple lines. Exact configured headers identify the columns; only blocks
    whose lines align to those columns are treated as table data.
    """
    blocks = {}
    for line, chars in lines:
        blocks.setdefault(line['block_index'], []).append((line, chars))
    headers = None
    header_bottom = 0
    for rows in blocks.values():
        labels = [''.join(c['c'] for c in chars).strip() for _, chars in rows]
        known = [transform.is_field_key(label) for label in labels]
        baselines = [chars[0]['origin'][1] for _, chars in rows]
        columns_x = {round(line['bbox'][0],1) for line, _ in rows}
        if sum(known) >= 2 and len(columns_x) >= 2 and max(baselines)-min(baselines) <= 2:
            headers = [(line['bbox'][0], label) for (line, _), label in zip(rows, labels)]
            header_bottom = max(line['bbox'][3] for line, _ in rows)
            # A horizontal key/value form can resemble a header. Only exact
            # configured labels are exempt: always inspect unrecognized text.
            for (line, chars), is_label in zip(rows, known):
                yield line, chars, None, is_label
            continue
        columns = []
        if headers and min(line['bbox'][1] for line, _ in rows) >= header_bottom:
            for line, _ in rows:
                columns.append(next((i for i, (x, _) in enumerate(headers)
                                     if abs(line['bbox'][0]-x) < 2), None))
        if columns and None not in columns and len(set(columns)) >= 2:
            grouped = {}
            for column, (line, chars) in zip(columns, rows):
                grouped.setdefault(column, []).append((line, chars))
            for column, cell in grouped.items():
                if any(line['dir'] != cell[0][0]['dir'] for line, _ in cell):
                    raise FileProcessingError('PDF 儲存格含不同方向文字，無法安全替換')
                yield cell[0][0], [c for _, chars in cell for c in chars], headers[column][1], False
        else:
            for line, chars in rows: yield line, chars, None, False


def _color(integer):
    return ((integer>>16 & 255)/255, (integer>>8 & 255)/255, (integer & 255)/255)


def _font_runs(text):
    # Built-in CJK PDF fonts render Latin characters at full width, even
    # though Font.text_length reports proportional widths for them. Use the
    # same font for measuring and inserting each run to prevent clipping.
    for ascii_run, chars in groupby(text, key=lambda c: ord(c) < 128):
        yield ('helv' if ascii_run else 'china-t'), ''.join(chars)


def _text_width(text, size=1):
    return sum(len(run)*size if font == 'china-t'
               else pymupdf.Font(fontname=font).text_length(run, fontsize=size)
               for font, run in _font_runs(text))


def _fit_replacement(page, all_chars, targets, replacement, following_x=None):
    original = pymupdf.Rect(targets[0]['bbox'])
    for c in targets[1:]: original |= pymupdf.Rect(c['bbox'])
    right = page.mediabox.width - 10
    target_ids = {id(c) for c in targets}
    for c in all_chars:
        if id(c) in target_ids: continue
        box = pymupdf.Rect(c['bbox'])
        if box.x0 >= original.x1-.1 and box.y0 < original.y1 and box.y1 > original.y0:
            right = min(right, box.x0-1)
    right = max(original.x1, right)
    if following_x is not None: right = min(right, following_x-1)
    width = _text_width(replacement)
    size = min(targets[0]['size'], (right-original.x0)/max(width, .001))
    return (pymupdf.Point(targets[0]['origin']), replacement, size, _color(targets[0]['color']))


def transform_pdf(content, transform):
    try:
        doc = pymupdf.open(stream=content, filetype='pdf')
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise FileProcessingError('PDF 檔案損壞或無法讀取') from exc
    with doc:
        if doc.needs_pass: raise FileProcessingError('不支援加密 PDF')
        found_text = False
        expected = []
        changed = False
        warnings = ['PDF 已處理文字層；圖片、註解、表單、附件與文件屬性內個資未處理。字型可能變更，排版盡量保留。']
        for page in doc:
            lines = list(_line_chars(page))
            all_chars = [c for _,chars in lines for c in chars]
            operations = []
            redactions = []
            target_ids = set()
            for line, chars, field_key, is_header in _text_units(lines, transform):
                text = ''.join(c['c'] for c in chars)
                found_text |= bool(text.strip())
                if is_header: continue
                if field_key is not None:
                    output = transform.for_field(text, field_key)
                    # Rewrite the cell as a whole, keeping its complete token
                    # and removing every line of a wrapped sensitive value.
                    edits = [] if output == text else [(0, len(chars), output)]
                else:
                    edits = compute_edits(text, transform)
                if edits and (abs(line['dir'][0]-1) > .01 or abs(line['dir'][1]) > .01):
                    raise FileProcessingError('PDF 含直書或旋轉文字，無法安全保留替換排版')
                prepared = []
                for start,end,replacement in edits:
                    if not 0 <= start < end <= len(chars): raise FileProcessingError('PDF 文字替換位置不合法')
                    targets = chars[start:end]
                    following = [chars[a]['bbox'][0] for a,_,_ in edits if a > start]
                    prepared.append((targets, _fit_replacement(page, all_chars, targets, replacement,
                                                               min(following) if following else None)))
                if any(operation[2] < MIN_FONT_SIZE for _, operation in prepared):
                    # An inline value may be tightly followed by punctuation.
                    # Rewrite its line, including unchanged text, to use the
                    # line's available whitespace instead of overlapping it.
                    output = text
                    for start,end,replacement in reversed(edits):
                        output = output[:start]+replacement+output[end:]
                    prepared = [(chars, _fit_replacement(page, all_chars, chars, output))]
                for targets, operation in prepared:
                    if operation[2] < MIN_FONT_SIZE:
                        raise FileProcessingError('PDF 替換區域空間不足，無法容納完整且可讀的代碼／原文')
                    # Remove rewritten glyphs and retain artwork/images beneath.
                    for c in targets:
                        target_ids.add(id(c))
                        box = pymupdf.Rect(c['bbox'])
                        shrink = box.height*.2
                        box.y0 += shrink; box.y1 -= shrink
                        if box.width > .1:
                            box.x0 += .05; box.x1 -= .05
                        redactions.append(box)
                    operations.append(operation)
            if operations:
                for rect in redactions:
                    if any(id(c) not in target_ids and rect.intersects(pymupdf.Rect(c['bbox'])) for c in all_chars):
                        raise FileProcessingError('PDF 敏感文字與相鄰文字過近，移除會影響其他內容，已停止輸出')
                changed = True
                for rect in redactions: page.add_redact_annot(rect, fill=False, cross_out=False)
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE, text=pymupdf.PDF_REDACT_TEXT_REMOVE)
                for point,text,size,color in operations:
                    for fontname, run in _font_runs(text):
                        page.insert_text(point, run, fontname=fontname, fontsize=size, color=color)
                        point = pymupdf.Point(point.x + _text_width(run, size), point.y)
                    expected.append((page.number,text))
        if not found_text: raise FileProcessingError('PDF 沒有可讀文字層，掃描檔需要 OCR（第一版未提供）')
        if not changed: return FileResult(content, 'application/pdf', warnings)
        output = doc.tobytes(garbage=4, deflate=True, clean=True)
    with pymupdf.open(stream=output, filetype='pdf') as verify:
        for page_number,text in expected:
            if text not in verify[page_number].get_text():
                raise FileProcessingError('PDF 替換文字無法完整抽取，已停止輸出以避免無法復原')
    return FileResult(output, 'application/pdf', warnings)
