# -*- coding: utf-8 -*-
"""
Coleta de TikTok pelos endpoints de EMBED — sem sessão, sem navegador, sem assinatura.

Por que este caminho
--------------------
A página de perfil (tiktok.com/@handle) é protegida por gestão de bots: a grade
de vídeos só hidrata se o TikTok aceitar o dispositivo, e a API interna
(api/post/item_list) responde 200 com corpo vazio para requisição sem
assinatura. Já os endpoints de embed existem para sites de terceiros e por
isso respondem a um GET simples, com JSON embutido no HTML:

  GET /embed/@<handle>        -> userInfo (seguidores, curtidas) + videoList (12 mais recentes, com playCount)
  GET /embed/v2/<video_id>    -> itemInfos (createTime, playCount, diggCount, commentCount, shareCount, text)

Validado em 09/09/2026 nos 9 perfis monitorados, por curl, sem cookie.

Precisão (leia antes de confiar)
--------------------------------
Números >= 10.000 chegam arredondados a 3 algarismos significativos
(11800, 2800000). Abaixo disso são exatos (9723, 2356). É a MESMA precisão do
bloco __UNIVERSAL_DATA_FOR_REHYDRATION__ da página de perfil, que o projeto já
tratava como "medido" (269100 seguidores da Casa Saturno em ambos). Ou seja:
esta fonte não é pior do que a anterior — mas não é exata acima de 10k, e o
painel não deve fingir que é. A fonte se chama "tk_embed" para que isso fique
rastreável na base.

Uso
---
  python coletar_tiktok.py                # coleta e aplica em base_atual.xlsx (+ espelho CSV em base/)
  python coletar_tiktok.py --dry-run      # só imprime o que coletaria
  python coletar_tiktok.py --perfis 3     # limita a N perfis (teste)
"""
import argparse, csv, datetime, json, os, re, sys, time, zoneinfo

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import saturno
from saturno import Base, Post, Contador

TZ = zoneinfo.ZoneInfo("America/Sao_Paulo")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
BLOB = re.compile(r'<script id="__FRONTITY_CONNECT_STATE__" type="application/json">(.*?)</script>', re.S)
PAUSA = 0.6          # segundos entre requisições — 9 perfis x ~13 chamadas
TENTATIVAS = 3

# registra a fonte no núcleo (regra 1: a fonte decide o que pode gravar)
saturno.FONTES.setdefault("tk_embed", {"views": True, "leituras": True})


class EmbedIndisponivel(RuntimeError):
    pass


def _get(url, sessao):
    ultimo = None
    for i in range(TENTATIVAS):
        try:
            r = sessao.get(url, timeout=30, allow_redirects=True)
            m = BLOB.search(r.text)
            if r.status_code == 200 and m:
                return json.loads(m.group(1))
            ultimo = "HTTP %s sem blob (%d bytes)" % (r.status_code, len(r.text))
        except Exception as e:                       # rede, JSON, timeout
            ultimo = str(e)
        time.sleep(2 + 3 * i)
    raise EmbedIndisponivel("%s -> %s" % (url, ultimo))


def _hora_do_id(video_id):
    """Os 32 bits altos do id são o epoch de criação — vale como fallback."""
    return datetime.datetime.fromtimestamp(int(video_id) >> 32, TZ)


def ler_perfil(handle, sessao):
    d = _get("https://www.tiktok.com/embed/@%s" % handle, sessao)
    v = d["source"]["data"].get("/embed/@%s" % handle) or {}
    ui = v.get("userInfo") or {}
    if ui.get("code") not in (200, None) or not ui.get("uniqueId"):
        raise EmbedIndisponivel("@%s: userInfo code=%s" % (handle, ui.get("code")))
    return ui, (v.get("videoList") or [])


def ler_video(video_id, sessao):
    d = _get("https://www.tiktok.com/embed/v2/%s" % video_id, sessao)
    vd = (d["source"]["data"].get("/embed/v2/%s" % video_id) or {}).get("videoData") or {}
    return vd.get("itemInfos") or {}


def perfis_tiktok(caminho_perfis):
    out = []
    with open(caminho_perfis, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("Plataforma") == "TikTok" and r.get("Monitorar?") == "Sim":
                artista = r.get("Artista") or r.get("Artista/Perfil")
                handle = (r.get("Handle") or "").lstrip("@").strip()
                if artista and handle:
                    out.append((artista, handle))
    # regra 4 — perfis de maior volume primeiro
    ordem = {a: i for i, a in enumerate(saturno.PERFIS_PRIORIDADE)}
    out.sort(key=lambda x: ordem.get(x[0], 99))
    return out


def coletar(perfis, log=print, limite_perfis=None):
    """Devolve (posts, contadores, falhas). Nunca levanta por um perfil só."""
    sessao = requests.Session()
    sessao.headers.update({"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    posts, contadores, falhas = [], {}, []
    for artista, handle in perfis[:limite_perfis]:
        try:
            ui, lista = ler_perfil(handle, sessao)
        except EmbedIndisponivel as e:
            falhas.append(str(e)); log("AVISO %s" % e); continue
        contadores[(artista, "TikTok")] = Contador(
            artista, "TikTok", handle,
            seguidores=ui.get("followerCount"),
            posts=None,                      # o embed de perfil não expõe videoCount
            likes=ui.get("heartCount"), medido=ui.get("followerCount") is not None)
        n_ok = 0
        for item in lista:
            vid = str(item.get("id") or "")
            if not vid.isdigit():
                continue
            time.sleep(PAUSA)
            try:
                info = ler_video(vid, sessao)
            except EmbedIndisponivel as e:
                falhas.append(str(e)); log("AVISO %s" % e); info = {}
            ct = info.get("createTime")
            quando = (datetime.datetime.fromtimestamp(int(ct), TZ) if ct
                      else _hora_do_id(vid))
            views = info.get("playCount", item.get("playCount"))
            posts.append(Post(
                artista, "TikTok", quando.strftime("%Y-%m-%d"), quando.strftime("%H:%M"),
                "Vídeo", vid,
                titulo=(info.get("text") or item.get("desc") or "").strip() or None,
                url="https://www.tiktok.com/@%s/video/%s" % (handle, vid),
                views=int(views) if views is not None else None,
                likes=int(info["diggCount"]) if info.get("diggCount") is not None else None,
                coment=int(info["commentCount"]) if info.get("commentCount") is not None else None,
                fonte="tk_embed"))
            n_ok += 1
        log("@%-18s seguidores=%-9s videos=%d" % (handle, ui.get("followerCount"), n_ok))
        time.sleep(PAUSA)
    return posts, contadores, falhas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.join(os.path.dirname(__file__), "base_atual.xlsx"))
    ap.add_argument("--csv", default=os.path.join(os.path.dirname(__file__), "base"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--perfis", type=int, default=None)
    ap.add_argument("--sem-contadores", action="store_true",
                    help="não toca na aba Contadores (útil se outra rodada do dia vai medir)")
    a = ap.parse_args()

    agora = datetime.datetime.now(TZ)
    COLETA, HOJE = agora.strftime("%Y-%m-%d %H:%M"), agora.strftime("%Y-%m-%d")
    perfis = perfis_tiktok(os.path.join(a.csv, "perfis.csv"))
    print("perfis de TikTok monitorados: %d" % len(perfis))

    posts, contadores, falhas = coletar(perfis, limite_perfis=a.perfis)
    print("coletados: %d videos, %d contadores, %d falhas" % (len(posts), len(contadores), len(falhas)))
    if a.dry_run:
        for p in posts[:5]:
            print("  ", p.artista, p.data, p.hora, p.pid, p.views, p.likes, p.coment, (p.titulo or "")[:40])
        return 0
    if not posts and not contadores:
        print("nada coletado — base inalterada")
        return 0

    if not os.path.exists(a.base):
        saturno.carregar_base_dos_csv(a.csv, a.base)
    base = Base(a.base)
    if posts:
        base.aplicar_posts(posts, COLETA)
    if contadores and not a.sem_contadores:
        base.aplicar_contadores(contadores, HOJE)
    if posts:
        base.aplicar_leituras(posts, COLETA, HOJE)
    base.salvar(csv_dir=a.csv)
    print(base.resumo())
    # para o workflow: carimbo da rodada
    ge = os.environ.get("GITHUB_ENV")
    if ge:
        with open(ge, "a") as f:
            f.write("COLETA=%s\nHOJE=%s\n" % (COLETA, HOJE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
