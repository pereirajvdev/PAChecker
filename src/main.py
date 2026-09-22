import os
import re
import sys

import fitz
import pytesseract
from PIL import Image
from tqdm import tqdm


# ============================================================
# CONFIGURAÇÕES
# ============================================================

PASTA_PROJETO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

CAMINHO_TESSERACT = os.path.join(
    PASTA_PROJETO,
    "tesseract",
    "tesseract.exe"
)

pytesseract.pytesseract.tesseract_cmd = CAMINHO_TESSERACT


# ============================================================
# OCR
# ============================================================

def extrair_texto_pdf(caminho_pdf):

    documento = fitz.open(caminho_pdf)
    texto = ""

    for pagina in documento:

        imagem = pagina.get_pixmap(dpi=300)

        imagem_pil = Image.frombytes(
            "RGB",
            [imagem.width, imagem.height],
            imagem.samples
        )

        texto += pytesseract.image_to_string(
            imagem_pil,
            lang="por"
        )

    documento.close()

    return texto


# ============================================================
# NOME DO ARQUIVO
# ============================================================

def extrair_informacoes_nome_arquivo(nome_arquivo):

    padrao = (
        r"^PA - "
        r"(.+?) - "
        r"(.+?) - "
        r"(\d{2}\.\d{2}\.\d{4}) A "
        r"(\d{2}\.\d{2}\.\d{4})"
        r"\.pdf$"
    )

    resultado = re.match(
        padrao,
        nome_arquivo,
        re.IGNORECASE
    )

    if not resultado:
        return None

    return {
        "nome": resultado.group(1).strip(),
        "setor": resultado.group(2).strip(),
        "data_inicio": resultado.group(3),
        "data_fim": resultado.group(4)
    }


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_texto(texto):

    texto = texto.upper()

    substituicoes = {
        "Á": "A",
        "À": "A",
        "Ã": "A",
        "Â": "A",
        "É": "E",
        "Ê": "E",
        "Í": "I",
        "Ó": "O",
        "Ô": "O",
        "Õ": "O",
        "Ú": "U",
        "Ç": "C"
    }

    for original, substituto in substituicoes.items():
        texto = texto.replace(original, substituto)

    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


# ============================================================
# LOCALIZAÇÃO DO NOME
# ============================================================

def encontrar_nome_no_texto(nome_esperado, texto_pdf):

    texto = normalizar_texto(texto_pdf)
    nome = normalizar_texto(nome_esperado)

    if nome in texto:
        return nome

    return None


# ============================================================
# LOCALIZAÇÃO DO SETOR
# ============================================================

def extrair_setor_do_pdf(texto_pdf):

    texto = normalizar_texto(texto_pdf)

    padrao = (
        r"SECRETARIA\s+DE\s+LOTACAO\s*:\s*"
        r"([A-Z]+)"
    )

    resultado = re.search(
        padrao,
        texto
    )

    if resultado:
        return resultado.group(1).strip()

    return None


# ============================================================
# PROCESSAMENTO
# ============================================================

def processar_pdf(caminho_pdf):

    nome_arquivo = os.path.basename(caminho_pdf)

    informacoes = extrair_informacoes_nome_arquivo(
        nome_arquivo
    )

    if informacoes is None:
        return {
            "status": "fora_padrao",
            "arquivo": nome_arquivo
        }

    texto_pdf = extrair_texto_pdf(caminho_pdf)

    nome_encontrado = encontrar_nome_no_texto(
        informacoes["nome"],
        texto_pdf
    )

    setor_encontrado = extrair_setor_do_pdf(
        texto_pdf
    )

    nome_correto = nome_encontrado is not None

    setor_correto = (
        setor_encontrado is not None
        and normalizar_texto(informacoes["setor"])
        == normalizar_texto(setor_encontrado)
    )

    if nome_correto and setor_correto:
        return {
            "status": "correto"
        }

    return {
        "status": "divergente",
        "arquivo": nome_arquivo,
        "nome_esperado": informacoes["nome"],
        "nome_encontrado": nome_encontrado,
        "setor_esperado": informacoes["setor"],
        "setor_encontrado": setor_encontrado
    }


# ============================================================
# MAIN
# ============================================================

def main():

    if len(sys.argv) != 2:
        print('Uso: python src/main.py "pasta_com_os_pdfs"')
        return

    pasta_pdfs = sys.argv[1]

    if not os.path.isdir(pasta_pdfs):
        print("Pasta não encontrada.")
        return

    pdfs = [
        arquivo
        for arquivo in os.listdir(pasta_pdfs)
        if arquivo.lower().endswith(".pdf")
    ]

    if not pdfs:
        print("Nenhum PDF encontrado.")
        return

    resultados = {
        "correto": 0,
        "divergente": 0,
        "fora_padrao": 0
    }

    divergencias = []
    fora_padrao = []

    for arquivo in tqdm(
        pdfs,
        desc="Processando",
        unit="pdf"
    ):

        caminho_pdf = os.path.join(
            pasta_pdfs,
            arquivo
        )

        resultado = processar_pdf(caminho_pdf)

        resultados[resultado["status"]] += 1

        if resultado["status"] == "divergente":
            divergencias.append(resultado)

        elif resultado["status"] == "fora_padrao":
            fora_padrao.append(
                resultado["arquivo"]
            )

    # ========================================================
    # RESULTADO
    # ========================================================

    print(
        f"\n✓ {resultados['correto']} corretos"
    )

    if divergencias:

        print(
            f"✗ {resultados['divergente']} divergente(s):"
        )

        for divergencia in divergencias:

            print(
                f"\n  Arquivo: "
                f"{divergencia['arquivo']}"
            )

            print(
                f"  Nome: "
                f"{divergencia['nome_esperado']} "
                f"→ "
                f"{divergencia['nome_encontrado'] or 'não encontrado'}"
            )

            print(
                f"  Setor: "
                f"{divergencia['setor_esperado']} "
                f"→ "
                f"{divergencia['setor_encontrado'] or 'não encontrado'}"
            )

    if fora_padrao:

        print(
            f"\n⚠ {resultados['fora_padrao']} "
            f"fora do padrão:"
        )

        for arquivo in fora_padrao:
            print(f"  {arquivo}")


if __name__ == "__main__":
    main()