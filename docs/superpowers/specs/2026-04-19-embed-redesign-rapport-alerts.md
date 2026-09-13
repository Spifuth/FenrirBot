# Embed Redesign: /rapport and /alerts

## Goal

Redesign the `/rapport` and `/alerts` Discord embeds to match a Glances-style aesthetic: clean, minimal, static colour, code-block fields with properly aligned ASCII bars.

## Design principles

- Static embed colour `#2C2F33` on all embeds (no dynamic colour based on values)
- All metric values inside triple-backtick code blocks — guaranteed monospace alignment on every client
- ASCII progress bar: filled `█`, empty `·`, width 10, wrapped in `[…]`
- Severity labels in `/alerts` padded to the same width so the separator `·` always aligns
- French UI text, English code

---

## Progress bar helper

Replace `create_progress_bar` usage with a local `_bar(value, total=100, width=10)` function (defined in the cog file, not in helpers — no other cog uses this style).

```python
def _bar(value: float, width: int = 10) -> str:
    filled = round(max(0.0, min(value, 100.0)) / 100 * width)
    return "[" + "█" * filled + "·" * (width - filled) + "]"
```

Output examples:
- `_bar(42.3)` → `[████······]`
- `_bar(91.0)` → `[█████████·]`
- `_bar(0)`    → `[··········]`

---

## /rapport embed

### Layout

| Property | Value |
|----------|-------|
| Color | `0x2C2F33` |
| Title | `Rapport · {period_label}` |
| Fields | 3 × full-width (not inline) |
| Footer | `Fenrir · VictoriaMetrics` |
| Timestamp | `datetime.now()` |

### Field: CPU

Name: `CPU`
Value (code block):
```
avg  [████████··]  78.3%
pic  [█████████·]  91.0%
```

Format string:
```python
f"```\navg  {_bar(cpu_stats['avg'])}  {cpu_stats['avg']:5.1f}%\npic  {_bar(cpu_stats['max'])}  {cpu_stats['max']:5.1f}%\n```"
```

If `cpu_stats` is None: value is ```` ```\nn/a\n``` ````

### Field: RAM

Same structure as CPU using `ram_stats`.

### Field: Réseau

Name: `Réseau`
Value (code block):
```
↓  12.40 GB
↑   3.10 GB
```

Format string:
```python
f"```\n↓  {_fmt_bytes(net_rx)}\n↑  {_fmt_bytes(net_tx)}\n```"
```

`_fmt_bytes` returns right-aligned strings: values padded so GB/MB/KB align.
Exact format: `f"{value:>8.2f} GB"` / `f"{value:>8.1f} MB"` / `f"{value:>8.1f} KB"`.
If None: `"     N/A"`.

---

## /alerts embed

### No alerts firing

| Property | Value |
|----------|-------|
| Color | `0x2C2F33` |
| Title | `Aucune alerte` |
| Description | `Tous les systèmes sont opérationnels.` |
| Footer | `Fenrir · Grafana` |
| Timestamp | `datetime.now()` |

### Alerts firing

| Property | Value |
|----------|-------|
| Color | `0x2C2F33` |
| Title | `Alertes · {count}` |
| Description | e.g. `1 critique · 2 avertissements` (see below) |
| Fields | Up to 10 × full-width |
| Footer | `Fenrir · Grafana Alertmanager` (+ overflow note if >10) |
| Timestamp | `datetime.now()` |

### Description line

Count criticals and warnings separately:
```python
parts = []
if n_critical: parts.append(f"{n_critical} critique")
if n_warning:  parts.append(f"{n_warning} avertissement{'s' if n_warning > 1 else ''}")
if not parts:  parts.append(f"{count} alerte{'s' if count > 1 else ''}")
description = " · ".join(parts)
```

### Per-alert field

Name: alert name (e.g. `HighCPUUsage`)
Value (code block):

```
CRITICAL  · depuis 14m
node:9100
CPU usage above threshold (94.2%)
```

Severity label padded to 8 chars so `·` aligns:
```python
SEV_WIDTH = 8  # len("CRITICAL")
label = severity.upper().ljust(SEV_WIDTH)
duration_part = f" · depuis {duration}" if duration else ""
line1 = f"{label}{duration_part}"
```

Instance line: only included if non-empty.
Summary line: `annotations.summary` or `annotations.description`, truncated to 100 chars. Only included if non-empty.

Full value:
```python
lines = [line1]
if instance: lines.append(instance)
if summary:  lines.append(summary[:100])
value = "```\n" + "\n".join(lines) + "\n```"
```

---

## Files changed

| File | Change |
|------|--------|
| `src/cogs/reports.py` | Replace embed build logic; add `_bar()` helper; update `_fmt_bytes()` for fixed-width output |
| `src/cogs/alerts.py` | Replace embed build logic; add severity counting and padded label formatting |

No changes to `src/utils/`, `src/config.py`, or `src/bot.py`.
