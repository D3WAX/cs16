#!/usr/bin/env python3
"""nojs: auto-bhop client-side supaya slowdown pendaratan (friction) sebisa mungkin hilang.
Jalankan dari root repo:  python3 scripts/install_nojs.py   (aman dijalankan berkali-kali)

Console:
  nojs 0/1   nyalain/matiin. Cara pakai: TAHAN tombol lompat, auto-hop jalan sendiri.

Cara kerja: tiap tick player dikirim IN_JUMP hanya saat menyentuh tanah (lompat di frame pertama
mendarat, sebelum friction sempat makan speed) dan IN_JUMP dilepas selama di udara (CS butuh tombol
dilepas antar lompatan). Status onground diambil dari prediksi pmove client.

BATAS: slowdown yang dihitung server (cap speed bhop, penalti jatuh) tetap berlaku dan tidak bisa
dihapus dari client. Ini cuma menghilangkan kehilangan speed karena telat lompat saat mendarat.
"""
import os, re, sys

NEW = "cl_dll/nojs.cpp"
INPUT = "cl_dll/input.cpp"
CDLL = "cl_dll/cdll_int.cpp"
HUD = "cl_dll/hud.cpp"

CPP = r'''// nojs: client-side auto-bhop (IN_JUMP hanya saat onground)
#include "hud.h"
#include "cl_util.h"
#include "usercmd.h"
#include "in_buttons.h"
#include "pm_defs.h"
#include "const.h"

static cvar_t *nojs = NULL;
static int g_onGround = 1;
static int g_skip = 0; // air/ladder: jangan sentuh tombol lompat

void NoJS_Init( void )
{
	nojs = CVAR_CREATE( "nojs", "0", 0 );
}

// dipanggil setelah prediksi pmove client
void NoJS_SavePM( struct playermove_s *pm )
{
	if( !pm )
		return;
	g_onGround = ( pm->onground != -1 );
	g_skip = ( pm->waterlevel >= 2 || pm->movetype == MOVETYPE_FLY || pm->dead );
}

// dipanggil dari CL_CreateMove (player hidup)
void NoJS_Apply( struct usercmd_s *cmd )
{
	if( !nojs || nojs->value == 0.0f || g_skip )
		return;
	if( !( cmd->buttons & IN_JUMP ) ) // hanya kalau player menahan tombol lompat
		return;

	if( g_onGround )
		cmd->buttons |= IN_JUMP;
	else
		cmd->buttons &= ~IN_JUMP;
}
'''

def read(p):
    with open(p, encoding="utf-8", newline="") as f: return f.read()
def write(p, s):
    with open(p, "w", encoding="utf-8", newline="") as f: f.write(s)
def nl_of(s): return "\r\n" if "\r\n" in s else "\n"
def die(msg): sys.exit("GAGAL: " + msg)

def main():
    for p in (INPUT, CDLL, HUD):
        if not os.path.exists(p):
            die("jalankan dari root repo (nggak nemu %s)" % p)

    write(NEW, CPP)
    print("[ok] %s ditulis" % NEW)

    # --- input.cpp: panggil NoJS_Apply di CL_CreateMove (cabang player hidup)
    s = read(INPUT)
    if "NoJS_Apply" not in s:
        nl = nl_of(s)
        a = "\t\tVectorCopy( viewangles, cmd->viewangles );"
        if s.count(a) != 1: die("anchor VectorCopy(viewangles, cmd->viewangles) tidak unik/ketemu di input.cpp")
        s = s.replace(a, "\t\tNoJS_Apply( cmd );" + nl + a, 1)
        m = re.search(r"^void DLLEXPORT CL_CreateMove\s*\(", s, re.M)
        if not m: die("CL_CreateMove nggak ketemu di input.cpp")
        s = s[:m.start()] + "void NoJS_Apply( struct usercmd_s *cmd );" + nl + s[m.start():]
        write(INPUT, s)
        print("[ok] hook CL_CreateMove dipasang")
    else:
        print("[skip] input.cpp sudah ke-patch")

    # --- cdll_int.cpp: simpan state pmove setelah prediksi
    c = read(CDLL)
    if "NoJS_SavePM" not in c:
        nl = nl_of(c)
        a = "\tPM_Move( ppmove, server );"
        if c.count(a) != 1: die("anchor PM_Move(ppmove, server) tidak unik/ketemu di cdll_int.cpp")
        c = c.replace(a, a + nl + "\tif( !server )" + nl + "\t\tNoJS_SavePM( ppmove );", 1)
        m = re.search(r"^void DLLEXPORT HUD_PlayerMove\s*\(", c, re.M)
        if not m: die("HUD_PlayerMove nggak ketemu di cdll_int.cpp")
        c = c[:m.start()] + "void NoJS_SavePM( struct playermove_s *pm );" + nl + c[m.start():]
        write(CDLL, c)
        print("[ok] hook HUD_PlayerMove dipasang")
    else:
        print("[skip] cdll_int.cpp sudah ke-patch")

    # --- hud.cpp: registrasi cvar
    h = read(HUD)
    if "NoJS_Init" not in h:
        nl = nl_of(h)
        m = re.search(r'^([ \t]*)CVAR_CREATE\(\s*"_ah"[^\n]*\n', h, re.M)
        if not m: die('anchor CVAR_CREATE("_ah") nggak ketemu di hud.cpp')
        h = h[:m.end()] + m.group(1) + "NoJS_Init();" + nl + h[m.end():]
        m2 = re.search(r'^void CHud\s*::\s*Init\s*\(', h, re.M)
        if not m2: die("CHud::Init nggak ketemu di hud.cpp")
        h = h[:m2.start()] + "void NoJS_Init( void );" + nl + h[m2.start():]
        write(HUD, h)
        print("[ok] cvar init dipasang")
    else:
        print("[skip] hud.cpp sudah ke-patch")

    for path, needle in ((INPUT, "NoJS_Apply( cmd );"), (CDLL, "NoJS_SavePM( ppmove );"), (HUD, "NoJS_Init();")):
        if needle not in read(path):
            die("VERIFIKASI: %s tidak berisi %s" % (path, needle))
    print("[ok] verifikasi lolos")

if __name__ == "__main__":
    main()
