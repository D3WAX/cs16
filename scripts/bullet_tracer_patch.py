#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Patch: bullet tracer + console cvar "bullet_trace" (0..1).

  bullet_trace 0     -> off (default)
  bullet_trace 1     -> tracer on every shot
  bullet_trace 0.3   -> 30% chance of a tracer per bullet

Usage (from repo root):  python scripts/bullet_tracer_patch.py
Safe to run more than once.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TARGET = os.path.join(ROOT, "cl_dll", "events", "ev_cs16.cpp")
MARKER = "EV_CS16_BulletTracer"

HELPER = '''/*
================
EV_CS16_BulletTracer

Draws a tracer for the "bullet_trace" cvar (0..1, chance per bullet).
================
*/
static cvar_t *g_pBulletTrace = NULL;

static void EV_CS16_BulletTracer( int idx, float *vecSrc, float *end, float *forward, float *right )
{
\tif( !g_pBulletTrace )
\t\tg_pBulletTrace = CVAR_CREATE( "bullet_trace", "0", FCVAR_ARCHIVE );

\tif( !g_pBulletTrace )
\t\treturn;

\tfloat chance = g_pBulletTrace->value;

\tif( chance <= 0.0f )
\t\treturn;

\tif( chance < 1.0f && gEngfuncs.pfnRandomFloat( 0.0f, 1.0f ) > chance )
\t\treturn;

\tvec3_t start;

\t// muzzle-ish position, same offsets the HL events used
\tfor( int i = 0; i < 3; i++ )
\t\tstart[i] = vecSrc[i] + right[i] * 2.0f + forward[i] * 16.0f;

\tstart[2] -= 4.0f;

\tgEngfuncs.pEfxAPI->R_TracerEffect( start, end );
}

'''

# (anchor, replacement, description)
EDITS = [
    (
        "/*\n================\nEV_HLDM_FireBullets\n",
        HELPER + "/*\n================\nEV_HLDM_FireBullets\n",
        "helper + cvar",
    ),
    (
        "\t\twhile (iShotPenetration != 0)\n",
        "\t\tbool bTracerDone = false;\n\n\t\twhile (iShotPenetration != 0)\n",
        "tracer flag",
    ),
    (
        "\t\t\tgEngfuncs.pEventAPI->EV_PlayerTrace( vecShotSrc, vecEnd, 0, -1, &tr );\n",
        "\t\t\tgEngfuncs.pEventAPI->EV_PlayerTrace( vecShotSrc, vecEnd, 0, -1, &tr );\n\n"
        "\t\t\t// only the first segment (muzzle -> first impact)\n"
        "\t\t\tif( !bTracerDone )\n\t\t\t{\n\t\t\t\tbTracerDone = true;\n"
        "\t\t\t\tEV_CS16_BulletTracer( idx, vecSrc, tr.endpos, forward, right );\n\t\t\t}\n",
        "tracer call",
    ),
]


def main():
    if not os.path.isfile(TARGET):
        sys.exit("not found: " + TARGET)

    with open(TARGET, "r", newline="") as f:
        src = f.read()

    if MARKER in src:
        print("already patched, nothing to do")
        return

    crlf = "\r\n" in src
    if crlf:
        src = src.replace("\r\n", "\n")

    for anchor, repl, name in EDITS:
        if src.count(anchor) != 1:
            sys.exit("anchor for '%s' matched %d times (expected 1), aborting; file untouched"
                     % (name, src.count(anchor)))
        src = src.replace(anchor, repl)

    if crlf:
        src = src.replace("\n", "\r\n")

    with open(TARGET, "w", newline="") as f:
        f.write(src)

    print("patched " + os.path.relpath(TARGET, ROOT))


if __name__ == "__main__":
    main()
