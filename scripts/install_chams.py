#!/usr/bin/env python3
"""esp: ESP sederhana (kotak + nama) di client, tanpa DLL server.
Jalankan dari root repo:  python3 scripts/install_esp.py   (aman dijalankan berkali-kali)

Console:
  esp_on 0/1     nyalain/matiin
  esp_name 0/1   tampilkan nama (default 1)
  esp_team 0/1   0 = semua player, 1 = musuh saja
Tim T = merah, CT = biru. Hanya player yang dikirim server ke client (dalam PVS) yang bisa digambar.
"""
import os, re, sys

NEW = "cl_dll/simple_esp.cpp"
REDRAW = "cl_dll/hud_redraw.cpp"
HUD = "cl_dll/hud.cpp"

CPP = r'''// simple_esp: kotak + nama player (2D overlay), dipanggil dari CHud::Redraw
#include "hud.h"
#include "cl_util.h"
#include "draw_util.h"
#include "triangleapi.h"
#include <math.h>
#include <string.h>

static cvar_t *esp_on = NULL, *esp_name = NULL, *esp_team = NULL;

void SimpleESP_Init( void )
{
	esp_on   = CVAR_CREATE( "esp_on", "0", 0 );
	esp_name = CVAR_CREATE( "esp_name", "1", FCVAR_ARCHIVE );
	esp_team = CVAR_CREATE( "esp_team", "0", 0 );
}

static bool ToScreen( const float *world, int &x, int &y )
{
	float w[3] = { world[0], world[1], world[2] };
	float s[3] = { 0, 0, 0 };
	if( gEngfuncs.pTriAPI->WorldToScreen( w, s ) ) // 1 = di belakang kamera
		return false;
	x = (int)( ScreenWidth  * 0.5f + s[0] * ScreenWidth  * 0.5f );
	y = (int)( ScreenHeight * 0.5f - s[1] * ScreenHeight * 0.5f );
	return true;
}

static void Rect( int x, int y, int w, int h, int r, int g, int b )
{
	// kotak 1px dari 4 garis
	FillRGBABlend( x, y, w, 1, r, g, b, 255 );
	FillRGBABlend( x, y + h - 1, w, 1, r, g, b, 255 );
	FillRGBABlend( x, y, 1, h, r, g, b, 255 );
	FillRGBABlend( x + w - 1, y, 1, h, r, g, b, 255 );
}

void SimpleESP_Draw( void )
{
	if( !esp_on || esp_on->value == 0.0f )
		return;

	cl_entity_t *local = gEngfuncs.GetLocalPlayer();
	if( !local )
		return;

	const int myTeam = g_PlayerExtraInfo[local->index].teamnumber;
	const bool enemiesOnly = esp_team->value != 0.0f;

	for( int i = 1; i <= gEngfuncs.GetMaxClients() && i <= MAX_PLAYERS; i++ )
	{
		cl_entity_t *ent = gEngfuncs.GetEntityByIndex( i );
		if( !ent || !ent->model || i == local->index )
			continue;
		if( ent->curstate.messagenum < local->curstate.messagenum ) // data basi (nggak diupdate frame ini)
			continue;
		if( ent->curstate.spectator || g_PlayerExtraInfo[i].dead )
			continue;

		const int team = g_PlayerExtraInfo[i].teamnumber;
		if( enemiesOnly && team > 0 && myTeam > 0 && team == myTeam )
			continue;

		const float half = ent->curstate.usehull ? 18.0f : 36.0f; // setengah tinggi hull
		float top[3]    = { ent->origin[0], ent->origin[1], ent->origin[2] + half };
		float bottom[3] = { ent->origin[0], ent->origin[1], ent->origin[2] - half };

		int tx, ty, bx, by;
		if( !ToScreen( top, tx, ty ) || !ToScreen( bottom, bx, by ) )
			continue;

		int h = by - ty;
		if( h < 4 )
			continue;
		int w = h / 2;
		int x = ( tx + bx ) / 2 - w / 2;

		int r = 255, g = 255, b = 255;
		if( team == 1 )      { r = 255; g = 50;  b = 50;  } // T
		else if( team == 2 ) { r = 50;  g = 130; b = 255; } // CT

		Rect( x, ty, w, h, r, g, b );

		if( esp_name && esp_name->value != 0.0f && g_PlayerInfoList[i].name )
			DrawUtils::DrawHudString( x, ty - 14, ScreenWidth, g_PlayerInfoList[i].name, r, g, b );
	}
}
'''

def read(p):
    with open(p, encoding="utf-8", newline="") as f: return f.read()
def write(p, s):
    with open(p, "w", encoding="utf-8", newline="") as f: f.write(s)
def nl_of(s): return "\r\n" if "\r\n" in s else "\n"
def die(msg): sys.exit("GAGAL: " + msg)

def main():
    for p in (REDRAW, HUD):
        if not os.path.exists(p):
            die("jalankan dari root repo (nggak nemu %s)" % p)

    write(NEW, CPP)
    print("[ok] %s ditulis" % NEW)

    r = read(REDRAW)
    if "SimpleESP_Draw" not in r:
        nl = nl_of(r)
        m = re.search(r"^([ \t]*)// are we in demo mode\?[^\n]*\n", r, re.M)
        if not m: die("anchor '// are we in demo mode?' nggak ketemu di hud_redraw.cpp")
        r = r[:m.start()] + m.group(1) + "SimpleESP_Draw();" + nl + nl + r[m.start():]
        m2 = re.search(r"^int CHud\s*::\s*Redraw\s*\(", r, re.M)
        if not m2: die("CHud::Redraw nggak ketemu di hud_redraw.cpp")
        r = r[:m2.start()] + "void SimpleESP_Draw( void );" + nl + r[m2.start():]
        write(REDRAW, r)
        print("[ok] hook Redraw dipasang")
    else:
        print("[skip] hud_redraw.cpp sudah ke-patch")

    h = read(HUD)
    if "SimpleESP_Init" not in h:
        nl = nl_of(h)
        m = re.search(r'^([ \t]*)CVAR_CREATE\(\s*"_ah"[^\n]*\n', h, re.M)
        if not m: die('anchor CVAR_CREATE("_ah") nggak ketemu di hud.cpp')
        h = h[:m.end()] + m.group(1) + "SimpleESP_Init();" + nl + h[m.end():]
        m2 = re.search(r'^void CHud\s*::\s*Init\s*\(', h, re.M)
        if not m2: die("CHud::Init nggak ketemu di hud.cpp")
        h = h[:m2.start()] + "void SimpleESP_Init( void );" + nl + h[m2.start():]
        write(HUD, h)
        print("[ok] cvar init dipasang")
    else:
        print("[skip] hud.cpp sudah ke-patch")

    for path, needle in ((REDRAW, "SimpleESP_Draw();"), (HUD, "SimpleESP_Init();")):
        if needle not in read(path):
            die("VERIFIKASI: %s tidak berisi %s" % (path, needle))
    print("[ok] verifikasi lolos")

if __name__ == "__main__":
    main()
		
