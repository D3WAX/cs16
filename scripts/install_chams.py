#!/usr/bin/env python3
"""chams: overlay warna tembus pandang di tubuh player (client-only, tanpa DLL server).
Jalankan dari root repo:  python3 scripts/install_chams.py   (aman dijalankan berkali-kali)

Console:
  gl_chams 0/1        nyalain/matiin
  gl_chams_near <u>   jarak "tarik ke depan" dasar (default 28). Naikin kalau chams ketutup tembok dekat kamera
  gl_chams_amt <0-255> ketebalan/kecerahan shell (default 10). Kalau blobby turunin, kalau nggak kelihatan naikin

Cara kerja: tanpa akses OpenGL dari cl_dll, depth test nggak bisa dimatikan. Jadi tiap player digambar ulang
sekali sebagai glow-shell berwarna, tapi posisinya diskalakan ke arah kamera (ukuran di layar sama, jaraknya
jauh lebih dekat), sehingga lolos depth test dan kelihatan di balik tembok. Tim T = merah, CT = biru.
"""
import os, re, sys

NEW = "cl_dll/chams.cpp"
GHDR = "cl_dll/GameStudioModelRenderer.h"
GCPP = "cl_dll/GameStudioModelRenderer.cpp"
HUD = "cl_dll/hud.cpp"

CHAMS_CPP = r'''// chams: cvar registration (rendering lives in CGameStudioModelRenderer::StudioChams)
#include "hud.h"
#include "cl_util.h"

void Chams_Init( void )
{
	CVAR_CREATE( "gl_chams", "0", FCVAR_ARCHIVE );
	CVAR_CREATE( "gl_chams_near", "28", FCVAR_ARCHIVE );
	CVAR_CREATE( "gl_chams_amt", "10", FCVAR_ARCHIVE );
}
'''

STUDIO_CHAMS = r'''void CGameStudioModelRenderer::StudioChams( void )
{
	static cvar_t *s_chams = NULL, *s_near = NULL, *s_amt = NULL;
	if( !s_chams )
	{
		s_chams = gEngfuncs.pfnGetCvarPointer( "gl_chams" );
		s_near  = gEngfuncs.pfnGetCvarPointer( "gl_chams_near" );
		s_amt   = gEngfuncs.pfnGetCvarPointer( "gl_chams_amt" );
	}
	if( !s_chams || !s_near || !s_amt || s_chams->value == 0.0f )
		return;
	if( !IEngineStudio.IsHardware() || !m_pStudioHeader || !m_pCurrentEntity )
		return;

	cl_entity_t *local = gEngfuncs.GetLocalPlayer();
	const int idx = m_pCurrentEntity->index;
	if( !local || idx <= 0 || idx == local->index || idx > MAX_PLAYERS )
		return;
	if( g_PlayerExtraInfo[idx].dead )
		return;

	const int nb = m_pStudioHeader->numbones;
	if( nb <= 0 || nb > MAXSTUDIOBONES )
		return;

	// jarak player ke kamera -> jarak baru (lebih dekat, urutan antar-player tetap terjaga)
	const float *O = m_vRenderOrigin;
	float dx = m_pCurrentEntity->origin[0] - O[0];
	float dy = m_pCurrentEntity->origin[1] - O[1];
	float dz = m_pCurrentEntity->origin[2] - O[2];
	float dist = sqrtf( dx * dx + dy * dy + dz * dz );
	if( dist < 1.0f )
		return;
	float k = ( s_near->value + dist * 0.01f ) / dist;
	if( k >= 1.0f )
		return; // player lebih dekat dari jarak tarik: gambar normal sudah cukup

	// simpan bone asli, skala semua bone ke arah kamera
	static float s_save[MAXSTUDIOBONES][3][4];
	memcpy( s_save, *m_pbonetransform, sizeof( float ) * 12 * nb );
	for( int b = 0; b < nb; b++ )
	{
		for( int r = 0; r < 3; r++ )
		{
			for( int c = 0; c < 3; c++ )
				( *m_pbonetransform )[b][r][c] *= k;
			( *m_pbonetransform )[b][r][3] = O[r] + k * ( ( *m_pbonetransform )[b][r][3] - O[r] );
		}
	}

	// simpan state render entity
	const int sMode = m_pCurrentEntity->curstate.rendermode;
	const int sFx   = m_pCurrentEntity->curstate.renderfx;
	const int sAmt  = m_pCurrentEntity->curstate.renderamt;
	const color24 sCol = m_pCurrentEntity->curstate.rendercolor;

	const int team = g_PlayerExtraInfo[idx].teamnumber;
	color24 col;
	if( team == 1 )      { col.r = 255; col.g = 50;  col.b = 50;  } // T
	else if( team == 2 ) { col.r = 50;  col.g = 130; col.b = 255; } // CT
	else                 { col.r = 255; col.g = 255; col.b = 255; }

	int amt = (int)s_amt->value;
	if( amt < 0 ) amt = 0;
	if( amt > 255 ) amt = 255;

	m_pCurrentEntity->curstate.renderfx = kRenderFxGlowShell;
	m_pCurrentEntity->curstate.renderamt = amt;
	m_pCurrentEntity->curstate.rendercolor = col;

	IEngineStudio.SetChromeOrigin();
	gEngfuncs.pTriAPI->SpriteTexture( m_pChromeSprite, 0 );
	IEngineStudio.SetForceFaceFlags( STUDIO_NF_CHROME );
	StudioRenderFinal();
	IEngineStudio.SetForceFaceFlags( 0 );

	// kembalikan semuanya
	m_pCurrentEntity->curstate.rendermode = sMode;
	m_pCurrentEntity->curstate.renderfx = sFx;
	m_pCurrentEntity->curstate.renderamt = sAmt;
	m_pCurrentEntity->curstate.rendercolor = sCol;
	memcpy( *m_pbonetransform, s_save, sizeof( float ) * 12 * nb );
}

'''

def read(p):
    with open(p, encoding="utf-8", newline="") as f: return f.read()
def write(p, s):
    with open(p, "w", encoding="utf-8", newline="") as f: f.write(s)
def nl_of(s): return "\r\n" if "\r\n" in s else "\n"

def die(msg): sys.exit("GAGAL: " + msg)

def main():
    for p in (GHDR, GCPP, HUD):
        if not os.path.exists(p):
            die("jalankan dari root repo (nggak nemu %s)" % p)

    write(NEW, CHAMS_CPP)
    print("[ok] %s ditulis" % NEW)

    # --- header: deklarasi method
    h = read(GHDR)
    if "StudioChams" not in h:
        nl = nl_of(h)
        a = "void RestorePlayerState(entity_state_t *pplayer);"
        if a not in h: die("anchor RestorePlayerState nggak ada di GameStudioModelRenderer.h")
        h = h.replace(a, a + nl + "\tvoid StudioChams(void);", 1)
        write(GHDR, h)
        print("[ok] deklarasi StudioChams ditambah")
    else:
        print("[skip] header sudah ke-patch")

    # --- cpp: definisi + pemanggilan
    c = read(GCPP)
    if "StudioChams" not in c:
        nl = nl_of(c)
        d = "int CGameStudioModelRenderer::StudioDrawPlayer(int flags, entity_state_t *pplayer)"
        if d not in c: die("anchor StudioDrawPlayer nggak ketemu")
        body = STUDIO_CHAMS.replace("\n", nl)
        c = c.replace(d, body + d, 1)

        m = re.search(r"([ \t]*)StudioRenderModel\(dir\);(\r?\n)([ \t]*)m_pPlayerInfo = NULL;", c)
        if not m: die("anchor 'StudioRenderModel(dir); m_pPlayerInfo = NULL;' nggak ketemu")
        c = c[:m.end(1)] + "StudioRenderModel(dir);" + m.group(2) + m.group(1) + "StudioChams();" + m.group(2) + m.group(3) + "m_pPlayerInfo = NULL;" + c[m.end():]
        write(GCPP, c)
        print("[ok] StudioChams ditambah + dipanggil setelah render player")
    else:
        print("[skip] cpp sudah ke-patch")

    # --- hud.cpp: registrasi cvar
    s = read(HUD)
    if "Chams_Init" not in s:
        nl = nl_of(s)
        m = re.search(r'^([ \t]*)CVAR_CREATE\(\s*"_ah"[^\n]*\n', s, re.M)
        if not m: die('anchor CVAR_CREATE("_ah") nggak ketemu di hud.cpp')
        s = s[:m.end()] + m.group(1) + "Chams_Init();" + nl + s[m.end():]
        m2 = re.search(r'^void CHud\s*::\s*Init\s*\(', s, re.M)
        if not m2: die("CHud::Init nggak ketemu di hud.cpp")
        s = s[:m2.start()] + "void Chams_Init( void );" + nl + s[m2.start():]
        write(HUD, s)
        print("[ok] cvar init dipasang")
    else:
        print("[skip] hud.cpp sudah ke-patch")

    # --- verifikasi (kalau ada yang nggak masuk, build harus gagal, jangan diam-diam)
    checks = ((GHDR, "void StudioChams(void);"), (GCPP, "StudioChams();"),
              (GCPP, "void CGameStudioModelRenderer::StudioChams"), (HUD, "Chams_Init();"))
    for path, needle in checks:
        if needle not in read(path):
            die("VERIFIKASI: %s tidak berisi %s" % (path, needle))
    print("[ok] verifikasi lolos")

if __name__ == "__main__":
    main()
