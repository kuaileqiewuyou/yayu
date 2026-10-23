# 芽语许可适用范围 / Yayu License Scope

Required Notice: Copyright (c) 2026 kuaileqiewuyou (https://github.com/kuaileqiewuyou/yayu)

自芽语（Yayu）**1.0.5** 起，发布者有权授权的自有内容按 **PolyForm Noncommercial License 1.0.0** 提供。完整英文条款见本目录的 [Yayu-Noncommercial.txt](Yayu-Noncommercial.txt)；源码仓库根目录的 `LICENSE` 与该文件逐字相同。本说明界定许可对象，不改写或增加标准许可条款。

## 哪些内容适用

在没有单独许可声明的情况下，PolyForm Noncommercial 1.0.0 适用于发布者有权授权的芽语自有代码、对上游代码所作的自有新增或修改、项目文档，以及受版权保护且发布者有权授权的内置素材。内置小芽的人设、立绘、图标和 README 演示素材仅在符合上述权利条件的范围内适用；本说明不主张对不受版权保护的内容享有排他权。

许可允许条款规定的非商业用途，以及相应的修改和分发。个人用途与非商业组织用途的具体范围以英文原文的 “Noncommercial Purposes”“Personal Uses” 和 “Noncommercial Organizations” 为准。条款未允许的商业用途需要取得相应权利人的另行授权；本项目不通过这份许可授予该授权。分发适用内容时，请按标准条款的 “Notices” 保留许可全文或许可 URL，以及上面的 `Required Notice:` 行。

这是**源码可见、非商业授权**，不属于允许商业用途的 OSI 开源许可。

## 哪些内容有各自的许可

| 内容 | 适用许可与边界 |
| --- | --- |
| Shinsekai 早期 MIT 实现 | 原上游部分继续按 [Shinsekai-MIT.txt](Shinsekai-MIT.txt) 的 MIT 许可提供，保留 Copyright (c) 2026 Chihiro。包括保留或演化于 `sdk/messages.py`、`core/messaging/stream_parser.py`、`llm/llm_adapter.py` 的早期上游部分；这些文件内芽语的自有新增或修改只在发布者享有相应权利的范围内按本项目许可提供。文件所在位置不改变原上游部分的 MIT 权利，也不能以非商业条件撤销这些权利。来源核对版本与范围见[第三方通知](../THIRD_PARTY_NOTICES.md)。 |
| Python、Qt、PySide6、Shiboken6、FFmpeg 及其他依赖 | 各自的原始许可继续适用，详见运行时目录、依赖的 `*.dist-info/`、便携包 `THIRD_PARTY_NOTICES.txt` 和 `licenses/qt/`。 |
| 内置字体 | 按 [SIL OFL 1.1](../ui/assets/fonts/OFL.txt) 提供；保留字体原版权与保留名称。 |
| 用户导入的角色、图片、音频和其他素材 | 权利属于各自权利人，本项目许可不授予这些素材的使用权。 |
| 用户的密钥、私人配置、聊天记录和记忆 | 不属于本项目的授权发行内容，不随官方源码和便携包分发；本许可不改变用户对自己数据原有的权利。 |

各第三方许可原文及其版权、通知和权利保持不变。芽语的非商业条件不覆盖这些组件，不限制其原许可已经允许的使用、修改或分发，包括原许可允许的商业用途。

对 LGPL 涵盖的库，使用者保留适用许可要求的修改、替换和重新链接权利，以及为调试这些库的修改而进行逆向工程的权利。项目的非商业许可不限制这些权利。便携版以独立动态库提供相关组件，并附原始条款、对应源码和替换说明，详见 [Windows 便携版文档](../docs/windows-portable.md#第三方许可与源码)；请同时遵守各组件各自的条款。

## 版本与文件位置

本次选择的项目许可从 **1.0.5** 的发行内容开始适用，不追溯改写 **1.0.4 及更早发行版**当时的授权状态，也不撤销用户已从第三方许可或其他有效授权获得的权利。

源码仓库提供根目录 `LICENSE`，便于发现项目许可。Windows 便携包在 `licenses/Yayu-Noncommercial.txt` 和 `licenses/Yayu-LICENSE-SCOPE.md` 提供同一标准条款与本说明；不在包根目录新增 `LICENSE`，以兼容 1.0.4 更新器的文件白名单。许可效力与正文不因文件位置而变化。再次分发时，也须一并保留适用的第三方许可和通知。
