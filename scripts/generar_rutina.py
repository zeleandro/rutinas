#!/usr/bin/env python3
"""Genera el árbol markdown de una rutina a partir del JSON normalizado.

Uso:
    python3 scripts/generar_rutina.py

Lee rutinas_normalizadas_v3.json y emite el árbol rutina-x-men/ con:
  rutina-x-men/README.md            índice de la rutina (lista de semanas)
  rutina-x-men/semana-K/README.md   índice de la semana (lista de días)
  rutina-x-men/semana-K/dia-N.md    tabla del día

NO toca rutina-ia/ (esa es a mano).
"""

import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(ROOT, "rutinas_normalizadas_v3.json")
SLUG = "rutina-x-men"
TITULO = "Rutina X-Men"
FUENTE = "IMG_0717 (PDF escaneado, normalizado v3)"


def num_suffix(key):
    """semana_10 -> 10, dia_3 -> 3."""
    return int(key.rsplit("_", 1)[1])


def fmt_reps(reps):
    """[10, 8] -> '10, 8'; [3] -> '3'; 'Fallo' -> 'Fallo'; None -> ''.

    reps puede venir como array numérico o como string suelto (p. ej.
    'Fallo', '20 pasos', 'ilegible').
    """
    if reps is None:
        return ""
    if isinstance(reps, str):
        return reps
    return ", ".join(str(r) for r in reps)


def render_dia(semana_n, dia_n, bloques, prev_dia, next_dia):
    lines = [f"# Semana {semana_n} · Día {dia_n}", ""]
    lines.append("| Ejercicio | Series | Reps |")
    lines.append("|-----------|:------:|:----:|")

    notas = []  # (ejercicio, observaciones)
    for b in bloques:
        if b.get("tipo") == "superserie":
            lines.append(f"| **Superserie ×{b.get('series', '')}** |  |  |")
            for e in b.get("ejercicios", []):
                lines.append(f"| ↳ {e['ejercicio']} |  | {fmt_reps(e.get('reps'))} |")
        else:
            lines.append(
                f"| {b['ejercicio']} | {b.get('series', '')} | {fmt_reps(b.get('reps'))} |"
            )
        if b.get("observaciones"):
            etiqueta = b.get("ejercicio") or "Superserie"
            notas.append((etiqueta, b["observaciones"]))

    lines.append("")
    for etiqueta, obs in notas:
        lines.append(f"> ⚠️ *{etiqueta}:* {obs}")
    if notas:
        lines.append("")

    nav = []
    if prev_dia is not None:
        nav.append(f"◀ [Día {prev_dia}](dia-{prev_dia}.md)")
    nav.append("[Índice semana](README.md)")
    if next_dia is not None:
        nav.append(f"[Día {next_dia} ▶](dia-{next_dia}.md)")
    lines.append("---")
    lines.append(" · ".join(nav))
    lines.append("")
    return "\n".join(lines)


def render_semana_index(semana_n, dias, prev_sem, next_sem):
    lines = [f"# {TITULO} — Semana {semana_n}", ""]
    lines.append("| Día | Bloques |")
    lines.append("|-----|--------:|")
    for dia_n, bloques in dias:
        lines.append(f"| [Día {dia_n}](dia-{dia_n}.md) | {len(bloques)} |")
    lines.append("")

    nav = []
    if prev_sem is not None:
        nav.append(f"◀ [Semana {prev_sem}](../semana-{prev_sem}/README.md)")
    nav.append("[Índice rutina](../README.md)")
    if next_sem is not None:
        nav.append(f"[Semana {next_sem} ▶](../semana-{next_sem}/README.md)")
    lines.append("---")
    lines.append(" · ".join(nav))
    lines.append("")
    return "\n".join(lines)


def render_rutina_index(semanas):
    lines = [f"# {TITULO}", ""]
    lines.append(f"{len(semanas)} semanas. Fuente: {FUENTE}.")
    lines.append("")
    lines.append("| Semana | Días |")
    lines.append("|--------|-----:|")
    for semana_n, dias in semanas:
        lines.append(f"| [Semana {semana_n}](semana-{semana_n}/README.md) | {len(dias)} |")
    lines.append("")
    lines.append("---")
    lines.append("[← Volver al índice](../README.md)")
    lines.append("")
    return "\n".join(lines)


def main():
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    rutinas = data["rutinas"]
    out_dir = os.path.join(ROOT, SLUG)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    # Lista ordenada de (numero_semana, [(numero_dia, bloques), ...])
    semanas = []
    for sk in sorted(rutinas, key=num_suffix):
        sn = num_suffix(sk)
        dias = [
            (num_suffix(dk), rutinas[sk][dk])
            for dk in sorted(rutinas[sk], key=num_suffix)
        ]
        semanas.append((sn, dias))

    sem_nums = [sn for sn, _ in semanas]

    for idx, (sn, dias) in enumerate(semanas):
        sem_dir = os.path.join(out_dir, f"semana-{sn}")
        os.makedirs(sem_dir)
        prev_sem = sem_nums[idx - 1] if idx > 0 else None
        next_sem = sem_nums[idx + 1] if idx < len(sem_nums) - 1 else None

        with open(os.path.join(sem_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write(render_semana_index(sn, dias, prev_sem, next_sem))

        dia_nums = [dn for dn, _ in dias]
        for j, (dn, bloques) in enumerate(dias):
            prev_dia = dia_nums[j - 1] if j > 0 else None
            next_dia = dia_nums[j + 1] if j < len(dia_nums) - 1 else None
            with open(os.path.join(sem_dir, f"dia-{dn}.md"), "w", encoding="utf-8") as f:
                f.write(render_dia(sn, dn, bloques, prev_dia, next_dia))

    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(render_rutina_index(semanas))

    total_dias = sum(len(dias) for _, dias in semanas)
    print(f"Generado {SLUG}/: {len(semanas)} semanas, {total_dias} días.")


if __name__ == "__main__":
    main()
