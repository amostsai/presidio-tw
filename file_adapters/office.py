"""Edit Office XML in-place in its ZIP container; do not rebuild Office files."""
import io
import re
import zipfile
from copy import deepcopy
from lxml import etree
from .base import FileResult, FileProcessingError, MAX_UNPACKED_BYTES, compute_edits, replace_spans
from .structured import validate_xml

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'


def replace_text_nodes(nodes, transform):
    if not nodes: return False
    values = [n.text or '' for n in nodes]
    text = ''.join(values)
    if not text: return False
    edits = compute_edits(text, transform)
    if not edits: return False
    # Character edits are routed back to the originating run; replacement takes
    # the first run's formatting and trailing unaffected text retains its style.
    offset = 0
    for i, (node, value) in enumerate(zip(nodes, values)):
        end = offset + len(value)
        changes = []
        for start,stop,replacement in edits:
            left,right = max(start,offset), min(stop,end)
            insertion_here = offset <= start < end or (start == end == len(text) and i == len(nodes)-1)
            if left < right or insertion_here:
                changes.append((max(0,left-offset), max(0,right-offset), replacement if insertion_here else ''))
        if changes:
            node.text = replace_spans(value, changes)
            if node.text[:1].isspace() or node.text[-1:].isspace(): node.set(XML_SPACE, 'preserve')
        offset = end
    return True


def _word_text_groups(paragraph, namespace):
    # Tabs and line breaks are semantic boundaries, not absent characters.
    group = []
    for node in paragraph.iter():
        if next((a for a in node.iterancestors() if a.tag == '{'+namespace+'}p'), None) is not paragraph:
            continue
        if node.tag == '{'+namespace+'}t': group.append(node)
        elif node.tag in ('{'+namespace+'}tab', '{'+namespace+'}br', '{'+namespace+'}cr'):
            if group: yield group
            group = []
    if group: yield group


def _field_transform(transform,key):
    return lambda value: transform.for_field(value,key)


def _word_fields(root,transform):
    contexts = {}
    for table in root.iter('{'+W+'}tbl'):
        rows = table.findall('{'+W+'}tr')
        if not rows: continue
        cells = rows[0].findall('{'+W+'}tc')
        headers = [''.join(node.text or '' for node in cell.iter('{'+W+'}t')).strip() for cell in cells]
        if not any(transform.is_field_key(value) for value in headers): continue
        for cell in cells:
            for p in cell.iter('{'+W+'}p'): contexts[p] = False
        for row in rows[1:]:
            for index,cell in enumerate(row.findall('{'+W+'}tc')):
                if index >= len(headers): continue
                for p in cell.iter('{'+W+'}p'): contexts[p] = headers[index]
    return contexts


def _spreadsheet_fields(archive,names,transform):
    shared = validate_xml(archive.read('xl/sharedStrings.xml')) if 'xl/sharedStrings.xml' in names else None
    strings = list(shared) if shared is not None else []
    sheets, changed, skip, header_strings, converted = {}, set(), set(), set(), set()
    def shared_index(cell):
        try: return int(cell.find('{'+S+'}v').text)
        except (AttributeError,TypeError,ValueError) as exc: raise FileProcessingError('Excel 字串索引不合法') from exc
    def content(cell):
        if cell.get('t') == 's':
            index = shared_index(cell)
            if not 0 <= index < len(strings): raise FileProcessingError('Excel 字串索引超出範圍')
            return ''.join(node.text or '' for node in strings[index].iter('{'+S+'}t'))
        return ''.join(node.text or '' for node in cell.find('{'+S+'}is').iter('{'+S+'}t')) if cell.find('{'+S+'}is') is not None else (cell.findtext('{'+S+'}v') or '')
    def column(cell): return re.sub(r'[0-9]+$','',cell.get('r',''))
    for name in names:
        if not re.fullmatch(r'xl/worksheets/[^/]+\.xml',name): continue
        root = sheets[name] = validate_xml(archive.read(name))
        rows = list(root.iter('{'+S+'}row'))
        header = next((row for row in rows if any(transform.is_field_key(content(c).strip()) for c in row.findall('{'+S+'}c'))),None)
        if header is None: continue
        headers = {column(c):content(c).strip() for c in header.findall('{'+S+'}c')}
        for cell in header.findall('{'+S+'}c'):
            skip.add(cell)
            if cell.get('t') == 's': header_strings.add(shared_index(cell))
        for row in rows[rows.index(header)+1:]:
            for cell in row.findall('{'+S+'}c'):
                key = headers.get(column(cell))
                if key is None or not transform.is_field_key(key) or cell.find('{'+S+'}f') is not None: continue
                handler = _field_transform(transform,key)
                if cell.get('t') == 's':
                    index = shared_index(cell)
                    inline = deepcopy(strings[index]); inline.tag = '{'+S+'}is'
                    if replace_text_nodes(list(inline.iter('{'+S+'}t')),handler):
                        cell.remove(cell.find('{'+S+'}v')); cell.append(inline); cell.set('t','inlineStr')
                        converted.add(index); changed.add(name)
                elif cell.get('t') == 'inlineStr':
                    if replace_text_nodes(list(cell.iter('{'+S+'}t')),handler): changed.add(name)
                elif cell.get('t') == 'str':
                    nodes = cell.findall('{'+S+'}v')
                    if replace_text_nodes(nodes,handler): changed.add(name)
                skip.add(cell)
    remaining = {shared_index(c) for root in sheets.values() for c in root.iter('{'+S+'}c') if c.get('t')=='s'}
    # Remove private source strings after their last cell reference is converted.
    for index in converted-remaining:
        strings[index].clear(); etree.SubElement(strings[index],'{'+S+'}t').text = ''
        changed.add('xl/sharedStrings.xml')
    if shared is not None: sheets['xl/sharedStrings.xml'] = shared
    return sheets,changed,skip,header_strings


def _office(content, extension, transform):
    expected = {'docx':'word/document.xml', 'xlsx':'xl/workbook.xml'}[extension]
    media = {'docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}[extension]
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        with archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(names) != len(set(names)) or len(names) > 5000: raise FileProcessingError('Office ZIP 項目重複或過多')
            if sum(i.file_size for i in infos) > MAX_UNPACKED_BYTES: raise FileProcessingError('Office 解壓後超過 50 MiB')
            if any(i.flag_bits & 1 for i in infos): raise FileProcessingError('不支援加密 Office 文件')
            if expected not in names or '[Content_Types].xml' not in names: raise FileProcessingError('檔案不是指定的 Office 格式')
            if any('vbaproject' in n.lower() for n in names): raise FileProcessingError('不支援含巨集的 Office 文件')
            content_types = archive.read('[Content_Types].xml')
            types = validate_xml(content_types)
            main_type = {'docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml', 'xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'}[extension]
            if not any(e.get('PartName') == '/'+expected and e.get('ContentType') == main_type for e in types): raise FileProcessingError('Office 主文件类型與副檔名不符')
            modified = {}
            sheets,staged,skip,header_strings = _spreadsheet_fields(archive,names,transform) if extension=='xlsx' else ({},set(),set(),set())
            for name in names:
                if not name.endswith('.xml'): continue
                if extension == 'docx' and not name.startswith('word/'): continue
                if extension == 'xlsx' and not (name == 'xl/sharedStrings.xml' or re.fullmatch(r'xl/worksheets/[^/]+\.xml', name)): continue
                raw = archive.read(name)
                root = sheets[name] if name in sheets else validate_xml(raw)
                changed = name in staged
                if extension == 'docx':
                    fields = _word_fields(root,transform)
                    for paragraph in root.iter('{'+W+'}p'):
                        key = fields.get(paragraph)
                        if key is False: continue
                        handler = _field_transform(transform,key) if key is not None else transform
                        for nodes in _word_text_groups(paragraph, W):
                            changed |= replace_text_nodes(nodes, handler)
                    for paragraph in root.iter('{'+A+'}p'):
                        for nodes in _word_text_groups(paragraph, A):
                            changed |= replace_text_nodes(nodes, transform)
                else:
                    for index,string in enumerate(root.iter('{'+S+'}si')):
                        if index in header_strings: continue
                        changed |= replace_text_nodes(list(string.iter('{'+S+'}t')), transform)
                    for string in root.iter('{'+S+'}is'):
                        if string.getparent() in skip: continue
                        changed |= replace_text_nodes(list(string.iter('{'+S+'}t')), transform)
                    # Formula-cached text is not editable without changing formulas.
                    for cell in root.iter('{'+S+'}c'):
                        if cell in skip: continue
                        if cell.get('t') == 'str' and cell.find('{'+S+'}f') is None:
                            changed |= replace_text_nodes(list(cell.iter('{'+S+'}v')), transform)
                if changed:
                    declaration = raw.lstrip().startswith(b'<?xml')
                    modified[name] = etree.tostring(root, encoding='UTF-8', xml_declaration=declaration)
            if not modified: return FileResult(content, media, _warnings(extension))
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as writer:
                for info in infos: writer.writestr(info, modified.get(info.filename, archive.read(info.filename)))
            # Re-open and check CRC to catch a damaged output package.
            with zipfile.ZipFile(io.BytesIO(output.getvalue())) as verify:
                if verify.testzip() is not None: raise FileProcessingError('Office 輸出檔案驗證失敗')
            return FileResult(output.getvalue(), media, _warnings(extension))
    except (zipfile.BadZipFile, RuntimeError, KeyError, NotImplementedError) as exc:
        raise FileProcessingError('Office 檔案損壞、加密或無法讀取') from exc


def _warnings(extension):
    if extension == 'docx':
        return ['已處理段落、表格、頁首頁尾與可讀文字框；圖片、欄位指令、批註、文件屬性與嵌入物件內文字未處理。代碼長度可能影響換行。']
    return ['已處理字串儲存格與富文字；數字儲存格、公式、工作表名稱、批註、圖片、文件屬性與嵌入物件內個資未處理。列高、欄寬與公式保持原樣。']


def transform_docx(content, transform): return _office(content, 'docx', transform)


def transform_xlsx(content, transform): return _office(content, 'xlsx', transform)
