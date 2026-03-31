from dotenv import load_dotenv
import os
import shutil
import json
from PyPDF2 import PdfReader
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from openai import OpenAI

load_dotenv()

# -----------------------------
# CONFIGURAÇÃO
# -----------------------------

# 🔑 Use variável de ambiente (recomendado)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

downloads = os.path.expanduser("~/Downloads")

# Pastas base
BASE_PASTAS = ["Revisar", "Imagens", "Videos", "Planilhas", "Design", "Outros"]

for pasta in BASE_PASTAS:
    os.makedirs(os.path.join(downloads, pasta), exist_ok=True)


# -----------------------------
# EXTRAÇÃO DE TEXTO
# -----------------------------

def extrair_texto_pdf(caminho):
    try:
        reader = PdfReader(caminho)
        texto = ""
        for page in reader.pages:
            texto += page.extract_text() or ""
        return texto.strip()
    except:
        return ""


def extrair_texto_ocr_pdf(caminho):
    try:
        imagens = convert_from_path(caminho)
        texto = ""
        for img in imagens:
            texto += pytesseract.image_to_string(img)
        return texto.strip()
    except:
        return ""


def extrair_texto_imagem(caminho):
    try:
        return pytesseract.image_to_string(Image.open(caminho))
    except:
        return ""


# -----------------------------
# CLASSIFICAÇÃO SIMPLES (RÁPIDA)
# -----------------------------

def classificar_texto_simples(texto):
    texto = texto.lower()

    if "nota fiscal" in texto or "cnpj" in texto:
        return "Financeiro"

    if "abstract" in texto or "doi" in texto:
        return "Estudos"

    if "contrato" in texto or "cláusula" in texto:
        return "Contratos"

    if "relatório" in texto or "projeto" in texto:
        return "Trabalho"

    return "Revisar"


# -----------------------------
# CLASSIFICAÇÃO COM IA
# -----------------------------

def classificar_com_ia(texto):
    try:
        prompt = f"""
        Analise o documento abaixo e retorne APENAS um JSON válido:

        {{
          "categoria": "Financeiro | Estudos | Trabalho | Pessoal",
          "subcategoria": "nome curto da subpasta",
          "confianca": número de 0 a 100
        }}

        Documento:
        {texto[:3000]}
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        resposta = response.choices[0].message.content.strip()
        return json.loads(resposta)

    except:
        return {
            "categoria": "Revisar",
            "subcategoria": "",
            "confianca": 0
        }


def decidir_destino(resposta):
    if resposta["confianca"] < 70:
        return "Revisar"

    categoria = resposta["categoria"]
    subcategoria = resposta["subcategoria"].strip()

    # Evitar erro de pasta inválida
    subcategoria = subcategoria.replace("/", "-")

    if not subcategoria:
        return categoria

    return os.path.join(categoria, subcategoria)


def limpar_nome(nome):
    """Limpa o nome removendo caracteres especiais"""
    nome = nome.replace(" ", "_")
    nome = nome.replace("/", "-")
    nome = nome.replace("\\", "-")
    nome = nome.replace(":", "")
    nome = nome.replace("*", "")
    nome = nome.replace("?", "")
    nome = nome.replace('"', "")
    nome = nome.replace("'", "")
    nome = nome.replace("|", "")
    nome = nome.replace(",", "")
    nome = nome.replace(".", "")
    # Remove CNPJ/CPF se estiver junto
    import re
    nome = re.sub(r'\d+', '', nome)  # remove números
    nome = re.sub(r'_+', '_', nome)  # remove underscores duplicados
    nome = nome.strip('_')
    return nome


def evitar_duplicado(caminho):
    base, ext = os.path.splitext(caminho)
    i = 1

    while os.path.exists(caminho):
        caminho = f"{base}_{i}{ext}"
        i += 1

    return caminho


# -----------------------------
# PROCESSAMENTO (SOMENTE FINANCEIRO)
# -----------------------------

financeiro_path = os.path.join(downloads, "Financeiro")

if not os.path.exists(financeiro_path):
    print("Pasta Financeiro não encontrada ❌")
    print("Criando pasta Financeiro...")
    os.makedirs(financeiro_path, exist_ok=True)
else:
    for root, dirs, files in os.walk(financeiro_path):
        apenas_renomear = root != financeiro_path

        arquivos = list(files)

        for arquivo in arquivos:
            caminho = os.path.join(root, arquivo)

            if not os.path.isfile(caminho):
                continue

            ext = os.path.splitext(arquivo)[1].lower()

            print(f"\n📄 Processando: {arquivo}")

            texto = ""
            categoria = "Revisar"
            confianca = 0
            nome_novo = ""
            nome_tomador = ""
            data_emissao = ""

            # ---------------- PDF ----------------
            if ext == ".pdf":
                print("  📑 Extraindo texto do PDF...")
                texto = extrair_texto_pdf(caminho)

                if len(texto) < 50:
                    print("  🔍 Texto insuficiente, usando OCR...")
                    texto = extrair_texto_ocr_pdf(caminho)

            # ---------------- IMAGENS ----------------
            elif ext in [".png", ".jpg", ".jpeg"]:
                print("  🖼️ Extraindo texto da imagem com OCR...")
                texto = extrair_texto_imagem(caminho)

            # ---------------- OUTROS ----------------
            else:
                print("  📁 Arquivo não suportado, movendo para Outros...")
                destino = os.path.join(financeiro_path, "Outros")
                os.makedirs(destino, exist_ok=True)
                shutil.move(caminho, os.path.join(destino, arquivo))
                continue

            # ---------------- IA PARA EXTRAIR NOME DO TOMADOR E DATA ----------------
            try:
                if not apenas_renomear and len(texto.strip()) >= 30:
                    print("  🤖 Chamando IA para extrair informações...")
                    
                    prompt = f"""
                    Você é um especialista em extração de informações de documentos fiscais e financeiros.

                    Analise o documento abaixo e extraia com PRECISÃO:

                    1. **NOME_TOMADOR**: Nome do TOMADOR DO SERVIÇO (quem contratou/recebeu o serviço)
                       - Em notas fiscais, é o campo "Tomador", "Cliente", "Contratante", "Sacado"
                       - Pode ser Pessoa Física (nome completo) ou Jurídica (razão social)
                       - Exemplos: "Empresa Cliente Ltda", "João da Silva Oliveira", "Secretaria de Educação"
                       - NÃO confundir com o prestador/emitente!
                       
                    2. **DATA_EMISSAO**: Data de emissão do documento
                       - Formato: YYYY-MM-DD
                       - Procure por: "Data de Emissão", "Data", "Emissão", "Data do Documento"
                       - Se não encontrar, use a data mais recente no documento
                    
                    3. **CATEGORIA**: Tipo do documento financeiro
                       - Opções: "Notas Fiscais", "Extratos Bancários", "Contratos", "Boletos", "Impostos", "Outros"
                    
                    4. **CONFIANCA**: Nível de confiança na extração (0-100)
                       - 90-100: Informações claras e explícitas
                       - 70-89: Informações presentes mas com alguma ambiguidade
                       - Abaixo de 70: Informações incertas ou não encontradas

                    Retorne APENAS um JSON válido com esta estrutura exata:

                    {{
                        "nome_tomador": "nome_do_tomador_extraido",
                        "data_emissao": "YYYY-MM-DD",
                        "categoria": "Notas Fiscais",
                        "confianca": 95
                    }}

                    Documento:
                    {texto[:3000]}
                    """

                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0
                    )

                    conteudo = response.choices[0].message.content.strip()
                    print(f"  📝 Resposta IA recebida")

                    # Extrair JSON da resposta
                    inicio = conteudo.find("{")
                    fim = conteudo.rfind("}") + 1

                    if inicio != -1 and fim != -1:
                        resposta = json.loads(conteudo[inicio:fim])

                        nome_tomador = resposta.get("nome_tomador", "")
                        data_emissao = resposta.get("data_emissao", "")
                        categoria = resposta.get("categoria", "Revisar")
                        confianca = resposta.get("confianca", 0)

                        # Mapear categoria para nome correto da pasta
                        mapa_categorias = {
                            "notas fiscais": "Notas Fiscais",
                            "extratos bancarios": "Extratos Bancários",
                            "contratos": "Contratos",
                            "boletos": "Boletos",
                            "impostos": "Impostos",
                            "outros": "Outros"
                        }
                        
                        # Normalizar categoria
                        categoria_normalizada = categoria.strip().lower()
                        categoria = mapa_categorias.get(categoria_normalizada, "Revisar")

                        print(f"  ✅ Extraído:")
                        print(f"     Tomador: {nome_tomador}")
                        print(f"     Data: {data_emissao}")
                        print(f"     Categoria: {categoria}")
                        print(f"     Confiança: {confianca}%")

                        # GERAR NOME PERSONALIZADO COM O TOMADOR
                        if confianca >= 70 and nome_tomador and data_emissao:
                            nome_tomador_limpo = limpar_nome(nome_tomador)
                            # Formato: TOMADOR_AAAA-MM-DD.ext
                            nome_novo = f"{nome_tomador_limpo}_{data_emissao}"
                            print(f"  📝 Nome gerado: {nome_novo}")
                        elif confianca >= 70 and nome_tomador:
                            # Se tem tomador mas não tem data
                            nome_tomador_limpo = limpar_nome(nome_tomador)
                            nome_novo = f"{nome_tomador_limpo}"
                            print(f"  📝 Nome gerado (sem data): {nome_novo}")
                        else:
                            print(f"  ⚠️ Confiança baixa ou dados incompletos, mantendo nome original")
                            if not nome_tomador:
                                print(f"     → Motivo: Nome do tomador não encontrado")
                            if not data_emissao:
                                print(f"     → Motivo: Data de emissão não encontrada")
                            
            except json.JSONDecodeError as e:
                print(f"  ❌ Erro ao decodificar JSON: {e}")
                print(f"  Resposta recebida: {conteudo[:200]}")
            except Exception as e:
                print(f"  ❌ Erro na IA: {e}")

            # ---------------- MOVER ARQUIVO ----------------
            if apenas_renomear:
                destino = root  # mantém na mesma pasta
                print(f"  📂 Mantendo em subpasta: {os.path.basename(root)}")
            else:
                destino = os.path.join(financeiro_path, categoria)
                print(f"  📂 Movendo para: {categoria}")
                
            os.makedirs(destino, exist_ok=True)

            # Definir nome final do arquivo
            if nome_novo and confianca >= 70:
                novo_nome = f"{nome_novo}{ext}"
            else:
                novo_nome = arquivo

            caminho_destino = evitar_duplicado(os.path.join(destino, novo_nome))

            try:
                shutil.move(caminho, caminho_destino)
                print(f"  ✅ Sucesso: {arquivo} -> {novo_nome}")
            except Exception as e:
                print(f"  ❌ Erro ao mover {arquivo}: {e}")

    print("\n" + "="*50)
    print("✨ Financeiro organizado com IA ✅")
    print("="*50)