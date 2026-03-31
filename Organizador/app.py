import sys
import os
import shutil
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton,
    QTextEdit, QProgressBar, QLabel
)
from PySide6.QtCore import QThread, Signal
from PyPDF2 import PdfReader
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = get_base_path()

# Caminhos internos
TESSERACT_PATH = os.path.join(BASE_PATH, "tesseract", "tesseract.exe")
POPPLER_PATH = os.path.join(BASE_PATH, "poppler", "Library", "bin")

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


# -----------------------------
# CONFIG
# -----------------------------

downloads = os.path.expanduser("~/Downloads")

BASE_PASTAS = [
    "Financeiro", "Estudos", "Contratos", "Trabalho",
    "Imagens", "Videos", "Planilhas", "Design",
    "Livros", "Outros", "Revisar"
]

# -----------------------------
# WORKER (THREAD)
# -----------------------------

class Worker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int)

    def run(self):
        arquivos = os.listdir(downloads)
        total = len(arquivos)

        for pasta in BASE_PASTAS:
            os.makedirs(os.path.join(downloads, pasta), exist_ok=True)

        for i, arquivo in enumerate(arquivos):
            caminho = os.path.join(downloads, arquivo)

            if not os.path.isfile(caminho):
                continue

            ext = os.path.splitext(arquivo)[1].lower()

            self.log_signal.emit(f"📄 {arquivo}")

            try:
                pasta_relativa = self.processar_arquivo(caminho, arquivo, ext)
                destino = os.path.join(downloads, pasta_relativa)

                shutil.move(caminho, os.path.join(destino, arquivo))

            except Exception as e:
                self.log_signal.emit(f"❌ Erro: {e}")

            progresso = int((i + 1) / total * 100)
            self.progress_signal.emit(progresso)

        self.log_signal.emit("\n✅ Organização concluída!")

    def processar_arquivo(self, caminho, arquivo, ext):
        if ext == ".pdf":
            texto, paginas = self.extrair_texto_pdf(caminho)

            if paginas > 30:
                return "Livros"

            if len(texto) < 50:
                texto = self.extrair_texto_ocr_pdf(caminho)

            categoria_nome = self.analisar_nome_arquivo(arquivo)
            if categoria_nome:
                return categoria_nome

            return self.classificar_texto_score(texto)

        elif ext in [".png", ".jpg", ".jpeg"]:
            texto = self.extrair_texto_imagem(caminho)

            if len(texto) > 30:
                categoria_nome = self.analisar_nome_arquivo(arquivo)
                if categoria_nome:
                    return categoria_nome
                return self.classificar_texto_score(texto)

            return "Imagens"

        elif ext in [".mp4", ".mov", ".avi"]:
            return "Videos"

        elif ext in [".xlsx", ".xls", ".csv"]:
            return "Planilhas"

        elif ext == ".psd":
            return "Design"

        elif ext in [".docx", ".txt"]:
            return "Trabalho"

        return "Outros"

    # -----------------------------
    # FUNÇÕES AUXILIARES
    # -----------------------------

    def extrair_texto_pdf(self, caminho):
        try:
            reader = PdfReader(caminho)
            texto = ""
            total_paginas = len(reader.pages)

            if total_paginas > 30:
                return "", total_paginas

            for i, page in enumerate(reader.pages):
                if i > 1:
                    break
                texto += page.extract_text() or ""

            return texto[:2000], total_paginas
        except:
            return "", 0

    def extrair_texto_ocr_pdf(self, caminho):
        try:
            imagens = imagens = convert_from_path(
    caminho,
    first_page=1,
    last_page=2,
    poppler_path=POPPLER_PATH
)
            texto = ""
            for img in imagens:
                texto += pytesseract.image_to_string(img)
            return texto[:2000]
        except:
            return ""

    def extrair_texto_imagem(self, caminho):
        try:
            return pytesseract.image_to_string(Image.open(caminho))[:2000]
        except:
            return ""

    def analisar_nome_arquivo(self, nome):
        nome = nome.lower()

        if any(p in nome for p in ["nota", "invoice", "boleto"]):
            return "Financeiro"

        if any(p in nome for p in ["contrato", "contract"]):
            return "Contratos"

        if any(p in nome for p in ["study", "paper", "artigo"]):
            return "Estudos"

        return None

    def classificar_texto_score(self, texto):
        texto = texto.lower()

        scores = {
            "Financeiro": 0,
            "Estudos": 0,
            "Contratos": 0,
            "Trabalho": 0
        }

        for p in ["nota fiscal", "cnpj", "cpf", "boleto", "r$", "pagamento"]:
            if p in texto:
                scores["Financeiro"] += 2

        for p in ["abstract", "doi", "study", "research", "introduction", "method"]:
            if p in texto:
                scores["Estudos"] += 2

        if "abstract" in texto and "introduction" in texto:
            scores["Estudos"] += 5

        for p in ["contrato", "cláusula", "acordo", "assinatura"]:
            if p in texto:
                scores["Contratos"] += 2

        for p in ["relatório", "projeto", "análise", "empresa"]:
            if p in texto:
                scores["Trabalho"] += 2

        categoria = max(scores, key=scores.get)

        if scores[categoria] < 2:
            return "Revisar"

        return categoria


# -----------------------------
# INTERFACE
# -----------------------------

class App(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Organizador Inteligente")
        self.setGeometry(300, 200, 600, 500)

        layout = QVBoxLayout()

        self.label = QLabel("Organize seus arquivos com 1 clique")
        layout.addWidget(self.label)

        self.button = QPushButton("Organizar Downloads")
        self.button.clicked.connect(self.iniciar)
        layout.addWidget(self.button)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.setLayout(layout)

    def iniciar(self):
        self.worker = Worker()
        self.worker.log_signal.connect(self.atualizar_log)
        self.worker.progress_signal.connect(self.progress.setValue)

        self.button.setEnabled(False)
        self.worker.start()

    def atualizar_log(self, msg):
        self.log.append(msg)


# -----------------------------
# RUN
# -----------------------------

app = QApplication(sys.argv)
window = App()
window.show()
sys.exit(app.exec())