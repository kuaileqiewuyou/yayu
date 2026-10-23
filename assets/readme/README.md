# Yayu README visual assets

The README uses the user-selected B direction: the project's sage palette,
original mascot, and real Qt interface in one PNG opening image. The title is
芽语 / Yayu, with the subtitle 有角色、有故事的 AI 桌面伙伴.

- `hero.png` — published opening image, 1200 × 650.
- `chat-demo.png` — real Qt chat capture, 1100 × 850.
- `settings-demo.png` — real Qt system-settings capture, 1280 × 900.
- `source/hero-layout.svg` — editable typography and placement source.
- `source/render_hero.py` — deterministic Qt composition renderer.
- `source/capture_chat.py` — isolated real chat and system-settings capture.

Both captures were refreshed on 2026-10-21 for the Yayu name. The chat capture
uses XiaoYa's third-version full-body sprite; the settings title is 芽语 · 设置中心.
Both use temporary configuration files and authored demonstration data.
No model service was contacted, and no private character, chat history, API
key, or real user configuration appears in the screenshots. The captured
dialogue is authored demonstration data. The matching interface code and
built-in XiaoYa package are included in the repository. First-time startup
loads XiaoYa without replacing an existing local character configuration.
The accompanying `xiaoya-persona.md` is a documentation copy of the original
character setting; the runtime source is `data/characters/xiaoya/persona.md`.

The published README embeds the PNG. The SVG is an editable source and
references `../chat-demo.png`; keep that relative structure when editing.
The published PNG uses the development checkout's ChillRoundF font;
the renderer can also use an installed CJK system font. Commands, links,
configuration, and body copy remain searchable Markdown.

To rebuild from the repository root with its existing dependencies:

```powershell
.\venv\Scripts\python.exe assets\readme\source\capture_chat.py
.\venv\Scripts\python.exe assets\readme\source\render_hero.py
```

Use `--output <path.png>` to check a rebuild without replacing the published
asset, or `--font-family "Microsoft YaHei UI"` to select an installed font.
For `capture_chat.py`, use `--output <chat.png> --settings-output <settings.png>`
to direct the two real captures to different paths. All configuration and
authorization paths are temporary, and no model runtime is started.
Capturing a new screenshot requires the Qt application; the hero can be
rebuilt from the supplied PNG. The layout SVG does not recreate product
controls.

