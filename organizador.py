from dotenv import load_dotenv
import os
import shutil
import json
import re
from PyPDF2 import PdfReader
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from openai import OpenAI
import pdfplumber

load_dotenv()

# -----------------------------
# CONFIGURAÇÃO
# -----------------------------

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
downloads = os.path.expanduser("~/Downloads")

# -----------------------------
# EXTRAÇÃO DE TEXTO (APENAS PRIMEIRA PÁGINA)
# -----------------------------

def extrair_primeira_pagina_pdf(caminho):
    """
    Extrai texto APENAS da primeira página do PDF (otimizado para artigos)
    """
    print("  📖 Extraindo primeira página...")
    texto = ""
    
    # Estratégia 1: pdfplumber (apenas página 1)
    try:
        with pdfplumber.open(caminho) as pdf:
            if len(pdf.pages) > 0:
                primeira_pagina = pdf.pages[0]
                texto = primeira_pagina.extract_text()
                if texto and len(texto.strip()) > 10:
                    print(f"     ✅ pdfplumber extraiu {len(texto)} caracteres")
                    return texto
    except Exception as e:
        print(f"     ⚠️ pdfplumber falhou: {str(e)[:50]}")
    
    # Estratégia 2: PyPDF2 (apenas página 1)
    try:
        reader = PdfReader(caminho)
        if len(reader.pages) > 0:
            primeira_pagina = reader.pages[0]
            texto = primeira_pagina.extract_text()
            if texto and len(texto.strip()) > 10:
                print(f"     ✅ PyPDF2 extraiu {len(texto)} caracteres")
                return texto
    except Exception as e:
        print(f"     ⚠️ PyPDF2 falhou: {str(e)[:50]}")
    
    # Estratégia 3: OCR (apenas página 1)
    try:
        print("     🔍 Tentando OCR na primeira página...")
        imagens = convert_from_path(caminho, first_page=1, last_page=1, dpi=200)
        if imagens:
            texto_ocr = pytesseract.image_to_string(imagens[0], lang='eng+por')
            if len(texto_ocr.strip()) > 10:
                print(f"     ✅ OCR extraiu {len(texto_ocr)} caracteres")
                return texto_ocr
    except Exception as e:
        print(f"     ⚠️ OCR falhou: {str(e)[:50]}")
    
    print("     ❌ Não foi possível extrair texto da primeira página")
    return ""

def extrair_texto_imagem_avancado(caminho):
    """Extrai texto de imagem com OCR"""
    try:
        print("  🖼️ Extraindo texto da imagem...")
        imagem = Image.open(caminho)
        texto = pytesseract.image_to_string(imagem, lang='eng+por')
        if len(texto.strip()) > 10:
            print(f"     ✅ OCR extraiu {len(texto)} caracteres")
            return texto
        return ""
    except Exception as e:
        print(f"     ❌ Falha no OCR: {e}")
        return ""

# -----------------------------
# EXTRAÇÃO DE TÍTULO CIENTÍFICO
# -----------------------------

def extrair_titulo_metadata(caminho):
    """
    Tenta extrair título dos metadados do PDF
    """
    try:
        reader = PdfReader(caminho)
        metadata = reader.metadata
        
        if metadata:
            # Tentar diferentes campos de metadados
            titulo = metadata.get('/Title', '')
            if titulo and len(titulo) > 5:
                return titulo.strip()
            
            # Alguns PDFs usam /Subject como título
            assunto = metadata.get('/Subject', '')
            if assunto and len(assunto) > 10:
                return assunto.strip()
        
        # Tenta com pdfplumber para metadados
        with pdfplumber.open(caminho) as pdf:
            if pdf.metadata:
                titulo = pdf.metadata.get('Title', '')
                if titulo and len(titulo) > 5:
                    return titulo.strip()
                    
    except Exception as e:
        pass
    
    return None

def identificar_titulo_por_heuristica(texto):
    """
    Identifica o título em artigos científicos usando heurísticas específicas
    Processa apenas as primeiras 30 linhas (primeira página)
    """
    if not texto:
        return None
    
    linhas = texto.split('\n')
    linhas_limpas = [linha.strip() for linha in linhas if linha.strip()]
    
    if not linhas_limpas:
        return None
    
    candidatos = []
    
    # Palavras que indicam título científico
    palavras_titulo = ['study', 'analysis', 'effect', 'impact', 'review', 
                      'evaluation', 'assessment', 'comparison', 'novel', 
                      'new', 'approach', 'method', 'technique', 'role',
                      'investigation', 'determination', 'influence', 'factor',
                      'article', 'paper', 'research', 'systematic']
    
    # Palavras que indicam cabeçalho (ignorar)
    cabecalhos = ['abstract', 'introduction', 'background', 'methods', 
                  'results', 'conclusion', 'keywords', 'received', 
                  'accepted', 'published', 'doi', 'vol', 'no', 'page',
                  'author', 'affiliation', 'correspondence', 'email',
                  'references', 'appendix', 'supplementary', 'funding',
                  'conflict', 'interest', 'editor', 'reviewer']
    
    for i, linha in enumerate(linhas_limpas[:30]):  # Primeiras 30 linhas
        # Ignora linhas muito curtas
        if len(linha) < 15:
            continue
            
        linha_lower = linha.lower()
        
        # Ignora linhas que parecem cabeçalho
        if any(cabecalho in linha_lower for cabecalho in cabecalhos):
            continue
        
        # Critérios de pontuação
        pontuacao = 0
        
        # 1. Tamanho (títulos geralmente são longos)
        if len(linha) > 60:
            pontuacao += 4
        elif len(linha) > 40:
            pontuacao += 3
        elif len(linha) > 25:
            pontuacao += 2
        else:
            pontuacao += 1
        
        # 2. Posição (quanto mais cedo, maior chance)
        pontuacao += max(0, 12 - i)
        
        # 3. Presença de dois pontos (subtítulo)
        if ':' in linha:
            pontuacao += 3
        
        # 4. Letras maiúsculas (títulos costumam ter maiúsculas)
        maiusculas = sum(1 for c in linha if c.isupper())
        if maiusculas > len(linha) * 0.2:  # Mais de 20% maiúsculas
            pontuacao += 2
        
        # 5. Não contém números de página ou referências
        if not re.search(r'page \d+|p\. \d+|\b\d{1,3}\b.*\b\d{1,3}\b', linha_lower):
            pontuacao += 1
        
        # 6. Palavras comuns em títulos científicos
        if any(palavra in linha_lower for palavra in palavras_titulo):
            pontuacao += 2
        
        # 7. Começa com letra maiúscula
        if linha and linha[0].isupper():
            pontuacao += 1
        
        # 8. Não tem muitos números (títulos não têm muitos números)
        numeros = sum(1 for c in linha if c.isdigit())
        if numeros < 5:
            pontuacao += 1
        
        candidatos.append((pontuacao, linha, i))
    
    # Ordenar por pontuação e pegar o melhor
    if candidatos:
        candidatos.sort(reverse=True)
        melhor_titulo = candidatos[0][1]
        
        # Limpar título
        melhor_titulo = re.sub(r'\s+', ' ', melhor_titulo)  # Remove espaços extras
        melhor_titulo = re.sub(r'^[\d\.]+\s*', '', melhor_titulo)  # Remove numeração inicial
        melhor_titulo = re.sub(r'^["\']|["\']$', '', melhor_titulo)  # Remove aspas
        
        # Remove palavras muito comuns se estiverem no início
        palavras_comuns_inicio = ['the', 'a', 'an', 'this', 'that', 'these', 'those']
        palavras = melhor_titulo.split()
        if palavras and palavras[0].lower() in palavras_comuns_inicio and len(palavras) > 3:
            melhor_titulo = ' '.join(palavras[1:])
        
        return melhor_titulo
    
    return None

def extrair_titulo_cientifico_com_ia(texto):
    """
    Usa IA com prompt específico para artigos científicos
    """
    if not texto or len(texto.strip()) < 100:
        return None
    
    prompt = f"""
    Você é um especialista em artigos científicos.
    
    Extraia o TÍTULO PRINCIPAL deste artigo científico.
    O título está nas primeiras linhas da primeira página.
    
    Características do título científico:
    - Geralmente é a primeira linha de destaque após o cabeçalho
    - Costuma ser longo (30-150 caracteres)
    - Pode conter dois pontos separando título principal e subtítulo
    - Está em inglês ou português
    - Não contém palavras como "Abstract", "Introduction"
    
    Regras:
    1. Ignore cabeçalhos de periódico, autores, afiliações
    2. Ignore números de páginas, DOI, datas
    3. Retorne APENAS o título limpo, sem formatação
    4. Se houver subtítulo, inclua após os dois pontos
    
    Texto da primeira página:
    {texto[:3000]}
    
    Título:
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200
        )
        
        titulo = response.choices[0].message.content.strip()
        
        # Validar título
        if titulo and 10 < len(titulo) < 200:
            # Remover possíveis artefatos
            titulo = re.sub(r'^["\']|["\']$', '', titulo)
            titulo = re.sub(r'\s+', ' ', titulo)
            return titulo
        
        return None
        
    except Exception as e:
        return None

def extrair_titulo_cientifico_completo(caminho, nome_arquivo):
    """
    Pipeline completo para extrair título de artigo científico
    (processa apenas a primeira página)
    """
    # Estratégia 1: Metadados do PDF (mais rápido)
    titulo = extrair_titulo_metadata(caminho)
    if titulo:
        print(f"     📋 Extraído de metadados: {titulo[:70]}...")
        return titulo
    
    # Extrair texto da primeira página
    texto = extrair_primeira_pagina_pdf(caminho)
    
    if not texto or len(texto.strip()) < 50:
        print(f"     ⚠️ Não foi possível extrair texto da primeira página")
        # Fallback: usar nome do arquivo
        nome_sem_ext = os.path.splitext(nome_arquivo)[0]
        nome_limpo = nome_sem_ext.replace('_', ' ').replace('-', ' ')
        nome_limpo = re.sub(r'\[\d+\]|\(\d+\)|\.pdf$', '', nome_limpo)
        nome_limpo = re.sub(r'\s+', ' ', nome_limpo).strip()
        
        if len(nome_limpo) > 10:
            print(f"     📁 Usando nome do arquivo: {nome_limpo[:70]}...")
            return nome_limpo
        return None
    
    # Estratégia 2: IA com contexto científico
    if len(texto.strip()) > 100:
        titulo = extrair_titulo_cientifico_com_ia(texto)
        if titulo:
            print(f"     🤖 Extraído com IA: {titulo[:70]}...")
            return titulo
    
    # Estratégia 3: Heurísticas
    titulo = identificar_titulo_por_heuristica(texto)
    if titulo:
        print(f"     📊 Extraído por heurística: {titulo[:70]}...")
        return titulo
    
    # Estratégia 4: Primeiras linhas não vazias
    linhas = [l.strip() for l in texto.split('\n') if l.strip()]
    for linha in linhas[:10]:
        # Pega a primeira linha com mais de 30 caracteres
        if len(linha) > 30 and not any(x in linha.lower() for x in ['abstract', 'introduction', 'background']):
            print(f"     📄 Usando primeira linha: {linha[:70]}...")
            return linha
    
    # Estratégia 5: Nome do arquivo
    nome_sem_ext = os.path.splitext(nome_arquivo)[0]
    nome_limpo = nome_sem_ext.replace('_', ' ').replace('-', ' ')
    nome_limpo = re.sub(r'\[\d+\]|\(\d+\)|\.pdf$', '', nome_limpo)
    nome_limpo = re.sub(r'\s+', ' ', nome_limpo).strip()
    
    if len(nome_limpo) > 10:
        print(f"     📁 Usando nome do arquivo: {nome_limpo[:70]}...")
        return nome_limpo
    
    return None

# -----------------------------
# FUNÇÕES AUXILIARES
# -----------------------------

def limpar_nome(nome):
    """Limpa o nome removendo caracteres especiais"""
    nome = nome.replace(" ", "_")
    nome = nome.replace("/", "-")
    nome = nome.replace("\\", "-")
    nome = nome.replace(":", "-")
    nome = nome.replace("*", "")
    nome = nome.replace("?", "")
    nome = nome.replace('"', "")
    nome = nome.replace("'", "")
    nome = nome.replace("|", "")
    nome = nome.replace("<", "")
    nome = nome.replace(">", "")
    nome = nome.replace("\n", " ")
    nome = nome.replace("\r", " ")
    # Remove múltiplos underscores
    nome = re.sub(r'_+', '_', nome)
    # Remove números de CNPJ/CPF
    nome = re.sub(r'_\d{11,}$', '', nome)
    # Remove extensões duplicadas
    nome = re.sub(r'\.pdf\.pdf$', '.pdf', nome)
    # Limita tamanho
    if len(nome) > 200:
        nome = nome[:200]
    return nome.strip('_')

def evitar_duplicado(caminho):
    """Evita sobrescrever arquivos existentes"""
    if not os.path.exists(caminho):
        return caminho
    
    base, ext = os.path.splitext(caminho)
    i = 1
    while os.path.exists(f"{base}_{i}{ext}"):
        i += 1
    return f"{base}_{i}{ext}"

# -----------------------------
# PROCESSAMENTO DE ARTIGOS
# -----------------------------

def processar_artigos_sem_mover():
    """
    Processa especificamente artigos em Downloads/Artigos sem mover de pasta
    """
    pasta_artigos = os.path.expanduser("~/Downloads/Artigos")
    
    if not os.path.exists(pasta_artigos):
        print(f"\n❌ Pasta não encontrada: {pasta_artigos}")
        print(f"📂 Criando pasta...")
        os.makedirs(pasta_artigos, exist_ok=True)
        print(f"✅ Pasta criada: {pasta_artigos}")
        return
    
    print(f"\n{'='*60}")
    print(f"📚 ORGANIZADOR DE ARTIGOS CIENTÍFICOS")
    print(f"📂 Pasta: {pasta_artigos}")
    print(f"{'='*60}\n")
    
    # Listar todos os PDFs
    arquivos = [f for f in os.listdir(pasta_artigos) 
                if f.lower().endswith('.pdf') and os.path.isfile(os.path.join(pasta_artigos, f))]
    
    if not arquivos:
        print("📭 Nenhum PDF encontrado na pasta")
        return
    
    print(f"📄 Total de arquivos: {len(arquivos)}\n")
    
    stats = {
        "processados": 0,
        "renomeados": 0,
        "erros": 0,
        "falhas": 0
    }
    
    for i, arquivo in enumerate(arquivos, 1):
        caminho = os.path.join(pasta_artigos, arquivo)
        ext = os.path.splitext(arquivo)[1].lower()
        
        print(f"[{i}/{len(arquivos)}] 📄 {arquivo[:80]}...")
        
        # Extrair título usando pipeline completo (apenas primeira página)
        titulo = extrair_titulo_cientifico_completo(caminho, arquivo)
        
        if titulo:
            # Limpar título para nome de arquivo
            titulo_limpo = limpar_nome(titulo)
            novo_nome = f"{titulo_limpo}{ext}"
            
            # Evitar nomes muito longos
            if len(novo_nome) > 200:
                novo_nome = novo_nome[:197] + ext
            
            print(f"     📝 Novo nome: {novo_nome[:80]}...")
            stats["renomeados"] += 1
        else:
            novo_nome = arquivo
            print(f"     ⚠️ Não foi possível extrair título")
            stats["falhas"] += 1
        
        # Renomear (manter na mesma pasta)
        if novo_nome != arquivo:
            caminho_destino = evitar_duplicado(os.path.join(pasta_artigos, novo_nome))
            
            try:
                shutil.move(caminho, caminho_destino)
                print(f"     ✅ Renomeado com sucesso!")
                stats["processados"] += 1
            except Exception as e:
                print(f"     ❌ Erro ao renomear: {e}")
                stats["erros"] += 1
        else:
            print(f"     ⚠️ Mantendo nome original")
            stats["processados"] += 1
        
        print()
    
    # Estatísticas finais
    print(f"\n{'='*60}")
    print(f"✨ RENOMEAÇÃO CONCLUÍDA!")
    print(f"{'='*60}")
    print(f"📊 Estatísticas:")
    print(f"   ✅ Processados: {stats['processados']}")
    print(f"   ✏️  Renomeados: {stats['renomeados']}")
    print(f"   ❌ Erros: {stats['erros']}")
    print(f"   ⚠️  Falhas na extração: {stats['falhas']}")
    print(f"{'='*60}\n")

# -----------------------------
# INTERFACE PRINCIPAL
# -----------------------------

def main():
    print("\n" + "="*60)
    print("📂 ASSISTENTE DE ORGANIZAÇÃO DE ARTIGOS CIENTÍFICOS")
    print("="*60)
    print("\nEscolha uma opção:")
    print("1️⃣  Renomear artigos em Downloads/Artigos (sem mover)")
    print("2️⃣  Sair")
    
    opcao = input("\n👉 Opção (1-2): ").strip()
    
    if opcao == "1":
        confirmar = input("\n⚠️  Isso renomeará TODOS os PDFs em Downloads/Artigos. Continuar? (s/n): ")
        if confirmar.lower() == 's':
            processar_artigos_sem_mover()
        else:
            print("❌ Operação cancelada.")
    elif opcao == "2":
        print("👋 Até mais!")
    else:
        print("❌ Opção inválida")

if __name__ == "__main__":
    # Verificar dependências
    try:
        import pdfplumber
    except ImportError:
        print("⚠️ Instalando dependências necessárias...")
        os.system("pip install pdfplumber")
        print("✅ Dependências instaladas. Reinicie o script.")
        exit()
    
    main()