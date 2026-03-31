from dotenv import load_dotenv
import os
import shutil
from PyPDF2 import PdfReader
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

load_dotenv()

# -----------------------------
# CONFIGURAÇÃO
# -----------------------------

downloads = os.path.expanduser("~/Downloads")

BASE_PASTAS = [
    "Financeiro", "Estudos", "Contratos", "Trabalho",
    "Imagens", "Videos", "Planilhas", "Design",
    "Livros", "Outros", "Revisar"
]

for pasta in BASE_PASTAS:
    os.makedirs(os.path.join(downloads, pasta), exist_ok=True)


# -----------------------------
# EXTRAÇÃO DE TEXTO
# -----------------------------

def extrair_texto_pdf(caminho):
    try:
        reader = PdfReader(caminho)
        texto = ""
        total_paginas = len(reader.pages)

        # Se for livro (>30 páginas)
        if total_paginas > 30:
            return "", total_paginas

        for i, page in enumerate(reader.pages):
            if i > 1:  # só primeiras 2 páginas
                break
            texto += page.extract_text() or ""

        return texto[:2000], total_paginas
    except:
        return "", 0


def extrair_texto_ocr_pdf(caminho):
    try:
        imagens = convert_from_path(caminho, first_page=1, last_page=2)
        texto = ""
        for img in imagens:
            texto += pytesseract.image_to_string(img)
        return texto[:2000]
    except:
        return ""


def extrair_texto_imagem(caminho):
    try:
        return pytesseract.image_to_string(Image.open(caminho))[:2000]
    except:
        return ""


# -----------------------------
# CLASSIFICAÇÃO POR NOME
# -----------------------------

def analisar_nome_arquivo(nome):
    nome = nome.lower()

    if any(p in nome for p in ["nota", "invoice", "boleto"]):
        return "Financeiro"

    if any(p in nome for p in ["contrato", "contract"]):
        return "Contratos"

    if any(p in nome for p in ["study", "paper", "artigo"]):
        return "Estudos"

    return None


# -----------------------------
# CLASSIFICAÇÃO COM SCORE
# -----------------------------

def classificar_texto_score(texto):
    texto = texto.lower()

    scores = {
        "Financeiro": 0,
        "Estudos": 0,
        "Contratos": 0,
        "Trabalho": 0
    }

    # Financeiro
    for p in ["nota fiscal", "cnpj", "cpf", "boleto", "r$", "pagamento"]:
        if p in texto:
            scores["Financeiro"] += 2

    # Estudos
    for p in ["abstract", "doi", "study", "research", "introduction", "method"]:
        if p in texto:
            scores["Estudos"] += 2

    # sinal forte
    if "abstract" in texto and "introduction" in texto:
        scores["Estudos"] += 5

    # Contratos
    for p in ["contrato", "cláusula", "acordo", "assinatura"]:
        if p in texto:
            scores["Contratos"] += 2

    # Trabalho
    for p in ["relatório", "projeto", "análise", "empresa"]:
        if p in texto:
            scores["Trabalho"] += 2

    categoria = max(scores, key=scores.get)

    # regra de confiança
    if scores[categoria] < 2:
        return "Revisar"

    return categoria


# -----------------------------
# PROCESSAMENTO
# -----------------------------

for arquivo in os.listdir(downloads):
    caminho = os.path.join(downloads, arquivo)

    if not os.path.isfile(caminho):
        continue

    ext = os.path.splitext(arquivo)[1].lower()

    print(f"Processando: {arquivo}")

    # ---------------- PDF ----------------
    if ext == ".pdf":
        texto, paginas = extrair_texto_pdf(caminho)

        # Detectar livro
        if paginas > 30:
            pasta_relativa = "Livros"
        else:
            if len(texto) < 50:
                print("Usando OCR...")
                texto = extrair_texto_ocr_pdf(caminho)

            # 1. nome do arquivo
            categoria_nome = analisar_nome_arquivo(arquivo)

            if categoria_nome:
                pasta_relativa = categoria_nome
            else:
                pasta_relativa = classificar_texto_score(texto)

    # ---------------- IMAGENS ----------------
    elif ext in [".png", ".jpg", ".jpeg"]:
        texto = extrair_texto_imagem(caminho)

        if len(texto) > 30:
            categoria_nome = analisar_nome_arquivo(arquivo)
            if categoria_nome:
                pasta_relativa = categoria_nome
            else:
                pasta_relativa = classificar_texto_score(texto)
        else:
            pasta_relativa = "Imagens"

    # ---------------- VÍDEOS ----------------
    elif ext in [".mp4", ".mov", ".avi"]:
        pasta_relativa = "Videos"

    # ---------------- PLANILHAS ----------------
    elif ext in [".xlsx", ".xls", ".csv"]:
        pasta_relativa = "Planilhas"

    # ---------------- DESIGN ----------------
    elif ext in [".psd"]:
        pasta_relativa = "Design"

    # ---------------- DOCUMENTOS ----------------
    elif ext in [".docx", ".txt"]:
        pasta_relativa = "Trabalho"

    # ---------------- OUTROS ----------------
    else:
        pasta_relativa = "Outros"

    destino = os.path.join(downloads, pasta_relativa)
    os.makedirs(destino, exist_ok=True)

    try:
        shutil.move(caminho, os.path.join(destino, arquivo))
    except Exception as e:
        print(f"Erro ao mover {arquivo}: {e}")

print("Organização concluída ✅")