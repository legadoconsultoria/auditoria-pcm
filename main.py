import flet as ft
import sqlite3
import threading
import time
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
    cursor.execute("CREATE TABLE IF NOT EXISTS perguntas (id INTEGER PRIMARY KEY AUTOINCREMENT, cidade_id INTEGER, texto_pergunta TEXT, FOREIGN KEY(cidade_id) REFERENCES cidades(id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS alternativas (id INTEGER PRIMARY KEY AUTOINCREMENT, pergunta_id INTEGER, texto_alternativa TEXT, votos INTEGER DEFAULT 0, FOREIGN KEY(pergunta_id) REFERENCES perguntas(id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS fila_sincronizacao (id INTEGER PRIMARY KEY AUTOINCREMENT, alternativa_id INTEGER, sincronizado INTEGER DEFAULT 0)")
    conexao.commit()
    conexao.close()

# ==========================================
# 3. SINCRONIZAÇÃO INTELIGENTE (COM TEXTOS)
# ==========================================
def sincronizar_com_supabase():
    try:
        supabase: Client = create_client(URL_SUPABASE, CHAVE_SUPABASE)
        print("✅ Conectado ao Supabase!")
    except Exception as e:
        print(f"❌ Erro de conexão: {e}")
        return

    while True:
        try:
            conexao = sqlite3.connect("banco_local.db")
            cursor = conexao.cursor()
            
            # Buscamos o ID da fila + os textos reais usando JOIN
            cursor.execute("""
                SELECT 
                    f.id, 
                    f.alternativa_id, 
                    a.texto_alternativa, 
                    p.texto_pergunta, 
                    c.nome 
                FROM fila_sincronizacao f
                JOIN alternativas a ON f.alternativa_id = a.id
                JOIN perguntas p ON a.pergunta_id = p.id
                JOIN cidades c ON p.cidade_id = c.id
                WHERE f.sincronizado = 0
            """)
            pendentes = cursor.fetchall()

            for registro in pendentes:
                id_fila, alt_id, txt_alternativa, txt_pergunta, nome_cidade = registro
                
                # Enviamos o pacote completo de dados para facilitar o Dashboard
                dados_nuvem = {
                    "alternativa_id": alt_id,
                    "resposta": txt_alternativa,
                    "pergunta": txt_pergunta,
                    "cidade": nome_cidade
                }
                
                resposta = supabase.table("votos_nuvem").insert(dados_nuvem).execute()
                
                if hasattr(resposta, 'data') and len(resposta.data) > 0:
                    cursor.execute("UPDATE fila_sincronizacao SET sincronizado = 1 WHERE id = ?", (id_fila,))
                    conexao.commit()
                    print(f"☁️ Sincronizado: {nome_cidade} -> {txt_alternativa}")
            
            conexao.close()
        except Exception as e:
            print(f"🚨 Erro ao sincronizar: {e}") 
            
        time.sleep(10)

# ==========================================
# 4. INTERFACE PRINCIPAL
# ==========================================
def main(page: ft.Page):
    page.title = "Auditoria de Pesquisas"
    page.theme_mode = ft.ThemeMode.LIGHT 
    page.bgcolor = "white"
    page.window_width = 450
    page.window_height = 800
    
    inicializar_banco_local()
    threading.Thread(target=sincronizar_com_supabase, daemon=True).start()

    estilo_input = {"border_radius": 8, "filled": True, "bgcolor": "white", "color": "black"}

    # --- ABA: DESENHAR ---
    nome_cidade_input = ft.TextField(label="Nome da Cidade", width=380, **estilo_input)
    cidade_dropdown = ft.Dropdown(label="Escolha a Cidade", width=380, **estilo_input)
    pergunta_input = ft.TextField(label="Pergunta", width=380, **estilo_input)
    coluna_alternativas = ft.Column(controls=[ft.TextField(label="Alternativa 1", width=380, **estilo_input)])
    msg_desenhar = ft.Text(weight="bold", color="black")

    def atualizar_dropdowns():
        conexao = sqlite3.connect("banco_local.db")
        cursor = conexao.cursor()
        cursor.execute("SELECT id, nome FROM cidades")
        opcoes = [ft.dropdown.Option(key=str(c[0]), text=c[1]) for c in cursor.fetchall()]
        cidade_dropdown.options = opcoes
        cidade_dropdown_res.options = opcoes
        conexao.close()
        page.update()

    def salvar_cidade(e):
        if nome_cidade_input.value:
            conexao = sqlite3.connect("banco_local.db")
            cursor = conexao.cursor()
            cursor.execute("INSERT INTO cidades (nome) VALUES (?)", (nome_cidade_input.value,))
            conexao.commit(); conexao.close()
            nome_cidade_input.value = ""
            atualizar_dropdowns(); carregar_cidades_voto()
            msg_desenhar.value = "✅ Cidade salva!"; msg_desenhar.color = "green"; page.update()

    def add_alt(e):
        n = len(coluna_alternativas.controls) + 1
        coluna_alternativas.controls.append(ft.TextField(label=f"Alternativa {n}", width=380, **estilo_input))
        page.update()

    def salvar_pergunta(e):
        alts = [c.value.strip() for c in coluna_alternativas.controls if c.value.strip()]
        if not cidade_dropdown.value or not pergunta_input.value or not alts: return
        conexao = sqlite3.connect("banco_local.db"); cursor = conexao.cursor()
        cursor.execute("INSERT INTO perguntas (cidade_id, texto_pergunta) VALUES (?, ?)", (int(cidade_dropdown.value), pergunta_input.value))
        p_id = cursor.lastrowid
        for a in alts: cursor.execute("INSERT INTO alternativas (pergunta_id, texto_alternativa) VALUES (?, ?)", (p_id, a))
        conexao.commit(); conexao.close()
        pergunta_input.value = ""; coluna_alternativas.controls = [ft.TextField(label="Alternativa 1", width=380, **estilo_input)]
        msg_desenhar.value = "✅ Pergunta salva!"; msg_desenhar.color = "green"; page.update()

    tela_desenhar = ft.Column(scroll=ft.ScrollMode.AUTO, controls=[
        ft.Container(padding=20, content=ft.Column([ft.Text("🏢 Cadastrar Cidade", weight="bold", color="black"), nome_cidade_input, ft.ElevatedButton("Criar", on_click=salvar_cidade)])),
        ft.Container(padding=20, content=ft.Column([ft.Text("❓ Adicionar Pergunta", weight="bold", color="black"), cidade_dropdown, pergunta_input, coluna_alternativas, ft.TextButton("+ Alternativa", on_click=add_alt), ft.ElevatedButton("Salvar Pergunta", on_click=salvar_pergunta)])),
        msg_desenhar
    ])

    # --- ABA: VOTAR ---
    lista_cidades_voto = ft.Column(spacing=15)
    area_votacao = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=15, expand=True)

    def registrar_voto(alt_id, cid_id):
        conexao = sqlite3.connect("banco_local.db"); cursor = conexao.cursor()
        cursor.execute("UPDATE alternativas SET votos = votos + 1 WHERE id = ?", (alt_id,))
        cursor.execute("INSERT INTO fila_sincronizacao (alternativa_id, sincronizado) VALUES (?, 0)", (alt_id,))
        conexao.commit(); conexao.close()
        try:
            page.snack_bar = ft.SnackBar(content=ft.Text("✅ Voto contabilizado!", color="white"), bgcolor="green")
            page.snack_bar.open = True
            page.update()
        except: pass
        exibir_pesquisa(cid_id)

    def exibir_pesquisa(cid_id):
        area_votacao.controls.clear()
        conexao = sqlite3.connect("banco_local.db"); cursor = conexao.cursor()
        cursor.execute("SELECT nome FROM cidades WHERE id = ?", (cid_id,))
        area_votacao.controls.append(ft.Row([ft.TextButton("⬅️ Voltar", on_click=lambda e: carregar_cidades_voto()), ft.Text(cursor.fetchone()[0], size=22, weight="bold", color="black")]))
        cursor.execute("SELECT id, texto_pergunta FROM perguntas WHERE cidade_id = ?", (cid_id,))
        for p in cursor.fetchall():
            btns = []
            cursor.execute("SELECT id, texto_alternativa FROM alternativas WHERE pergunta_id = ?", (p[0],))
            for a in cursor.fetchall():
                btns.append(ft.ElevatedButton(a[1], on_click=lambda e, aid=a[0]: registrar_voto(aid, cid_id), width=350))
            area_votacao.controls.append(ft.Container(padding=20, border_radius=12, border=ft.border.all(1, "black"), content=ft.Column([ft.Text(p[1], weight="bold", size=18, color="blue"), ft.Divider(color="black"), ft.Column(btns)])))
        conexao.close(); lista_cidades_voto.visible = False; area_votacao.visible = True; page.update()

    def carregar_cidades_voto():
        lista_cidades_voto.controls.clear()
        lista_cidades_voto.controls.append(ft.Text("📋 Escolha a pesquisa:", size=20, weight="bold", color="black"))
        conexao = sqlite3.connect("banco_local.db"); cursor = conexao.cursor()
        cursor.execute("SELECT id, nome FROM cidades")
        for c in cursor.fetchall():
            lista_cidades_voto.controls.append(ft.ElevatedButton(f"🏢 {c[1]}", width=380, height=50, on_click=lambda e, cid=c[0]: exibir_pesquisa(cid)))
        conexao.close(); lista_cidades_voto.visible = True; area_votacao.visible = False; page.update()

    tela_votar = ft.Container(content=ft.Column([lista_cidades_voto, area_votacao], expand=True), padding=20, expand=True)

    # --- ABA: RESULTADOS ---
    cidade_dropdown_res = ft.Dropdown(label="Cidade", width=380, **estilo_input)
    exibicao_res = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=15, expand=True)

    def mostrar_res(e):
        if not cidade_dropdown_res.value: return
        exibicao_res.controls.clear()
        conexao = sqlite3.connect("banco_local.db"); cursor = conexao.cursor()
        cursor.execute("SELECT id, texto_pergunta FROM perguntas WHERE cidade_id = ?", (int(cidade_dropdown_res.value),))
        perguntas = cursor.fetchall()
        cores = ["red", "blue", "green", "orange", "purple", "cyan", "pink", "brown"]
        for p in perguntas:
            perg_id, texto_perg = p
            cursor.execute("SELECT texto_alternativa, votos FROM alternativas WHERE pergunta_id = ?", (perg_id,))
            alternativas = cursor.fetchall()
            total_votos = sum(a[1] for a in alternativas)
            cartao_conteudo = [ft.Text(texto_perg, weight="bold", size=18, color="blue"), ft.Divider(color="black")]
            for i, a in enumerate(alternativas):
                texto_alt, votos = a
                cor = cores[i % len(cores)]
                porcentagem = (votos / total_votos * 100) if total_votos > 0 else 0
                cartao_conteudo.append(ft.Row(controls=[ft.Text(f"{texto_alt}", weight="bold", size=15, color="black"), ft.Text(f"{votos} votos ({porcentagem:.1f}%)", size=15, color="black")], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
                largura_maxima, largura_atual = 340, 340 * (porcentagem / 100) if porcentagem > 0 else 5
                cartao_conteudo.append(ft.Stack([ft.Container(width=largura_maxima, height=15, bgcolor="#E2E8F0", border_radius=8), ft.Container(width=largura_atual, height=15, bgcolor=cor, border_radius=8)]))
                cartao_conteudo.append(ft.Container(height=5))
            exibicao_res.controls.append(ft.Container(padding=20, border_radius=12, border=ft.border.all(1, "black"), content=ft.Column(cartao_conteudo)))
        conexao.close(); page.update()

    tela_resultados = ft.Column([
        ft.Container(padding=20, content=ft.Column([ft.Text("📊 Resultados por Cidade", weight="bold", color="black"), cidade_dropdown_res, ft.ElevatedButton("Carregar Dados", on_click=mostrar_res)])),
        ft.Container(content=exibicao_res, padding=10, expand=True)
    ], expand=True)

    # --- ESTRUTURA FINAL ---
    tab_bar, tab_view = ft.TabBar(tabs=[ft.Tab(label="Votar", icon="how_to_vote"), ft.Tab(label="Desenhar", icon="edit_document"), ft.Tab(label="Resultados", icon="pie_chart")]), ft.TabBarView(expand=True, controls=[tela_votar, tela_desenhar, tela_resultados])
    page.add(ft.Tabs(length=3, expand=True, content=ft.Column([tab_bar, tab_view], expand=True)))
    atualizar_dropdowns(); carregar_cidades_voto()

ft.app(target=main)