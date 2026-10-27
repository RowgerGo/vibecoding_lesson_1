# 简历测试样本

这些文件仅含虚构资料，不含真实个人信息。

- `resume.rtf`：Word 样本的可读源文件。
- `resume.doc`：使用 macOS `textutil -convert doc` 从 RTF 生成的二进制 Word 文件，包含真实 `WordDocument` 数据流。
- `resume.docx`：使用 `textutil -convert docx` 从 RTF 生成的 Office Open XML 文档。
- `resume.pdf`：包含一页文字、字体、交叉引用表和根目录的 PDF 1.4 文档。

样本直接随仓库保存，其他平台运行测试无需安装 `textutil`。测试不会通过改扩展名来模拟文件格式。
