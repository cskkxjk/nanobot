# xlsx / pdf / pptx / docx 依赖说明

- **Python 包**：见项目根目录 `requirements.txt`，或 `pip install -e ".[skills]"`。
- **系统依赖**（LibreOffice、Poppler、Tesseract、Playwright 浏览器）：见项目根目录 `system-dependencies.txt`。

以下 skill 的完整功能依赖**系统二进制**和 **Python 包**，**不需要任何 API Key**，仅通过本地安装即可使用。

---

## 一、XLSX

| 类型 | 依赖 | 用途 | 仅 Python 可替代？ |
|------|------|------|--------------------|
| **系统** | **LibreOffice**（`soffice`） | 公式重算 `scripts/recalc.py` | 否，公式重算需 soffice |
| **系统** | `git`（可选） | 校验/redlining 时 diff 输出 | 可选 |
| **Python** | `openpyxl` | 读写 xlsx、公式与格式 | 是，核心读写不依赖 soffice |
| **Python** | `pandas` | 数据分析、`df.to_excel()` / `read_excel()` | 是（pandas 会依赖 openpyxl 或 xlrd） |

**结论**：  
- **仅“生成 xlsx 且数据分列”**：只需 Python 包 `openpyxl`（及可选 `pandas`），无需 API，也**不必**装 LibreOffice。  
- **需要公式在 Excel 中可重算**：必须安装 LibreOffice，并运行 `scripts/recalc.py`。

**安装示例**：
```bash
# 仅 Python（推荐先满足此项，解决“数据在一列”等基础问题）
pip install openpyxl pandas

# 公式重算（可选）
# Ubuntu/Debian: sudo apt install libreoffice-core
# macOS: brew install --cask libreoffice
```

---

## 二、PDF

| 类型 | 依赖 | 用途 | 仅 Python 可替代？ |
|------|------|------|--------------------|
| **Python** | `pypdf` | 合并/拆分/旋转/加密、表单字段 | 是 |
| **Python** | `pdfplumber` | 按版式提取文本、表格 | 是 |
| **Python** | `reportlab` | 生成 PDF | 是 |
| **Python** | `pdf2image` | PDF → 图片（用于 OCR/缩略图） | 需系统 Poppler，见下 |
| **系统** | **Poppler**（`pdftoppm` / `pdftotext`） | `pdf2image` 后端、命令行提取文本 | 否，pdf2image 依赖它 |
| **Python** | `pytesseract` | OCR 扫描版 PDF | 需系统 Tesseract |
| **系统** | **Tesseract**（可选） | OCR | 否 |

**结论**：  
- **读写/合并/拆分/填表/生成 PDF**：只需 Python 包（`pypdf`、`pdfplumber`、`reportlab`），**不需要 API**。  
- **OCR 扫描版 PDF**：需安装 Tesseract + `pytesseract`、`pdf2image`；`pdf2image` 又依赖 Poppler。

**安装示例**：
```bash
pip install pypdf pdfplumber reportlab

# 需要 PDF→图片 或 OCR 时再装
pip install pdf2image pytesseract
# Ubuntu/Debian: sudo apt install poppler-utils tesseract-ocr
# macOS: brew install poppler tesseract
```

---

## 三、PPTX

| 类型 | 依赖 | 用途 | 仅 Python 可替代？ |
|------|------|------|--------------------|
| **系统** | **LibreOffice**（`soffice`） | pptx → PDF 转换 | 否 |
| **系统** | **Poppler**（`pdftoppm`） | PDF → 图片，缩略图流程 | 否 |
| **Python** | `pdf2image`（可选） | 无 pdftoppm 时的 fallback | 依赖 Poppler |
| **Python** | `markitdown` | 从 pptx 提取文本（`python -m markitdown file.pptx`） | 是 |
| **Python** | 脚本内 `PIL`、`defusedxml` 等 | 缩略图、解包/校验 | 是 |

**结论**：  
- **仅读取/解析 pptx 文本**：可用 `markitdown` 等 Python 方案，**不需要 API**。  
- **缩略图、pptx→PDF→图片**：需要 LibreOffice + Poppler。

**安装示例**：
```bash
pip install markitdown Pillow defusedxml

# 缩略图 / 转 PDF 时
# Ubuntu/Debian: sudo apt install libreoffice-core poppler-utils
# macOS: brew install libreoffice poppler
```

---

## 四、DOCX

| 类型 | 依赖 | 用途 | 仅 Python 可替代？ |
|------|------|------|--------------------|
| **系统** | **LibreOffice**（`soffice`） | .doc→.docx、接受修订、导出 PDF | 否 |
| **系统** | **Poppler**（`pdftoppm`） | 文档→图片流程 | 否 |
| **系统** | `pandoc`（可选） | 从 docx 提取带修订的文本 | 可选 |
| **Python** | 脚本内 `defusedxml`、`lxml` 等 | 解包/校验/编辑 XML | 是 |

**结论**：  
- **只处理已是 .docx 的读写/编辑（XML 解包）**：可主要依赖 Python 脚本，**不需要 API**。  
- **.doc 转 .docx、导出 PDF、文档转图片**：需要 LibreOffice（及按需 Poppler）。

---

## 五、总结

| Skill | 仅用 Python 包可完成 | 需要系统二进制时 | 需要 API？ |
|-------|------------------------|------------------|------------|
| **xlsx** | 是（openpyxl/pandas）：创建/编辑/分列写入 | 公式重算 → LibreOffice | **否** |
| **pdf** | 是（pypdf/pdfplumber/reportlab）：读写/合并/拆分/填表/生成 | OCR/PDF→图 → Poppler、Tesseract | **否** |
| **pptx** | 部分（如 markitdown 读文本） | 缩略图/转 PDF → LibreOffice + Poppler | **否** |
| **docx** | 部分（解包/编辑 XML） | .doc 转换/导出 PDF → LibreOffice | **否** |

**实现“数据分列、不丢列”等基础表格行为**：只需安装 **openpyxl**（及按需 **pandas**），无需 LibreOffice 或任何 API。  
若希望公式在 Excel 中可重算，再单独安装 LibreOffice 并配合 `scripts/recalc.py` 使用即可。
