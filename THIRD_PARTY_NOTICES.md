# 第三方来源与许可

本文件说明项目中的第三方来源。自 1.0.5 起，芽语（Yayu）有权授权的自有内容按 PolyForm Noncommercial 1.0.0 提供，具体对象与例外见 [许可适用范围](licenses/Yayu-LICENSE-SCOPE.md)，标准条款见 [licenses/Yayu-Noncommercial.txt](licenses/Yayu-Noncommercial.txt)。这不改变下列第三方内容的原许可；各组件及素材继续遵守其各自条款，请连同相应版权和许可通知一起保留。

## Shinsekai 早期实现

芽语（Yayu，原 Galgame Agent）的早期设计与部分实现来自 [RachelForster/Shinsekai](https://github.com/RachelForster/Shinsekai) 的 MIT 许可时期，之后持续重构和扩展。保留和演化的部分包括结构化消息模型、流式解析器接口，以及模型参数白名单与过滤逻辑，分别位于 `sdk/messages.py`、`core/messaging/stream_parser.py` 和 `llm/llm_adapter.py`。

- 上游版权：**Copyright (c) 2026 Chihiro**。
- 适用于这些上游部分的许可：**MIT License**，全文原样保存在 [licenses/Shinsekai-MIT.txt](licenses/Shinsekai-MIT.txt)。
- 来源核对版本：[`697c1c1556018f3461f6fcd65f333762cf734155`](https://github.com/RachelForster/Shinsekai/tree/697c1c1556018f3461f6fcd65f333762cf734155)（2026-05-16）；该版本的 [LICENSE](https://github.com/RachelForster/Shinsekai/blob/697c1c1556018f3461f6fcd65f333762cf734155/LICENSE) 为 MIT。此提交用来固定核对的源码和许可，不表示已知最初导入的精确提交。

此来源说明仅针对早期 MIT 部分，不将上游后来采用其他许可的版本或其全部子项目列为本项目的 MIT 组成部分，也不表示芽语（Yayu）是上游官方发行版。

原上游 MIT 部分仍可按 MIT 许可使用、修改和分发，包括 MIT 允许的商业用途。芽语自有新增或修改仅在发布者享有相应权利的范围内采用项目许可；项目的非商业条件不覆盖或撤销原上游部分的 MIT 权利。

## Windows 便携版依赖

Windows 便携版还分发 CPython、PySide6 / Shiboken6、Qt 以及其他 Python 依赖。其具体版本和下载哈希记录在包内 `BUILD_INFO.json`，原始版权、许可和通知保留在 `runtime/`、各依赖的 `*.dist-info/` 及 `licenses/` 中。包内 `THIRD_PARTY_NOTICES.txt` 提供该次发行的组件清单、许可位置和对应源码获取说明。

有关便携包、第三方源码资产及库替换的具体说明，见 [Windows 便携版文档](docs/windows-portable.md)。

## 字体与角色资源

内置字体的许可随字体文件保存在 `ui/assets/fonts/`；内置小芽图像和角色资源不是 Shinsekai 素材。本通知不授予用户导入的第三方角色、图片、音频或其他素材的使用权。
