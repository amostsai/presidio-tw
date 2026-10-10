import io
import zipfile


def package(parts):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, value in parts.items(): z.writestr(name, value)
    return out.getvalue()


def docx_sample():
    return package({
      '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
      'word/document.xml': '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>王</w:t></w:r><w:r><w:t>小明</w:t></w:r><w:r><w:t> 記錄</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>王小明</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>',
      'word/header1.xml': '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>王小明</w:t></w:r></w:p></w:hdr>',
      'word/styles.xml': '<styles/>', 'word/media/image.png': b'unchanged-image',
    })


def xlsx_sample():
    return package({
      '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>',
      'xl/workbook.xml': '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="Sheet1" sheetId="1"/></sheets></workbook>',
      'xl/sharedStrings.xml': '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><r><rPr><b/></rPr><t>王</t></r><r><t>小明</t></r></si></sst>',
      'xl/worksheets/sheet1.xml': '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cols><col min="1" max="1" width="20"/></cols><sheetData><row r="1"><c r="A1" t="s" s="1"><v>0</v></c><c r="B1" t="inlineStr"><is><t>王小明</t></is></c><c r="C1"><f>1+1</f><v>2</v></c></row></sheetData><mergeCells><mergeCell ref="A2:B2"/></mergeCells></worksheet>',
      'xl/styles.xml': '<styles/>', 'xl/media/image.png': b'unchanged-image',
    })
