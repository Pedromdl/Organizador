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
    nome = nome.replace(" ", "_")
    nome = nome.replace("/", "-")
    nome = nome.replace("\\", "-")
    nome = nome.replace(":", "")
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
else:
    for root, dirs, files in os.walk(financeiro_path):
        apenas_renomear = root != financeiro_path

        arquivos = list(files)

        for arquivo in arquivos:
            caminho = os.path.join(root, arquivo)

            if not os.path.isfile(caminho):
                continue

            ext = os.path.splitext(arquivo)[1].lower()

            print(f"Processando Financeiro: {arquivo}")

            texto = ""
            categoria = "Revisar"
            confianca = 0
            nome_novo = ""

            # ---------------- PDF ----------------
            if ext == ".pdf":
                texto = extrair_texto_pdf(caminho)

                if len(texto) < 50:
                    print("Usando OCR...")
                    texto = extrair_texto_ocr_pdf(caminho)

            # ---------------- IMAGENS ----------------
            elif ext in [".png", ".jpg", ".jpeg"]:
                texto = extrair_texto_imagem(caminho)

            # ---------------- OUTROS ----------------
            else:
                destino = os.path.join(financeiro_path, "Outros")
                os.makedirs(destino, exist_ok=True)
                shutil.move(caminho, os.path.join(destino, arquivo))
                continue

            # ---------------- IA ----------------
            try:
                if not apenas_renomear and len(texto.strip()) >= 30:
                    prompt = f"""
                    Você é um sistema de organização de documentos financeiros.

                    Classifique o documento e gere um nome de arquivo claro.

                    Retorne JSON:

                    {{
                    "categoria": "Notas Fiscais | Extratos Bancários | Contratos | Boletos | Impostos | Outros",
                    "confianca": 0-100,
                    "nome_arquivo": "nome_sem_espacos"
                    }}

                    Documento:
                    {texto[:2000]}
                    """

                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0
                    )

                    conteudo = response.choices[0].message.content.strip()
                    print("RESPOSTA IA:", conteudo)

                    inicio = conteudo.find("{")
                    fim = conteudo.rfind("}") + 1

                    if inicio != -1 and fim != -1:
                        resposta = json.loads(conteudo[inicio:fim])

                        categoria = resposta.get("categoria", "Revisar").strip().lower()

                        mapa_categorias = {
                            "notas fiscais": "Notas Fiscais",
                            "extratos bancarios": "Extratos Bancários",
                            "contratos": "Contratos",
                            "boletos": "Boletos",
                            "impostos": "Impostos",
                            "outros": "Outros"
                        }

                        categoria = mapa_categorias.get(categoria, "Revisar") 
                        confianca = resposta.get("confianca", 0)
                        nome_novo = resposta.get("nome_arquivo", "")

                        if confianca < 70:
                            categoria = "Revisar"

            except Exception as e:
                print("Erro IA:", e)

            # ---------------- MOVER ----------------
            if apenas_renomear:
                destino = root  # mantém na mesma pasta
            else:
                destino = os.path.join(financeiro_path, categoria)
            os.makedirs(destino, exist_ok=True)

            if nome_novo and confianca >= 70:
                nome_novo = limpar_nome(nome_novo)
                novo_nome = f"{nome_novo}{ext}"
            else:
                novo_nome = arquivo

            caminho_destino = evitar_duplicado(os.path.join(destino, novo_nome))

            try:
                shutil.move(caminho, caminho_destino)
            except Exception as e:
                print(f"Erro ao mover {arquivo}: {e}")

    print("Financeiro organizado com IA ✅")