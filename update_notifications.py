"""
update_notifications.py
Lê todos os dashboards da Easy House e atualiza o NOTIFICACOES_HOJE no index.html.
Roda localmente ou via GitHub Actions.
"""

import re
import json
from datetime import date
from pathlib import Path
from bs4 import BeautifulSoup

BASE  = Path(__file__).parent
TODAY = date.today().strftime("%d/%m/%Y")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def fmt(n, decimais=2):
    """Formata número com separadores brasileiros (ex: 1.234,56)."""
    s = f"{n:,.{decimais}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def soup(filename):
    path = BASE / filename
    if not path.exists():
        return None
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")

def read(filename):
    path = BASE / filename
    return path.read_text(encoding="utf-8") if path.exists() else None

def last_hist_sla(text):
    m = re.findall(r"\['[^']+','([\d.]+)'\]", text)
    return float(m[-1]) if m else 0.0

def last_day_block(text):
    matches = re.findall(r"const D(\d+)=(\{[^}]+\})", text)
    if not matches:
        return None
    _, raw = sorted(matches, key=lambda x: int(x[0]))[-1]
    raw = re.sub(r'(\w+):', r'"\1":', raw.replace("'", '"'))
    try:
        return json.loads(raw)
    except Exception:
        return None

def transportadoras(text):
    return [(m[0], float(m[1]))
            for m in re.findall(r"\{s:'([^']+)'.*?sla:([\d.]+)\}", text)]


# ─────────────────────────────────────────────
# PARSERS
# ─────────────────────────────────────────────

def parse_estoque():
    s = soup("estoque.html")
    if not s:
        return None

    badge   = s.find("div", class_="badge-alert")
    alertas = re.search(r"(\d+)\s+ALERTAS", badge.text).group(1) if badge else "?"

    kpi_amb = s.find("div", class_=lambda c: c and "kpi-card" in c and "amber" in c)
    pct_res = "?"
    if kpi_amb:
        sub = kpi_amb.find("div", class_="kpi-sub")
        if sub:
            m = re.search(r"([\d,.]+)%", sub.text)
            if m:
                pct_res = m.group(1)

    alert_el = s.find("div", class_="alert-text")
    detalhe  = alert_el.text.strip()[:180] if alert_el else ""

    return dict(
        id=1, icon="📦", cor="rgba(212,160,23,0.15)",
        titulo=f"Estoque: {alertas} variações em alerta ⚠️",
        desc=f"{pct_res}% reservado · {detalhe}",
        hora=TODAY, lida=False, link="estoque.html",
        critico=int(alertas) >= 5 if alertas != "?" else False
    )


def parse_sla():
    text = read("sla_transporte.html")
    if not text:
        return None
    s = BeautifulSoup(text, "html.parser")

    title_tag = s.find("title")
    dash_date = re.search(r"(\d{2}/\d{2}/\d{4})", title_tag.text).group(1) if title_tag else TODAY

    sla_pct = last_hist_sla(text)
    d       = last_day_block(text)
    late    = d.get("late", "?") if d else "?"
    sf      = d.get("sf",   "?") if d else "?"

    transp = transportadoras(text)
    ruins  = sorted([t for t in transp if t[1] < 95.0], key=lambda x: x[1])

    acima  = sla_pct >= 95.0
    cor    = "rgba(39,174,96,0.15)" if acima else "rgba(204,40,40,0.18)"
    titulo = f"SLA: {'✅ Acima' if acima else '⚠️ Abaixo'} da meta — {fmt(sla_pct)}%"

    if ruins:
        detalhes = " · ".join(
            f"{t[0].split('·')[0].strip()} {fmt(t[1])}%{'🔴' if t[1] < 80 else ''}"
            for t in ruins[:4]
        )
        desc = f"{late} em atraso · {sf} sem faturar · Pior transp.: {detalhes}"
    else:
        desc = f"{late} em atraso · {sf} sem faturar · Todas transportadoras na meta ✅"

    return dict(
        id=2, icon="🚚", cor=cor,
        titulo=titulo, desc=desc, hora=dash_date,
        lida=False, link="sla_transporte.html", critico=not acima
    )


def parse_comercial():
    text = read("comercial.html")
    if not text:
        return None
    s = BeautifulSoup(text, "html.parser")

    dias_abr = re.findall(r"\{d:'(\d{2}/04)',\s*g:([\d.]+)", text)
    if dias_abr:
        total    = sum(float(v) for _, v in dias_abr)
        n_dias   = len(dias_abr)
        ultimo   = dias_abr[-1][0]
        media    = total / n_dias
        pct_meta = fmt(total / 8_600_000 * 100) + "% da Meta"
    else:
        total = n_dias = media = 0
        ultimo   = "?"
        pct_meta = "?"

    # Badge Ano x Ano — bloco específico de Abril
    ano_x_ano = ""
    hdr = s.find("div", id="apr-hdr-periodo")
    if hdr:
        blk = hdr.find_next("div", class_="header-badges")
        if blk:
            for b in blk.find_all("span", class_="badge"):
                if "Ano x Ano" in b.text:
                    ano_x_ano = b.text.strip()
                    break

    return dict(
        id=3, icon="📈", cor="rgba(45,125,210,0.15)",
        titulo=f"Comercial: Abr {pct_meta} (01–{ultimo})",
        desc=(f"R$ {fmt(total/1e6)}M faturado em {n_dias} dias · "
              f"Média diária R$ {fmt(media/1000, 0)}K · Meta R$ 8,6M"
              + (f" · {ano_x_ano}" if ano_x_ano else "")),
        hora=TODAY, lida=False, link="comercial.html", critico=False
    )


def parse_financeiro():
    text = read("financeiro.html")
    if not text:
        return None

    taxa     = re.search(r"Taxa de recebimento.*?<b>([\d.,]+%)</b>",    text, re.S)
    recebido = re.search(r"Total recebido.*?<b>(R\$[^<]+)</b>",         text, re.S)
    juridico = re.search(r"Jurídico em aberto.*?<b>(R\$[^<]+)</b>",     text, re.S)
    pendente = re.search(r"Total a Receber.*?kpi-value[^>]*>(R\$[^<]+)",text, re.S)

    # Taxa: normaliza para vírgula (ex: 94.2% → 94,2%)
    taxa_txt = taxa.group(1).strip().replace(".", ",") if taxa else "?"
    rec_txt  = recebido.group(1).strip()               if recebido else "?"
    jur_txt  = juridico.group(1).strip()               if juridico \
               else "R$ 70.804 em jurídico (Vix · Dominalog · Vhz · Novo Rumo)"
    pend_txt = re.sub(r'<[^>]+>', '', pendente.group(1)).strip() if pendente else ""

    desc = f"Cartas de Débito · {rec_txt} recebido"
    if pend_txt:
        desc += f" · {pend_txt} pendente"
    desc += f" · ⚠️ {jur_txt}"

    return dict(
        id=6, icon="💰", cor="rgba(34,197,94,0.12)",
        titulo=f"Financeiro: {taxa_txt} recebido ✓",
        desc=desc, hora=TODAY, lida=False,
        link="financeiro.html", critico=False
    )


def parse_assistencia():
    s = soup("assistencia.html")
    if not s:
        return None

    def kpi(label):
        for card in s.find_all("div", class_="kpi-card"):
            lbl = card.find("div", class_="kpi-label")
            val = card.find("div", class_="kpi-value")
            if lbl and val and label.lower() in lbl.text.lower():
                v = re.sub(r'<[^>]+>', ' ', str(val)).strip()
                return re.split(r'\s+', v)[0], card
        return "?", None

    itens,   _         = kpi("Total de Itens")
    pedidos, _         = kpi("Total de Pedidos")
    atraso,  _         = kpi("Em Atraso (>")
    med,     _         = kpi("Atraso Médio")
    _, mod_card        = kpi("Moderados (31")
    _, crit_card       = kpi("Críticos (>45")
    _, ma_card         = kpi("Maior Atraso")

    def val_text(card):
        if not card:
            return "0"
        v = card.find("div", class_="kpi-value")
        return re.split(r'\s+', re.sub(r'<[^>]+>', ' ', str(v)).strip())[0] if v else "0"

    def sub_text(card):
        if not card:
            return ""
        sub = card.find("div", class_="kpi-sub")
        return sub.text.strip() if sub else ""

    moderados = val_text(mod_card)
    criticos  = val_text(crit_card)
    dias_ma   = val_text(ma_card)
    mod_sub   = sub_text(mod_card)
    ma_sub    = sub_text(ma_card)

    n_mod = int(moderados) if moderados.isdigit() else 0
    titulo = f"Assistência: {moderados} moderado(s) ⚠️" if n_mod > 0 else "Assistência: Em dia ✅"
    desc   = (f"{itens} itens · {pedidos} pedidos · {atraso} em atraso · "
              f"Atraso médio {med} · Maior: {dias_ma} ({ma_sub}) · "
              f"{moderados} moderado(s): {mod_sub} · {criticos} críticos")

    return dict(
        id=4, icon="🔧", cor="rgba(234,179,8,0.12)",
        titulo=titulo, desc=desc, hora=TODAY,
        lida=False, link="assistencia.html", critico=False
    )


def parse_cancelamentos():
    text = read("cancelamentos.html")
    if not text:
        return None

    dias = re.findall(r"\{d:'(\d{2}/04)',\s*g:([\d.]+)", text)
    if not dias:
        return None

    total  = sum(float(v) for _, v in dias)
    n_dias = len(dias)
    ultimo = dias[-1][0]

    # Soma por canal
    canais = []
    for nome, chave in [("Shopee", "sh"), ("Magalu", "ma"), ("ML", "me")]:
        vals = re.findall(rf"\{{d:'\d{{2}}/04'[^}}]*{chave}:([\d.]+)", text)
        if vals:
            canais.append(f"{nome} {int(sum(float(v) for v in vals))}")

    return dict(
        id=5, icon="❌", cor="rgba(204,40,40,0.12)",
        titulo=f"Cancelamentos: {int(total)} em Abril (01–{ultimo})",
        desc=f"{n_dias} dias · R$ {fmt(total/1000, 0)}K · {' · '.join(canais)}",
        hora=TODAY, lida=False, link="cancelamentos.html", critico=False
    )


def parse_devolucao():
    s = soup("devolucao.html")
    if not s:
        return None

    badge = s.find("div", class_="header-badge")
    total_notas = re.search(r"(\d+)\s+REGISTROS", badge.text).group(1) if badge else "?"

    def kpi_pair(label):
        for el in s.find_all(class_="kpi-label"):
            if label.lower() in el.text.lower():
                val = el.find_next_sibling(class_="kpi-value") or el.parent.find(class_="kpi-value")
                sub = el.find_next_sibling(class_="kpi-sub")  or el.parent.find(class_="kpi-sub")
                return (val.text.strip() if val else "?",
                        sub.text.strip() if sub else "")
        return "?", ""

    total_val,  total_sub = kpi_pair("Total Devolvido")
    ticket,     _         = kpi_pair("Ticket Médio")
    motivo_pct, mot_sub   = kpi_pair("Principal Motivo")
    transp_val, tr_sub    = kpi_pair("Top Transportadora")
    maior_mes,  mm_sub    = kpi_pair("Maior Mês")

    desc = (f"{total_sub} · {total_val} · {total_notas} notas · "
            f"Ticket médio {ticket} · "
            f"Top motivo: {motivo_pct} ({mot_sub}) · "
            f"Top transp: {transp_val} ({tr_sub}) · "
            f"Maior mês: {maior_mes} {mm_sub}")

    return dict(
        id=7, icon="↩️", cor="rgba(188,140,255,0.12)",
        titulo=f"Devoluções: {total_notas} no período",
        desc=desc, hora=TODAY, lida=False,
        link="devolucao.html", critico=False
    )


def parse_reputacao():
    text = read("reputacao.html")
    if not text:
        return None

    STATUS_MAP = {
        "laranja": "Laranja", "amarelo": "Amarelo",
        "verde":   "Verde",   "green":   "Verde",
        "ótimo":   "Ótimo",   "otimo":   "Ótimo",
        "vermelho":"Vermelho","red":     "Vermelho",
    }
    EMOJI = {
        "Ótimo": "✓", "Verde": "✓",
        "Amarelo": "⚠️", "Laranja": "🔴", "Vermelho": "🔴"
    }

    partes   = []
    laranjas = []
    amarelos = []

    for comment in re.findall(r'<!--(.*?)-->', text, re.S):
        c = comment.strip()

        # Score: número com . ou , (pode ter ~)
        score_m = re.search(r'~?([\d]+[.,][\d]+)', c)
        score   = score_m.group(1) if score_m else None

        # Status: primeira palavra reconhecida
        status = None
        for word in re.findall(r'[A-Za-záéíóúãõâêôÓóÀàÉéÍíÚú]+', c):
            s = STATUS_MAP.get(word.lower())
            if s:
                status = s
                break

        if not status or not score:
            continue

        # Nome: remove score, status e parênteses
        nome = c
        nome = re.sub(r'~?[\d]+[.,][\d]+', '', nome)
        nome = re.sub(r'\([^)]*\)', '', nome)
        for word in list(STATUS_MAP.keys()) + list(STATUS_MAP.values()):
            nome = re.sub(rf'\b{re.escape(word)}\b', '', nome, flags=re.IGNORECASE)
        nome = ' '.join(nome.split())  # colapsa espaços

        # Remove duplicação ("Madeira Madeira" → "Madeira")
        parts = nome.split()
        if len(parts) >= 2 and parts[0].lower() == parts[1].lower():
            nome = parts[0]

        if not nome or len(nome) > 25:
            continue

        e = EMOJI.get(status, "")
        partes.append(f"{nome} {score} {status} {e}")
        if status in ("Laranja", "Vermelho"):
            laranjas.append(nome)
        elif status == "Amarelo":
            amarelos.append(nome)

    if laranjas:
        titulo = "Reputação: " + " · ".join(laranjas) + " Laranja 🔴"
    elif amarelos:
        titulo = "Reputação: " + " · ".join(amarelos) + " Amarelo ⚠️"
    else:
        titulo = "Reputação: Todas as plataformas OK ✅"

    return dict(
        id=8, icon="⭐", cor="rgba(245,158,11,0.12)",
        titulo=titulo,
        desc=" · ".join(partes) if partes else "Dados não disponíveis",
        hora=TODAY, lida=False, link="reputacao.html", critico=False
    )


# ─────────────────────────────────────────────
# GERADOR DE JS
# ─────────────────────────────────────────────

def notif_to_js(n):
    esc = lambda s: str(s).replace("'", "\\'")
    return (
        f"  {{id:{n['id']},icon:'{esc(n['icon'])}',cor:'{esc(n['cor'])}',"
        f"titulo:'{esc(n['titulo'])}',desc:'{esc(n['desc'])}',"
        f"hora:'{esc(n['hora'])}',lida:{'true' if n['lida'] else 'false'},"
        f"link:'{esc(n['link'])}',critico:{'true' if n['critico'] else 'false'}}}"
    )


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    parsers = [
        parse_estoque, parse_sla, parse_comercial, parse_financeiro,
        parse_assistencia, parse_cancelamentos, parse_devolucao, parse_reputacao,
    ]

    notifs = []
    for fn in parsers:
        result = fn()
        if result:
            notifs.append(result)
            print(f"  ✅ {fn.__name__[6:]}: ok")
        else:
            print(f"  ⚠️  {fn.__name__[6:]}: arquivo não encontrado, pulado")

    notifs.sort(key=lambda x: x["id"])

    novo_bloco = ("let NOTIFICACOES_HOJE = [\n"
                  + ",\n".join(notif_to_js(n) for n in notifs)
                  + "\n];")

    index_path = BASE / "index.html"
    conteudo   = index_path.read_text(encoding="utf-8")
    novo, trocas = re.subn(
        r"let NOTIFICACOES_HOJE\s*=\s*\[.*?\];",
        novo_bloco, conteudo, flags=re.S
    )
    if trocas == 0:
        print("❌  Padrão NOTIFICACOES_HOJE não encontrado no index.html!")
        return

    index_path.write_text(novo, encoding="utf-8")
    print(f"\n✅  index.html atualizado com {len(notifs)} notificações ({TODAY})")


if __name__ == "__main__":
    main()
