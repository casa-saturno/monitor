# -*- coding: utf-8 -*-
"""
Coleta de Instagram por navegador PRÓPRIO (Playwright + perfil persistente).

Por que este caminho
--------------------
Desde 04/09/2026 o endpoint /api/v1/feed/user/<uid>/ responde 200 redirecionado
para a home (HTML), mesmo logado — o "feed em JSON" morreu. O que continua
funcionando, validado em 09/09/2026 no Chrome logado:

  * a página de perfil renderiza os 12 posts mais recentes, e a árvore React
    dos itens da grade carrega o objeto completo de cada mídia: code, taken_at,
    product_type, like_count, comment_count, legenda, coautores;
  * GET /api/v1/users/<uid>/info/  -> follower_count, media_count (exatos);
  * GET /api/v1/media/<pk>/info/   -> JSON da mídia (views de Reels quando o
    Instagram os expõe; ver VIEWS abaixo).

O que este script substitui: a "rodada de navegador" que rodava dentro de uma
sessão do Cowork, dependia da extensão do Chrome estar conectada e publicava
por upload manual. Aqui o navegador é um Chromium do Playwright com perfil
persistente em disco, logado UMA vez pelo humano (--login), e a rodada roda
sozinha pelo launchd (ver OPERACAO.md).

VIEWS
-----
A grade NÃO traz views (play_count ausente, view_count null). Para Reels o
script consulta /api/v1/media/<pk>/info/ e grava views só se vierem de lá.
Sem views, o post entra com views vazio — honesto, nunca estimado.

Uso
---
  python coletar_instagram.py --login          # abre janela; faça login e feche
  python coletar_instagram.py --dry-run        # coleta e imprime, não grava
  python coletar_instagram.py                  # coleta e aplica em base_atual.xlsx + base/*.csv
  python coletar_instagram.py --perfis 2       # limita a N perfis (teste)
"""
import argparse, csv, datetime, json, os, sys, time, zoneinfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import saturno
from saturno import Base, Post, Contador

TZ = zoneinfo.ZoneInfo("America/Sao_Paulo")
PERFIL_NAVEGADOR = os.environ.get(
    "MONITOR_PERFIL_NAVEGADOR",
    os.path.expanduser("~/Library/Application Support/MonitorSaturno/chromium-profile"))
APP_ID = "936619743392459"
PAUSA_ENTRE_PERFIS = 8       # segundos; o rate-limit do IG castiga rajadas
PAUSA_ENTRE_MEDIAS = 1.5
TIPOS = {"clips": "Reel", "carousel_container": "Carrossel", "feed": "Foto", "igtv": "Reel/Video"}

saturno.FONTES.setdefault("ig_pagina", {"views": True, "leituras": True})

# Extração pela árvore React. Validado em 09/09/2026: 12/12 posts em @oifidelisx.
JS_GRADE = r"""
() => {
  const main = document.querySelector('main') || document.body;
  const first = main.querySelector('a[href*="/p/"],a[href*="/reel/"]');
  if (!first) return {erro: 'grade sem links', titulo: document.title};
  function fiber(el){ for (const k in el) if (k.startsWith('__reactFiber$')) return el[k]; return null; }
  const medias = {}; const seen = new Set();
  function scan(o, d){
    if (!o || typeof o !== 'object' || d > 9 || seen.has(o)) return; seen.add(o);
    if (o.code && o.taken_at && o.like_count !== undefined) { if (!medias[o.code]) medias[o.code] = o; }
    for (const k in o) { try { scan(o[k], d+1); } catch(e) {} }
  }
  let f = fiber(first), h = 0;
  while (f && h < 80) { scan(f.memoizedProps, 0); scan(f.memoizedState, 0); f = f.return; h++; }
  return {itens: Object.values(medias).map(m => ({
    code: m.code, pk: String(m.pk || m.id || ''), taken_at: m.taken_at,
    product_type: m.product_type, media_type: m.media_type,
    like_count: m.like_count, comment_count: m.comment_count,
    play_count: m.play_count ?? m.ig_play_count ?? m.view_count ?? null,
    caption: (m.caption && m.caption.text) || '',
    coautores: (m.coauthor_producers || []).map(u => u.username),
    pinned: !!(m.timeline_pinned_user_ids && m.timeline_pinned_user_ids.length),
  }))};
}
"""

JS_FETCH_JSON = r"""
async (url) => {
  const r = await fetch(url, {credentials: 'include',
      headers: {'x-ig-app-id': '%s', 'x-requested-with': 'XMLHttpRequest'}});
  const t = await r.text();
  let j = null; try { j = JSON.parse(t); } catch (e) {}
  return {status: r.status, redirected: r.redirected, ok: !!j, json: j};
}
""" % APP_ID


def perfis_instagram(caminho):
    out = []
    with open(caminho, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("Plataforma") == "Instagram" and r.get("Monitorar?") == "Sim":
                artista = r.get("Artista") or r.get("Artista/Perfil")
                handle = (r.get("Handle") or "").lstrip("@").strip()
                uid = str(r.get("ID técnico") or r.get("ID tecnico") or "").strip()
                if artista and handle:
                    out.append((artista, handle, uid if uid.isdigit() else None))
    ordem = {a: i for i, a in enumerate(saturno.PERFIS_PRIORIDADE)}
    out.sort(key=lambda x: ordem.get(x[0], 99))
    return out


def _views_da_media(page, pk, log):
    """Views de um Reel via /api/v1/media/<pk>/info/. None se o IG não expõe."""
    try:
        r = page.evaluate(JS_FETCH_JSON, "/api/v1/media/%s/info/" % pk.split("_")[0])
    except Exception as e:
        log("   media_info %s: %s" % (pk, e)); return None
    if not r.get("ok") or r.get("redirected"):
        return None
    it = ((r.get("json") or {}).get("items") or [{}])[0]
    for k in ("play_count", "ig_play_count", "view_count", "fb_play_count", "video_view_count"):
        v = it.get(k)
        if isinstance(v, int) and v > 0:
            return v
    return None


def coletar(perfis, log=print, limite_perfis=None, headless=True):
    from playwright.sync_api import sync_playwright
    posts, contadores, falhas = [], {}, []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PERFIL_NAVEGADOR, headless=headless, locale="pt-BR",
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            for artista, handle, uid in perfis[:limite_perfis]:
                try:
                    page.goto("https://www.instagram.com/%s/" % handle,
                              wait_until="domcontentloaded", timeout=60000)
                except Exception as e:
                    falhas.append("@%s: navegação (%s)" % (handle, e)); log("AVISO " + falhas[-1]); continue
                # login caiu? a página de login não tem <main> com grade
                grade = None
                for _ in range(10):
                    time.sleep(2)
                    grade = page.evaluate(JS_GRADE)
                    if grade.get("itens"):
                        break
                if "accounts/login" in page.url or not grade or not grade.get("itens"):
                    falhas.append("@%s: grade não carregou (%s) — sessão expirada? rode --login"
                                  % (handle, (grade or {}).get("titulo") or page.url))
                    log("AVISO " + falhas[-1]); continue

                # contadores exatos
                if uid:
                    r = page.evaluate(JS_FETCH_JSON, "/api/v1/users/%s/info/" % uid)
                    u = ((r.get("json") or {}).get("user") or {}) if r.get("ok") else {}
                    if u.get("follower_count") is not None:
                        contadores[(artista, "Instagram")] = Contador(
                            artista, "Instagram", handle,
                            seguidores=u["follower_count"], posts=u.get("media_count"), medido=True)

                n = 0
                for it in grade["itens"]:
                    quando = datetime.datetime.fromtimestamp(int(it["taken_at"]), TZ)
                    tipo = TIPOS.get(it.get("product_type"), {1: "Foto", 2: "Reel", 8: "Carrossel"}.get(it.get("media_type")))
                    views = it.get("play_count")
                    if views is None and tipo in ("Reel", "Reel/Video") and it.get("pk"):
                        time.sleep(PAUSA_ENTRE_MEDIAS)
                        views = _views_da_media(page, it["pk"], log)
                    posts.append(Post(
                        artista, "Instagram", quando.strftime("%Y-%m-%d"), quando.strftime("%H:%M"),
                        tipo, it["code"], titulo=(it.get("caption") or "").strip()[:300] or None,
                        url="https://www.instagram.com/p/%s/" % it["code"],
                        views=int(views) if views else None,
                        likes=it.get("like_count"), coment=it.get("comment_count"),
                        fonte="ig_pagina"))
                    n += 1
                log("@%-18s seguidores=%-9s posts=%d" % (
                    handle, getattr(contadores.get((artista, "Instagram")), "seguidores", "-"), n))
                time.sleep(PAUSA_ENTRE_PERFIS)
        finally:
            ctx.close()
    return posts, contadores, falhas


def login():
    from playwright.sync_api import sync_playwright
    os.makedirs(PERFIL_NAVEGADOR, exist_ok=True)
    print("Abrindo o navegador. Faça login no Instagram e depois FECHE a janela.")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PERFIL_NAVEGADOR, headless=False, locale="pt-BR",
                                                   args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.instagram.com/accounts/login/")
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
        try:
            ctx.close()
        except Exception:
            pass
    print("Perfil salvo em", PERFIL_NAVEGADOR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.join(os.path.dirname(__file__), "base_atual.xlsx"))
    ap.add_argument("--csv", default=os.path.join(os.path.dirname(__file__), "base"))
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--headed", action="store_true", help="mostra a janela (diagnóstico)")
    ap.add_argument("--perfis", type=int, default=None)
    a = ap.parse_args()
    if a.login:
        login(); return 0

    agora = datetime.datetime.now(TZ)
    COLETA, HOJE = agora.strftime("%Y-%m-%d %H:%M"), agora.strftime("%Y-%m-%d")
    perfis = perfis_instagram(os.path.join(a.csv, "perfis.csv"))
    print("perfis de Instagram monitorados: %d" % len(perfis))
    posts, contadores, falhas = coletar(perfis, limite_perfis=a.perfis, headless=not a.headed)
    print("coletados: %d posts, %d contadores, %d falhas" % (len(posts), len(contadores), len(falhas)))
    com_views = sum(1 for p in posts if p.views)
    print("posts com views: %d de %d" % (com_views, len(posts)))
    if a.dry_run:
        for p in posts[:6]:
            print("  ", p.artista, p.data, p.hora, p.tipo, p.pid, p.views, p.likes, p.coment, (p.titulo or "")[:30])
        return 0 if not falhas else 1
    if not posts and not contadores:
        print("nada coletado — base inalterada"); return 1

    if not os.path.exists(a.base):
        saturno.carregar_base_dos_csv(a.csv, a.base)
    base = Base(a.base)
    if posts:
        base.aplicar_posts(posts, COLETA)
    if contadores:
        base.aplicar_contadores(contadores, HOJE)
    if posts:
        base.aplicar_leituras(posts, COLETA, HOJE)
    base.salvar(csv_dir=a.csv)
    print(base.resumo())
    ge = os.environ.get("GITHUB_ENV")
    if ge:
        with open(ge, "a") as f:
            f.write("COLETA=%s\nHOJE=%s\n" % (COLETA, HOJE))
    return 0 if not falhas else 2


if __name__ == "__main__":
    sys.exit(main())
