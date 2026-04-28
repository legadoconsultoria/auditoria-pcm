import flet as ft
import sqlite3
import threading
import time
import datetime
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURAÇÕES DO SUPABASE
# ==========================================
URL_SUPABASE = "https://mtjqwikzotfvqlkspbtm.supabase.co"
CHAVE_SUPABASE = "sb_publishable_-IuFm5vzE3e0bdzvgkajFg_LGwZtvYm"

# ==========================================
# 2. BANCO DE DADOS LOCAL
# ==========================================
def inicializar_banco_local():
    conexao = sqlite3.connect("banco_local.db")
    cursor = conexao.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS cidades (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS perguntas (id INTEGER PRIMARY KEY AUTOINCREMENT, cidade_id INTEGER, texto_pergunta TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS alternativas (id INTEGER PRIMARY KEY AUTOINCREMENT, pergunta_id INTEGER, texto_alternativa TEXT, votos INTEGER DEFAULT 0)")
    cursor.execute("CREATE TABLE IF NOT EXISTS fila_sincronizacao (id INTEGER PRIMARY KEY AUTOINCREMENT, alternativa_id INTEGER, sincronizado INTEGER DEFAULT 0)")
    conexao.commit()
    conexao.close()

# ==========================================
# 3. PARTE 2: BAIXAR PESQUISAS DO STREAMLIT (SUPABASE)
# ==========================================
def baixar_pesquisas_da_nuvem():
    try:
        supabase: Client = create_client(URL_SUPABASE, CHAVE_SUPABASE)
        
        # 1. Baixa Cidades/Unidades
        cidades_nuvem = supabase.table("cidades").select("*").execute()
        conexao = sqlite3.connect("banco_local.db")
        cursor = conexao.cursor()
        
        for c in cidades_nuvem.data:
            cursor.execute("INSERT OR IGNORE INTO cidades (id, nome) VALUES (?, ?)", (c['id'], c['nome']))
        
        # 2. Baixa Perguntas
        perguntas_nuvem = supabase.table("perguntas").select("*").execute()
        for p in perguntas_nuvem.data:
            cursor.execute("INSERT OR IGNORE INTO perguntas (id, cidade_id, texto_pergunta) VALUES (?, ?, ?)", 
                           (p['id'], p['cidade_id'], p['texto_pergunta']))
            
        # 3. Baixa Alternativas
        alts_nuvem = supabase.table("alternativas").select("*").execute()
        for a in alts_nuvem.data:
            cursor.execute("INSERT OR IGNORE INTO alternativas (id, pergunta_id, texto_alternativa, votos) VALUES (?, ?, ?, ?)", 
                           (a['id'], a['pergunta_id'], a['texto_alternativa'], a['votos']))
            
        conexao.commit()
        conexao.close()
        return True
    except Exception as e:
        print(f"Erro ao baixar dados: {e}")
        return False

# ==========================================
# 4. SINCRONIZAÇÃO DE VOTOS (OFFLINE -> ONLINE)
# ==========================================
def sincronizar_votos():
    try:
        supabase: Client = create_client(URL_SUPABASE, CHAVE_SUPABASE)
        while True:
            try:
                conexao = sqlite3.connect("banco_local.db")
                cursor = conexao.cursor()
                cursor.execute("""
                    SELECT f.id, f.alternativa_id, a.texto_alternativa, p.texto_pergunta, c.nome 
                    FROM fila_sincronizacao f
                    JOIN alternativas a ON f.alternativa_id = a.id
                    JOIN perguntas p ON a.pergunta_id = p.id
                    JOIN cidades c ON p.cidade_id = c.id
                    WHERE f.sincronizado = 0
                """)
                for r in cursor.fetchall():
                    res = supabase.table("votos_nuvem").insert({
                        "alternativa_id": r[1], "resposta": r[2], 
                        "pergunta": r[3], "cidade": r[4]
                    }).execute()
                    if res.data:
                        cursor.execute("UPDATE fila_sincronizacao SET sincronizado = 1 WHERE id = ?", (r[0],))
                        conexao.commit()
                conexao.close()
            except: pass
            time.sleep(10)
    except: pass

# ==========================================
# 5. INTERFACE PRINCIPAL
# ==========================================
def main(page: ft.Page):
    page.title = "Pesquisa PCM"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "white"
    page.scroll = ft.ScrollMode.AUTO
    inicializar_banco_local()
    threading.Thread(target=sincronizar_votos, daemon=True).start()

    lista_pesquisas = ft.Column(spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO)
    area_votacao = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=20, visible=False)

    def atualizar_app(e):
        page.snack_bar = ft.SnackBar(ft.Text("Sincronizando com a nuvem..."))
        page.snack_bar.open = True
        page.update()
        
        if baixar_pesquisas_da_nuvem():
            page.snack_bar = ft.SnackBar(ft.Text("✅ Pesquisas atualizadas!", color="white"), bgcolor="green")
        else:
            page.snack_bar = ft.SnackBar(ft.Text("⚠️ Sem internet ou erro no servidor."), bgcolor="orange")
        
        page.snack_bar.open = True
        carregar_lista()

    def registrar_voto(alt_id, cid_id):
        conexao = sqlite3.connect("banco_local.db"); cursor = conexao.cursor()
        cursor.execute("UPDATE alternativas SET votos = votos + 1 WHERE id = ?", (alt_id,))
        cursor.execute("INSERT INTO fila_sincronizacao (alternativa_id) VALUES (?)", (alt_id,))
        conexao.commit(); conexao.close()
        exibir_pesquisa(cid_id)

    def registrar_aberta(e, p_id, cid_id, tf):
        texto = tf.value.strip()
        if not texto: return
        conexao = sqlite3.connect("banco_local.db"); cursor = conexao.cursor()
        cursor.execute("SELECT id FROM alternativas WHERE pergunta_id = ? AND UPPER(texto_alternativa) = UPPER(?)", (p_id, texto))
        existe = cursor.fetchone()
        if existe:
            cursor.execute("UPDATE alternativas SET votos = votos + 1 WHERE id = ?", (existe[0],))
            cursor.execute("INSERT INTO fila_sincronizacao (alternativa_id) VALUES (?)", (existe[0],))
        else:
            cursor.execute("INSERT INTO alternativas (pergunta_id, texto_alternativa, votos) VALUES (?, ?, 1)", (p_id, texto))
            cursor.execute("INSERT INTO fila_sincronizacao (alternativa_id) VALUES (?)", (cursor.lastrowid,))
        conexao.commit(); conexao.close()
        exibir_pesquisa(cid_id)

    def exibir_pesquisa(cid_id):
        area_votacao.controls.clear()
        conexao = sqlite3.connect("banco_local.db"); cursor = conexao.cursor()
        cursor.execute("SELECT nome FROM cidades WHERE id = ?", (cid_id,))
        area_votacao.controls.append(ft.Row([ft.TextButton("⬅️ Voltar", on_click=lambda _: carregar_lista()), ft.Text(cursor.fetchone()[0], size=20, weight="bold", color="black")]))
        
        cursor.execute("SELECT id, texto_pergunta FROM perguntas WHERE cidade_id = ?", (cid_id,))
        for p in cursor.fetchall():
            btns = []
            cursor.execute("SELECT id, texto_alternativa FROM alternativas WHERE pergunta_id = ?", (p[0],))
            for a in cursor.fetchall():
                btns.append(ft.ElevatedButton(a[1], on_click=lambda e, aid=a[0]: registrar_voto(aid, cid_id), width=350, bgcolor="#E3F2FD", color="#0D47A1"))
            
            # --- CORREÇÃO AQUI: Ordem de montagem correta ---
            # 1. Cria a "peça" (campo de texto)
            tf = ft.TextField(label="Outra resposta...")
            
            # 2. Conecta as ações depois que a peça já existe
            tf.on_submit = lambda e, pid=p[0], cid=cid_id, field=tf: registrar_aberta(e, pid, cid, field)
            btn_add = ft.ElevatedButton("Adicionar", on_click=lambda e, pid=p[0], cid=cid_id, field=tf: registrar_aberta(e, pid, cid, field))
            
            # 3. Coloca tudo na tela
            area_votacao.controls.append(ft.Container(padding=15, border=ft.border.all(1, "grey"), border_radius=10, content=ft.Column([ft.Text(p[1], weight="bold", color="black"), ft.Column(btns), tf, btn_add])))
        
        conexao.close(); lista_pesquisas.visible = False; area_votacao.visible = True; page.update()

    def carregar_lista():
        lista_pesquisas.controls.clear()
        lista_pesquisas.controls.append(ft.Text("📋 Pesquisas PCM", size=22, weight="bold", color="black"))
        lista_pesquisas.controls.append(ft.ElevatedButton("🔄 Atualizar Pesquisas (Nuvem)", on_click=atualizar_app, icon="refresh"))
        
        conexao = sqlite3.connect("banco_local.db"); cursor = conexao.cursor()
        cursor.execute("SELECT id, nome FROM cidades")
        for c in cursor.fetchall():
            lista_pesquisas.controls.append(ft.ElevatedButton(f"🏢 {c[1]}", width=350, height=50, on_click=lambda e, cid=c[0]: exibir_pesquisa(cid)))
        conexao.close(); lista_pesquisas.visible = True; area_votacao.visible = False; page.update()

    page.add(ft.Container(content=ft.Column([lista_pesquisas, area_votacao]), padding=20))
    carregar_lista()

ft.app(target=main)