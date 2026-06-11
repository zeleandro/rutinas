#!/usr/bin/env python3
"""Genera el árbol markdown de las rutinas a partir de sus JSON normalizados.

Uso:
    python3 scripts/generar_rutina.py

Para cada rutina en ROUTINES emite:
  <slug>/README.md            índice de la rutina (lista de semanas)
  <slug>/semana-K/README.md   índice de la semana (lista de días)
  <slug>/semana-K/dia-N.md    tabla del día

Las semanas listadas en "manual" se hacen a mano y NO se tocan (solo se
generan las semanas presentes en el JSON). El índice de rutina se arma
escaneando el filesystem, así lista por igual las semanas manuales y las
generadas.
"""

import json
import os
import shutil
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROUTINES = [
    {
        "slug": "rutina-x-men",
        "titulo": "Rutina X-Men",
        "json": "rutinas_normalizadas_v3.json",
        "descripcion": "31 semanas. Fuente: IMG_0717 (PDF escaneado, normalizado v3).",
        "manual": [],
        "enfoque": {},
    },
    {
        "slug": "rutina-gemini",
        "titulo": "Rutina Gemini",
        "json": "gemini-code-1780609073340.json",
        "descripcion": (
            "10 semanas. Semana 1 a mano (PPL 6 días); semanas 2-10 generadas "
            "(Gemini: hipertrofia, 45-60 min, superseries, énfasis glúteo/cadena posterior)."
        ),
        "manual": [1],
        # Grupo muscular por número de día (el split se repite igual en cada semana).
        "enfoque": {
            1: "Piernas y Glúteos",
            2: "Pecho y Espalda",
            3: "Hombros y Brazos",
            4: "Piernas y Glúteos",
            5: "Pecho y Espalda",
            6: "Hombros y Brazos",
        },
    },
    {
        "slug": "rutina-claude",
        "titulo": "Rutina Claude",
        "json": "rutinas_nuevas_10semanas.json",
        "descripcion": (
            "10 semanas / 6 días. PPL con días de especialización y superseries. "
            "Objetivo: hipertrofia con bajo % de grasa."
        ),
        "manual": [],
        # "auto": el grupo muscular se infiere por día desde los ejercicios
        # (el split no es posicional fijo; el día 6 es de especialización).
        "enfoque": "auto",
    },
]


# Clasificador de grupo muscular por ejercicio. Lista ordenada: el primer
# substring (en minúsculas) que aparece en el nombre define el grupo. El orden
# va de específico a genérico para resolver ambigüedades (p. ej. "Remo al Ment."
# es Hombros y no Espalda; "Bíc. c/m. Bco. Incl." es Bíceps y no Pecho).
GRUPOS_KEYWORDS = [
    ("remo al ment", "Hombros"),
    ("press incl", "Pecho"),
    ("press declin", "Pecho"),
    ("press mancuerna hombros", "Hombros"),
    ("press mil", "Hombros"),
    ("v. lat", "Hombros"),
    ("vuel. lat", "Hombros"),
    ("vuelos lat", "Hombros"),
    ("v. later", "Hombros"),
    ("v. post", "Hombros"),
    ("vuel. post", "Hombros"),
    ("vuelos front", "Hombros"),
    ("delt. post", "Hombros"),
    ("encogim", "Hombros"),
    ("curl fr", "Tríceps"),          # Curl Francés
    ("ext. tric", "Tríceps"),
    ("hammer tric", "Tríceps"),
    ("pol. p/tric", "Tríceps"),
    ("pol. c/soga", "Tríceps"),
    ("apert", "Pecho"),
    ("cruce pol", "Pecho"),
    ("mariposa", "Pecho"),
    ("paralelas", "Pecho"),
    ("lagartijas", "Pecho"),
    ("hammer bíc", "Bíceps"),
    ("bco. scott", "Bíceps"),
    ("scott", "Bíceps"),
    ("bíc", "Bíceps"),               # antes que "bco." -> "Bíc. c/m. Bco. Incl."
    ("bco.", "Pecho"),               # Bco. Plano/Pl/Inclin/Incl/Declinado/Decl
    ("dominadas", "Espalda"),
    ("dorian", "Espalda"),
    ("pullover", "Espalda"),
    ("pol. al pecho", "Espalda"),
    ("remo", "Espalda"),
    ("sentadilla", "Piernas"),
    ("sent", "Piernas"),             # Sent. Fr., Sent. c/manc.
    ("hack", "Piernas"),
    ("prensa", "Piernas"),
    ("sillón", "Piernas"),
    ("camilla", "Piernas"),
    ("estoc", "Piernas"),
    ("tijeras", "Piernas"),
    ("peso muerto", "Piernas"),
    ("despegue", "Piernas"),
    ("si-si", "Piernas"),
    ("costurera", "Piernas"),
    ("pant", "Piernas"),             # Pantorrillera, Pant. Parado/Multif, Pantorrillas
]

# Orden de display (y desempate) cuando un día combina dos grupos.
PRIORIDAD_ENFOQUE = ["Piernas", "Pecho", "Espalda", "Hombros", "Bíceps", "Tríceps"]


def grupo_de(ejercicio):
    """Devuelve el grupo muscular de un ejercicio, o None si no matchea."""
    nombre = ejercicio.lower()
    for kw, grupo in GRUPOS_KEYWORDS:
        if kw in nombre:
            return grupo
    return None


def clasificar_enfoque(bloques):
    """Infiere el enfoque (grupo muscular) de un día a partir de sus ejercicios.

    Cuenta los grupos sobre todos los ejercicios del día (incluidos los de cada
    superserie), toma los 2 más frecuentes y los ordena por PRIORIDAD_ENFOQUE.
    """
    conteo = {}
    for b in bloques:
        ejercicios = b.get("ejercicios", [b]) if b.get("tipo") == "superserie" else [b]
        for e in ejercicios:
            g = grupo_de(e.get("ejercicio", ""))
            if g:
                conteo[g] = conteo.get(g, 0) + 1
    if not conteo:
        return ""
    # Top 2 por conteo desc, desempate por prioridad.
    top = sorted(conteo, key=lambda g: (-conteo[g], PRIORIDAD_ENFOQUE.index(g)))[:2]
    top.sort(key=PRIORIDAD_ENFOQUE.index)
    return " y ".join(top)


def num_suffix(key):
    """semana_10 -> 10, dia_3 -> 3."""
    return int(key.rsplit("_", 1)[1])


def fmt_reps(reps):
    """[10, 8] -> '10, 8'; [3] -> '3'; 'Fallo' -> 'Fallo'; None -> ''.

    reps puede venir como array (con números y/o strings, p. ej.
    [12, 10, 8, '6+Fallo']) o como string suelto ('Fallo', '20 pasos').
    """
    if reps is None:
        return ""
    if isinstance(reps, str):
        return reps
    return ", ".join(str(r) for r in reps)


def render_dia(semana_n, dia_n, bloques, prev_dia, next_dia, enfoque=None):
    titulo = f"# Semana {semana_n} · Día {dia_n}"
    if enfoque:
        titulo += f" — {enfoque}"
    lines = [titulo, ""]
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


def render_semana_index(titulo, semana_n, dias, prev_sem, next_sem, enfoque_map=None):
    lines = [f"# {titulo} — Semana {semana_n}", ""]
    if enfoque_map:
        lines.append("| Día | Enfoque | Bloques |")
        lines.append("|-----|---------|--------:|")
        for dia_n, bloques in dias:
            enf = enfoque_map.get(dia_n, "")
            lines.append(f"| [Día {dia_n}](dia-{dia_n}.md) | {enf} | {len(bloques)} |")
    else:
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


def render_rutina_index(titulo, descripcion, semanas_con_dias):
    """semanas_con_dias: lista ordenada de (numero_semana, cantidad_dias)."""
    lines = [f"# {titulo}", ""]
    lines.append(descripcion)
    lines.append("")
    lines.append("| Semana | Días |")
    lines.append("|--------|-----:|")
    for sn, ndias in semanas_con_dias:
        lines.append(f"| [Semana {sn}](semana-{sn}/README.md) | {ndias} |")
    lines.append("")
    lines.append("---")
    lines.append("[← Volver al índice](../README.md)")
    lines.append("")
    return "\n".join(lines)


def contar_dias(sem_dir):
    """Cuenta archivos dia-*.md dentro de una carpeta de semana."""
    if not os.path.isdir(sem_dir):
        return 0
    return len([f for f in os.listdir(sem_dir) if re.fullmatch(r"dia-\d+\.md", f)])


def generar(rutina):
    with open(os.path.join(ROOT, rutina["json"]), encoding="utf-8") as f:
        data = json.load(f)
    rutinas = data["rutinas"]
    out_dir = os.path.join(ROOT, rutina["slug"])
    manual = set(rutina["manual"])
    enfoque_cfg = rutina.get("enfoque") or {}
    os.makedirs(out_dir, exist_ok=True)

    def enfoque_semana(dias):
        """Mapa {num_dia: label} para una semana, según la config de enfoque."""
        if enfoque_cfg == "auto":
            return {dn: clasificar_enfoque(bloques) for dn, bloques in dias}
        if isinstance(enfoque_cfg, dict) and enfoque_cfg:
            return {dn: enfoque_cfg.get(dn, "") for dn, _ in dias}
        return {}

    # Semanas presentes en el JSON, ordenadas: (num, [(num_dia, bloques), ...])
    json_semanas = []
    for sk in sorted(rutinas, key=num_suffix):
        sn = num_suffix(sk)
        dias = [
            (num_suffix(dk), rutinas[sk][dk])
            for dk in sorted(rutinas[sk], key=num_suffix)
        ]
        json_semanas.append((sn, dias))

    # Rango completo (manuales + generadas) para la navegación entre semanas.
    todas = sorted(manual | {sn for sn, _ in json_semanas})

    # Borrado selectivo: limpiar solo las semanas generadas (preserva las manuales).
    for name in os.listdir(out_dir):
        m = re.fullmatch(r"semana-(\d+)", name)
        if m and int(m.group(1)) not in manual:
            shutil.rmtree(os.path.join(out_dir, name))

    for sn, dias in json_semanas:
        sem_dir = os.path.join(out_dir, f"semana-{sn}")
        os.makedirs(sem_dir, exist_ok=True)
        i = todas.index(sn)
        prev_sem = todas[i - 1] if i > 0 else None
        next_sem = todas[i + 1] if i < len(todas) - 1 else None

        week_enf = enfoque_semana(dias)
        with open(os.path.join(sem_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write(render_semana_index(rutina["titulo"], sn, dias, prev_sem, next_sem, week_enf or None))

        dia_nums = [dn for dn, _ in dias]
        for j, (dn, bloques) in enumerate(dias):
            prev_dia = dia_nums[j - 1] if j > 0 else None
            next_dia = dia_nums[j + 1] if j < len(dia_nums) - 1 else None
            with open(os.path.join(sem_dir, f"dia-{dn}.md"), "w", encoding="utf-8") as f:
                f.write(render_dia(sn, dn, bloques, prev_dia, next_dia, week_enf.get(dn)))

    # Índice de rutina: escanea el filesystem (manuales + generadas).
    semanas_con_dias = [
        (sn, contar_dias(os.path.join(out_dir, f"semana-{sn}"))) for sn in todas
    ]
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(render_rutina_index(rutina["titulo"], rutina["descripcion"], semanas_con_dias))

    gen = sum(len(dias) for _, dias in json_semanas)
    print(f"Generado {rutina['slug']}/: {len(todas)} semanas ({len(json_semanas)} del JSON, "
          f"{len(manual)} manual), {gen} días generados.")


def main():
    for rutina in ROUTINES:
        generar(rutina)


if __name__ == "__main__":
    main()
